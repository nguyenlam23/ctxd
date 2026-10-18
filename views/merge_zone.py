#-*- coding: utf-8 -*-

import json
import math
import re
import datetime
import numpy
import random
import cPickle as pickle
from sqlalchemy import *
import zlib
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.conf import settings
from django.core.cache import get_cache
from admin.logic import login_permission_required
import datetime
from game_lib.models.main import UserZone
from game_lib.models.zone import Zones, MergeRecord
from game_lib.common import utils
from game_lib.logics import game_config
from game_lib.models.cache import CacheTable
from db.database import pay_records_table as ASP
from game_lib.libs.model import Serializer
from .maintain import _get_zone_maintain_status

cache = get_cache(settings.CACHE_BACKEND)

default_value = '''{
}
'''

def get_zone_ids(merge_index, zone_range):
    zones = []
    for start, stop in zone_range:
        zones += range(start, stop+1)
    if merge_index == 0:
        return map(lambda x: str(x), zones)
    else:
        return map(lambda x: 'h%s_%s' % (merge_index, x), zones)

def get_last_merge_zone(zone):
    """
    计算合区最新的起始ID
    :param zone:
    :return:
    """
    zone_list = game_config.help_msg['zone_merge']
    for zone_ranges in zone_list.values():
        merge_index = None
        for _merge_index, zone_range in enumerate(zone_ranges):
            zone_ids = get_zone_ids(_merge_index, zone_range)
            if zone not in zone_ids:
                continue
            merge_index = _merge_index + 1
            break
        if merge_index is None:
            continue
        for merge_zone in get_zone_ids(merge_index, zone_ranges[merge_index]):
            if list(Zones.query({'zone_id': merge_zone})):
                continue
            if merge_zone in game_config.zone.keys():
                continue
            return merge_zone, zone_ranges[merge_index], merge_index
    return None, None, None

def get_zone_thirty_days_pay_records(zone):
    """
    获取指定区最近30天内的充值记录
    :param zone:
    :return:
    """
    data = {}
    stop_at = datetime.datetime.now()
    start_at = datetime.datetime(*(stop_at.date() - datetime.timedelta(days=30)).timetuple()[:6])
    pay_records = select([ASP.c.uid, ASP.c.old_zone, ASP.c.pay_money], and_(ASP.c.pay_time >= start_at,
                                                                            ASP.c.pay_time <= stop_at,
                                                                            ASP.c.zone == zone)).execute().fetchall()
    for uid, old_zone, pay_money in pay_records:
        uid_zone = '%s|%s' % (uid, old_zone)
        data.setdefault(uid_zone, 0)
        data[uid_zone] += int(pay_money)
    return data

def get_zone_country_data(zone):
    """

    :param zone:
    :return: data: 国家数据
            [
            {
                'open_days': '',    #开服天数
                'country': '',      #国家
                'capital_num': 0,   #都城
                'city_num': 0,      #城池
                'powerful_num': 0,  #活跃高战
                'active_num': 0,    #活跃中坚
                'rank_score': 0,    #排名积分
                'top_power': 0,     #尖端战力
                'active_power_sum': 0,  #活跃总战力
                'active_pay': 0,    #活跃实际充值
                'active_pay_fake': 0,   #活跃虚拟充值
                'active_coin': 0,   #活跃coin
                'multiple_power': 0,    #综合国力
                'top20_country_credit': 0,         #前20战功和
                'country_active': 0,    #国家活跃
                'normal_num': 0,    #活跃低战
                'best_hero_power': 0, #单将最高战力
                'thirty_pay_money': 0, #30天活跃充值
            },]
    """
    now = datetime.datetime.now()
    data = []
    zone_config = game_config.zone
    zone_pay_records = get_zone_thirty_days_pay_records(zone)
    res = UserZone.call_server_api(zone, 'user_power_rank', {})
    res.pop()
    open_days = res[0]
    for country_index, country_data in enumerate(res[1]):
        country_data['open_days'] = open_days
        country_data['country'] = country_index
        country_data['best_hero_power'] = 0
        country_data['thirty_pay_money'] = 0
        for item in res[4:]:
            if item['country'] != country_index:
                continue
            if zone_config[zone][8]:
                old_uid = int(item['uid']) % settings.UIDADD
                old_zone = int(item['uid']) / settings.UIDADD
            else:
                old_uid = item['uid']
                old_zone = zone
            uid_zone = '%s|%s' % (old_uid, old_zone)
            if country_data['best_hero_power'] < item['best_hero_power']:
                country_data['best_hero_power'] = item['best_hero_power']
            if utils.total_seconds(now - item['t']) < 48 * 3600 and item['rank'] <= 100:
                country_data['thirty_pay_money'] += zone_pay_records.get(uid_zone, 0)
        data.append(country_data)
    return data

def _get_player_num(item):
    return sum([item['powerful_num'], item['active_num'], item['normal_num']])

def calculate_variance(potential_list):
    """
    根据三个国家的潜力值计算方差
        方差值越大，说明该区国家战力越不平衡
    :param potential_list: [121232, 3232131, 123123]
    :return:
    """
    arr = numpy.array(potential_list)
    return numpy.var(arr)

def _is_merge_zone(zone):
    return True if re.match(r"h[0-9]{1}_\d+", zone) else False

def _get_zone_ids(zone_range):
    zone_ids = []
    s, e = zone_range
    if _is_merge_zone(s):
        _s = int(s.split('_')[1])
        _e = int(e.split('_')[1]) + 1
    else:
        _s = int(s)
        _e = int(e) + 1
    for i in xrange(_s, _e):
        if _is_merge_zone(s):
            prefix = s.split("_")[0]
            zone_ids.append('%s_%s' % (prefix, i))
        else:
            zone_ids.append(str(i))
    return zone_ids

def _get_next_to_zone(zone, range_nums):
    p = zone.split('_')[0]
    n = int(zone.split('_')[1])
    n += 1
    for i in range_nums:
        if n > i[1]:
            continue
        if i[0] <= n <= i[1]:
            break
        n = i[0]
    return '%s_%s' % (p, n)

def _get_merge_config(merge_times):
    config_value = CacheTable.get('merge_config_%s' % merge_times, default_value)
    return json.loads(str(config_value))

def _get_merge_rewards(countries, merge_config):
    max_day = max([c['open_days'] for c in countries])
    used_average_day = max_day + (1000 / merge_config['reward']['coin'])
    rewards = {}
    for country in countries:
        if country['zone_id'] in rewards:
            continue
        reward = {}
        for k,v in merge_config['reward'].items():
            reward[k] = (used_average_day - country['open_days']) * v
        for k,v in merge_config['rewardExtra'].items():
            reward.setdefault(k, 0)
            reward[k] += v
        rewards[country['zone_id']] = reward
    return rewards

@login_permission_required('merge_zone')
def calculate_merge_zone(request):
    zone_ranges = request.POST['zone_ranges']
    zone_ranges = json.loads(zone_ranges)
    if not zone_ranges:
        return HttpResponse(u'<script>alert("合服区间不能为空");history.go(-1);</script>')
    ## 合服配置
    merge_plan_config = {}
    ## 合服展示数据
    view_data = []

    for zone_range in zone_ranges:
        to_zone, range_nums, merge_times = get_last_merge_zone(zone_range[0])
        merge_config = _get_merge_config(merge_times)
        max_nums = merge_config['maxNum']
        ## 分离国家，并计算国家潜力值，按潜力值降序排列所有国家
        from_countries = []
        for zone_id in _get_zone_ids(zone_range):
            if zone_id not in game_config.zone:
                continue
                # return HttpResponse(u'<script>alert("【%s】区ID不存在");history.go(-1);</script>' % zone_id)
            zone_config = game_config.zone[zone_id]
            if not zone_config[1][0]:
                return HttpResponse(u'<script>alert("【%s】区已合区，不能重复合区");history.go(-1);</script>' % zone_id)
            merge_plan_config[zone_id] = [{}, {}, {}]
            country_data = get_zone_country_data(zone_id)
            for country, item in enumerate(country_data):
                item['zone_id'] = zone_id
                item['player_num'] = _get_player_num(item)
                from_countries.append(item)
        ## 按照尖端战力排序
        from_countries.sort(key=lambda x: x['top_power'])
        for top_rank, item in enumerate(from_countries):
            if merge_times > 2:
                right1 = merge_config['Right1']
            else:
                try:
                    right1 = merge_config['Right1'][top_rank/3]
                except IndexError:
                    right1 = 0
            item['potential'] = right1 * item['top_power'] + \
                merge_config['Right2'] * item['active_power_sum'] + \
                merge_config['Right3'] * item['active_pay_fake'] + \
                merge_config['Right4'] * item['thirty_pay_money'] + \
                merge_config['Right5'] * _get_player_num(item) + \
                merge_config['Right6'] * item['active_coin']
        ## 按照国家潜力值排序
        from_countries.sort(key=lambda x:x['potential'], reverse=True)

        ## 所有区合服奖励
        zone_rewards = _get_merge_rewards(from_countries, merge_config)

        ## 所有合区玩家数总和
        total_player_nums = sum([c['player_num'] for c in from_countries])
        ## 新增合区数量
        merge_zone_nums = total_player_nums / max_nums
        if merge_zone_nums <= 0:
            merge_zone_nums = 1

        ## 基础区国家分配，按新增合区数量为步长取国家，为每个新增合区分配三个国家
        plan_merge_zones = []
        for i in xrange(merge_zone_nums):
            c_list = [0, 1, 2]
            _zone = {'countries': [], 'variance': 0, 'from_countries': [], 'zone_id': ''}
            for _index in [i, merge_zone_nums*2-i-1, merge_zone_nums*2+i]:
                ## 随机目标国家
                c_list_index = random.randrange(len(c_list))
                to_country = c_list[c_list_index]
                c_list.pop(c_list_index)
                _c = from_countries[_index]
                _c['to_country'] = to_country
                _c['to_zone'] = to_zone
                _zone['countries'].append({
                    'zone': to_zone,
                    'country': to_country,
                    'potential': _c['potential'],
                    'player_num': _c['player_num'],
                    'country_num': 1,
                    'powerful_num': _c['powerful_num'],
                    'active_num': _c['active_num'],
                    'normal_num': _c['normal_num'],
                    'top_power': _c['top_power'],
                    'active_power_sum': _c['active_power_sum'],
                    'thirty_pay_money': _c['thirty_pay_money'],
                    'active_pay': _c['active_pay'],
                    'active_pay_fake': _c['active_pay_fake'],
                    'active_coin': _c['active_coin'],
                    'multiple_power': _c['multiple_power'],
                    'best_hero_power': _c['best_hero_power']
                })
                _zone['from_countries'].append(_c)
                merge_plan_config[_c['zone_id']][_c['country']] = {
                    'to_zone': to_zone,
                    'to_country': to_country,
                    'reward': zone_rewards[_c['zone_id']]
                }
            _zone['variance'] = calculate_variance([c['potential'] for c in _zone['countries']])
            _zone['zone_id'] = to_zone
            plan_merge_zones.append(_zone)
            to_zone = _get_next_to_zone(to_zone, range_nums)
        # for item in plan_merge_zones[0]['countries']:
        #     print item
        # print "===================================="
        ## 剩余国家分配
        for c in from_countries[merge_zone_nums*3:]:
            insert_zone_index = sorted([[index, len(item['from_countries']), item['variance']] for index, item in enumerate(plan_merge_zones)], key=lambda x:(x[1], -x[2]))[0][0]
            insert_zone = plan_merge_zones[insert_zone_index]
            insert_country = sorted(insert_zone['countries'], key=lambda x:x['potential'])[0]
            for k,v in insert_country.items():
                if k in ['country', 'zone']:
                    continue
                elif k == 'best_hero_power':
                    if c['best_hero_power'] > v:
                        insert_country[k] = c['best_hero_power']
                elif k == 'country_num':
                    insert_country[k] += 1
                else:
                    insert_country[k] += c[k]
            c['to_country'] = insert_country['country']
            c['to_zone'] = insert_country['zone']
            insert_zone['from_countries'].append(c)
            insert_zone['variance'] = calculate_variance([_c['potential'] for _c in insert_zone['countries']])

            merge_plan_config[c['zone_id']][c['country']] = {
                'to_zone': insert_country['zone'],
                'to_country': insert_country['country'],
                'reward': zone_rewards[c['zone_id']]
            }
        for item in plan_merge_zones:
            item['from_countries'] = sorted(item['from_countries'], key=lambda
                    x:(int(x['zone_id'].split('_')[1]) if x['zone_id'].startswith('h')
                    else x['zone_id'], x['country']))
            item['countries'] = sorted(item['countries'], key=lambda x:x['country'])
        view_data.extend(plan_merge_zones)
    return render_to_response('admin/merge_zone/merge_plan.html', {
        'view_data': view_data,
        'show_confirm_button': True if view_data else False,
        'view_data_dump': json.dumps(view_data),
        'merge_plan_config': json.dumps(merge_plan_config),
        'target_zones': [item['zone_id'] for item in view_data]
    }, RequestContext(request))

@login_permission_required('merge_zone')
def recalculate_merge_zone(request):
    """
    重新计算合服结果
    :param request:
    :return:
    """
    merge_plan_config = request.POST.get('merge_plan_config')
    view_data = request.POST.get('view_data')
    if not merge_plan_config:
        return HttpResponse(u'<script>alert("合服配置不能为空");history.go(-1);</script>')
    merge_plan_config = json.loads(merge_plan_config)
    view_data = json.loads(view_data)
    action = request.POST['action']
    zone_id = request.POST['zone_id']
    change_value = request.POST['change_value']
    country_index = int(request.POST['country_index'])
    change_country = None
    for item in view_data:
        if item['zone_id'] != zone_id:
            continue
        change_country = item['from_countries'].pop(country_index)
        for k, v in item['countries'][change_country['to_country']].items():
            if k in ['country', 'zone']:
                continue
            elif k == 'best_hero_power':
                if change_country['best_hero_power'] < v:
                    continue
                best_powers = [i['best_hero_power'] for i in item['from_countries'] if i['to_country'] == item['countries'][change_country['to_country']]['country']]
                item['countries'][change_country['to_country']][k] = max(best_powers) if best_powers else 0
            elif k == 'country_num':
                item['countries'][change_country['to_country']][k] -= 1
            else:
                item['countries'][change_country['to_country']][k] -= change_country[k]
            if item['countries'][change_country['to_country']][k] < 0:
                item['countries'][change_country['to_country']][k] = 0
    if not change_country:
        return HttpResponse(u'<script>alert("国家数据错误，请重新生成合服数据");history.go(-1);</script>')
    if action == 'change_to_zone':
        merge_plan_config[change_country['zone_id']][change_country['country']]['to_zone'] = change_value
        change_country['to_zone'] = change_value
    elif action == 'change_to_country':
        merge_plan_config[change_country['zone_id']][change_country['country']]['to_country'] = int(change_value)
        change_country['to_country'] = int(change_value)
    for item in view_data:
        if item['zone_id'] != change_country['to_zone']:
            continue
        for k, v in item['countries'][change_country['to_country']].items():
            if k in ['country', 'zone']:
                continue
            elif k == 'best_hero_power':
                if change_country['best_hero_power'] <= v:
                    continue
                item['countries'][change_country['to_country']][k] = change_country['best_hero_power']
            elif k == 'country_num':
                item['countries'][change_country['to_country']][k] += 1
            else:
                item['countries'][change_country['to_country']][k] += change_country[k]
        item['from_countries'].append(change_country)
        item['from_countries'] = sorted(item['from_countries'], key=lambda
                x:(int(x['zone_id'].split('_')[1]) if x['zone_id'].startswith('h')
                else x['zone_id'], x['country']))
    return render_to_response('admin/merge_zone/merge_plan.html', {
        'view_data': view_data,
        'show_confirm_button': True,
        'view_data_dump': json.dumps(view_data),
        'merge_plan_config': json.dumps(merge_plan_config),
        'target_zones': [item['zone_id'] for item in view_data]
    }, RequestContext(request))

@login_permission_required('merge_zone', ajax=True)
def confirm_merge_config(request):
    merge_plan_config = request.POST.get('merge_plan_config')
    view_data = request.POST.get('view_data')
    if not merge_plan_config:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置不能为空'}))
    merge_plan_config = json.loads(merge_plan_config)
    view_data = json.loads(view_data)
    for k,v in merge_plan_config.items():
        for c in v:
            if 'to_country' not in c or 'to_zone' not in c or 'reward' not in c:
                return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置格式错误'}))

    merge_running_zones = set()
    for item in MergeRecord.query({'status_not': MergeRecord.merge_finish}):
        for k in item.merge_config.keys():
            merge_running_zones.add(k)
    for zone_id in merge_plan_config.keys():
        if zone_id in merge_running_zones:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】区已在合服任务中' % zone_id}))

    r = MergeRecord()
    r.admin_user = request.session['admin_user']['username']
    r.merge_config = merge_plan_config
    r.view_data = view_data
    r.sub_time = datetime.datetime.now()
    r.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('merge_zone')
def merge_zone(request):
    merge_config_value = CacheTable.get('merge_config_1', default_value)
    return render_to_response('admin/merge_zone/merge_zone.html', {
        'merge_config_value': merge_config_value
    },
    RequestContext(request))

@login_permission_required('merge_zone', ajax=True)
def get_merge_records(request):
    merge_records = []
    set_timeout = False
    today = datetime.date.today() + datetime.timedelta(days=1)
    yesterday = today - datetime.timedelta(days=15)
    start_at = datetime.datetime(*yesterday.timetuple()[:6])
    stop_at = datetime.datetime(*today.timetuple()[:6])
    for r in MergeRecord.query(condition={'_or_': [{'status_not': MergeRecord.merge_finish}, {'start_time_gte':start_at, 'start_time_lt': stop_at}]}, order_by='-sub_time', limit=100):
        if r.status == MergeRecord.merge_running and r.progress != 100:
            server_manage_host = set()
            for z in r.merge_config.keys():
                zone_config = game_config.zone[z]
                server_manage_host.add(zone_config[1][0])
            for host in server_manage_host:
                try:
                    server_addr = '%s:%s' % (host, settings.SERVER_MANAGE_PORT)
                    result = UserZone.call_duplicate_server_api(server_addr,
                                                                'get_merge_finish_zones',
                                                                {
                                                                    'merge_id': r.id
                                                                }, timeout=1)
                    zones = result
                    finish_zones = r.finish_zones
                    finish_zones.extend(zones)
                    r.finish_zones = list(set(finish_zones))

                    finish_zone_count = len(r.finish_zones)
                    merge_zone_count = len(r.merge_config)
                    if finish_zone_count == merge_zone_count:
                        r.status = MergeRecord.merge_finish
                        r.progress = 100
                        r.end_time = datetime.datetime.now()
                    else:
                        r.progress = int(math.ceil((finish_zone_count/(merge_zone_count*1.0))*100))

                    r.save()
                except:
                    pass
        item = {
            'id': r.id,
            'admin_user': r.admin_user,
            'sub_time': r.sub_time,
            'start_time': r.start_time,
            'end_time': r.end_time,
            'progress': r.progress,
            'merge_config': r.merge_config,
            'view_data': r.view_data,
            'status': [r.status, MergeRecord.status_maps[r.status]]
        }
        merge_records.append(item)
        if r.status == MergeRecord.merge_running:
            set_timeout = True
    merge_record_html = loader.render_to_string('admin/merge_zone/merge_records.html', {
        'merge_records': merge_records,
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state': 'success', 'merge_record_html': merge_record_html, 'set_timeout': set_timeout}))

@login_permission_required('merge_zone')
def view_merge_result(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(u'<script>alert("记录不存在");history.go(-1);</script>')
    return render_to_response('admin/merge_zone/merge_plan.html', {
        'view_data': r.view_data,
        'show_confirm_button': False,
        'view_data_dump': '{}',
        'merge_plan_config': '{}',
        'target_zones': [item['zone_id'] for item in r.view_data]
    }, RequestContext(request))

@login_permission_required('merge_zone')
def download_merge_config(request):
    record_id = request.GET['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(u'<script>alert("记录不存在");history.go(-1);</script>')

    merge_config_value = json.dumps(r.merge_config,sort_keys=True,indent=4,default=Serializer.json_default)
    res = HttpResponse(merge_config_value)
    res['Content-Disposition'] = 'attachment;filename=%s_%s.json' % (settings.WHERE, datetime.date.today().strftime('%Y%m%d'))
    return res

@login_permission_required('merge_zone', ajax=True)
def get_merge_config(request):
    merge_times = request.GET['merge_times']
    config_value = CacheTable.get('merge_config_%s' % merge_times, default_value)
    return HttpResponse(json.dumps({'config_value': config_value}))

@login_permission_required('merge_zone', ajax=True)
def modify_merge_config(request):
    merge_times = request.POST['merge_times']
    config_value = request.POST.get('config_value').encode('utf-8').replace('\r', '').strip()
    if not config_value:
        return HttpResponse(json.dumps({'state':'error','msg':u'配置不能为空'}))
    try:
        eval(config_value)
    except Exception, e:
        utils.print_err()
        try:
            return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.text}))
        except:
            return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.message}))
    CacheTable.set('merge_config_%s' % merge_times, config_value, 3600*24*365*100)
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('merge_zone', ajax=True)
def del_merge_record(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if r:
        r.delete()
        r.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('merge_zone', ajax=True)
def get_maintain_zones(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置不存在'}))
    maintain_zone = set()
    for z, value in r.merge_config.items():
        maintain_zone.add(z)
        for item in value:
            maintain_zone.add(item['to_zone'])
    maintain_zone = sorted(list(maintain_zone),
                           key=lambda x: int(x.split('_')[1]) - int(x.split('_')[0][1:]) * 100000 if x.startswith(
                               'h') else x)
    maintain_zone_str = ','.join(['"%s"' % z for z in maintain_zone])
    return HttpResponse(json.dumps({'state': 'success', 'maiantain_zones': maintain_zone_str}))

@login_permission_required('merge_zone', ajax=True)
def view_merge_progress(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置不存在'}))
    merge_progress = []
    for z in r.merge_config.keys():
        merge_progress.append([z, r.server_host.get(z, ''), 1 if z in r.finish_zones else 0])
    merge_progress = sorted(merge_progress,
                           key=lambda x: int(x[0].split('_')[1]) -
                           int(x[0].split('_')[0][1:]) * 100000 if x[0].startswith(
                               'h') else x[0])
    merge_progress_html = loader.render_to_string('admin/merge_zone/merge_progress.html', {
        'merge_progress': merge_progress
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state': 'success', 'merge_progress_html': merge_progress_html}))

@login_permission_required('merge_zone', ajax=True)
def start_merge(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置不存在'}))
    if r.status == MergeRecord.merge_running:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'正在合服中，请稍等'}))
    maintain_zone = set()
    server_manage_host = set()
    for z, value in r.merge_config.items():
        zone_config = game_config.zone[z]
        server_manage_host.add(zone_config[1][0])
        r.server_host[z] = '%s:%s' % zone_config[1]
        maintain_zone.add(z)
        for item in value:
            maintain_zone.add(item['to_zone'])
    not_maintain_zones = []
    for z in maintain_zone:
        if _get_zone_maintain_status(z) == 0:
            continue
        not_maintain_zones.append(z)
    if not_maintain_zones:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'%s 等区未处于维护状态' % ', '.join(not_maintain_zones)}))
    merge_config = {
        'buildinglv_per': game_config.system_simple['merge_reward']['buildinglv_per'],
        'base_reward': game_config.system_simple['merge_reward']['base_reward'],
        'game_id': game_config.system_simple.get('game_id', 'sg')
    }
    for host in server_manage_host:
        server_addr = '%s:%s' % (host, settings.SERVER_MANAGE_PORT)
        UserZone.call_duplicate_server_api(server_addr,
                                           'start_merge_zone',
                                           {
                                               'merge_id': record_id,
                                               'merge_config': merge_config,
                                               'merge_zones': r.merge_config
                                           })
    r.start_time = datetime.datetime.now()
    r.status = MergeRecord.merge_running
    r.save()
    return HttpResponse(json.dumps({'state': 'success'}))

def update_user_login_zone(from_zone, uid, to_zone):
    if int(uid)/settings.UIDADD > 0:
	from_zone = int(uid)/settings.UIDADD
    else:
	from_zone = int(from_zone)
    uid = uid % settings.UIDADD
    user_zone = UserZone.get(uid)
    if str(from_zone) in user_zone.zone_login:
	user_zone.zone_login[str(from_zone)]['merge_zone'] = to_zone
	user_zone.save()

def del_user_login_zone(from_zone, uid):
    try:
        if int(uid)/settings.UIDADD > 0:
            from_zone = int(uid)/settings.UIDADD
        else:
            from_zone = int(from_zone)
        uid = uid % settings.UIDADD
	user_zone = UserZone.get(uid)
        if str(from_zone) in user_zone.zone_login:
            del user_zone.zone_login[str(from_zone)]
	    user_zone.save()
    except:
        pass

def update_system_data(from_zone, to_zone, mysql_conn):
    to_system_data = mysql_conn.execute("select * from system_data where zone='%s'" % to_zone).fetchone()
    if not to_system_data:
	db_system_data = mysql_conn.execute("select * from system_data where zone='%s'" % from_zone).fetchone()
	if not db_system_data:
	    system_data = {}
	else:
	    system_data =zlib.decompress(db_system_data.data)
	    system_data = eval(system_data)
	    
	res = {}
	res['festival'] = system_data.get('festival', {})
	res = repr(res)
	res =zlib.compress(res)
	mysql_conn.execute(text(
	    "insert into system_data (zone, data) VALUES (:zone,:data) ON DUPLICATE KEY UPDATE data=:data"),
		    {'zone': to_zone, 'data': res})

def get_msg_info(from_zone, pf):
    merge_times = str(UserZone.get_zone_merge_times(from_zone) + 1)
    if settings.WHERE in ['kr', 'cb37kr']:
        msg_config = game_config.server_raise_msg_kr['merge_msg']
    elif settings.WHERE in ['hk', 'tw37', 'cbhk']:
        if pf == 'r2g_xm':
            msg_config = game_config.server_raise_msg['merge_msg']
        else:
            msg_config = game_config.server_raise_msg_tw['merge_msg']
    elif settings.WHERE == 'ea37':
        pf_lan = game_config.system_simple['server_raise_pf'].get(pf)
        if pf_lan:
            msg_config = getattr(game_config, 'server_raise_msg_%s' % pf_lan)['merge_msg']
        else:
            msg_config = game_config.server_raise_msg['merge_msg']
    elif settings.WHERE in ['vn', 'cbvn']:
        msg_config = game_config.server_raise_msg_viet['merge_msg']
    elif settings.WHERE == 'th':
        msg_config = game_config.server_raise_msg_th['merge_msg']
    elif settings.WHERE == 'jpn':
        msg_config = game_config.server_raise_msg_ja['merge_msg']
    elif settings.WHERE == 'indofun':
        msg_config = game_config.server_raise_msg_bahasa['merge_msg']
    else:
        msg_config = game_config.server_raise_msg['merge_msg']
    return msg_config[merge_times]

def update_merge_zone(from_zone, merge_maps):
    DBENGINE = 'mysql://%s:%s@%s:%s/%s?charset=utf8' % settings.DB_ACCOUNT_PASSWORD['shards']['1']['master']
    _MasterDB = create_engine(DBENGINE, echo=False, encoding='utf-8', pool_recycle=120, pool_size=1, max_overflow=-1)
    _conn = _MasterDB.connect()
    uid_add = settings.UIDADD
    if 'country_ftask' in game_config.system_simple:
        merge_times = UserZone.get_zone_merge_times(to_zone)
        if game_config.system_simple.get('use_merge_maps') == 1:
            try:
                merge_maps = game_config.system_simple['merge_maps'][merge_times]
            except IndexError:
                merge_maps = game_config.system_simple['merge_maps'][-1]
        else:
            merge_maps = -1
        if merge_maps == -1:
            country_ftask = game_config.system_simple['country_ftask']
        else:
            country_ftask = game_config.system_simple['country_ftask_maps'][merge_maps]
    else:
        if game_config.system_simple.get('game_id') == 'cb':
            country_ftask = [['11009', '11007'], ['21009', '21007'], ['31009', '31007']]
        else:
            country_ftask = [['144','146'],['31','62'],['350','353']]
    buildinglv_per = game_config.system_simple['merge_reward']['buildinglv_per']
    base_reward = game_config.system_simple['merge_reward']['base_reward']
    buildinglv_dict = {}
    #'':[[18,1],[12,0.6],[6,0.2],[1,0]],
    n = 37
    for item in buildinglv_per:
        for i in range(item[0],n):
            buildinglv_dict[i] = item[1]
        n = item[0]

    now = datetime.datetime.now()

    from_user_table = utils.get_table_name('user',from_zone,settings.USER_TABLE_NUM)
    db_user = _conn.execute("select * from %s where zone='%s'" % (from_user_table,from_zone)).fetchall()

    # 赛季结算
    db_system_data = _conn.execute("select * from system_data where zone='%s'" % from_zone).fetchone()
    if not db_system_data:
        system_data = {}
    else:
        system_data =zlib.decompress(db_system_data.data)
        system_data = eval(system_data)
    honour = system_data.get('honour')
    honour_start_time = honour.get('start_time', datetime.datetime.now())
    honour_end_time = datetime.datetime.now()
    honour_rank_dict = {}
    rank = 1
    for item in honour.get('rank', []):
        honour_rank_dict[item[0]] = rank
        rank += 1
    from_merge_times = game_config.zone[from_zone][8]

    to_zones = set()
    for item in db_user:
        user_data =zlib.decompress(item.user_data)
	if settings.USE_SERIALIZE == 'json':
	    user_data = json.loads(user_data, object_hook=Serializer.json_object_hook)
	else:
	    user_data = eval(user_data)
        if not user_data:
            continue
        to_zone = merge_maps[user_data['country']]['to_zone']
        to_user_table = utils.get_table_name('user', to_zone, settings.USER_TABLE_NUM)

        cache_key = '%smerge_zone_uname_%s' % (settings.CACHE_PRE, to_zone)
        uname_list = cache.get(cache_key, [])

        uid = int(user_data['uid']) % settings.UIDADD
        if int(user_data['uid'])/settings.UIDADD > 0:
            old_zone = int(user_data['uid'])/settings.UIDADD
        else:
            old_zone = from_zone

        new_uid = uid_add * int(old_zone) + uid
        #insert to db
        db_uid = str(new_uid)
        #print to_user_table
        #print new_uid
        _db_user = _conn.execute("select * from %s where uid='%s' and zone='%s'" % (to_user_table, db_uid, to_zone)).fetchone()
        if _db_user:
            continue	

        if user_data['country'] not in [0,1,2]:
            del_user_login_zone(from_zone,user_data['uid'])
            continue
        building_lv = user_data['home']['building001']['lv']
        if not user_data['online_log']['login_time']:
            del_user_login_zone(from_zone,user_data['uid'])
            continue
        if user_data['records']['pay_money'] == 0 and building_lv < 12 and user_data['online_log']['login_time']+datetime.timedelta(days=7) < now:
            del_user_login_zone(from_zone,user_data['uid'])
            continue
        rewards = merge_maps[user_data['country']]['reward']
        user_data['country'] = merge_maps[user_data['country']]['to_country']
        uname = user_data['uname']

        if not uname:
            del_user_login_zone(from_zone,user_data['uid'])
            continue
        gift_dict = {}
        while 1:
            if uname not in uname_list:
                break
            uname_n = re.findall('\d+$', uname)
            if uname_n:
                uname_n = int(uname_n[0]) + 1
                uname = re.split('\d+$',uname)[0]
                uname = u'%s%s' % (uname,uname_n)
            else:
                uname = u'%s1' % uname
            user_data['uname'] = uname
            gift_dict.update(game_config.help_msg['change_uname_gift'])

        uname_list.append(uname)
        cache.set(cache_key, uname_list, timeout=60*60*2)
        gift_dict.update(base_reward)
        for hid,hvl in user_data['hero'].items():
            hvl['work'] = None
        user_data['task']['country'] = []
        for x,y in rewards.items():
            yy = int(y*buildinglv_dict[building_lv])
            if yy:
                gift_dict.setdefault(x,0)
                gift_dict[x] += yy
        for k in settings.MERGE_DELETE_ATTR['user_del_key_list']:
            if user_data.has_key(k):
                del user_data[k]
        user_data['msg']['usr'] = []
        msg_name, msg_info = get_msg_info(from_zone, user_data['pf'])
        gift_list = [msg_name, msg_info, gift_dict, now, 0]
        user_data['msg']['sys'].insert(0, gift_list)
        for k in settings.MERGE_DELETE_ATTR['user_del_records_key_list']:
            if user_data['records'].has_key(k):
                del user_data['records'][k]
        for k in settings.MERGE_DELETE_ATTR['user_del_total_records_key_list']:
            if user_data['total_records'].has_key(k):
                del user_data['total_records'][k]

        user_data['uid'] = new_uid
        user_data['ftask'] = {}
        for city_id in country_ftask[user_data['country']]:
            user_data['ftask'][city_id] = [-1,0,0]

        # 赛季结算
        if user_data['honour_hero']:
            exp_max_hero = user_data['honour_hero'].get('exp_max_hero', None)
            if exp_max_hero:
                exp_max_hero[1] = user_data['honour_hero'][exp_max_hero[0]]['lv']
                total_lv = user_data['honour_hero'].get('total_lv',0)
                x,y,z = game_config.honour['honour_reward_%s' % from_merge_times]
                reward_num = min((total_lv*x),y)
                log_dict = {
                        'start_time': honour_start_time,
                        'end_time': honour_end_time,
                        'total_lv': total_lv,
                        'reward_num': reward_num,
                        'rank': honour_rank_dict.get(user_data['uid'],None),
                        'exp_max_hero': exp_max_hero,
                        'status': 0,
                        'merge_times': from_merge_times,
                        'task_done_num': user_data['honour_task'].get('done_num',0),
                        }
                user_data['honour_log'].append(log_dict)
                user_data['honour_hero'] = {}
                user_data['honour_task'] = {}

        str_user = repr(user_data)
        str_user =zlib.compress(str_user)
        power = user_data['power']

        _conn.execute(text("insert into %s (uid,zone,power,user_data) values (:uid,:zone,:power,:user_data)" % to_user_table),{'uid':db_uid,'zone': to_zone,'power': power,'user_data': str_user})

        ### 更新合区指向
        update_user_login_zone(from_zone, new_uid, to_zone)
        to_zones.add(to_zone)
    for i in to_zones:
        update_system_data(from_zone, i, _conn)
    _conn.close()

def get_open_time():
    current_data = datetime.date.today()
    open_time = datetime.datetime(current_data.year, current_data.month, current_data.day, 8, 0)
    return open_time

@login_permission_required('merge_zone', ajax=True)
def manual_merge_zone(request):
    record_id = request.POST['record_id']
    r = MergeRecord.get(record_id)
    if not r:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服配置不存在'}))
    if r.status != MergeRecord.merge_running:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'还未开始合服，不能手动操作'}))
    now = datetime.datetime.now()
    if (now-r.start_time).total_seconds() < 30*60:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'合服开始30分钟以后才能使用该功能'}))

    try:
        for k,v in r.merge_config.items():
            if k in r.finish_zones:
                continue
            update_merge_zone(k, v)
            r.finish_zones.append(k)
        r.status = MergeRecord.merge_finish
        r.progress = 100
        r.end_time = datetime.datetime.now()
        r.save()
        add_merge_zone = set()
        for z, value in r.merge_config.items():
            for item in value:
                add_merge_zone.add(item['to_zone'])
        for add_zone in add_merge_zone:
            if Zones.get_zone(add_zone):
                continue
            z = Zones()
            z.zone_id = add_zone
            z.zone_name = add_zone
            z.host = ''
            z.port = UserZone.get_service_port(add_zone)
            z.open_time = get_open_time()
            z.register_limit = 0
            z.state = 0
            z.recommend = 0
            z.merge_times = UserZone.get_zone_merge_times(add_zone)
            z.active = 0
            z.zone_group = UserZone.get_zone_group(add_zone)
            z.save()
        for z in r.merge_config.keys():
            _zone = Zones.get_zone(z)
            _zone.host = ''
            _zone.port = 0
            _zone.active = 2
            _zone.save()
    except:
        utils.print_err()
    return HttpResponse(json.dumps({'state': 'success'}))
