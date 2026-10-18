#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.conf import settings
from admin.logic import login_permission_required
from game_lib.models.main import UserZone
from game_lib.models.cache import CacheTable
from game_lib.models.config import ConfigLog
from game_lib.logics import game_config
from game_lib.common import utils
import json, hashlib
import datetime,time
from game_lib.models.main import AdminLog
from game_lib.libs.model import Serializer

maintain_value = '''
{
}
'''

@login_permission_required('zone_maintain')
def zone_maintain(request):
    request_method = request.method
    if request_method == 'POST':
        config_value = request.POST.get('config_value').encode('utf-8').replace('\r', '').strip()
        if not config_value:
            return HttpResponse(json.dumps({'state':'error','msg':u'请填写完整'}))

        try:
            py_val = eval(config_value)
            maintain_list = py_val.get('zone_list', [])
        except Exception, e:
            utils.print_err()
            try:
                return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.text}))
            except:
                return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.message}))
        CacheTable.set('zone_maintain_config', config_value, 3600*24*365*100)
        disp = {
            'sub_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'admin_user': request.session.get('admin_user')['username']
        }
        CacheTable.set('zone_maintain_disp', disp, 3600*24*365*100)

        config_log = ConfigLog()
        config_log.cname = 'maintain'
        config_log.cval = config_value
        config_log.sub_time = datetime.datetime.now()
        config_log.admin_user = request.session['admin_user']['username']
        config_log.save()

        return HttpResponse(json.dumps({'state': 'success'}))
    config = {}
    zone_maintain_config = CacheTable.get('zone_maintain_config', maintain_value)
    disp = CacheTable.get('zone_maintain_disp', {})
    config['sub_time'] = disp.get('sub_time')
    config['admin_user'] = disp.get('admin_user')
    config['config_value'] = zone_maintain_config
    current_maintain_status = _get_current_maintain_status()

    config_logs = []
    config_log_list = ConfigLog.query(attrs=['id', 'sub_time', 'admin_user'], condition={'cname': 'maintain'},
                                      order_by='-sub_time', limit=30)
    for item in config_log_list:
        item['version'] = '%s-%s' % (item['sub_time'].strftime('%Y%m%d|%H%M%S'), item['admin_user'])
        config_logs.append(item)

    return render_to_response('admin/maintain/maintain.html', {
            'config': config,
            'current_maintain_status': current_maintain_status,
            'config_logs': config_logs
        },
        RequestContext(request))



@login_permission_required('publish')
def get_server_list(request):
    server_list = []
    item_list = []
    zone_list = UserZone.get_zone_list('running')
    for item in zone_list:
        try:
            cache_res = CacheTable.get('maintain_status_%s' % item[0], None)
            if not cache_res or cache_res[0] != _get_zone_maintain_status(item[0]):
                server_res = UserZone.call_server_api(item[0], 'get_maintain_status', {})
            else:
                server_res = cache_res
            res = ['red','red']
            if server_res[0]:
                res[0] = 'green'
            if server_res[1]:
                res[1] = 'green'
            if not cache_res and res == ['green', 'green']:
                CacheTable.set('maintain_status_%s' % item[0], server_res, 60*60*24)
        except:
            utils.print_err()
            res = ['gray','gray']
        item += res
        item_list.append(item)
        if len(item_list) >= 10:
            server_list.append(item_list)
            item_list = []
    else:
        server_list.append(item_list)
    server_list_body = loader.render_to_string('admin/maintain/server_list_body.html', {
        'server_list': server_list
        },
        RequestContext(request))
    return HttpResponse(json.dumps({'server_list_body': server_list_body}))

@login_permission_required('zone_maintain')
def change_full_maintain_status(request):
    """
    修改全服维护状态
    :param request:
            status:  0：维护 1：开服
    :return:
    """
    status = int(request.POST['status'])
    full_maintain_status = CacheTable.get('full_maintain_status', 1)
    # if status == full_maintain_status:
    #     return HttpResponse(json.dumps({'state': 'error', 'msg': u'维护状态未修改'}))
    CacheTable.set('full_maintain_status', status, 3600*24*365*100)
    zone_list = get_zones_status(push_all=True)
    current_maintain_status = _get_current_maintain_status()
    return HttpResponse(json.dumps({'state': 'success', 'zone_list': zone_list, 'current_maintain_status': current_maintain_status}))

@login_permission_required('zone_maintain')
def change_zone_maintain_status(request):
    """
    修改分区维护状态
    :param request:
            status:  0：维护 1：开服
    :return:
    """
    status = int(request.POST['status'])
    maintain_config = CacheTable.get('zone_maintain_config', '{}')
    maintain_config = eval(str(maintain_config))
    zone_maintain_list = maintain_config.get('zone_list', [])
    if len(zone_maintain_list) == 0:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'分区维护列表不能为空'}))
    CacheTable.set('zone_maintain_status', status, 3600*24*365*100)
    zone_list = get_zones_status(zone_maintain_list=zone_maintain_list)
    current_maintain_status = _get_current_maintain_status()
    return HttpResponse(json.dumps({'state': 'success', 'zone_list': zone_list, 'current_maintain_status': current_maintain_status}))

def _get_current_maintain_status():
    full_maintain_status = CacheTable.get('full_maintain_status', 1)
    zone_maintain_status = CacheTable.get('zone_maintain_status', 1)
    if full_maintain_status == 0:
        ## 全区维护
        current_maintain_status = 1
    elif zone_maintain_status == 0:
        ## 分区维护
        current_maintain_status = 2
    else:
        ## 正常运行
        current_maintain_status = 3
    return current_maintain_status


def get_zones_status(push_all=False, zone_maintain_list=None):
    zone_list = []
    for item in UserZone.get_zone_list('running'):
        zone_id = item[0]
        if push_all:
            zone_list.append([zone_id, 1])
        else:
            if zone_id in zone_maintain_list:
                zone_list.append([zone_id, 1])
            else:
                zone_list.append([zone_id, 0])
    return zone_list

def _get_zone_maintain_status(zone):
    full_maintain_status = CacheTable.get('full_maintain_status', 1)
    zone_maintain_status = CacheTable.get('zone_maintain_status', 1)
    maintain_config = CacheTable.get('zone_maintain_config', '{}')
    maintain_config = eval(str(maintain_config))
    zone_maintain_list = maintain_config.get('zone_list', [])
    status = 1
    if full_maintain_status == 0:
        status = 0
    elif zone_maintain_status == 0 and zone in zone_maintain_list:
        status = 0
    return status

@login_permission_required('zone_maintain')
def get_zone_maintain_status(request):
    """
    获取分区进程状态
    :param request:
    :return:
    """
    try:
        zone = request.GET['zone']
        cache_res = CacheTable.get('maintain_status_%s' % zone, None)
        if not cache_res or cache_res[0] != _get_zone_maintain_status(zone):
            server_res = UserZone.call_server_api(zone, 'get_maintain_status', {})
        else:
            server_res = cache_res
        res = ['red','red']
        if server_res[0]:
            res[0] = 'green'
        if server_res[1]:
            res[1] = 'green'
        if not cache_res and res == ['green', 'green']:
            CacheTable.set('maintain_status_%s' % zone, server_res, 60*60*24)
    except:
        # utils.print_err()
        res = ['gray','gray']
    return HttpResponse(json.dumps(res))

@login_permission_required('zone_maintain')
def push_zone_maintain_status(request):
    """
    推送长链分区维护状态
    :param request:
    :return:
    """
    zone = request.POST['zone']
    maintain_type = request.POST['maintain_type']
    maintain_status = int(request.POST['maintain_status'])

    maintain_config = CacheTable.get('zone_maintain_config', '{}')
    maintain_config = eval(str(maintain_config))
    white_list = maintain_config.get('white_list', [])
    info_msg = maintain_config.get('info_msg')
    try:
        UserZone.call_server_api(zone, 'change_maintain_status', {'maintain_type': maintain_type,
                                                         'maintain_status': maintain_status,
                                                         'white_list': white_list,
                                                         'info_msg': info_msg})
        CacheTable.rem('maintain_status_%s' % zone)
        return HttpResponse(json.dumps({'state': 'success'}))
    except:
        utils.print_err()
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'%s区维护推送失败' % zone}))