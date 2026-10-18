#-*- coding: utf-8 -*-

import datetime
import json
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from admin.logic import login_permission_required
from game_lib.models.main import UserZone, GatherPlayer, GatherPlayerData, AdminLog
from game_lib.logics import game_config
from game_lib.libs.model import Serializer
from admin.pager import Pager


@login_permission_required('gather_player')
def index(request):
    uid = request.GET.get('uid', '')
    return render_to_response('admin/gather_player/view_player.html', {
        'uid': uid,
    }, RequestContext(request))

@login_permission_required('gather_player', ajax=True)
def get_player_template(request):
    uid = request.GET['uid']

    gather_player = GatherPlayer.get(uid)
    if not gather_player:
        return HttpResponse(json.dumps({'state':'error','msg':u'模板ID不存在'}))

    player = gather_player.dumps()

    player['add_time'] = str(gather_player.add_time)[:19]
    player['login_time'] = str(gather_player.login_time)[:19]
    player['score'] = gather_player.score
    player['menu'] = gather_player.get_operation_menu()
    player['status_cn'] = gather_player.status_cn
    player['join_num'] = 0
    if gather_player.status == 1:
        user_zone = list(UserZone.query({'player_id': uid}))
        if user_zone:
            player['join_num'] = len(user_zone[0].zone_login)
    player_data = []
    for item in GatherPlayerData.query({'uid': uid}, order_by="-time",
            attrs=['id', 'did']):
        player_data.append([item['id'], item['did']])
    open_data_id = None
    if player_data:
        open_data_id = player_data[0][0]
    
    player_template_html = loader.render_to_string('admin/gather_player/player_template.html', {
        'player': player,
        'player_data': player_data,
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state':'success', 'player_template_html':
        player_template_html, 'open_data_id': open_data_id}))


@login_permission_required('gather_player', ajax=True)
def get_player_data(request):
    data_id = request.GET['data_id']

    gather_player_data = GatherPlayerData.get(data_id)
    if not gather_player_data:
        return HttpResponse(json.dumps({'state':'error','msg':u'存档数据不存在'}))

    app_user = gather_player_data.data

    mod_user = [
        [
            ['uname', u'Uname'],
            ['building_lv', u'官邸等级'],
            ['country', u'国家'],
            ['office', u'爵位等级'],
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
        ],
        [
            ['power_hero_list', u'最强英雄'],
        ],
    ]

    pay_money, admin_pay, sale_money = GatherPlayer.get_user_pay(app_user)    
    for x in mod_user:
        for item in x:
            if item[0] == 'member':
                item.append(app_user['member'][0])
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
            elif item[0] == 'pay_money':
                item.append(pay_money)
            elif item[0] == 'admin_pay':
                item.append(admin_pay)
            elif item[0] == 'sale_money':
                item.append(sale_money)
            elif item[0] == 'power_hero_list':
                hero_list = []
                for hid,hero in sorted(app_user['hero'].items(),key=lambda
                        x:x[1]['power'],reverse=True)[:20]:
                    _item = [hid, hero['power']]
                    hero_name = game_config.return_msg[game_config.hero[hid]['name']]
                    if hero.get('awaken', 0) == 1:
                        hero_name = u'神·' + hero_name
                    _item.append(hero_name)
                    hero_list.append(_item)
                item.append(hero_list)
            else:
                item.append(app_user.get(item[0]))

    player_data_html = loader.render_to_string('admin/gather_player/player_data.html', {
        'data_id': data_id,
        'mod_user': mod_user,
        'app_user': json.dumps(gather_player_data.data, sort_keys=True, indent=4, default=Serializer.json_default),
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state':'success', 'player_data_html':
        player_data_html}))

@login_permission_required('gather_player', ajax=True)
def get_player_hero_dict(request):
    data_id = request.REQUEST.get('data_id',None)
    hid = request.REQUEST.get('hid',None)
    gather_player_data = GatherPlayerData.get(data_id)
    hero_dict = GatherPlayer.get_fight_prepare_data(hid, gather_player_data.data)
    json_hero = json.dumps(hero_dict,sort_keys=True,indent=4,default=Serializer.json_default)
    return HttpResponse(json_hero)

@login_permission_required('gather_player', ajax=True)
def save_player_data(request):
    data_id = request.REQUEST.get('data_id',None)
    app_user = request.REQUEST.get('app_user',None)
    data = json.loads(app_user, object_hook=Serializer.json_object_hook)
    gather_player_data = GatherPlayerData.get(data_id)
    if not gather_player_data:
        return HttpResponse(json.dumps({'state':'error','msg':u'存档数据不存在'}))
    gather_player_data.data = data
    gather_player_data.save()
    admin_user = request.session['admin_user']['username']
    AdminLog.add_adminlog(admin_user, 'save_player_data', data_id)
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('gather_player')
def view_zone_gather(request):
    zone_list = [[u'all', u'全部']]
    for item in GatherPlayer.query(attrs=['zone'], group_by='zone', order_by='zone'):
        if item['zone'] not in game_config.zone:
            continue
        zone_list.append([item['zone'], u'%s区-%s' % (item['zone'],
            game_config.zone[item['zone']][0])])
    return render_to_response('admin/gather_player/view_zone_gather.html', {
        'mould_day': game_config.player_robot['mould_day'],
        'mould_times': game_config.player_robot['mould_times'],
        'zone_list': zone_list,
    }, RequestContext(request))

@login_permission_required('gather_player')
def get_zone_mod_data(request):
    zone = request.GET['zone']
    cond = {}
    if zone != 'all':
        cond['zone'] = zone
        zone_name = '%s-%s' % (zone, game_config.zone[zone][0])
        deviation = game_config.system_simple['deviation']
        deviation_minutes = datetime.timedelta(minutes = deviation)

        now = datetime.datetime.now()
        dev_now = now-deviation_minutes
        open_game_time = game_config.zone[zone][2]
        dev_open_game_time = open_game_time-deviation_minutes
        season_num = (dev_now.date()-dev_open_game_time.date()).days
        open_days = season_num + 1
    else:
        zone_name = u'全部'
        open_days = None
    mod_data = {
            'user_num': 0,
            'gather_num': 0,
            'status_0_0': 0,
            'status_0_1': 0,
            'status_1': 0,
            'status_2': 0,
            'status_3': 0,
            'join_num': 0,
            }
    for item in GatherPlayer.query(cond):
        mod_data['gather_num'] += 1
        if item.status == 0:
            if item.registrable:
                mod_data['status_0_1'] += 1
            mod_data['status_0_0'] += 1
        elif item.status == 1:
            mod_data['status_1'] += 1
            user_zone = list(UserZone.query({'player_id': item.uid}))
            if user_zone:
                mod_data['join_num'] += len(user_zone[0].zone_login)
        elif item.status == 2:
            mod_data['status_2'] += 1
        elif item.status == 3:
            mod_data['status_3'] += 1
    zone_mod_data_html = loader.render_to_string('admin/gather_player/zone_mod_data.html', {
        'mod_data': mod_data,
        'zone_name': zone_name,
        'open_days': open_days,
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state':'success', 'zone_mod_data_html':
        zone_mod_data_html}))

@login_permission_required('gather_player')
def get_zone_player_data(request):
    zone = request.GET['zone']
    offset = int(request.GET.get('offset', 1))
    page_size = int(request.GET.get('limit', 10))
    order_by = request.GET.get('order_by', '-score')
    status = request.GET.get('status', 'all')  # 0_0未采满 0_1可登用
    cond = {}
    if zone != 'all':
        cond['zone'] = zone
    if status != 'all':
        cond['status'] = int(status.split('_')[0])

    if status == '0_1':
        result = []
        for i in GatherPlayer.query(cond, order_by=order_by):
            if not i.registrable:
                continue
            result.append(i)
        total = len(result)
        result = result[offset:offset+page_size]
    else:
        total = GatherPlayer.count(cond)
        result = GatherPlayer.query(cond, order_by=order_by, offset=offset, limit=page_size)
    data = []
    for item in result:
        _item = item.to_dict()
        if item.last_did:
            player_data = GatherPlayerData.get(item.last_did)
            user_data = player_data.data
            _item['uname'] = user_data['uname']
            _item['building_lv'] = user_data['home']['building001']['lv']
            _item['office_lv'] = user_data['office']
            _item['pay_money'] = user_data['records']['pay_money']
            _item['kill_num'] = user_data['total_records']['kill_num']
            _item['build_count'] = user_data['total_records']['build_count']
            _item['power'] = user_data['power']
            _item['best_hero_power'] = user_data['best_hero_power']
            hero_list = []
            for hid,hero in sorted(user_data['hero'].items(),key=lambda
                    x:x[1]['power'],reverse=True)[:3]:
                _hero = [hid, hero['power']]
                hero_name = game_config.return_msg[game_config.hero[hid]['name']]
                if hero.get('awaken', 0) == 1:
                    hero_name = u'神·' + hero_name
                _hero.append(hero_name)
                hero_list.append(_hero)
            _item['hero_list'] = hero_list
            _item['join_num'] = 0
        user_zone = list(UserZone.query({'player_id': item.uid}))
        if user_zone:
            _item['user_zone'] = user_zone[0].uid
            _item['join_num'] = len(user_zone[0].zone_login)
        _item['menu'] = item.get_operation_menu()
        data.append(_item)
    return HttpResponse(json.dumps({'total': total, 'rows': data}))

def change_server_gather_status(player_id, status):
    """
    更改数据采集状态 0: 继续采集 1: 采集结束
    """
    try:
        old_uid = int(player_id) % settings.UIDADD
        old_zone = int(player_id) / settings.UIDADD
        if UserZone.get(old_uid):
            UserZone.call_server_api(str(old_zone), 'modify_gather_status', {'player_id': player_id, 'status': status})
    except:
        pass

@login_permission_required('gather_player')
def change_player_user_zone_status(request):
    """
    更改AI机器人实例逻辑执行状态 0: 停止逻辑 1: 继续逻辑
    """
    uid = request.POST['uid']
    status = request.POST['status']
    user_zone = UserZone.get(uid)
    if not user_zone:
        return
    user_zone.player = status
    user_zone.save()
    for k in user_zone.zone_login:
        try:
            UserZone.call_server_api(k, 'modify_player_status', {'uid': user_zone.uid, 'status': status})
        except:
            continue
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('gather_player')
def modify_player_status(request):
    uids = request.POST['uids']
    status = int(request.POST['status'])
        
    for uid in uids.split(','):
        gather_player = GatherPlayer.get(uid)
        if not gather_player:
            return HttpResponse(json.dumps({'state':'error','msg':u'模板(%s)不存在' % uid}))
        if gather_player.status == 4:
            return HttpResponse(json.dumps({'state':'error','msg':u'模板(%s)已删除' % uid}))
        if gather_player.status == status:
            return HttpResponse(json.dumps({'state':'error','msg':u'模板(%s)不可操作' % uid}))

        if status == 0:
            if gather_player.status != 2:
                return HttpResponse(json.dumps({'state':'error','msg':u'模板(%s)不可操作' % uid}))
            gather_player.status = 0
            if gather_player.discard_time:
                gather_player.discard_time = None
            gather_player.save()
            change_server_gather_status(uid, 0)
        elif status == 1:
            # if not gather_player.registrable:
                # return HttpResponse(json.dumps({'state':'error','msg':u'模板(%s)不可操作' % uid}))
            if gather_player.registrable:
                user_zone = list(UserZone.query({'player_id': uid}))
                if not user_zone:
                    UserZone.register_player(uid)
                gather_player.status = 1
                if gather_player.discard_time:
                    gather_player.discard_time = None
                gather_player.save()
        elif status == 2:
            gather_player.status = 2
            gather_player.discard_time = datetime.datetime.now()
            gather_player.save()
            change_server_gather_status(uid, 1)
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('gather_player') 
def view_player_data(request):
    uid = request.GET['uid']
    zone = request.GET['zone']
    player_data = UserZone.call_server_api(zone, 'get_player_data', {'uid': uid})
    data = {
        'state': 'success',
        'data':json.dumps(player_data,sort_keys=True,indent=4,default=Serializer.json_default)
    }
    return HttpResponse(json.dumps(data))

@login_permission_required('gather_player') 
def player_command(request):
    uid = request.GET['uid']
    zone = request.GET['zone']
    action = request.GET['action']
    UserZone.call_server_api(zone, 'player_command', {'uid': uid, 'action':
        action})
    return HttpResponse(json.dumps({'state': 'success'}))
