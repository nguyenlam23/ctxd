#-*- coding: utf-8 -*-

import json
import xlrd
import re
from sqlalchemy import and_, or_, func, select
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.conf import settings
from admin.logic import login_permission_required
import datetime
from game_lib.models.zone import Zones
from game_lib.db.database import Zones_table as zt
from game_lib.common import utils
from game_lib.logics import game_config
from game_lib.libs.model import Serializer
from admin.pager import Pager
from game_lib.models.main import AdminLog, UserZone
from game_lib.models.cache import CacheTable
from game_lib.models.config import Configs, TestConfigs


@login_permission_required('zone_manage')
def zone_manage(request):
    page = int(request.REQUEST.get('page', 1))
    order_by = request.REQUEST.get('order_by')
    search_keyword = request.REQUEST.get('search_keyword', None)
    merge_times = request.REQUEST.get('merge_times', None)
    zone_active = request.REQUEST.get('zone_active', None)
    select_zone_group = request.REQUEST.get('zone_group', None)
    where = []
    page_params = {}
    if search_keyword:
        where.append(or_(zt.c.zone_id == search_keyword, zt.c.zone_name == search_keyword))
        page_params['search_keyword'] = search_keyword
    if merge_times:
        where.append(zt.c.merge_times == merge_times)
        where.append(zt.c.host != '')
        page_params['merge_times'] = merge_times
    if zone_active:
        where.append(zt.c.active == int(zone_active))
        page_params['zone_active'] = zone_active
    if select_zone_group:
        where.append(zt.c.zone_group == select_zone_group)
        page_params['zone_group'] = select_zone_group
    order_by = [zt.c.active, zt.c.merge_times.desc(), zt.c.port, zt.c.open_time.desc(), zt.c.id]
    active_select = [
        {'id': '', 'text': u'--请选择--'},
        {'id': '0', 'text': u'未开区'},
        {'id': '1', 'text': u'运行中'},
        {'id': '2', 'text': u'已合区'},
    ]
    merge_times_select = [
        {'id': '', 'text': u'--请选择--'},
    ]
    for item in sorted(Zones.merge_state_maps.items(), key=lambda x:x[0]):
        merge_times_select.append({
            'id': str(item[0]),
            'text': item[1]
        })
    zone_group_select = [
        {'id': '', 'text': u'--请选择--'},
    ]
    for item in UserZone.get_zone_group_list():
        zone_group_select.append({
            'id': item['id'],
            'text': item['name']
        })
    total = select([func.count(zt.c.id)], and_(*where)).execute().fetchone()[0]
    page_size = 10
    offset = page_size * (page - 1)
    p = Pager(total, page_size, page, parameter=page_params)
    zone_list = []
    state_color_maps = {0: 'default', 1: 'danger', 2: 'success', 3: 'warning'}
    zones = zt.select(and_(*where)).order_by(*order_by).offset(offset).limit(page_size).execute().fetchall()
    for item in zones:
        zone = dict(item)
        zone['open_time'] = utils.get_time_str(item.open_time)
        if item.zone_group:
            zone['zone_group'] = game_config.help_msg['zone_groups'].get(item.zone_group, {}).get('name', item.zone_group)
        else:
            zone['zone_group'] = '--'
        zone['register_limit'] = [Zones.register_limit_maps.get(item.register_limit), 'success' if item.register_limit else 'danger']
        zone['recommend'] = [Zones.recommend_maps.get(item.recommend), 'success' if item.recommend else 'default']
        zone['state'] = [Zones.state_maps.get(item.state), state_color_maps[item.state]]
        zone['merge_times'] = Zones.merge_state_maps[item.merge_times]
        zone['op_merge_times'] = item.op_merge_times if item.merge_times == 0 else '--'
        if item.port == 0 and item.active == 2:
            zone['can_edit'] = False
        else:
            zone['can_edit'] = True
        zone_list.append(zone)
    auto_open_server_configs = []
    for item in UserZone.get_zone_group_list():
        zone_group_config = CacheTable.get('auto_open_config_%s' % item['id'], {
            'auto_stop_at': '',
            'import_user_num': '',
            'time_interval': '',
            'ban_open_time': ['', ''],
            'server_user_num': '',
            'open_delay': '',
            'active': 0
        })
        zone_group_config['zone_group_id'] = item['id']
        zone_group_config['zone_group_name'] = item['name']
        if zone_group_config['auto_stop_at']:
            zone_group_config['auto_stop_at'] = zone_group_config['auto_stop_at'].strftime('%Y-%m-%d %H:%M')
        auto_open_server_configs.append(zone_group_config)
    return render_to_response('admin/zone_manage/zone.html', {
        'p': p,
        'search_keyword': search_keyword,
        'merge_times': merge_times,
        'zone_active': zone_active,
        'zone_group': select_zone_group,
        'active_select': active_select,
        'zone_group_select': zone_group_select,
        'merge_times_select': merge_times_select,
        'zone_list': zone_list,
        'auto_open_server_configs': auto_open_server_configs
    },
    RequestContext(request))

@login_permission_required('zone_manage')
def batch_import(request):
    """
    批量导入新服
    :param request:
    :return:
    """
    import_file = request.FILES.get('batch_import_file')
    if not import_file:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请选择导入文件'}))
    try:
        workbook = xlrd.open_workbook(filename=None, file_contents=import_file.read())
    except:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请选择Excel(97-2003)xls文件'}))
    sheet = workbook.sheets()[0]
    for row in xrange(sheet.nrows):
        item = sheet.row_values(row)
        zone_id, zone_name, host, port, open_time, register_limit, state, _, recommend, _, merge_times = item
        zone_id = str(int(float(zone_id)))
        if Zones.get_zone(zone_id):
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】区服ID重复' % zone_id}))
        timetuple = [int(i) for i in open_time.split(',')]
        zone = Zones()
        zone.zone_id = zone_id
        zone.zone_name = zone_name
        zone.host = host.strip()
        zone.port = int(float(port))
        zone.open_time = datetime.datetime(*timetuple)
        zone.register_limit = int(register_limit)
        zone.state = int(float(state))
        zone.recommend = int(float(recommend))
        zone.merge_times = int(float(merge_times))
        zone.active = 0
        zone.zone_group = UserZone.get_zone_group(zone_id)
        zone.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('zone_manage')
def get_zone(request):
    action = request.GET['action']
    today = datetime.date.today()
    zone_group_select = [
        {'id': '', 'text': u'--请选择--'},
    ]
    for item in UserZone.get_zone_group_list():
        zone_group_select.append({
            'id': item['id'],
            'text': item['name']
        })
    merge_times_select = [
    ]
    for item in sorted(Zones.merge_state_maps.items(), key=lambda x:x[0]):
        merge_times_select.append({
            'id': item[0],
            'text': item[1]
        })
    if action == 'add':
        zone = {
            'merge_times': 0,
            'register_limit': 0,
            'state': 0,
            'recommend': 0,
            'op_merge_times': 0,
            'open_time': datetime.datetime(*(list(today.timetuple()[:3]) + [8, 0]))
        }
    else:
        zone_id = request.GET['zone_id']
        zone = Zones.get_zone(zone_id)
        if not zone:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】区服不存在' % zone_id}))
    edit_zone_modal = loader.render_to_string('admin/zone_manage/edit_zone.html', {
        'zone': zone,
        'action': action,
        'zone_group_select': zone_group_select,
        'merge_times_select': merge_times_select
    }, RequestContext(request))
    return HttpResponse(json.dumps({'state': 'success', 'edit_zone_modal': edit_zone_modal}))

@login_permission_required('zone_manage')
def edit_zone(request):
    action = request.POST['action']
    zone_id = request.POST['zone_id']
    zone_group = request.POST.get('zone_group', '')
    host = request.POST.get('host', '')
    port = request.POST.get('port', 0)
    open_time = request.POST.get('open_time', '')
    zone_name = request.POST.get('zone_name', '')
    register_limit = request.POST.get('register_limit', 0)
    state = request.POST.get('state', 0)
    recommend = request.POST.get('recommend', 0)
    op_merge_times = request.POST.get('op_merge_times', 0)
    if action in ['edit', 'add']:
        # if not host:
        #     return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写主机IP/域名'}))
        # if not port:
        #     return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写端口号'}))
        if not open_time:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写开服时间'}))
    zone = Zones.get_zone(zone_id)
    if action in ['active', 'edit', 'remove', 'deactive']:
        if not zone:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】区服不存在' % zone_id}))
    if action == 'edit':
        zone.zone_name = zone_name
        zone.host = host.strip()
        zone.port = int(port)
        zone.open_time = open_time
        zone.register_limit = int(register_limit)
        zone.state = int(state)
        zone.recommend = int(recommend)
        zone.zone_group = zone_group
        zone.op_merge_times = int(op_merge_times)
        zone.save()
    elif action == 'add':
        if zone:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】区服ID重复' % zone_id}))
        if list(Zones.query({'port': int(port)})):
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'【%s】端口号已被占用' % port}))
        merge_times = request.POST['merge_times']
        zone = Zones()
        zone.zone_id = zone_id
        zone.zone_name = zone_name
        zone.host = host.strip()
        zone.port = int(port)
        zone.open_time = open_time
        zone.register_limit = int(register_limit)
        zone.recommend = int(recommend)
        zone.state = int(state)
        zone.merge_times = int(merge_times)
        zone.active = 0
        zone.zone_group = zone_group if zone_group else UserZone.get_zone_group(zone_id)
        zone.op_merge_times = int(op_merge_times)
        zone.save()
    elif action == 'active':
        if not zone.host or not zone.port:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写主机IP/域名'}))
        if not zone.open_time:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写开服时间'}))
        zone.active = 1
        zone.save()
    elif action == 'deactive':
        zone.active = 0
        zone.save()
    elif action == 'remove':
        if zone.active != 0:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'未停服的区不能被删除' % port}))
        zone.delete()
        zone.save()
    else:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'非法请求'}))
    content = zone.dumps()
    content['action'] = action
    op = {
        'admin_user': request.session['admin_user']['username'],
        'func_name': 'edit_zone',
        'content': content
    }
    AdminLog.add_adminlog(**op)
    take_config_type = CacheTable.get('take_config_type', 'setting')
    if take_config_type == 'setting':
        ConfigModel = Configs
    else:
        ConfigModel = TestConfigs
    zone_config = ConfigModel.get('zone')
    zone_config.sub_time = datetime.datetime.now()
    zone_config.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required()
def view_zone_op_logs(request):
    op_list = []
    for item in AdminLog.query(condition={'func_name': 'edit_zone'}, limit=100, order_by='-subtime'):
        _item = eval(str(item.content))
        _item['admin_user'] = item.admin_user
        _item['subtime'] = item.subtime
        op_list.append(_item)
    return render_to_response('admin/zone_manage/view_zone_op_logs.html', {
        'op_list': op_list
    }, RequestContext(request))

@login_permission_required('zone_manage', ajax=True)
def modify_auto_open_config(request):
    zone_group_id = request.POST['zone_group_id']
    auto_stop_at = request.POST['auto_stop_at']
    import_user_num = request.POST['import_user_num']
    time_interval = request.POST['time_interval']
    s_ban_open_time = request.POST['s_ban_open_time']
    e_ban_open_time = request.POST['e_ban_open_time']
    server_user_num = request.POST['server_user_num']
    open_delay = request.POST['open_delay']
    if zone_group_id not in game_config.help_msg['zone_groups']:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'非法的区服ID'}))
    if not auto_stop_at:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写计划截止时间'}))
    if not import_user_num:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写单服导入人数（数字整数）'}))
    if not time_interval:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写最长时间间隔（数字整数）'}))
    if not s_ban_open_time:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写禁止开服时间（数字整数）'}))
    if not e_ban_open_time:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写禁止开服时间（数字整数）'}))
    if not server_user_num:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写单服最大人数（数字整数）'}))
    if not open_delay:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写开服延迟时间（数字整数）'}))
    config = CacheTable.get('auto_open_config_%s' % zone_group_id, {'active': 0})
    config['auto_stop_at'] = datetime.datetime.strptime(auto_stop_at, '%Y-%m-%d %H:%M')
    config['import_user_num'] = int(import_user_num)
    config['time_interval'] = int(time_interval)
    config['ban_open_time'] = [int(s_ban_open_time), int(e_ban_open_time)]
    config['server_user_num'] = int(server_user_num)
    config['open_delay'] = int(open_delay)
    CacheTable.set('auto_open_config_%s' % zone_group_id, config, 60*60*24*365*100)
    op = {
        'admin_user': request.session['admin_user']['username'],
        'func_name': 'modify_auto_open',
        'content': config
    }
    AdminLog.add_adminlog(**op)
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('zone_manage', ajax=True)
def change_auto_active(request):
    zone_group_id = request.POST['zone_group_id']
    active = int(request.POST['active'])
    config = CacheTable.get('auto_open_config_%s' % zone_group_id, None)
    if active == 1 and config is None:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写完整配置'}))
    config['active'] = active
    CacheTable.set('auto_open_config_%s' % zone_group_id, config, 60*60*24*365*100)
    op = {
        'admin_user': request.session['admin_user']['username'],
        'func_name': 'change_auto_active',
        'content': config
    }
    AdminLog.add_adminlog(**op)
    return HttpResponse(json.dumps({'state': 'success'}))

