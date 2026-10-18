#-*- coding: utf-8 -*-
import math
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, Context, loader
from django.conf import settings
import datetime
from admin.logic import login_permission_required
import json
from game_lib.models.main import AdminLog, UserDuplicate
from game_lib.libs.model import Serializer, Model
from game_lib.logics import game_config
from db.database import pay_records_table as ASP
from admin.pager import Pager
from game_lib.common import utils
from sqlalchemy import *
from copy import deepcopy as copy
import hashlib
import string, time
import urllib, urllib2
import datetime
from game_lib.db.database import c_cache as cache, ShardMetas
from game_lib.db.database import DuplicateLog_table as dl

from game_lib.models.main import UserZone,FreezeLog,FreezeHistory,AdminPayRecord
import random
import base64
from libs.weixin_app import WeiXinPay
import qrcode
from io import BytesIO
from views.main import add_user_pay
import cPickle as pickle
import zlib
from game_lib.db.mongo import get_dbengine


@login_permission_required('chat_log') 
def chat_log(request):
    is_37 = False
    session_user = request.session.get('admin_user')
    if session_user['username'] != 'admin':
        if 'view_app_user' not in session_user['permissions']:
            is_37 = True
    zone = request.REQUEST.get('zone', None)
    date_str = request.REQUEST.get('date_str')
    if not date_str:
        date_str = datetime.date.today().strftime('%Y-%m-%d')
    zone_list = []
    for item in UserZone.get_zone_list('running', session_user=session_user):
        zone_list.append(item)
    log_list = []
    c_dict = {0:'魏',1:'蜀',2:'吴'}
    icon_dict = {0:'世界',1:'国家',2:'国家栋梁', 3:u'私聊'}
    notice_data = []
    if zone:
        zone_config = game_config.zone
        is_merge_zone = False
        if zone_config[zone][8]:
            is_merge_zone = True
        for item in UserZone.call_server_api(zone, 'get_chat_log', {'date_str': date_str}):
            if is_merge_zone:
                if item[0] == 3:
                    to_old_zone = item[6]/settings.UIDADD
                    item[6] = item[6] % settings.UIDADD
                    item.append(to_old_zone)
                old_zone = item[1]/settings.UIDADD
                item.insert(6,old_zone)
                item[1] = item[1] % settings.UIDADD
            else:
                if item[0] == 3:
                    item.insert(6,zone)
                item.append(zone)
            if item[0] == 3:
                item[9] = c_dict[item[9]]
            log_list.append(item)
            item[0] = icon_dict[item[0]]
            item[3] = c_dict[item[3]]
            item[4] = str(item[4])[:19]

        ## 国家公告数据
        world = UserZone.call_server_api(zone, 'get_world', {})
        coutry_notice = world['country_notice']
        for c_index, c in sorted(c_dict.iteritems(), key=lambda x:x[0]):
            notice = {}
            _item = coutry_notice[str(c_index)]
            notice['country'] = {'name': c, 'id': c_index}
            notice['locked'] = int(_item['locked'])
            notice['content'] = _item['content'] or ''
            modify_user = _item['modify_user']
            modify_service = _item['modify_service']
            if is_merge_zone:
                if modify_user['user']:
                    _uid = modify_user['user']%settings.UIDADD
                    _zone = modify_user['user']/settings.UIDADD
                    modify_user['user'] = '%s|%s' % (_uid, _zone)
            else:
                if modify_user['user']:
                    modify_user['user'] = '%s|%s' % (modify_user['user'], zone)
            modify_by = {}
            if modify_user['user'] is not None and modify_service['user'] is not None:
                if modify_user['t'] >= modify_service['t']:
                    modify_by['role'] = 'user'
                    modify_by['user'] = modify_user['user']
                    modify_by['t'] = utils.get_time_str(modify_user['t'])
                else:
                    modify_by['role'] = 'service'
                    modify_by['user'] = modify_service['user']
                    modify_by['t'] = utils.get_time_str(modify_service['t'])
            else:
                if modify_user['user'] is not None:
                    modify_by['role'] = 'user'
                    modify_by['user'] = modify_user['user']
                    modify_by['t'] = utils.get_time_str(modify_user['t'])
                elif modify_service['user'] is not None:
                    modify_by['role'] = 'service'
                    modify_by['user'] = modify_service['user']
                    modify_by['t'] = utils.get_time_str(modify_service['t'])
                else:
                    modify_by = {'user': '--', 't': '--', 'role': 'null'}
            notice['modify_by'] = modify_by
            notice_data.append(notice)
    return render_to_response('admin/app_user/chat_log.html', {
        'WHERE': settings.WHERE,
        'zone_list': zone_list,
        'zone': zone,
        'log_list': log_list,
        'date_str': date_str,
        'is_37': is_37,
        'notice_data': notice_data,
        },
        RequestContext(request))


@login_permission_required('change_country_notice',ajax=True)
def change_country_notice(request):
    try:
        zone = request.POST.get('zone')
        change_key = request.POST.get('change_key')
        params = {'change_key': change_key}
        if change_key == 'modify_country_notice':
            params['content'] = request.POST.get('content')
            params['user'] = request.session['admin_user']['username']
            params['modify_service'] = True
            params['country'] = request.POST.get('country')
        elif change_key == 'locked_country_notice':
            params['country'] = request.POST.get('country')
            params['locked'] = request.POST.get('status')

        else:
            return HttpResponse(json.dumps({'state':'error', 'msg': 'change_key error'}))
        world = UserZone.call_server_api(zone, 'change_world', params)
        if world.get('msg'):
            return HttpResponse(json.dumps({'state': 'error', 'msg': world['msg']}))

        return HttpResponse(json.dumps({'state':'success'}))

    except Exception, e:
        utils.print_err()
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))

@login_permission_required('user_msg_log') 
def user_msg_log(request):
    zone = request.REQUEST.get('zone', None)
    session_user = request.session.get('admin_user')
    if request.method == 'GET':
        zone_list = []
        item_list = []
        for item in UserZone.get_zone_list('running', session_user=session_user):
            item_list.append(item)
            if len(item_list) >= 10:
                zone_list.append(item_list)
                item_list = []
        else:
            zone_list.append(item_list)
        return render_to_response('admin/app_user/user_msg_log.html', {
            'zone_list': zone_list,
        },
            RequestContext(request))
    log_list = []
    c_dict = {0:'魏',1:'蜀',2:'吴'}
    if zone:
        zone_config = game_config.zone
        is_merge_zone = False
        if zone_config[zone][8]:
            is_merge_zone = True
        msg_log = UserZone.call_server_api(zone, 'get_user_msg_log', {})
        for item in sorted(msg_log.values(),key=lambda x:x[0][0],reverse=True):
            for _item in item:
                if is_merge_zone:
                    old_zone = _item[1]/settings.UIDADD
                    _item.append(old_zone)
                    _item[1] = _item[1] % settings.UIDADD
                    _item.append(_item[4]/settings.UIDADD)
                    _item[4] = _item[4] % settings.UIDADD
                else:
                    _item.append(zone)
                    _item.append(zone)
                _item[3] = c_dict[_item[3]]
                _item[6] = c_dict[_item[6]]
            log_list.append(item)

    user_msg_log_body = loader.render_to_string('admin/app_user/user_msg_log_body.html', {
        'log_list': log_list,
    },
        RequestContext(request))

    return HttpResponse(json.dumps({'user_msg_log_body': user_msg_log_body}))


@login_permission_required('view_session_key') 
def view_session_key(request):
    ulist = []
    exact = int(request.REQUEST.get('exact', 1))
    session_key = request.POST.get('session_key', '')
    session_user = request.session.get('admin_user')
    zone_list = UserZone.get_zone_list('running', session_user=session_user)
    zone = None
    zone_config = game_config.zone
    if request.POST:
        session_key = session_key.strip()
        zone = request.POST.get('zone', '')
        if session_key:
            if zone == 'all':
                for _zone in zone_list:
                    for item in UserZone.call_server_api(_zone[0], 'get_user_by_name', {'uname': session_key, 'exact': exact}):
                        if zone_config[_zone[0]][8]:
                            item_zone = item[0]/settings.UIDADD
                            item_uid = item[0] % settings.UIDADD
                            item[0] = '%s|%s' % (item_uid,item_zone)
                        else:
                            item[0] = '%s|%s' % (item[0],_zone[0])
                        ulist.append(item)
            else:
                for item in UserZone.call_server_api(zone, 'get_user_by_name', {'uname': session_key, 'exact': exact}):
                    if zone_config[zone][8]:
                        item_zone = item[0] / settings.UIDADD
                        item_uid = item[0] % settings.UIDADD
                        item[0] = '%s|%s' % (item_uid, item_zone)
                    else:
                        item[0] = '%s|%s' % (item[0], zone)
                    ulist.append(item)


    zone_list.insert(0, ['all', u'全部区服'])
    return render_to_response('admin/app_user/view_session_key.html', {
        'session_key': session_key,
        'zone_list': zone_list,
        'ulist': ulist,
        'exact': exact,
        'zone': zone,
        },
        RequestContext(request))

@login_permission_required('view_app_user') 
def download_world(request):
    zone = request.REQUEST.get('zone', None)
    type = request.REQUEST.get('type', None)
    world = UserZone.call_server_api(zone, 'get_world', {})
    world_str = json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default)
    res = HttpResponse(world_str)
    if type == 'json':
        res['Content-Type'] = 'text/json; charset=utf-8'
    else:
        res['Content-Disposition'] = 'attachment;filename=world_zone_%s.json' % zone
    return res
def _get_backup_status(backup_time):
    now = datetime.datetime.now()
    if not backup_time:
        backup_status = [u'未知', 'red']
    else:
        diff_time = int((now - backup_time).total_seconds() / 60)
        if diff_time > 30:
            color = 'red'
        else:
            color = 'green'
        backup_status = [backup_time.strftime('%Y-%m-%d %H:%M:%S'), color]
    return backup_status

@login_permission_required('view_world') 
def view_world(request):
    zone = request.REQUEST.get('zone', None)
    session_user = request.session.get('admin_user')
    zone_list = []
    item_list = []
    for item in UserZone.get_zone_list('running', session_user=session_user):
        item_list.append(item)
        if len(item_list) >= 10:
            zone_list.append(item_list)
            item_list = []
    else:
        zone_list.append(item_list)

    if request.method == 'GET':
        return render_to_response('admin/app_user/view_world.html', {'zone_list': zone_list}, RequestContext(request))
    season_dict = {
            1: u'春',
            2: u'夏',
            3: u'秋',
            0: u'冬',
            }
    c_dict = {0:'魏',1:'蜀',2:'吴'}
    story_dungeons = []
    if zone:
        world = UserZone.call_server_api(zone, 'get_world2', {})
        backup_status = _get_backup_status(world['backup_time'])
        world_lv = world['world_lv']
        pve_lv = world['pve_lv']
        finish_gtask_max = world['finish_gtask_max']
        open_days = world['open_days']
        _country_advise_score = world['country_advise_score']
        merge_maps, merge_ploys = world['use_merge']
        use_function = world.get('use_function', {})
        country_advise_score = []
        for k,v in sorted(_country_advise_score.iteritems(), key=lambda x:x[0]):
            country_advise_score.append([c_dict[k], k] + v)

        change_world_log = cache.get(settings.CACHE_PRE+'change_world_log'+str(zone),[])
        log_str_list = get_log_str_list(change_world_log).content
        season = season_dict[open_days % 4]
        merge_times = game_config.zone[zone][8]
        honour_dict = world['honour_dict']
        honour_rank = world['honour_rank']
        honour_open = honour_dict.get('if_open', False)
        if honour_open:
            honour_dict['keep_days'] = honour_dict['open_days'] - honour_dict['start_open_days']+1
            honour_dict['start_time'] = str(honour_dict['start_time'])[:19]
            zone_config = game_config.zone
            for item in honour_rank:
                item['country'] = c_dict[item['country']]
                if zone_config[zone][8]:
                    item['uid_zone']= '%s|%s' % (int(item['uid']) % settings.UIDADD,(item['uid'])/settings.UIDADD)
                else:
                    item['uid_zone']= '%s|%s' % (item['uid'],zone)
        if game_config.zone[zone][8] >= game_config.puppet['switch']:
            for k,v in enumerate(game_config.story['story_dungeon']):
                item = [k]
                item.append(game_config.return_msg[v['title']])
                item.append(1 if k == 0 else 0)
                story_dungeons.append(item)
    else:
        world = None
        world_lv = ''
        pve_lv = ''
        finish_gtask_max = ''
        open_days = ''
        log_str_list = ''
        season = ''
        merge_maps = ''
        merge_ploys = ''
        honour_open = False
        honour_dict = {}
        honour_rank = []
        use_function = {}

    world_body = loader.render_to_string('admin/app_user/view_world_body.html', {
        'admin_user': request.session['admin_user']['username'],
        #'world': json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default) if world else None,
        'backup_status': backup_status,
        'world_lv': world_lv,
        'pve_lv': pve_lv,
        'finish_gtask_max': finish_gtask_max,
        'open_days': open_days,
        'season': season,
        'WHERE': settings.WHERE,
        'zone_list': zone_list,
        'zone': zone,
        'log_str_list': log_str_list,
        'honour_open': honour_open,
        'honour_dict': honour_dict,
        'honour_rank': honour_rank,
        'country_advise_score': country_advise_score,
        'merge_maps': merge_maps,
        'merge_ploys': merge_ploys,
        'use_function': use_function,
        'story_dungeons': story_dungeons,
        },
        RequestContext(request))
    return HttpResponse(json.dumps({'world_body': world_body}))

@login_permission_required('hero_power_rank') 
def hero_power_rank(request):
    session_user = request.session.get('admin_user')
    zone_list = UserZone.get_zone_list('running', session_user=session_user)
    search_zone_list = request.POST.getlist('search_zone_list')
    order_by = request.POST.get('order_by')
    hero_power_min = request.POST.get('hero_power_min', '')
    hero_power_add = request.POST.get('hero_power_add', '')
    hero_count = request.POST.get('hero_count')
    if not hero_count:
        if settings.SUBTEST:
            hero_count = 100
        else:
            hero_count = 5
    for item in zone_list:
        if item[0] in search_zone_list:
            item[2] = 'checked'
    filter_power = False
    if hero_power_min:
        hero_power_min = int(hero_power_min)
        if not hero_power_add:
            hero_power_add = 500000
        else:
            hero_power_add = int(hero_power_add)
        hero_power_max = hero_power_min + hero_power_add + 1
        filter_power = True
    hero_power_list = []
    hero_dict = {}
    zone_config = game_config.zone
    if search_zone_list:
        for zone in search_zone_list:
            res = UserZone.call_server_api(zone, 'user_power_rank', {'hero_count': int(hero_count)})
            res.pop()
            for item in res[4:]:
                if zone_config[zone][8]:
                    uid_zone = '%s|%s' % (int(item['uid']) % settings.UIDADD,(item['uid'])/settings.UIDADD)
                else:
                    uid_zone = '%s|%s' % (item['uid'],zone)
                for hero in item['hero_list']:
                    if filter_power:
                        if hero[1] < hero_power_min or hero[1] > hero_power_max:
                            continue
                    hid = hero[0]
                    hero_dict.setdefault(hid,[0, hero[2],[]])
                    hero_dict[hid][2].append([uid_zone, item['uname'], hero[1], hero[3]])
                    if hero[1] > hero_dict[hid][0]:
                        hero_dict[hid][0] = hero[1]

    for item in sorted(hero_dict.items(),key=lambda x:x[1][0],reverse=True):
        h_list = sorted(item[1][2],key=lambda x:x[2],reverse=True)
        hero_power_list.append([item[0], item[1][0], item[1][1], h_list, len(h_list)])

    if order_by:
        if order_by.startswith('-'):
            reverse = True
            _order_by = order_by[1:]
        else:
            reverse = False
            _order_by = order_by
        if _order_by == 'hero_count':
            hero_power_list.sort(key=lambda x:x[4], reverse=reverse)
        else:
            _, hero_index = _order_by.split('|')
            def _sort_func(x):
                try:
                    return x[3][int(hero_index)][2], x[3][0][2]
                except:
                    return 0, x[3][0][2]
            hero_power_list.sort(key=_sort_func, reverse=reverse)

    return render_to_response('admin/app_user/hero_power_rank.html', {
        'search_zone_list': search_zone_list,
        'zone_list': zone_list,
        'hero_power_list': hero_power_list,
        'hero_power_min': hero_power_min,
        'hero_power_add': hero_power_add,
        'hero_count': hero_count,
        },
        RequestContext(request))

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

@login_permission_required('user_power_rank') 
def user_power_rank(request):
    now = datetime.datetime.now()
    zone = request.REQUEST.get('zone', None)
    content_open = request.REQUEST.get('content_open', 0)
    session_user = request.session.get('admin_user')
    include_ai = int(request.REQUEST.get('include_ai', 1))
    if request.method == 'GET':
        zone_list = []
        item_list = []
        for item in UserZone.get_zone_list('running', session_user=session_user):
            item_list.append(item)
            if len(item_list) >= 10:
                zone_list.append(item_list)
                item_list = []
        else:
            zone_list.append(item_list)

        return render_to_response('admin/app_user/user_power_rank.html', {
            'zone_list': zone_list,
            },
            RequestContext(request))

    try:
        if not zone:
            return HttpResponse(json.dumps({'state':'error', 'msg': '需指定区号'}))
        # 刷新排行榜开关
        refresh = request.POST.get('refresh')
        if refresh:
            UserZone.call_server_api(zone, 'user_power_rank', {'refresh_all': True})
            time.sleep(2)
        power_list = []
        c_dict = {0: '魏', 1: '蜀', 2: '吴'}
        country_res = []
        open_days = None
        auction_data = []
        auction_records = []
        """
        country_res = [
            {
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
            },
                ]
        country_rank_3_user_hero_list = [
                [],
                [],
                []
                ]
        """
        um = UserZone.call_server_api(zone, 'get_use_merge', {})
        merge_maps, merge_ploys = um.split('|')
        res = UserZone.call_server_api(zone, 'user_power_rank', {'include_ai': include_ai})
        backup_time = res.pop()
        backup_status = _get_backup_status(backup_time)
        zone_pay_records = get_zone_thirty_days_pay_records(zone)
        open_days = res[0]
        """
        for k,v in res[1].items():
            country_res[k][0] += v[0]
            country_res[k][1] += v[1]
        """
        country_res = res[1]
        for item in country_res:
            item['best_hero_power'] = 0
            item['thirty_pay_money'] = 0
        zone_config = game_config.zone
        auction = res[3]
        # auction_data = auction.get('data', [])
        # if auction_data:
        #     days_key = auction['open_days']
        #     if merge_ploys == '-1':
        #         auction_config = game_config.ploy['auction']
        #     else:
        #         auction_config = getattr(game_config, 'ploy_%s' % merge_ploys)['auction']
        #     i = 0
        #     for item in auction_data:
        #         try:
        #             gift_dict = auction_config['library'][days_key][i][2]
        #             hero_id = gift_dict['awaken'][0]
        #             hero_name = game_config.return_msg['700%s' % hero_id[4:]]
        #             item[3] = '%s-%s' % (hero_name, hero_id)
        #             item[2] = str(item[2])[:19]
        #             i += 1
        #         except IndexError:
        #             continue
        auction_records = auction.get('get_records', [])
        if zone_config[zone][8]:
            auction_records.sort(key=lambda x: x[4], reverse=True)
        else:
            auction_records.sort(key=lambda x: x[3], reverse=True)
        _auction_records = []
        for item in auction_records:
            if zone_config[zone][8]:
                old_uid = int(item[0]) % settings.UIDADD
                old_zone = int(item[0]) / settings.UIDADD
                item[0] = '%s|%s' % (old_uid, old_zone)
            else:
                item[0] = '%s|%s' % (item[0], zone)
            if zone_config[zone][8]:
                god_type = item[1]['god_data']['type']
                _item = [item[0],
                         '%s-%s' % (game_config.return_msg['%s_name' % god_type], god_type),
                         '%s|%s' % (item[2], item[3]),
                         str(item[4])[:19]
                         ]
                _auction_records.append(_item)
            else:
                hero_id = item[1]['awaken'][0]
                hero_name = game_config.return_msg['700%s' % hero_id[4:]]
                item[1] = '%s-%s' % (hero_name, hero_id)
                item[3] = str(item[3])[:19]
                _auction_records.append(item)

        for item in sorted(res[4:], key=lambda x:x['best_power'], reverse=True):
            if zone_config[zone][8]:
                old_uid = int(item['uid']) % settings.UIDADD
                old_zone = int(item['uid']) / settings.UIDADD
            else:
                old_uid = item['uid']
                old_zone = zone
            user_zone = UserZone.get(old_uid)
            if user_zone:
                item['user_ip'] = user_zone.user_ip
            else:
                item['user_ip'] = ''
            item['uid_zone'] = '%s|%s' % (old_uid, old_zone)

            item['last_login'] = str(item['last_login'])[:19]
            if country_res[item['country']]['best_hero_power'] < item['best_hero_power']:
                country_res[item['country']]['best_hero_power'] = item['best_hero_power']
            item['thirty_pay_money'] = zone_pay_records.get(item['uid_zone'], 0)
            if utils.total_seconds(now - item['t']) < 48 * 3600 and item['rank'] <= 100:
                country_res[item['country']]['thirty_pay_money'] += item['thirty_pay_money']

            item['country'] = c_dict.get(item['country'],'')
            item['t'] = utils.format_time(item['t'])
            hero = []
            for h in item['hero_list']:
                if h[3]:
                    h[2] = u'神·' + h[2]
                hero_info = u'%s%s' % (h[2], h[1])
                hero.append([h[0], hero_info])
            item['hero'] = hero
            skin = []
            for skin_id in item.get('skin_list', []):
                hid = 'hero%s' % skin_id.split('_')[0][4:]
                skin_name = game_config.return_msg[game_config.hero[hid]['name']] + '(%s)' % skin_id
                skin.append(skin_name)
            item['skin'] = ','.join(skin)
            if 'prop' not in item:
                item['prop'] = ['item036', game_config.return_msg.get(game_config.prop['item036']['name'], 'item036'), item['item036']]
            power_list.append(item)
        country_res[0]['country'] = u'魏'
        country_res[1]['country'] = u'蜀'
        country_res[2]['country'] = u'吴'
        is_refresh_rank = True
        if len(power_list) > 0:
            is_refresh_rank = False
        player_data = UserZone.call_server_api(zone, 'get_player_data1', {})
        power_rank_body = loader.render_to_string('admin/app_user/user_power_rank_body.html', {
            'include_ai': include_ai,
            'country_res': country_res,
            'is_refresh_rank': is_refresh_rank,
            'zone': zone,
            'power_list': power_list,
            'open_days': open_days,
            # 'auction_data': auction_data,
            'auction_records': _auction_records,
            'backup_status': backup_status,
            'player_data': player_data,
        }, RequestContext(request))
    except:
        utils.print_err()
    return HttpResponse(json.dumps({'power_rank_body': power_rank_body, 'content_open': content_open}))


@login_permission_required('user_pay_rank') 
def user_pay_rank(request):

    add_date_list = [1,3,7,14,30,60,90]
    from_date = request.REQUEST.get('from_date')
    add_date = int(request.REQUEST.get('add_date',30))
    zone = request.REQUEST.get('zone', None)
    country = request.REQUEST.get('country', 'all')
    pf = request.REQUEST.get('pf', 'all')
    check_time = int(request.REQUEST.get('check_time', 0))
    session_user = request.session.get('admin_user')
    if not from_date:
        to_date = datetime.date.today()
        from_date = to_date - datetime.timedelta(days=add_date)
    else:
        from_date = datetime.date(*[int(item) for item in from_date.split('-')])
        to_date = from_date + datetime.timedelta(days=add_date-1)
        if to_date > datetime.date.today():
            to_date = datetime.date.today()




    zone_list = UserZone.get_zone_list('running', session_user=session_user)
    pay_rank_list = []
    pay_config = game_config.pay_config
    c_dict = {0:'魏',1:'蜀',2:'吴'}
    if zone:
        u_dict = {}
        where = and_(ASP.c.zone == zone)
        if check_time:
            begin = datetime.datetime.strptime(str(from_date), '%Y-%m-%d')
            end = datetime.datetime.strptime(str(to_date), '%Y-%m-%d')
            where = and_(where,ASP.c.pay_time > begin,ASP.c.pay_time < end)
        if country != 'all':
            where = and_(where,ASP.c.country == int(country))
        if pf != 'all':
            where = and_(where,ASP.c.pf == pf)
        pay_sql = ASP.select().where(where).execute().fetchall()
        zone_config = game_config.zone
        for item in pay_sql:
            if zone_config[item.zone][8]:
                new_uid = UserZone.get_new_uid(item.uid,item.old_zone)
            else:
                new_uid = int(item.uid)
            if u_dict.has_key(new_uid):
                u_dict[new_uid] += item.pay_money
            else:
                u_dict[new_uid] = item.pay_money
        u_list = sorted(u_dict.items(),key=lambda x:x[1],reverse=True)

        for item in UserZone.call_server_api(zone, 'user_pay_rank', {'u_list':u_list[:100]}):
            if zone_config[zone][8]:
                item['uid'] = '%s|%s' % (int(item['uid']) % settings.UIDADD,(item['uid'])/settings.UIDADD)
            else:
                item['uid'] = '%s|%s' % (item['uid'], zone)

            item['last_login'] = str(item['last_login'])[:19]
            item['country'] = c_dict.get(item['country'],None)
            item['t'] = utils.format_time(item['t'])
            hero = ''
            for h in item['hero_list']:
                hero += u'%s%s，' % (h[2],h[1])
            item['hero'] = hero
            pay_rank_list.append(item)

    c_list = [('0', u'魏'),('1', u'蜀'),('2',u'吴')]
    return render_to_response('admin/app_user/user_pay_rank.html', {
        'WHERE': settings.WHERE,
        'pay_rank_list': pay_rank_list,
        'from_date': str(from_date),
        'add_date': add_date,
        'add_date_list': add_date_list,
        'check_time': check_time,
        'zone_list': zone_list,
        'zone': zone,
        'country': country,
        'pf': pf,
        'c_list': c_list,
        'pf_list': settings.PFLIST,

        },
        RequestContext(request))
@login_permission_required('freeze')
def relieve_duplicate_ban(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    res = UserZone.call_server_api(zone, 'relieve_duplicate_ban', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('freeze')
def freeze_do(request):
    now = datetime.datetime.now()
    mod_user = []
    uid = int(request.POST['uid'])
    uname = request.POST['uname']
    zone = request.POST['zone']

    freeze = int(request.POST.get('freeze',0))
    freeze_hours = int(request.POST.get('freeze_hours',-1))
    freeze_msg = request.POST.get('freeze_msg','')
    other_msg = request.POST.get('other_msg','')
    admin_user = request.session['admin_user']['username']
    freeze_dict = {'uid': uid,'admin_user': admin_user, 'freeze_status': freeze}
    if freeze != 0:
        if not freeze_hours:
            return HttpResponse('<script>alert("未填写冻结时间");history.go(-1);</script>')
        freeze_dict['hour'] = freeze_hours
        if freeze_msg == '-1':
            freeze_msg = other_msg
            if not other_msg:
                return HttpResponse('<script>alert("请填写冻结原因");history.go(-1);</script>')
        freeze_dict['msg'] = freeze_msg

    FreezeLog.add_freeze_log(uid, zone, uname,freeze, freeze_hours, admin_user, freeze_msg)
    if freeze == 0:
        zone_list = UserZone.get(uid).zone_login.keys()
        for zone in zone_list:
            if zone:
                try:
                    UserZone.call_server_api(zone, 'freeze_do', freeze_dict)
                except:
                    pass
    else:
        UserZone.call_server_api(zone, 'freeze_do', freeze_dict)
    is_37 = False
    session_user = request.session.get('admin_user')
    if session_user['username'] != 'admin':
        if 'view_app_user' not in session_user['permissions']:
            is_37 = True
    if is_37:
        return freeze_user(request)
    else:
        return view_app_user(request)

@login_permission_required('freeze')
def freeze_view(request):
    is_37 = False
    uid_zone = request.REQUEST.get('uid_zone')
    if uid_zone:
        uid, zone = uid_zone.split('|')
    else:
        uid, zone = None, None
    session_user = request.session.get('admin_user')
    if session_user['username'] != 'admin':
        if 'view_app_user' not in session_user['permissions']:
            is_37 = True
    now = datetime.datetime.now()
    parameter = {}
    page = int(request.GET.get('page','1'))
    if not zone:
        operable_zone_list = [item[0] for item in UserZone.get_zone_list('all', session_user=session_user)]
    else:
        operable_zone_list = [zone]

    page_size = 20
    page_list_num = 10
    cond = {'zone_in': operable_zone_list}
    if uid_zone:
        cond['uid'] = uid_zone
    total = FreezeLog.count(cond)
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,parameter=parameter) 
    freeze_db = FreezeLog.query(cond, order_by='-admin_time', limit=page_size, offset=offset)
    freeze_list = []
    for item in freeze_db:
        freeze_list.append(item)

    return render_to_response('admin/app_user/freeze_view.html', {
        'freeze_list': freeze_list,
        'p': p,
        'parameter': parameter,
        'page':page,
        'is_37':is_37,
        'uid_zone': uid_zone
        }, 
        RequestContext(request))

@login_permission_required('freeze')
def freeze_history(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    parameter = {}
    page = int(request.GET.get('page','1'))
    page_size = 20
    page_list_num = 10
    cond = {'uid': uid, 'zone': zone}
    total = FreezeHistory.count(cond)
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,parameter=parameter)
    freeze_history = list(FreezeHistory.query(cond, order_by='-admin_time', limit=page_size, offset=offset))

    return render_to_response('admin/app_user/freeze_history.html', {
        'freeze_history': freeze_history,
        'p': p,
        'parameter': parameter,
        'page':page
        },
        RequestContext(request))

@login_permission_required('view_app_user') 
def view_user_tel(request):
    view_type = request.REQUEST.get('view_type')
    view_val = request.REQUEST.get(view_type, '').strip()
    user_zone_list = list(UserZone.query({view_type:view_val}))
    if not user_zone_list:
        return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>') 
    user_zone = user_zone_list[0]
    return HttpResponseRedirect(settings.BASE_URL+'/admin/app_user/view_app_user/?uid=%s' % user_zone.uid)

@login_permission_required()
def get_user_hero_dict(request):
    uid_zone = request.REQUEST.get('uid_zone',None)
    uid,zone = uid_zone.split('|')
    hid = request.REQUEST.get('hid',None)
    hero_dict = UserZone.call_server_api(zone, 'get_user_hero_dict', {'uid': uid, 'hid': hid})
    json_hero = json.dumps(hero_dict,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_hero)

@login_permission_required('freeze_user') 
def freeze_user(request):
    now = datetime.datetime.now()
    mod_user = []
    uid = request.REQUEST.get('uid', None)
    zone = request.REQUEST.get('zone', None)
    uid_zone = request.REQUEST.get('uid_zone',None)
    session_user = request.session.get('admin_user')
    if uid_zone:
        uid,zone = uid_zone.split('|')
        uid = int(uid)
    app_user = None 
    uname = ''
    pay_config = game_config.pay_config
    pay_list = []
    freeze_list = []
    sale_pay_config = game_config.system_simple['sale_pay']
    for k,v in pay_config.items():
        if settings.WHERE != 'local' and sale_pay_config.has_key(k):
            continue
        if k == 'pf':
            continue
        pay_list.append([k,v[0]])
    is_online = False
    online_t = None
    user_zone = None
    if uid:
        user_zone = UserZone.get(uid)
        if not user_zone:
            return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>')
        zone_list = []
        zone_config = game_config.zone
        for _zone, _merge_zone in user_zone.get_login_zone_list(merge_zone=True):
            if not _zone:
                continue
            if not zone_config.has_key(_zone):
                continue
            if session_user['zone_list']:
                if _zone not in session_user['zone_list']:
                    continue
            elif session_user['zone_group_list']:
                if not UserZone.belong_to_zone_groups(_zone, session_user['zone_group_list']):
                    continue
            if _zone != _merge_zone:
                zone_list.append([_zone,u'%s区-%s(合)%s' % (_zone,zone_config[_zone][0],_merge_zone)])
            else:
                zone_list.append([_zone,u'%s区-%s' % (_zone,zone_config[_zone][0])])
    else:
        zone_list = None

    if uid and zone:
        uid = utils.to_uid(uid)

        app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})



        if not app_user: 
            return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>') 
        is_online = app_user['is_online']
        online_t = utils.format_time(app_user['t'])

        uname = app_user.get('uname')
        now = datetime.datetime.now()
        freeze_list = copy(app_user['records'].get('freeze'))
        if now < freeze_list[1]:
            freeze_list.append('red')
        else:
            freeze_list.append('green')
        freeze_list[1] = str(freeze_list[1])[:19]
        if freeze_list[4]:
            freeze_list[4] = str(freeze_list[4])[:19]
        mod_user = [
            ['uid', u'Uid'],
            ['pf', u'PF'],
            ['user_ip', u'UserIP'],
            ['uname', u'Uname'],
            ['building_lv', u'官邸等级'],
            ['country', u'国家'],
            ['office', u'爵位等级'],
            ['official', u'官职'],
            ['add_time', u'安装时间'],
            ['login_time', u'最后登录时间'],

            ['gold', u'钱'],
            ['food', u'粮'],
            ['wood', u'木'],
            ['iron', u'铁'],
            ['merit', u'功勋'],
            ['coin', u'Coin'],
            ['kill_num', u'击杀'],
            ['build_count', u'建设'],

            ['hero_num', u'英雄数量'],
            ['power_hero_list', u'最强英雄'],
            ['power', u'最强战力'],
            ['member', u'永久卡'],
            ]





        for item in mod_user:
            if item[0] == 'user_ip':
                item.append(user_zone.user_ip or '') 
            elif item[0] == 'phone_id':
                item.append(user_zone.phone_id or '') 
            elif item[0] == 'member':
                item.append(user_zone.member or '') 
            elif item[0] == 'login_time':
                item.append(str(app_user['online_log']['login_time'])[:19])
            elif item[0] == 'building_lv':
                item.append(app_user['home']['building001']['lv'])
            elif item[0] == 'hero_num':
                item.append(len(app_user.get('hero')))
            elif item[0] == 'kill_num':
                item.append(app_user['total_records']['kill_num'])
            elif item[0] == 'build_count':
                item.append(app_user['total_records']['build_count'])
            elif item[0] == 'country':
                c_dict = {0:'魏',1:'蜀',2:'吴'}
                user_country = app_user.get('country')
                if user_country < 0:
                    item.append('未选国家')
                else:
                    item.append(c_dict[user_country])
            elif item[0] == 'official':
                item.append(app_user['official'])
                del app_user['official']
            elif item[0] == 'power_hero_list':
                hero = ''
                for h in app_user['power_hero_list']:
                    hero += u'%s%s，' % (h[2],h[1])
                item.append(hero)
                del app_user['power_hero_list']
            else:
                item.append(app_user.get(item[0]))

    freeze_msgs = game_config.system_simple['freeze_msgs']
    admin_log = AdminLog.query({'func_name': 'admin_save_user'},limit=10,order_by='-subtime')
    interim_pwd = cache.get(settings.CACHE_PRE+'interim_pwd'+str(uid), '')


    return render_to_response('admin/app_user/freeze_user.html', {
        'interim_pwd': interim_pwd,
        'admin_log': admin_log,
        'user_zone':user_zone,
        'uid':uid,
        'uname': uname,
        'mod_user': mod_user,
        'admin_user': request.session['admin_user']['username'],
        'app_user': json.dumps(app_user,sort_keys=True,indent=4,default=Serializer.json_default),
        'WHERE': settings.WHERE,
        'zone_list': zone_list,
        'zone': zone,
        'pay_config': sorted(pay_list, key=lambda x:int(x[0][3:])),
        'freeze_msgs': freeze_msgs,
        'freeze_list': freeze_list,
        'is_online': is_online,
        'online_t': online_t,
        },
        RequestContext(request))

@login_permission_required('drop_user_prop') 
def drop_user_prop(request):
    now = datetime.datetime.now()
    mod_user = []
    uid = request.REQUEST.get('uid', None)
    pf_key = request.REQUEST.get('pf_key', None)
    zone = request.REQUEST.get('zone', None)
    session_user = request.session.get('admin_user')
    app_user = None 
    is_online = False
    online_t = None
    user_zone = None
    if uid:
        user_zone = UserZone.get(uid)
    elif pf_key:
        user_zone_list = list(UserZone.query({'pf_key': pf_key}))
        if user_zone_list:
            user_zone = user_zone_list[0]
    if user_zone:
        zone_list = []
        zone_config = game_config.zone
        for _zone, _merge_zone in user_zone.get_login_zone_list(merge_zone=True):
            if not _zone:
                continue
            if not zone_config.has_key(_zone):
                continue
            if session_user['zone_list']:
                if _zone not in session_user['zone_list']:
                    continue
            elif session_user['zone_group_list']:
                if not UserZone.belong_to_zone_groups(_zone, session_user['zone_group_list']):
                    continue
            if _zone != _merge_zone:
                zone_list.append([_zone,u'%s区-%s(合)%s' % (_zone,zone_config[_zone][0],_merge_zone)])
            else:
                zone_list.append([_zone,u'%s区-%s' % (_zone,zone_config[_zone][0])])
    else:
        zone_list = None

    input_content = []
    prop_list = []
    if uid and zone:
        app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})
        is_online = app_user['is_online']
        online_t = utils.format_time(app_user['t'])
        input_content = [
            ['coin', u'Coin', app_user['coin']],
            ['gold', u'钱', app_user['gold']],
            ['food', u'粮', app_user['food']],
            ['wood', u'木', app_user['wood']],
            ['iron', u'铁', app_user['iron']],
        ]
        dt = app_user['prop']
        prop_dict = {}
        item_list_dict = {}
        return_msg_config = game_config.return_msg
        config_list = sorted(game_config.prop.items(), key=lambda x:x[0])
        for k,v in config_list:
            name = return_msg_config[v['name']]
            pt = v['type']
            a_list = [k, "%s`%s" % (k,name)]
            if k in dt.keys():
                a_list.append(dt[k])
            if not item_list_dict.has_key(pt):
                item_list_dict[pt] = []
            if not prop_dict.has_key(pt):
                prop_dict[pt] = []
            item_list_dict[pt].append(a_list)
            if len(item_list_dict[pt]) >= 5:
                prop_dict[pt].append(item_list_dict[pt])
                item_list_dict[pt] = []
        else:
            for x,y in item_list_dict.items():
                if y:
                    prop_dict[x].append(y)
        native_list_dict = {}
        for k,v in sorted(game_config.native.items(), key=lambda x:x[0]):
            name = return_msg_config.get('%s_name' % k, k)
            pt = v['type']
            a_list = [k, "%s`%s" % (k, name)]
            if k in dt.keys():
                a_list.append(dt[k])
            if not native_list_dict.has_key(pt):
                native_list_dict[pt] = []
            if not prop_dict.has_key(pt):
                prop_dict[pt] = []
            native_list_dict[pt].append(a_list)
            if len(native_list_dict[pt]) >= 5:
                prop_dict[pt].append(native_list_dict[pt])
                native_list_dict[pt] = []
        else:
            for x,y in native_list_dict.items():
                if y:
                    prop_dict[x].append(y)
        prop_list = sorted(prop_dict.items(), key=lambda x:x[0])


    return render_to_response('admin/app_user/drop_user_prop.html', {
        'zone_list': zone_list,
        'user_zone': user_zone,
        'zone': zone,
        'is_online': is_online,
        'online_t': online_t,
        'app_user': app_user,
        'input_content': input_content,
        'all_prop_list': prop_list,
        },
        RequestContext(request))

@login_permission_required('drop_user_prop') 
def drop_user_prop_p(request):
    uid = request.POST.get('uid',None)
    zone = request.POST.get('zone',None)
    drop_dict = {}
    for k in ['coin', 'gold', 'food', 'wood', 'iron']:
        k_val = int(request.POST.get(k, 0) or 0)
        if k_val:
            drop_dict[k] = k_val
    for item in game_config.prop.keys():
        a_num = int(request.POST.get(item, 0) or 0)
        if a_num:
            drop_dict[item] = a_num
    for item in game_config.native.keys():
        a_num = int(request.POST.get(item, 0) or 0)
        if a_num:
            drop_dict[item] = a_num
    res = UserZone.call_server_api(zone, 'drop_user_prop', {'uid': uid, 'zone': zone,'drop_dict': drop_dict})
    if not res:
        return HttpResponse(u'<script>alert("扣除道具失败");history.go(-1);</script>') 
    admin_user = request.session['admin_user']['username']
    content = {
            'uid': uid,
            'zone': zone,
            'uname': res['uname'],
            'drop_dict': drop_dict,
            }
    AdminLog.add_adminlog(admin_user,'drop_user_prop', pickle.dumps(content,-1))
    return view_drop_prop(request)

@login_permission_required('drop_user_prop')
def view_drop_prop(request):
    now = datetime.datetime.now()
    page = int(request.GET.get('page','1'))
    session_user = request.session.get('admin_user')

    p = None
    page_size = 50
    page_list_num = 10
    total = AdminLog.count({'func_name': 'drop_user_prop'})
    offset = page_size*(page-1)
    res = AdminLog.query({'func_name': 'drop_user_prop'},order_by='-subtime',offset=offset,limit=page_size)
    res_list = []
    language_config = game_config.system_simple['language']

    for item in res:
        content = pickle.loads(str(item.content))
        zone = content['zone']
        if session_user['zone_list']:
            if zone not in session_user['zone_list']:
                total -= 1
                continue
        elif session_user['zone_group_list']:
            if not UserZone.belong_to_zone_groups(item, session_user['zone_group_list']):
                total -= 1
                continue
        drop_prop_str = parse_properties_str(content['drop_dict'])
        res_list.append({
            'id': item.id,
            'subtime': item.subtime,
            'admin_user': item.admin_user,
            'uid': content['uid'],
            'zone': content['zone'],
            'drop_prop_str': drop_prop_str,
            'uname': content['uname'],
            })
    p = Pager(total, page_size, page, page_list_num)
    return render_to_response('admin/app_user/view_drop_prop.html', {
        'res_list': res_list,
        'p': p,
        'page':page,
        }, 
        RequestContext(request))

def parse_properties_str(dt):
    input_key_list = [
        ['coin', u'Coin', '1000000'],
        ['gold', u'钱', '1000000'],
        ['food', u'粮', '1000000'],
        ['wood', u'木', '1000000'],
        ['iron', u'铁', '1000000'],
        ]
    p_str = ''
    star_config = game_config.star
    prop_config = game_config.prop
    equip_config = game_config.equip
    native_config = game_config.native

    return_msg_config = game_config.return_msg



    for item in input_key_list:
        if dt.has_key(item[0]):
            p_str += u'%s×%s,' % (item[1],dt[item[0]])

    for k,v in dt.items():
        if k.startswith('saledepot'):
            p_str += u'%s×%s,' % (k,v)
        elif k.startswith('star'):
            msg_id = star_config[k[:6]]['name']
            star_name = return_msg_config[str(msg_id)]
            p_str += u'%s×%s,' % (star_name,v)
        elif k.startswith('item'):
            msg_id = prop_config[k]['name']
            prop_name = return_msg_config[str(msg_id)]
            p_str += u'%s×%s,' % (prop_name,v)
        elif k == 'title':
            for tid in v:
                title_name = return_msg_config[str(tid)]
                p_str += u'%s,' % title_name
        elif k == 'equip':
            for eid in v:
                msg_id = equip_config[eid]['name']
                equip_name = return_msg_config[str(msg_id)]
                p_str += u'%s,' % equip_name
        elif k.startswith('scheme') or k.startswith('tc'):
            if k not in native_config:
                continue
            native_name = return_msg_config['%s_name' % k]
            p_str += u'%sx%s,' % (native_name, v)



    return p_str

@login_permission_required('view_app_user')
def coin_records(request):
    uid = request.GET.get('uid')
    zone = request.GET.get('zone')
    uid = utils.to_uid(uid)
    coin_records = []
    app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})
    if not app_user:
        return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>')

    for item in app_user['coin_records']:
        try:
            _item = copy(item)
            _item[3] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_item[3]))
            coin_records.append(_item)
        except:
            pass

    return render_to_response('admin/app_user/user_coin_records.html', {
        'coin_records': coin_records,
        'uid': uid,
        'zone': zone,
        'uname': app_user['uname']
        },
        RequestContext(request))
@login_permission_required('view_app_user')
def create_role(request):
    uid = request.POST['uid']
    zone = request.POST['zone']
    merge_zone = request.POST['merge_zone']
    user_zone = UserZone.get(uid)
    if not user_zone:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'用户不存在'}))
    if zone in user_zone.zone_login.keys():
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'%s区已存在角色' % zone}))
    if merge_zone and game_config.zone[zone][1][0]:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'%s区未合区' % zone}))
    if not game_config.zone[zone][1][0] and not merge_zone:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请选择合区'}))
    if not merge_zone:
        merge_zone = zone
    user_zone.zone_login[zone] = {'merge_zone': merge_zone, 'login_time': datetime.datetime.now()}
    if game_config.zone[zone][1][0]:
        new_uid = int(uid)
    else:
        new_uid = UserZone.get_new_uid(uid, zone)
    try:
        UserZone.call_server_api(merge_zone, 'create_role', {'new_uid': new_uid, 'country': 0, 'uname': 't%s' % str(new_uid)})
    except:
        utils.print_err()
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'角色创建失败'}))
    user_zone.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('view_app_user') 
def view_app_user(request):
    now = datetime.datetime.now()
    mod_user = []
    uid = request.REQUEST.get('uid', None)
    zone = request.REQUEST.get('zone', None)
    if uid and int(uid) > settings.UIDADD:
        zone = str(int(uid) / settings.UIDADD)
        uid = int(uid) % settings.UIDADD
    uid_zone = request.REQUEST.get('uid_zone',None)
    session_user = request.session.get('admin_user')
    if uid_zone:
        uid,zone = uid_zone.split('|')
        try:
            uid = int(uid)
        except:
            uid = None
    old_zone_list = []
    merge_zone_list = UserZone.get_zone_list('merge')
    merge_zone_list.insert(0, ['', '无'])
    app_user = None 
    uname = ''
    admin_pay_list = ''
    pay_config = game_config.pay_config
    pay_list = []
    freeze_list = []
    duplicate_freeze = { #跨服战禁赛状态
        'state': '未禁赛',
        'color': 'green',
        'ban_time': None
    }
    sale_pay_config = game_config.system_simple['sale_pay']
    is_online = False
    is_db_data = False
    online_t = None
    user_zone = None
    new_uid = None
    if uid:
        user_zone = UserZone.get(uid)
        if not user_zone:
            return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>') 
        login_zone_list = user_zone.get_login_zone_list(merge_zone=True)
        zone_list = []
        zone_config = game_config.zone
        for old_zone,merge_zone in login_zone_list:
            if old_zone not in zone_config or merge_zone not in zone_config:
                continue
            if session_user['zone_list']:
                if merge_zone not in session_user['zone_list']:
                    continue
            elif session_user['zone_group_list']:
                if not UserZone.belong_to_zone_groups(old_zone, session_user['zone_group_list']):
                    continue
            if old_zone != merge_zone:
                zone_list.append([old_zone,u'%s区-%s(合)%s' % (old_zone,zone_config[old_zone][0],merge_zone)])
            else:
                zone_list.append([old_zone,u'%s区-%s' % (old_zone,zone_config[old_zone][0])])
        for item in UserZone.get_zone_list('old'):
            if item[0] in user_zone.zone_login.keys():
                continue
            old_zone_list.append(item)
    else:
        zone_list = None
        old_zone_list = UserZone.get_zone_list('old')

    merge_zone = None
    api_black = None
    if uid and zone:

        common_pay = []
        for k, v in pay_config.items():
            if settings.WHERE != 'local' and sale_pay_config.has_key(k):
                continue
            if k == 'pf':
                continue
            common_pay.append([k, '%s--%s' % (k, v[0])])
        pay_list.append({'type': u'充值pay', 'data': sorted(common_pay, key=lambda x: int(x[0][3:]))})
        goods = {}
        for k, v in game_config.goods.items():
            if v['pay_id'] not in pay_config:
                continue
            good_type = pay_config[v['pay_id']][0]
            goods.setdefault(good_type, [])
            goods[good_type].append([k, '%s--%s' % (k, game_config.return_msg.get(v['info'], v['info']))])
        for k, v in sorted(goods.iteritems(), key=lambda x: x[0]):
            pay_list.append({'type': '%s元' % k, 'data': sorted(v, key=lambda x: int(x[0][2:]))})

        if game_config.zone[zone][8]:
            new_uid = app_user.get('uid')
        else:
            new_uid = settings.UIDADD * int(zone) + user_zone.uid


        uid = utils.to_uid(uid)
        merge_zone = user_zone.zone_login[zone]['merge_zone']
        app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})
        if not app_user:
            db_conn = ShardMetas['1']['db_engine'].connect()
            user_table = utils.get_table_name('user', merge_zone, settings.USER_TABLE_NUM)
            db_user = db_conn.execute(
                "select * from %s where uid='%s' and zone='%s'" % (user_table, new_uid, merge_zone)).fetchone()
            if db_user:
                user_data = zlib.decompress(db_user.user_data)
		if settings.USE_SERIALIZE == 'json':
                    user_data = json.loads(user_data, object_hook=Serializer.json_object_hook)
                else:
                    user_data = eval(user_data)
                user_data['uid'] = int(user_data['uid'])
                is_db_data = True
            else:
                user_data = {}
            db_conn.close()
            app_user = user_data

        if not app_user: 
            return HttpResponse(u'<script>alert("不存在该帐号");history.go(-1);</script>')
        api_black = app_user.get('api_black')
        if api_black and api_black > time.time():
            api_black = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(api_black))
        if app_user['duplicate_ban_time'] and app_user['duplicate_ban_time'] > now:
            duplicate_freeze['state'] = u'已禁赛'
            duplicate_freeze['color'] = 'red'
            duplicate_freeze['ban_time'] = app_user['duplicate_ban_time']
        is_online = app_user.get('is_online', False)
        ttt = app_user.get('t', app_user['online_log']['logout_time'])
        if not ttt:
            ttt = datetime.datetime.now()
        online_t = utils.format_time(ttt)

        uname = app_user.get('uname')
        now = datetime.datetime.now()
        freeze_list = copy(app_user['records'].get('freeze'))
        if now < freeze_list[1]:
            freeze_list.append('red')
        else:
            freeze_list.append('green')
        freeze_list[1] = str(freeze_list[1])[:19]
        if freeze_list[4]:
            freeze_list[4] = str(freeze_list[4])[:19]
        mod_user = [
            [
                ['data_source', u'数据来源'],
                ['uid', u'Uid'],
                ['new_uid', u'长UID'],
                ['pf', u'PF'],
                ['user_ip', u'UserIP'],
                ['phone_id', u'PhoneId'],
                ['add_time', u'安装时间'],
                ['login_time', u'最后登录时间'],
                ['is_online', u'在线状态'],
            ],
            [
                ['uname', u'Uname'],
                ['building_lv', u'官邸等级'],
                ['country', u'国家'],
                ['office', u'爵位等级'],
                ['official', u'官职'],
                ['hero_num', u'英雄数量'],
                ['power', u'最强战力'],
                ['best_hero_power', u'单将最高战力'],
            ],
            [
                ['gold', u'钱'],
                ['food', u'粮'],
                ['wood', u'木'],
                ['iron', u'铁'],
                ['merit', u'功勋'],
                ['coin', u'Coin'],
                ['kill_num', u'击杀'],
                ['build_count', u'建设'],
            ],
            [

                ['pay_money', u'实际充值'],
                ['admin_pay', u'虚拟充值'],
                ['sale_money', u'抵扣金额'],
                ['member', u'永久卡'],
                ['ucoin', u'内部货币'],
            ],
            [

                ['power_hero_list', u'最强英雄'],
            ],
        ]

        """
        <td><font color="red">实际充值</font></td>
        <td><font color="red">虚拟充值</font></td>
        """
        admin_pay_list = []
        for item in app_user['records']['pay_ids'][::-1]:
            if str(item).find('|') == -1:
                continue
            if str(item).startswith('pay'):
                pass
            pl = item.split('|')
            pid = pl[0]
            tt = pl[1]
            if len(pl) >= 3:
                admin_user = pl[2]
            else:
                admin_user = 'None'
            if str(item).startswith('pay'):
                pay_id = pid
            elif str(item).startswith('gd'):
                try:
                    pay_id = game_config.goods[pid]['pay_id']
                except:
                    continue
            else:
                continue
            if pay_id not in pay_config:
                continue
            admin_pay_list.append('|'.join([pid,str(pay_config[pay_id][0]),tt,admin_user]))
        admin_pay_list = '\n'.join(admin_pay_list)





        for x in mod_user:
            for item in x:
                if item[0] == 'user_ip':
                    item.append(user_zone.user_ip or '')
                elif item[0] == 'uid':
                    item.append(user_zone.uid)
                elif item[0] == 'new_uid':
                    item.append(new_uid)
                elif item[0] == 'phone_id':
                    item.append(user_zone.phone_id or '')
                elif item[0] == 'member':
                    item.append(user_zone.member or '')
                elif item[0] == 'login_time':
                    item.append(str(app_user['online_log']['login_time'])[:19])
                elif item[0] == 'add_time':
                    item.append(str(app_user.get('add_time', ''))[:19])
                elif item[0] == 'building_lv':
                    item.append(app_user['home']['building001']['lv'])
                elif item[0] == 'hero_num':
                    item.append(len(app_user.get('hero')))
                elif item[0] == 'kill_num':
                    item.append(app_user['total_records']['kill_num'])
                elif item[0] == 'build_count':
                    item.append(app_user['total_records']['build_count'])
                elif item[0] == 'country':
                    c_dict = {0:'魏',1:'蜀',2:'吴'}
                    user_country = app_user.get('country')
                    if user_country < 0:
                        item.append('未选国家')
                    else:
                        item.append(c_dict[user_country])
                elif item[0] == 'official':
                    if is_db_data:
                        item.append(-100)
                    else:
                        item.append(app_user['official'])
                        del app_user['official']
                elif item[0] == 'pay_money':
                    if is_db_data:
                        item.append(0)
                    else:
                        item.append(app_user['user_pay_money'])
                        del app_user['user_pay_money']
                elif item[0] == 'admin_pay':
                    if is_db_data:
                        item.append(0)
                    else:
                        item.append(app_user['user_admin_pay'])
                        del app_user['user_admin_pay']
                elif item[0] == 'sale_money':
                    if is_db_data:
                        item.append(0)
                    else:
                        item.append(app_user['user_sale_money'])
                        del app_user['user_sale_money']
                elif item[0] == 'admin_pay':
                    item.append(admin_pay)
                elif item[0] == 'power_hero_list':
                    hero = []
                    if is_db_data:
                        hero_list = []
                        for hid,h in sorted(app_user['hero'].items(),key=lambda x:x[1]['power'],reverse=True)[:20]:
                            hero_list.append([hid,h['power'],game_config.return_msg[game_config.hero[hid]['name']], h.get('awaken', 0)])
                    else:
                        hero_list = app_user['power_hero_list']
                        del app_user['power_hero_list']
                    for h in hero_list:
                        if h[3]:
                            h[2] = u'神·' + h[2]
                        hero.append(h)
                    item.append(hero)
                elif item[0] == 'is_online':
                    if is_online:
                        item.extend([u'在线%s' % online_t, 'green'])
                    else:
                        item.extend([u'离线%s' % online_t, 'red'])
                elif item[0] == 'data_source':
                    if is_db_data:
                        item.extend([u'数据库', 'red'])
                    else:
                        item.extend([u'游戏', 'green'])
                elif item[0] == 'ucoin':
                    item.append(user_zone.ucoin)
                else:
                    item.append(app_user.get(item[0]))

    freeze_msgs = game_config.system_simple['freeze_msgs']
    admin_log = AdminLog.query({'func_name': 'admin_save_user'},limit=100,order_by='-subtime')
    interim_pwd = cache.get(settings.CACHE_PRE+'interim_pwd'+str(uid), '')

    duplicate_level_list = []
    for index, level in enumerate(game_config.duplicate['level']):
        item = {'id': index, 'name': game_config.return_msg[level[5]]}
        item['selected'] = True if index == 0 else False
        duplicate_level_list.append(item)
    return render_to_response('admin/app_user/mod_app_user.html', {
        'old_zone_list': old_zone_list,
        'merge_zone_list': merge_zone_list,
        'merge_zone': merge_zone,
        'interim_pwd': interim_pwd,
        'admin_log': admin_log,
        'user_zone':user_zone,
        'uid':uid,
        'new_uid': new_uid,
        'uname': uname,
        'mod_user': mod_user,
        'admin_user': request.session['admin_user']['username'],
        'app_user': json.dumps(app_user,sort_keys=True,indent=4,default=Serializer.json_default),
        'WHERE': settings.WHERE,
        'zone_list': zone_list,
        'zone': zone,
        'pay_config': pay_list,
        'admin_pay_list': admin_pay_list,
        'freeze_msgs': freeze_msgs,
        'freeze_list': freeze_list,
        'is_online': is_online,
        'online_t': online_t,
        'duplicate_level_list': duplicate_level_list,
        'duplicate_freeze': duplicate_freeze,
        'is_db_data': is_db_data,
        'api_black': api_black,
        },
        RequestContext(request))

@login_permission_required('mod_app_user')
def cancel_member(request):
    """注销永久卡"""
    uid = request.POST['uid']
    user_zone = UserZone.get(uid)
    if not user_zone:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'用户不存在'}))
    user_zone.member = 0
    user_zone.save()
    for zone in user_zone.zone_login.keys():
        UserZone.call_server_api(zone, 'cancel_member', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('view_app_user')
def admin_join_duplicate(request):
    """跨服战报名"""
    level = request.POST['level']
    uid = request.POST['uid']
    zone = request.POST['zone']
    join_data = UserZone.call_server_api(zone, 'admin_join_duplicate', {'uid': uid, 'level': int(level)})
    if not join_data:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'报名失败'}))


    join_data = pickle.loads(join_data)
    uid = str(join_data['uid'])
    open_date = join_data['open_date']
    udid = '%s|%s' % (int(uid)%settings.UIDADD, open_date)
    user_duplicate = UserDuplicate.get(udid)
    if not user_duplicate:
        user_duplicate = UserDuplicate(udid=udid)
    else:
        if user_duplicate.uid != uid:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'报名失败'}))
    user_duplicate.uid = uid
    user_duplicate.open_date = open_date
    user_duplicate.group_id = join_data['group_id']
    user_duplicate.uname = join_data['uname']
    user_duplicate.pf = join_data['pf']
    user_duplicate.head = join_data['head']
    user_duplicate.zone = join_data['zone']
    user_duplicate.level = join_data['level']
    user_duplicate.join_time= datetime.datetime.now()
    user_duplicate.hero_data = join_data['hero_data']
    user_duplicate.troop_data = join_data['troop_data']
    user_duplicate.prestige = join_data['prestige']
    user_duplicate.pay_money = join_data['pay_money']
    user_duplicate.admin_pay = join_data['admin_pay']
    user_duplicate.power = join_data['power']
    user_duplicate.save()


    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('mod_app_user',ajax=True)
def mod_user_tel(request):
    try:
        uid = int(request.POST.get('uid'))
        tel = request.POST.get('tel')
        user_zone_list = list(UserZone.query({'tel':tel}))
        if user_zone_list:
            return HttpResponse(json.dumps({'state':'error', 'msg': '该手机已绑定'}))
        user_zone = UserZone.get(uid)
        user_zone.tel = tel
        user_zone.save()



    except Exception, e:
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('user_interim_pwd',ajax=True)
def user_interim_pwd(request):
    try:
        uid = int(request.POST.get('uid'))
        pwd = str(random.randint(100000000,1000000000))
        cache.set(settings.CACHE_PRE+'interim_pwd'+str(uid), pwd, 10*60)

    except Exception, e:
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success', 'pwd': pwd}))

@login_permission_required('mod_app_user',ajax=True)
def save_user(request):
    try:
        uid = int(request.POST.get('uid'))
        zone = request.POST.get('zone')
        json_str = request.POST.get('app_user')
        user_dict = json.loads(json_str, object_hook=Model.json_object_hook)
        if settings.WHERE == 'local':
            user_dict['records']['pay_ids'] = []

        UserZone.call_server_api(zone, 'sync_user', {'uid': uid, 'data': user_dict})
        content = '%s|%s' % (uid,zone)
        admin_user = request.session['admin_user']['username']
        AdminLog.add_adminlog(admin_user,'admin_save_user',content)


    except Exception, e:
        utils.print_err()
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('admin_pay',ajax=True)
def admin_pay(request):
    try:
        session_user = request.session['admin_user']
        uid = int(request.POST.get('uid'))
        if 'admin_waiter_pay' in session_user['permissions'] and uid > 10000:
            return HttpResponse(json.dumps({'state':'error', 'msg': '仅限waiter充值'}))
        admin_user = session_user['username']
        zone = request.POST.get('zone')
        pid = request.POST.get('pid')
        v = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        pay_id = '%s|%s|%s' % (pid,v,admin_user)
        if settings.WHERE == 'local11':
            ts = int(time.time())
            order_id = '%s|%s|local' % (uid,ts)
            new_uid = UserZone.get_new_uid(uid, zone)
            add_user_pay(order_id,new_uid,zone,pid,'success','no_check','local','local|%s' % ts,'local','local')
        else:
            pay_result = UserZone.call_server_api(zone, 'user_pay', {'uid': uid, 'pid': pid, 'pay_id': pay_id})
            if pay_result['succ'] != 1:
                return HttpResponse(json.dumps({'state':'error', 'msg': '充值失败'}))
        goods_config = game_config.goods.get(pid,None)
        if goods_config:
            pay_money = game_config.pay_config[goods_config['pay_id']][0]
        else:
            pay_money = game_config.pay_config[pid][0]

        app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})
        ## 添加充值记录
        AdminPayRecord.add_pay(admin_user, uid, pay_money, zone, app_user['uname'])

        admin_pay_list = []
        for item in app_user['records']['pay_ids'][::-1]:
            if str(item).find('|') == -1:
                continue
            pl = item.split('|')
            pid = pl[0]
            tt = pl[1]
            if len(pl) >= 3:
                item_admin_user = pl[2]
            else:
                item_admin_user = 'None'
            if str(item).startswith('pay'):
                pay_id = pid
            elif str(item).startswith('gd'):
                pay_id = game_config.goods[pid]['pay_id']
            else:
                continue
            admin_pay_list.append('|'.join([pid,str(game_config.pay_config[pay_id][0]),tt,item_admin_user]))
        admin_pay_list = '\n'.join(admin_pay_list)


        content = '%s_%s' % (pay_id,zone)
        AdminLog.add_adminlog(admin_user,'admin_pay',content)



    except Exception, e:
        utils.print_err()
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success','pay_ids': admin_pay_list}))


@login_permission_required('weixin_admin_pay',ajax=True)
def weixin_admin_pay(request):
    pay_config = game_config.pay_config
    try:
        uid = request.POST.get('uid')
        zone = request.POST.get('zone')
        uid = UserZone.get_new_uid(uid, zone)
        pay_coin = select([func.sum(ASP.c.pay_coin).label('cc')],and_(ASP.c.uid == uid)).execute().fetchone()['cc']
        if not pay_coin:
            pay_coin = 0
        pay_money = 0
        pid_list = []
        for k,v in pay_config.items():
            pid_num = int(request.POST.get(k,0))
            if pid_num <= 0:
                continue
            pid_list.append('%s_%s' % (k,pid_num))
            pay_money += v[0]*pid_num
            pay_coin += v[1]*pid_num
        if not pay_money:
            return HttpResponse(json.dumps({'state':'error', 'msg': u'请选择充值金额'}))
        sale_num = 1.0
        pids = '|'.join(pid_list)
        for item in game_config.system_simple['pay_sale']:
            if (pay_coin/10) >= item[0]:
                sale_num = item[1]
                break
        sale_num = 1.0
        pay_money = pay_money * sale_num
        order_id = '%s|%s|%s' % (uid,zone,int(time.time()))
        #notify_url = '%s/weixin_sale_callback/' % settings.BASE_URL
        #pay_api = WeiXinPay(notify_url,'wx_admin')
        #pay_url = pay_api.get_pay_img_url(order_id, pay_money, pids)
        order_dict = {
                'order_id': order_id,
                'pids': pids,
                'pay_money': pay_money,
                }
        order_key = hashlib.md5(order_id).hexdigest()
        cache.set(settings.CACHE_PRE+order_key, order_dict, 60*60*24*30)
        pay_url = '%s/wxjsp/?ok=%s' % (settings.BASE_URL,order_key)
        pay_url = base64.b64encode(pay_url)

    except Exception, e:
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success','pay_url': pay_url, 'sale_num': sale_num, 'pay_money': pay_money}))

@login_permission_required('weixin_admin_pay')
def pay_url_img(request):
    pay_url = request.GET.get('pay_url')
    pay_url = base64.b64decode(pay_url)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1
    )
    qr.add_data(pay_url)  # 二维码所含信息
    img = qr.make_image()  # 生成二维码图片
    byte_io = BytesIO()
    img.save(byte_io, 'PNG')  # 存入字节流
    byte_io.seek(0)
    #return http.send_file(byte_io, mimetype='image/png') #把字节流返回给客户端，解析得到二维码
    return HttpResponse(byte_io)

@login_permission_required('init_pk_yard',ajax=True)
def change_world(request):
    try:
        zone = request.POST.get('zone')
        change_key = request.POST.get('change_key')
        params = {'change_key': change_key}
        if change_key == 'change_world_lv':
            params['finish_gtask_max'] = request.POST.get('finish_gtask_max')
            params['world_lv'] = request.POST.get('world_lv')
            params['pve_lv'] = request.POST.get('pve_lv')
        elif change_key == 'change_country_task':
            params['country_task'] = request.POST.get('country_task')
            params['country_id'] = request.POST.get('country_id')
        elif change_key == 'change_xiangyang_country':
            params['country_id'] = request.POST.get('country_id')
        elif change_key == 'clean_land_lost':
            params['country_id'] = request.POST.get('country_id')
        elif change_key == 'change_country_king':
            params['king_uid'] = request.POST.get('king_uid')
            params['country_id'] = request.POST.get('country_id')
        elif change_key == 'init_country':
            params['country_id'] = request.POST.get('country_id')
        elif change_key == 'init_city':
            params['city_id'] = request.POST.get('city_id')
            params['init_type'] = request.POST.get('init_type')
        elif change_key == 'init_pk_yard':
            pass
        elif change_key == 'honour_done':
            pass
        elif change_key == 'change_country_advise_score': ## 修改国家积分
            params['country_id'] = int(request.POST.get('country_id'))
            rq_score = float(request.POST.get('renqi_score'))
            hq_score = float(request.POST.get('haoqi_score'))
            params['advise_score'] = [rq_score, hq_score]
        elif change_key == 'refresh_weather':
            pass
        elif change_key == 'clean_ask':
            pass
        elif change_key == 'clean_elect':
            pass
        elif change_key == 'clean_chat_cache':
            pass
        elif change_key == 'clean_pk_yard_new':
            pass
        elif change_key == 'clean_new_milepost':
            pass
        elif change_key == 'reset_exorcism':
            params['bindex'] = request.POST.get('bindex')
        elif change_key == 'change_use_function':
            params['change_function'] = request.POST['change_function']
        elif change_key ==  'report_country_data':
            params['country_id'] = request.POST.get('country_id')
        else:
            return HttpResponse(json.dumps({'state':'error', 'msg': 'change_key error'}))
        world = UserZone.call_server_api(zone, 'change_world', params)
        if world.get('msg'):
            return HttpResponse(json.dumps({'state': 'error', 'msg': world['msg']}))
        world_lv = world['world_lv']
        pve_lv = world['pve_lv']
        world_json = json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default)
        change_world_log = cache.get(settings.CACHE_PRE+'change_world_log'+str(zone),[])
        log_dict = {
                'time': str(datetime.datetime.now())[:19],
                'params': params,
                'admin_user': request.session['admin_user']['username'],
                }
        change_world_log.insert(0,log_dict)
        if len(change_world_log) > 10:
            change_world_log = change_world_log[:10]
        cache.set(settings.CACHE_PRE+'change_world_log'+str(zone), change_world_log, 60*60*24*30)
        log_str_list = get_log_str_list(change_world_log)

        return HttpResponse(json.dumps({'state':'success','world_json': world_json,'pve_lv':pve_lv,'world_lv': world_lv, 'log_str_list': log_str_list.content}))

    except Exception, e:
        utils.print_err()
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))

@login_permission_required('init_pk_yard',ajax=True)
def init_pk_yard(request):
    try:
        zone = request.POST.get('zone')
        params = {'change_key': 'init_pk_yard'}
        world = UserZone.call_server_api(zone, 'change_world', params)
        world_lv = world['world_lv']
        pve_lv = world['pve_lv']
        world_json = json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default)
        change_world_log = cache.get(settings.CACHE_PRE+'change_world_log'+str(zone),[])
        log_dict = {
                'time': str(datetime.datetime.now())[:19],
                'params': params,
                'admin_user': request.session['admin_user']['username'],
                }
        change_world_log.insert(0,log_dict)
        if len(change_world_log) > 10:
            change_world_log = change_world_log[:10]
        cache.set(settings.CACHE_PRE+'change_world_log'+str(zone), change_world_log, 60*60*24*30)
        log_str_list = get_log_str_list(change_world_log)

        return HttpResponse(json.dumps({'state':'success','world_json': world_json,'pve_lv': pve_lv,'world_lv': world_lv, 'log_str_list': log_str_list.content}))

    except Exception, e:
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))


def get_log_str_list(change_world_log):
    for item in change_world_log:
        if item['params']['change_key'] == 'change_world_lv':
            item['change_key'] = u'修改世界等级'
        elif item['params']['change_key'] == 'init_country':
            item['change_key'] = u'重置国家'
        elif item['params']['change_key'] == 'change_country_task':
            item['change_key'] = u'修改国家任务'
        elif item['params']['change_key'] == 'change_country_king':
            item['change_key'] = u'修改国王'
        elif item['params']['change_key'] == 'change_xiangyang_country':
            item['change_key'] = u'修改襄阳'
        elif item['params']['change_key'] == 'clean_land_lost':
            item['change_key'] = u'清空失地数据'
        elif item['params']['change_key'] == 'init_pk_yard':
            item['change_key'] = u'初始化比武大会'
        elif item['params']['change_key'] == 'clean_ask':
            item['change_key'] = u'清理答题数据'
        elif item['params']['change_key'] == 'clean_elect':
            item['change_key'] = u'清理国王选举数据'
        elif item['params']['change_key'] == 'clean_pk_yard_new':
            item['change_key'] = u'清理新比武大会'
        elif item['params']['change_key'] == 'clean_chat_cache':
            item['change_key'] = u'清理世界聊天'
        elif item['params']['change_key'] == 'clean_new_milepost':
            item['change_key'] = u'清理新天下大势'
        elif item['params']['change_key'] == 'honour_done':
            item['change_key'] = u'赛季结算'
        elif item['params']['change_key'] == 'change_country_advise_score':
            item['change_key'] = u'修改国家积分'
        elif item['params']['change_key'] == 'refresh_weather':
            item['change_key'] = u'刷新天气'
        elif item['params']['change_key'] == 'simulate_merge':
            item['change_key'] = u'模拟合服结算'
        elif item['params']['change_key'] == 'reset_exorcism':
            item['change_key'] = u'重置伏魔战场'
        elif item['params']['change_key'] == 'change_use_function':
            item['change_key'] = u'更改功能状态'
        elif item['params']['change_key'] == 'init_city':
            if item['params']['init_type'] == 'init_city':
                item['change_key'] = u'重置城市'
            elif item['params']['init_type'] == 'init_troop':
                item['change_key'] = u'清理战斗和部队'
            elif item['params']['init_type'] == 'full_des_army':
                item['change_key'] = u'补满城防军'
            elif item['params']['init_type'] == 'zero_des_army':
                item['change_key'] = u'清空城防军'
            elif item['params']['init_type'] == 'one_des_army':
                item['change_key'] = u'城防军置为1'
            elif item['params']['init_type'] == 'thief_one':
                item['change_key'] = u'刷出黄巾1军'
            elif item['params']['init_type'] == 'thief_two':
                item['change_key'] = u'刷出黄巾2军'
            del item['params']['init_type']
        del item['params']['change_key']
        item['params'] = json.dumps(item['params'])
    return render_to_response('admin/app_user/change_world_log.html', {
        'change_world_log': change_world_log,
        })
            

@login_permission_required('cleanup_troops', ajax=True)
def cleanup_troops(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    res = UserZone.call_server_api(zone, 'cleanup_user_troop', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('cleanup_troops', ajax=True)
def cleanup_homeland_building(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    res = UserZone.call_server_api(zone, 'cleanup_homeland_building', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('cleanup_troops', ajax=True)
def cleanup_ng_task(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    res = UserZone.call_server_api(zone, 'cleanup_ng_task', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('mod_app_user', ajax=True)
def refresh_tomb(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    res = UserZone.call_server_api(zone, 'refresh_tomb', {'uid': uid})
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('mod_app_user', ajax=True)
def cleanup_ucoin(request):
    uid = request.REQUEST.get('uid')
    user_zone = UserZone.get(uid)
    user_zone.ucoin = 0
    user_zone.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('simulate_merge', ajax=True)
def simulate_merge(request):
    uid = request.REQUEST.get('uid')
    zone = request.REQUEST.get('zone')
    UserZone.call_server_api(zone, 'simulate_merge', {'uid': uid}, timeout=20)

    change_world_log = cache.get(settings.CACHE_PRE + 'change_world_log' + str(zone), [])
    log_dict = {
        'time': str(datetime.datetime.now())[:19],
        'params': {'zone': zone, 'change_key': 'simulate_merge'},
        'admin_user': request.session['admin_user']['username'],
    }
    change_world_log.insert(0, log_dict)
    if len(change_world_log) > 10:
        change_world_log = change_world_log[:10]
    cache.set(settings.CACHE_PRE + 'change_world_log' + str(zone), change_world_log, 60 * 60 * 24 * 30)
    log_str_list = get_log_str_list(change_world_log)

    return HttpResponse(json.dumps({'state': 'success', 'log_str_list': log_str_list.content}))

@login_permission_required('view_duplicate')
def view_duplicate(request):
    """
        duplicate_state: 跨服战状态  -1: 功能关闭， 0：冷却期， 1：报名中， 2：截止报名， 3：可如战场， 4：对战中， 5：截止
    :param request:
    :return:
    """
    from game_lib.db.database import UserDuplicate_table
    now = datetime.datetime.now()
    search_group_list = request.REQUEST.getlist('search_group_list')
    search_open_date = request.REQUEST.get('search_open_date')
    duplicate_group_config = game_config.system_simple['duplicate_groups']
    search_uid = request.REQUEST.get('uid', '')
    duplicate_groups = []
    duplicate_group_name_maps = {}
    for group in sorted(duplicate_group_config, key=lambda x:x['index']):
        duplicate_group_name_maps[group['id']] = group['name']
        _group = [group['id'], group['name']]
        if not search_open_date:
            _group.append('checked')
        else:
            if group['id'] in search_group_list:
                _group.append('checked')
            else:
                _group.append('unchecked')
        duplicate_groups.append(_group)
    open_dates = []
    ## 最近一期开启时间
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    dup_data = select([UserDuplicate_table.c.open_date], and_(UserDuplicate_table.c.open_date != c_open_date))\
        .group_by(UserDuplicate_table.c.open_date).order_by(UserDuplicate_table.c.open_date.desc()).execute().fetchall()
    for _item in dup_data:
        if search_open_date and int(search_open_date) == _item.open_date:
            open_dates.append([_item.open_date, 'checked'])
        else:
            open_dates.append([_item.open_date, 'unchecked'])

    if not search_open_date or c_open_date == search_open_date:
        open_dates.insert(0, [c_open_date, 'checked'])
    else:
        open_dates.insert(0, [c_open_date, 'unchecked'])
    duplicate_config = game_config.duplicate
    duplicate_data = {}
    all_server_list = []
    level_data = []
    open_server = {}
    server_count = {}
    ## 初始化段位数据
    for index, level in enumerate(game_config.duplicate['level']):
        level_data.append({
            'level': [index, game_config.return_msg[level[5]][:2]],
            'join_count': 0,
            'group_count': 0,
            'server_list': []
        })
    if search_open_date:
        if search_open_date == c_open_date:
            ## 当前期战场数据
            _search_open_date = datetime.datetime.strptime(search_open_date, '%Y%m%d').date()
            ## 报名结束时间
            join_end_time = datetime.datetime(*(_search_open_date.timetuple()[:3]+tuple(duplicate_config['time'][0])))
            ## 报名开始时间
            join_start_time = join_end_time - datetime.timedelta(minutes=duplicate_config['first_time'])
            ## 进入战场时间
            enter_time = join_end_time + datetime.timedelta(minutes=duplicate_config['time'][1])
            ## 战斗开始时间
            fight_start_time = enter_time + datetime.timedelta(minutes=duplicate_config['time'][2])
            ## 战斗结束时间
            fight_end_time = fight_start_time + datetime.timedelta(minutes=duplicate_config['time'][3])
            ## 结算截止时间
            close_time = fight_end_time + datetime.timedelta(minutes=duplicate_config['time'][4])
            is_today = False
            if now.date() == _search_open_date:
                is_today = True
            if duplicate_config['switch'] == 0:
                duplicate_state = u'功能关闭'
            else:
                if not is_today:
                    if join_end_time > now >= join_start_time:
                        duplicate_state = u'报名中'
                    elif now > close_time:
                        duplicate_state = u'截止指令'
                    else:
                        duplicate_state = u'冷却期'
                else:
                    if now < join_end_time:
                        duplicate_state = u'报名中'
                    elif join_end_time <= now <= enter_time:
                        duplicate_state = u'截止报名'
                    elif enter_time <= now < fight_start_time:
                        duplicate_state = u'可入战场'
                    elif fight_start_time <= now < fight_end_time:
                        duplicate_state = u'对战中'
                    else:
                        duplicate_state = u'截止指令'
            duplicate_data['duplicate_time'] = {
                'open_date': str(_search_open_date),
                'join_end_time': str(join_end_time.time()),
                'enter_time': str(enter_time.time()),
                'fight_start_time': str(fight_start_time.time()),
                'fight_end_time': str(fight_end_time.time()),
                'close_time': str(close_time.time())
            }
            duplicate_data['duplicate_state'] = duplicate_state

            sign_up_data = select([UserDuplicate_table.c.level, UserDuplicate_table.c.group_id, UserDuplicate_table.c.open_date, func.count(UserDuplicate_table.c.uid).label('join_count')],
                                  and_(UserDuplicate_table.c.open_date == search_open_date))\
                .group_by(UserDuplicate_table.c.level, UserDuplicate_table.c.group_id).order_by(UserDuplicate_table.c.level).execute().fetchall()
            def sort_by_group_index(x):
                for group in duplicate_group_config:
                    if group['id'] != x.group_id:
                        continue
                    return x.level, group['index']
            sign_up_data.sort(key=sort_by_group_index)
            ## 计算段位数据
            port = game_config.system_simple['server_port'][0]
            for item in sign_up_data:
                court = game_config.duplicate['level'][item.level][7][1]
                least_number = game_config.duplicate['level'][item.level][7][0]
                _item = level_data[item.level]
                if item.group_id in search_group_list:
                    _item['join_count'] += item.join_count
                if item.join_count < least_number:
                    group_count = 0
                else:
                    group_count = int(math.ceil(item.join_count*1.0/court))
                group_name = duplicate_group_name_maps[item.group_id]
                level_name = game_config.return_msg[game_config.duplicate['level'][item.level][5]][:2]
                for i in xrange(group_count):
                    server = {
                        'name': '%s%s%s' % (group_name, level_name, port - game_config.system_simple['server_port'][0]),
                        'port': port,
                        'group_id': item.group_id
                    }
                    _item['server_list'].append(server)
                    port += 1
            for item in level_data:
                server_list = []
                for server in item['server_list']:
                    if server['group_id'] not in search_group_list:
                        continue
                    server_list.append(server)
                item['group_count'] = len(server_list)
                item['server_list'] = server_list
            duplicate_data['sign_up_data'] = level_data
        else:
            ### 历史数据
            duplicate_data['duplicate_state'] = u'战场结束'
            sign_up_data = select([UserDuplicate_table.c.level, UserDuplicate_table.c.open_date, func.count(UserDuplicate_table.c.uid).label('join_count')],
                                  and_(UserDuplicate_table.c.open_date == search_open_date, UserDuplicate_table.c.group_id.in_(search_group_list)))\
                .group_by(UserDuplicate_table.c.level).order_by(UserDuplicate_table.c.level).execute().fetchall()
            for item in sign_up_data:
                level_data[item.level]['join_count'] = item.join_count
            data = dl.select(and_(dl.c.open_date == search_open_date, dl.c.group_id.in_(search_group_list))).execute().fetchall()
            for item in data:
                if 'duplicate_time' not in duplicate_data:
                    world_data = pickle.loads(zlib.decompress(str(item.world)))
                    duplicate_time = world_data['duplicate_time']
                    duplicate_data['duplicate_time'] = {
                        'open_date': str(duplicate_time[0].date()),
                        'join_end_time': str(duplicate_time[0].time()),
                        'enter_time': str(duplicate_time[1].time()),
                        'fight_start_time': str(duplicate_time[2].time()),
                        'fight_end_time': str(duplicate_time[3].time()),
                        'close_time': str(duplicate_time[4].time())
                    }
                level_data[item.level]['group_count'] += 1
                group_name = duplicate_group_name_maps[item.group_id]
                level_name = game_config.return_msg[game_config.duplicate['level'][item.level][5]][:2]
                level_data[item.level]['server_list'].append({
                    'name': '%s%s%s' % (group_name, level_name, item.dnum),
                    'port': game_config.system_simple['server_port'][0] + item.dnum,
                    'group_id': item.group_id
                })
            duplicate_data['sign_up_data'] = level_data
        open_port = None
        if search_uid:
            ud = UserDuplicate.get('%s|%s' % (search_uid, search_open_date))
            if ud and ud.dnum != -1:
                open_port = game_config.system_simple['server_port'][0] + ud.dnum
        for item in duplicate_data['sign_up_data']:
            item['server_list'] = sorted(item['server_list'], key=lambda x:x['port'])
            for server in item['server_list']:
                all_server_list.append(server['port'])
                if open_port != server['port']:
                    continue
                open_server = server
        total_server_count = sum([item[0] for item in game_config.system_simple['server_port'][1]])
        open_server_count = sum([item['group_count'] for item in level_data])
        server_count = {
            'total': total_server_count,
            'open': open_server_count
        }
        if open_server_count > total_server_count:
            server_count['color'] = 'red'
    join_user_count = sum([item['join_count'] for item in level_data])
    return render_to_response('admin/app_user/view_duplicate.html', {
        'duplicate_groups': duplicate_groups,
        'open_dates': open_dates,
        'duplicate_data': duplicate_data,
        'search_open_date': search_open_date,
        'search_group_list': ','.join(search_group_list),
        'search_uid': search_uid,
        'open_server': json.dumps(open_server),
        'server_list': json.dumps(all_server_list),
        'server_count': server_count,
        'join_user_count': join_user_count
    },
    RequestContext(request))

def _get_duplicate_status_color(**kwargs):
    join_start_time = kwargs['join_start_time']
    join_end_time = kwargs['join_end_time']
    enter_time = kwargs['enter_time']
    fight_start_time = kwargs['fight_start_time']
    fight_end_time = kwargs['fight_end_time']
    close_time = kwargs['close_time']
    world = kwargs.get('world')
    open_date = kwargs['open_date']
    server_port = kwargs['server_port']
    c_dict = {40: u'楚', 41: u'汉'}
    cache_key = '%s_%s_duplicate_status' % (settings.CACHE_PRE, open_date)
    duplicate_status = cache.get(cache_key, {})
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    now = datetime.datetime.now()
    data = {
        'status': '',
        'color': '',
        'background_color': ''
    }
    if now < join_start_time:
        data['background_color'] = '#FFF0F5'   #未开始报名
        data['status'] = u'未开始报名'
    if join_start_time <= now < join_end_time:
        data['background_color'] = '#FFB6C1'   #报名时间
        data['status'] = u'正在报名'
    if join_end_time <= now < enter_time:
        data['background_color'] = '#CC0033'   #初始化战场
        data['status'] = u'等待初始化'
    if enter_time <= now < fight_start_time:
        data['background_color'] = '#FFFACD'   #可入战场
        data['status'] = u'可以入场'
    if fight_start_time <= now < fight_end_time:
        data['background_color'] = '#FFFF00'  # 开打
        data['status'] = u'正在对战'
    if now >= fight_end_time:
        data['background_color'] = '#808000'    #截止指令
        data['status'] = u'截止指令'
        if world is None:
            if open_date == c_open_date:
                res = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_duplicate_world_data', {})
                world = res['world']
            else:
                dnum = int(server_port) - game_config.system_simple['server_port'][0]
                res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
                world = pickle.loads(zlib.decompress(str(res.world)))
        if world['win_type'] is not None:
            if world['win_country'] == -1:
                data['background_color'] = '#77cc77'  #平局
                data['status'] = u'平局'
            else:
                data['background_color'] = game_config.world['COUNTRY_COLORS'][world['win_country']]
                data['status'] = u'%s胜利' % c_dict[world['win_country']]
            if world['win_type'] == 0:
                data['color'] = '#FFFF00'

            if server_port not in duplicate_status and not settings.SUBTEST:
                duplicate_status[server_port] = data
                cache.set(cache_key, duplicate_status, 60*60*24*30)
    return data

@login_permission_required('view_duplicate')
def get_duplicate_status_cache_data(request):
    open_date = request.GET.get('open_date')
    cache_key = '%s_%s_duplicate_status' % (settings.CACHE_PRE, open_date)
    if settings.SUBTEST:
        duplicate_status = {}
    else:
        duplicate_status = cache.get(cache_key, {})
    return HttpResponse(json.dumps({'duplicate_status': duplicate_status}))

@login_permission_required('view_duplicate')
def get_duplicate_server_status(request):
    search_open_date = request.GET.get('open_date')
    server_port = request.GET.get('server_port')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    now = datetime.datetime.now()
    if c_open_date == search_open_date:
        _open_date = datetime.datetime.strptime(search_open_date, '%Y%m%d').date()
        ## 报名结束时间
        join_end_time = datetime.datetime(*(_open_date.timetuple()[:3]+tuple(game_config.duplicate['time'][0])))
        ## 报名开始时间
        join_start_time = join_end_time - datetime.timedelta(minutes=game_config.duplicate['first_time'])
        ## 进入战场时间
        enter_time = join_end_time + datetime.timedelta(minutes=game_config.duplicate['time'][1])
        ## 战斗开始时间
        fight_start_time = enter_time + datetime.timedelta(minutes=game_config.duplicate['time'][2])
        ## 战斗结束时间
        fight_end_time = fight_start_time + datetime.timedelta(minutes=game_config.duplicate['time'][3])
        ## 结算截止时间
        close_time = fight_end_time + datetime.timedelta(minutes=game_config.duplicate['time'][4])
        world = None
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == search_open_date, dl.c.dnum == dnum)).execute().fetchone()
        world = pickle.loads(zlib.decompress(str(res.world)))
        join_end_time, enter_time, fight_start_time, fight_end_time, close_time = world['duplicate_time']
        join_start_time = join_end_time - datetime.timedelta(minutes=game_config.duplicate['first_time'])
    data = _get_duplicate_status_color(join_start_time=join_start_time,
                                       join_end_time=join_end_time,
                                       enter_time=enter_time,
                                       fight_start_time=fight_start_time,
                                       fight_end_time=fight_end_time,
                                       close_time=close_time,
                                       world=world,
                                       open_date=search_open_date,
                                       server_port=server_port)
    if now < enter_time:
        data['opened'] = False
    else:
        data['opened'] = True
    return HttpResponse(json.dumps(data))

def get_duplicate_group_name(group_id):
    for group in game_config.system_simple['duplicate_groups']:
        if group['id'] != group_id:
            continue
        group_name = group['name']
        break
    return group_name

@login_permission_required('view_duplicate')
def get_duplicate_join_user(request):
    open_date = request.GET.get('open_date')
    search_group_list = request.GET.get('search_group_list')
    search_group_list = search_group_list.split(',')
    level = int(request.GET.get('level'))
    order_by = request.GET.get('order_by')
    if not order_by:
        order_by = '-power'
    users = UserDuplicate.query({"open_date": open_date, "level": level, "group_id_in": search_group_list}, order_by=order_by)

    duplicate_join_users = []
    for user in users:
        old_uid, old_zone = UserZone.get_old_uid_zone(user.uid, user.zone)
        item = {
            'uid': old_uid,
            'zone': old_zone,
            'open_date': user.open_date,
            'uname': user.uname,
            'group': get_duplicate_group_name(user.group_id),
            'pay_money': user.pay_money,
            'admin_pay': user.admin_pay,
            'power': user.power,
            'prestige': user.prestige,
            'heros': []
        }
        for hid, hero_data in sorted(user.hero_data.iteritems(), key=lambda x:x[1]['server_power'], reverse=True):
            hero_name = game_config.return_msg[game_config.hero[hid]['name']]
            if hero_data.get('awaken', 0):
                hero_name = u'神·' + hero_name
            item['heros'].append([hid, hero_name, hero_data['server_power']])
        duplicate_join_users.append(item)

    duplicate_join_user = loader.render_to_string('admin/app_user/duplicate_join_user.html',
                                                  {
                                                      'duplicate_join_users': duplicate_join_users,
                                                      'open_date': open_date,
                                                      'level': level,
                                                      'level_name': game_config.return_msg[game_config.duplicate['level'][level][5]]
                                                  },
                                                  RequestContext(request))
    return HttpResponse(json.dumps({'duplicate_join_user': duplicate_join_user}))

def get_duplicate_server_addr(server_port):
    base_port = game_config.system_simple['server_port'][0]
    dnum = int(server_port) - base_port
    bnum = 0
    for item in game_config.system_simple['server_port'][1]:
        bnum += item[0]
        if dnum >= bnum:
            continue
        server_host = item[1]
        break
    return '%s:%s' % (server_host, server_port)

@login_permission_required('view_duplicate')
def get_duplicate_server_info(request):
    open_date = request.GET.get('open_date')
    server_port = request.GET.get('server_port')
    server_name = request.GET.get('server_name')
    order_by = request.GET.get('order_by', '-power')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        res = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_duplicate_world_data', {})
        world = res['world']
        users = res['users']
        if not world['duplicate_time']:
            return HttpResponse(json.dumps({'state': 'error', 'msg': '战场还未初始化'}))
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
        world = pickle.loads(zlib.decompress(str(res.world)))
        users = pickle.loads(zlib.decompress(str(res.user)))

    # 阵营汇总数据
    country_collect = {
        40: {
            'user_count': 0,
            'pay_money': 0,
            'admin_pay': 0,
            'power': 0,
            'd_score': 0,
            'k_score': 0,
            'cost_coin': 0,
            'move_times': 0,
            'win_count': 0,
            'fight_count': 0
        },
        41: {
            'user_count': 0,
            'pay_money': 0,
            'admin_pay': 0,
            'power': 0,
            'd_score': 0,
            'k_score': 0,
            'cost_coin': 0,
            'move_times': 0,
            'win_count': 0,
            'fight_count': 0
        }
    }
    fight_logs = []
    for fid, data in sorted(world['fight_logs'].items(), key=lambda x:x[1]['fight_time'], reverse=True):
        item = {}
        item['fid'] = fid
        item['fight_time'] = data['fight_time'].strftime('%Y-%m-%d %H:%M:%S')
        item['cid'] = data['cid']
        item['winner'] = data['winner']

        ## 攻击方数据
        attack_user = users[data['troop'][0]['uid']]
        attack_hid = data['troop'][0]['hid']
        attack_hero_data = attack_user['hero_data'][attack_hid]
        attack_hero_name = game_config.return_msg[game_config.hero[attack_hid]['name']]
        if attack_hero_data.get('awaken', 0):
            attack_hero_name = u'神·' + attack_hero_name
        attack_old_uid, attack_old_zone = UserZone.get_old_uid_zone(attack_user['uid'], attack_user['zone'])
        item['attack'] = {
            'uid': attack_user['uid'],
            'zone': attack_user['zone'],
            'old_uid': attack_old_uid,
            'old_zone': attack_old_zone,
            'uname': attack_user['uname'],
            'country': attack_user['country'],
            'hero': [attack_hid, attack_hero_name, attack_hero_data['server_power']]
        }

        ## 防守方数据
        defend_user = users[data['troop'][1]['uid']]
        defend_hid = data['troop'][1]['hid']
        defend_hero_data = defend_user['hero_data'][defend_hid]
        defend_hero_name = game_config.return_msg[game_config.hero[defend_hid]['name']]
        if defend_hero_data.get('awaken', 0):
            defend_hero_name = u'神·' + defend_hero_name
        defend_old_uid, defend_old_zone = UserZone.get_old_uid_zone(defend_user['uid'], defend_user['zone'])
        item['defend'] = {
            'uid': defend_user['uid'],
            'zone': defend_user['zone'],
            'old_uid': defend_old_uid,
            'old_zone': defend_old_zone,
            'uname': defend_user['uname'],
            'country': defend_user['country'],
            'hero': [defend_hid, defend_hero_name, defend_hero_data['server_power']]
        }
        fight_logs.append(item)
    user_list = []
    for uid, user in users.items():
        user['heros'] = []
        for hid, hero_data in sorted(user['hero_data'].iteritems(), key=lambda x: x[1]['server_power'],
                                     reverse=True):
            hero_name = game_config.return_msg[game_config.hero[hid]['name']]
            if hero_data.get('awaken', 0):
                hero_name = u'神·' + hero_name
            user['heros'].append([hid, hero_name, hero_data['server_power']])
        fight_log_list = []
        for fid in user['fight_log_ids']:
            fight_log_list.append(world['fight_logs'][fid])
        user['fight_log_list'] = fight_log_list
        win_count = 0
        for l in user['fight_log_list']:
            if l['troop'][l['winner']]['uid'] != user['uid']:
                continue
            win_count += 1
        if win_count == 0:
            win_rate = 0
        else:
            win_rate = int((win_count * 1.0 / len(fight_log_list)) * 100)
        user['win_info'] = '{win_count}(胜率{win_rate}%)'.format(win_count=win_count, win_rate=win_rate)
        old_uid, old_zone = UserZone.get_old_uid_zone(user['uid'], user['zone'])
        user['old_uid'] = old_uid
        user['old_zone'] = old_zone
        user['prestige_power'] = int(user['power'] * user['prestige'] * game_config.duplicate['prestige_ini'][1])
        user_list.append(user)
        for k in country_collect[user['country']].keys():
            if k == 'win_count':
                v = win_count
            elif k == 'user_count':
                v = 1
            elif k == 'fight_count':
                v = len(fight_log_list)
            else:
                v = user.get(k, 0)
            country_collect[user['country']][k] += v
    cities = world['cities']
    if order_by:
        if order_by.startswith('-'):
            reverse = True
            order_by = order_by[1:]
        else:
            reverse = False
        user_list.sort(key=lambda x:x[order_by], reverse=reverse)
    city_data = [[],[],[],[],[],[],[],[],[]]
    city_count = {}
    for x in range(9):
        for y in range(9):
            cid = str(x * 1000 + y)
            item = {'cid': cid, 'info': 0, 'bg_color': '#848484'}
            city = cities.get(cid)
            if city:
                city_count.setdefault(city['country'], 0)
                city_count[city['country']] += 1
                item['bg_color'] = game_config.world['COUNTRY_COLORS'][city['country']]
                if city['fight']:
                    item['info'] = '%s VS %s' % (len(city['fight']['team'][0]['troop']), len(city['fight']['team'][1]['troop']))
                else:
                    item['info'] = len(city['troop_ids']) + city['monster_num']
            city_data[y].append(item)
    join_end_time, enter_time, fight_start_time, fight_end_time, close_time = world['duplicate_time']
    join_start_time = join_end_time - datetime.timedelta(minutes=game_config.duplicate['first_time'])
    duplicate_time = {
        'open_date': str(join_end_time.date()),
        'join_end_time': str(join_end_time.time()),
        'enter_time': str(enter_time.time()),
        'fight_start_time': str(fight_start_time.time()),
        'fight_end_time': str(fight_end_time.time()),
        'close_time': str(close_time.time())
    }
    duplicate_status = _get_duplicate_status_color(join_start_time=join_start_time,
                                                   join_end_time=join_end_time,
                                                   enter_time=enter_time,
                                                   fight_start_time=fight_start_time,
                                                   fight_end_time=fight_end_time,
                                                   close_time=close_time,
                                                   world=world,
                                                   open_date=open_date,
                                                   server_port=server_port)
    c_dict = {40: u'楚', 41: u'汉'}
    country_collect_list = []
    for k, v in country_collect.items():
        v['country'] = c_dict[k]
        if v['fight_count'] == 0:
            win_rate = 0
        else:
            win_rate = int((v['win_count'] * 1.0 / v['fight_count']) * 100)
        v['win_info'] = '{win_count}(胜率{win_rate}%)'.format(win_count=v['win_count'], win_rate=win_rate)
        country_collect_list.append(v)
    duplicate_server_info = loader.render_to_string('admin/app_user/duplicate_server_info.html',
                                                    {
                                                        'open_date': open_date,
                                                        'city_data': city_data,
                                                        'world': world,
                                                        'users': user_list,
                                                        'city_count': city_count,
                                                        'fight_logs': fight_logs,
                                                        'server_port': server_port,
                                                        'server_name': server_name,
                                                        'duplicate_time': duplicate_time,
                                                        'win_country': c_dict.get(world['win_country'], u'未知'),
                                                        'country_collect_list': country_collect_list,
                                                        'duplicate_status': duplicate_status
                                                    },
                                                    RequestContext(request))
    return HttpResponse(json.dumps({'state': 'success', 'duplicate_server_info': duplicate_server_info}))

@login_permission_required('view_duplicate')
def duplicate_chat(request):
    open_date = request.GET.get('open_date')
    server_port = request.GET.get('server_port')
    log_list = []
    c_dict = {40: u'楚', 41: u'汉'}
    icon_dict = {3: u'跨服战', 4: u'阵营'}
    notice_data = []
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        chat_log = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_chat_log', {})
        for item in chat_log:
            item[0] = icon_dict[item[0]]
            item[4] = c_dict[item[4]]
            item[5] = str(item[5])[:19]
            old_uid, old_zone = UserZone.get_old_uid_zone(item[1], item[2])
            item.append(old_uid)
            item.append(old_zone)
            log_list.append(item)
    return render_to_response('admin/app_user/duplicate_chat.html', {
        'log_list': log_list
        },
        RequestContext(request))


@login_permission_required('view_duplicate')
def get_duplicate_user_hero_dict(request):
    uid_zone = request.REQUEST.get('uid_zone',None)
    uid,zone = uid_zone.split('|')
    hid = request.REQUEST.get('hid',None)
    open_date = request.GET.get('open_date')
    open_date = ''.join(open_date.split('-'))
    uid = UserZone.get_new_uid(uid, zone)
    user = list(UserDuplicate.query({"open_date": open_date, "uid": uid}))[0]
    hero_dict = user.hero_data[hid]
    json_hero = json.dumps(hero_dict,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_hero)

@login_permission_required('view_duplicate')
def get_db_user_dict(request):
    uid_zone = request.REQUEST.get('uid_zone',None)
    uid,zone = uid_zone.split('|')
    open_date = request.GET.get('open_date')
    open_date = ''.join(open_date.split('-'))
    uid = UserZone.get_new_uid(uid, zone)
    user = list(UserDuplicate.query({"open_date": open_date, "uid": uid}))[0]
    user_dict = {
        'hero_data': user.hero_data,
        'troop_data': user.troop_data
    }
    return HttpResponse(json.dumps(user_dict,sort_keys=True,indent=4,default=Serializer.json_default))

@login_permission_required('view_duplicate')
def get_duplicate_city_dict(request):
    open_date = request.GET.get('open_date')
    cid = request.REQUEST.get('cid')
    server_port = request.GET.get('server_port')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        res = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_duplicate_world_data', {})
        cities = res['world']['cities']
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
        world = pickle.loads(zlib.decompress(str(res.world)))
        cities = world['cities']
    city_dict = cities[cid]
    return HttpResponse(json.dumps(city_dict,sort_keys=True,indent=4,default=Serializer.json_default))


@login_permission_required('view_duplicate')
def get_duplicate_world_dict(request):
    open_date = request.GET.get('open_date')
    server_port = request.GET.get('server_port')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        res = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_duplicate_world_data', {})
        world = res['world']
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
        world = pickle.loads(zlib.decompress(str(res.world)))
    return HttpResponse(json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default))

@login_permission_required('view_duplicate')
def get_duplicate_user_dict(request):
    open_date = request.GET.get('open_date')
    uid = request.GET.get('uid')
    server_port = request.GET.get('server_port')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        user = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_duplicate_user', {'uid': uid})
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
        users = pickle.loads(zlib.decompress(str(res.user)))
        user = users[uid]
    return HttpResponse(json.dumps(user, sort_keys=True, indent=4, default=Serializer.json_default))

@login_permission_required('view_duplicate')
def get_duplicate_fight_js_data(request):
    open_date = request.GET.get('open_date')
    fid = request.GET.get('fid')
    server_port = request.GET.get('server_port')
    c_open_date = UserZone.get_duplicate_open_date()
    c_open_date = c_open_date.strftime('%Y%m%d')
    if open_date == c_open_date:
        data = UserZone.call_duplicate_server_api(get_duplicate_server_addr(server_port), 'get_fight_js_data', {'fid': fid})
    else:
        dnum = int(server_port) - game_config.system_simple['server_port'][0]
        res = dl.select(and_(dl.c.open_date == open_date, dl.c.dnum == dnum)).execute().fetchone()
        world = pickle.loads(zlib.decompress(str(res.world)))
        log_dict = world['fight_logs'][fid]

        troops = []
        for log_troop in log_dict['troop']:
            troop = world['troops'][log_troop['uid']][log_troop['hid']]
            troop['army'][0]['hp'] = log_troop['armyHP'][0]
            troop['army'][1]['hp'] = log_troop['armyHP'][1]
            troop['rush'] = log_troop['rush']
            troop['proud'] = log_troop['proud']
            troop['others'] = log_troop['others']
            troops.append(troop)

        data = {
            'mode': 80,
            'duplicate_level': log_dict['duplicate_level'],
            'winner': log_dict['winner'],
            'fight_time': log_dict['fight_time'],
            'cid': log_dict['cid'],
            'rnd': log_dict['rnd'],
            'troop': troops
        }

    return HttpResponse(json.dumps(data, sort_keys=True, indent=4, default=Serializer.json_default))

@login_permission_required('view_duplicate')
def duplication_operate(request):
    action = request.POST.get('action')
    open_date = request.POST.get('open_date')
    server_port = request.POST.get('server_port',None)
    if action == 'refresh_duplicate':
        if settings.SUBTEST:
            cache_key = '%s_%s_%s_duplicate_status' % (settings.CACHE_PRE, open_date, server_port)
            cache.delete(cache_key)
            addr, port = game_config.system_simple['server_port'][2][0]
            server_addr = '%s:%s' % (addr, port)
            if not server_port:
                dnum = -1
            else:
                dnum = int(server_port) - game_config.system_simple['server_port'][0]
            res = UserZone.call_duplicate_server_api(server_addr, 'refresh_duplicate', {'dnum': dnum})
    elif action == 'clear_duplicate_join_user':
        if settings.SUBTEST:
            dnum = 0
            for server in game_config.system_simple['server_port'][1]:
                for num in xrange(server[0]):
                    dnum += num
                    server_port = game_config.system_simple['server_port'][0] + dnum
                    cache_key = '%s_%s_%s_duplicate_status' % (settings.CACHE_PRE, open_date, server_port)
                    cache.delete(cache_key)
            for item in UserDuplicate.query({'open_date': open_date}):
                item.delete()
            for item in UserZone.get_zone_list('running'):
                UserZone.call_server_api(item[0], 'refresh_duplicate', {'open_date': open_date})
            for item in game_config.system_simple['server_port'][2]:
                addr, port = item
                server_addr = '%s:%s' % (addr, port)
                res = UserZone.call_duplicate_server_api(server_addr, 'refresh_duplicate', {'dnum': -1})
                


    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('view_duplicate')
def get_fight_logs(request):
    now = datetime.datetime.now()
    session_user = request.session.get('admin_user')
    zone_list = []
    for item in UserZone.get_zone_list('running', session_user=session_user):
        zone_list.append(item)

    search_keyword = request.REQUEST.get('search_keyword', '')
    start_at = request.REQUEST.get('start_at')
    end_at = request.REQUEST.get('end_at')
    zone = request.REQUEST.get('zone')
    if not start_at:
        start_at = datetime.date.today().strftime('%Y-%m-%d') + ' 00:00'
    if not end_at:
        end_at = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d') + ' 00:00'

    fight_logs = []

    if request.META['REQUEST_METHOD'] == 'POST':
        if not zone:
            return HttpResponse(u'<script>alert("请选择区服");history.go(-1);</script>')
        filters = {'zone': zone}
        if start_at:
            filters.setdefault('fight_time', {})
            filters['fight_time']['$gte'] = datetime.datetime.strptime(start_at, '%Y-%m-%d %H:%M')
        if end_at:
            filters.setdefault('fight_time', {})
            filters['fight_time']['$lt'] = datetime.datetime.strptime(end_at, '%Y-%m-%d %H:%M')
        if search_keyword:
            filters['$or'] = [{"battle_id": search_keyword}]
            try:
                filters['$or'].append({"cid": int(search_keyword)})
                filters['$or'].append({"attack_uid": int(search_keyword)})
                filters['$or'].append({"defense_uid": int(search_keyword)})
            except:
                pass
        db = get_dbengine(zone)
        for item in db['fight_logs'].find(filters).sort("fight_time", -1):
            initjs = pickle.loads(str(item['initJS']))
            attack_troop, defense_troop = initjs['troop']
            if attack_troop.get('awaken'):
                attack_hero_name = u'神·%s%s' % (game_config.return_msg[game_config.hero[attack_troop['hid']]['name']], attack_troop['power'])
            else:
                attack_hero_name = u'%s%s' % (game_config.return_msg[game_config.hero[attack_troop['hid']]['name']], attack_troop['power'])
            if defense_troop.get('awaken'):
                defense_hero_name = u'神·%s%s' % (game_config.return_msg[game_config.hero[defense_troop['hid']]['name']], defense_troop['power'])
            else:
                defense_hero_name = u'%s%s' % (game_config.return_msg[game_config.hero[defense_troop['hid']]['name']], defense_troop['power'])

            ##战前剩余兵百分比
            attack_fight_before_hp = initjs['troop'][0]['army'][0]['hp'] + initjs['troop'][0]['army'][1]['hp']
            attack_fight_before_hpm = initjs['troop'][0]['army'][0]['hpm'] + initjs['troop'][0]['army'][1]['hpm']
            attack_fight_before_hp_rate = int((attack_fight_before_hp*1.0/attack_fight_before_hpm)*100)

            defense_fight_before_hp = initjs['troop'][1]['army'][0]['hp'] + initjs['troop'][1]['army'][1]['hp']
            defense_fight_before_hpm = initjs['troop'][1]['army'][0]['hpm'] + initjs['troop'][1]['army'][1]['hpm']
            defense_fight_before_hp_rate = int((defense_fight_before_hp*1.0/defense_fight_before_hpm)*100)
            ##战后剩余兵百分比
            attack_fight_after_hp_rate = int((item['fight_result']['troop'][0]['hp']*1.0/item['fight_result']['troop'][0]['hpm'])*100)
            defense_fight_after_hp_rate = int((item['fight_result']['troop'][1]['hp']*1.0/item['fight_result']['troop'][1]['hpm'])*100)
            _item = {}
            _item['fight_id'] = item['fight_id']
            _item['battle_id'] = item['battle_id']
            _item['zone'] = zone
            attack_uid, attack_zone = UserZone.get_old_uid_zone(int(item['attack_uid']), zone)
            defense_uid, defense_zone = UserZone.get_old_uid_zone(int(item['defense_uid']), zone)
            _item['attack'] = {
                'uid': attack_uid,
                'zone': attack_zone,
                'is_user': attack_uid > 0,
                'winner': item['fight_result']['winner'] == 0,
                'hero': {'name': attack_hero_name, 'hid': attack_troop['hid']},
                'attack_fight_before_hp_rate': attack_fight_before_hp_rate,
                'attack_fight_after_hp_rate': attack_fight_after_hp_rate
            }
            _item['defense'] = {
                'uid': defense_uid,
                'zone': defense_zone,
                'is_user': defense_uid > 0,
                'winner': item['fight_result']['winner'] == 1,
                'hero': {'name': defense_hero_name, 'hid': defense_troop['hid']},
                'defense_fight_before_hp_rate': defense_fight_before_hp_rate,
                'defense_fight_after_hp_rate': defense_fight_after_hp_rate
            }
            _item['cid'] = '%s(%s)' % (game_config.return_msg['c_%s' % item['cid']], item['cid'])
            _item['fight_time'] = utils.get_time_str(item['fight_time'])
            fight_logs.append(_item)
    return render_to_response('admin/app_user/fight_log.html', {
        'zone_list': zone_list,
        'start_at': start_at,
        'end_at': end_at,
        'search_keyword': search_keyword,
        'zone': zone,
        'fight_logs': fight_logs
        },
        RequestContext(request))


@login_permission_required('view_duplicate')
def get_battle_hero_dict(request):
    battle_id = request.GET['battle_id']
    zone = request.GET['zone']
    troop_index = int(request.GET['troop_index'])
    db = get_dbengine(zone)
    fight = db['fight_logs'].find_one({"battle_id": battle_id})
    initJS = pickle.loads(str(fight['initJS']))
    hero_dict = initJS['troop'][troop_index]
    json_hero = json.dumps(hero_dict,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_hero)

@login_permission_required('view_duplicate')
def get_battle_dict(request):
    battle_id = request.GET['battle_id']
    zone = request.GET['zone']
    db = get_dbengine(zone)
    fight = db['fight_logs'].find_one({"battle_id": battle_id})
    if fight:
        fight['initJS'] = pickle.loads(str(fight['initJS']))
    json_fight = json.dumps(fight,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_fight)

@login_permission_required('mod_app_user', ajax=True)
def join_zone_server(request):
    uid = request.POST['uid']
    zone = request.POST['zone']
    new_uid = UserZone.get_new_uid(uid, zone)
    user_zone = UserZone.get(uid)
    if not user_zone:
        return HttpResponse(json.dumps({'state':'error', 'msg': 'UID: %s 不存在' % uid}))
    if zone not in user_zone.zone_login:
        return HttpResponse(json.dumps({'state':'error', 'msg': '区服ID错误'}))
    merge_zone = user_zone.zone_login[zone]['merge_zone']
    db_conn = ShardMetas['1']['db_engine'].connect()
    user_table = utils.get_table_name('user', merge_zone, settings.USER_TABLE_NUM)
    db_user = db_conn.execute(
        "select * from %s where uid='%s' and zone='%s'" % (user_table, new_uid, merge_zone)).fetchone()
    if not db_user:
        return HttpResponse(json.dumps({'state':'error', 'msg': '玩家数据不存在'}))
    user_data = zlib.decompress(db_user.user_data)
    if settings.USE_SERIALIZE == 'json':
	user_data = json.loads(user_data, object_hook=Serializer.json_object_hook)
    else:
	user_data = eval(user_data)
    user_data['uid'] = int(user_data['uid'])
    db_conn.close()
    UserZone.call_server_api(zone, 'join_user', {'uid': uid, 'data': user_data})
    data = {'state': 'success'}
    return HttpResponse(json.dumps(data))

@login_permission_required('sync_invitation', ajax=True)
def sync_invitation(request):
    uid = request.POST['uid']
    zone = request.POST['zone']
    new_uid = UserZone.get_new_uid(uid, zone)
    user_zone = UserZone.get(uid)
    if not user_zone:
        return HttpResponse(json.dumps({'state':'error', 'msg': 'UID: %s 不存在' % uid}))
    if zone not in user_zone.zone_login:
        return HttpResponse(json.dumps({'state':'error', 'msg': '区服ID错误'}))
    if not user_zone.inviter:
        return HttpResponse(json.dumps({'state':'error', 'msg': '非邀请用户'}))
    app_user = UserZone.call_server_api(zone, 'get_user', {'uid': uid})
    buildinglv = app_user['home']['building001']['lv']
    money = app_user['records']['pay_money']
    r = InvitationRecord.get(user_zone.inviter)
    if not r:
        r = InvitationRecord()
        r.uid = user_zone.inviter
    r.data.setdefault(uid, {})
    if buildinglv >= r.data[uid].get('buildinglv', 0):
        r.data[uid]['buildinglv'] = buildinglv
    if money >= r.data[uid].get('money', 0):
        r.data[uid]['money'] = money
    r.save()

    data = {'state': 'success'}
    return HttpResponse(json.dumps(data))

@login_permission_required('view_app_user') 
def get_pk_yard_log(request):
    zone = request.REQUEST.get('zone', None)
    ym = request.REQUEST.get('ym', None)
    tn = request.REQUEST.get('tn', None)
    sn = request.REQUEST.get('sn', None)
    world = UserZone.call_server_api(zone, 'get_pk_yard_log', {'ym': ym, 'tn': tn, 'sn': sn})
    world_str = json.dumps(world,sort_keys=True,indent=4,default=Serializer.json_default)
    res = HttpResponse(world_str)
    res['Content-Type'] = 'text/json; charset=utf-8'
    return res

@login_permission_required('view_app_user')
def ignore_user_list(request):
    zone = request.GET.get('zone')
    db_conn = ShardMetas['1']['db_engine'].connect()
    user_table = utils.get_table_name('user', zone, settings.USER_TABLE_NUM)
    db_users = []
    for item in db_conn.execute(
            "select uid from %s where zone='%s'" % (user_table, zone)).fetchall():
        db_users.append(int(item.uid))
    server_users = UserZone.call_server_api(zone, 'get_join_users', {})
    ignore_users = list(set(db_users) - set(server_users))
    data = json.dumps(ignore_users, sort_keys=True, indent=4, default=Serializer.json_default)
    res = HttpResponse(data)
    res['Content-Type'] = 'text/json; charset=utf-8'
    return res

@login_permission_required('mod_app_user', ajax=True)
def free_api_black(request):
    uid = request.POST['uid']
    zone = request.POST['zone']
    new_uid = UserZone.get_new_uid(uid, zone)
    user_zone = UserZone.get(uid)
    if not user_zone:
        return HttpResponse(json.dumps({'state':'error', 'msg': 'UID: %s 不存在' % uid}))
    if zone not in user_zone.zone_login:
        return HttpResponse(json.dumps({'state':'error', 'msg': '区服ID错误'}))
    UserZone.call_server_api(zone, 'free_api_black', {'uid': uid})
    data = {'state': 'success'}
    return HttpResponse(json.dumps(data))


@login_permission_required('view_app_user', ajax=True)
def test_story_dungeon(request):
    zone = request.POST['zone']
    dungeon_id = request.POST['dungeon_id']
    puppet_lv = request.POST['puppet_lv']
    times = request.POST['times']
    test_data = UserZone.call_server_api(zone, 'test_story_dungeon',
            {'dungeon_id': int(dungeon_id), 'puppet_lv': int(puppet_lv),
                'times': int(times)}, timeout=60)
    gift_list = ['%s:%s' % i for i in sorted(test_data['aver_gifts'].items(),  key=lambda x:x[1])]
    test_data['aver_gifts'] = ' | '.join(gift_list)
    goal_list = ['%s:%s' % i for i in sorted(test_data['aver_goals'].items(),  key=lambda x:x[1])]
    test_data['aver_goals'] = ' | '.join(goal_list)
    data = {'state': 'success', 'test_data': test_data}
    return HttpResponse(json.dumps(data))

@login_permission_required('view_world_report') 
def view_world_report(request):
    zone = request.REQUEST.get('zone', None)
    session_user = request.session.get('admin_user')
    smodel = request.REQUEST.get('smodel', 'core')
    zone_list = []
    item_list = []
    for item in UserZone.get_zone_list('running', session_user=session_user):
        item_list.append(item)
        if len(item_list) >= 10:
            zone_list.append(item_list)
            item_list = []
    else:
        zone_list.append(item_list)

    if request.method == 'GET':
        return render_to_response('admin/app_user/view_world_report.html',
                {'zone_list': zone_list}, RequestContext(request))
    db = get_dbengine(zone)
    c_maps = ['魏', '蜀', '吴']
    zone_pay_records = get_zone_thirty_days_pay_records(zone)

    data = []
    for item in db['country_year_data'].group(['years'], None, {'country_list': []}, 'function(obj, prev) {prev.country_list.push(obj)}'):
        _item = {'years': int(item['years']), 'country_list': []}
        if _item['years']%2 == 0:
            _item['bg_color'] = 'danger'
        else:
            _item['bg_color'] = 'active'
        for country in sorted(item['country_list'],  key=lambda x: x['country']):
            _data = pickle.loads(str(country.get('country_%s' % smodel)))
            if smodel == 'hero':
                __data = {}
                for k,v in enumerate(_data):
                    hero_name = game_config.return_msg[game_config.hero[v[1]]['name']]
                    if v[3].get('awaken', 0) == 1:
                        hero_name = u'神·' + hero_name
                    __data[k] = [hero_name, v[2]]
                _data = __data

            elif smodel == 'core':
                _data.setdefault('thirty_pay_money', 0)
                for uid_zone in _data.get('active_users', []):
                    _data['thirty_pay_money'] += zone_pay_records.get(uid_zone, 0)
            elif smodel == 'cities':
                for i in [0, 1, 2, 3, 4, 9]:
                    _data['city_%s' % i] = _data.get('city_%s' % i, 0)
            elif smodel == 'official':
                for k,v in _data.items():
                    if k.startswith('official_'):
                        if v is not None:
                            old_uid, old_zone = UserZone.get_old_uid_zone(v[0],
                                    zone)
                            _data[k][0] = '%s|%s' % (old_uid, old_zone)
            _data['country'] = country['country']
            _data['country_name'] = c_maps[country['country']]
            _data['report_at'] = country['report_at']
            _item['country_list'].append(_data)
        data.append(_item)
    data.sort(key=lambda x:x['years'], reverse=True)


    world_report_body = loader.render_to_string('admin/app_user/view_world_report_body.html', {
        'smodel': smodel,
        'zone': zone,
        'data': data,
        },
        RequestContext(request))
    return HttpResponse(json.dumps({'world_report_body': world_report_body}))

@login_permission_required('view_world_report') 
def get_world_report_hero_dict(request):
    hid = request.REQUEST['hid']
    year = request.REQUEST['year']
    country = request.REQUEST['country']
    zone = request.REQUEST['zone']
    db = get_dbengine(zone)
    country_data = db['country_year_data'].find_one({'years': int(year), 'country': int(country)})
    country_hero = pickle.loads(str(country_data['country_hero']))
    hero_dict = country_hero[int(hid)][3]
    json_hero = json.dumps(hero_dict,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_hero)
