#-*- coding: utf-8 -*-
import os
import time
import json
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.conf import settings
from sqlalchemy import *
from admin.logic import login_permission_required
import json, urllib2
from game_lib.models.main import AdminLog
from game_lib.models.config import Configs, TestConfigs
from game_lib.models.cache import CacheTable
from game_lib.models.zone import Zones
from game_lib.logics import config_cache
import datetime, hashlib

from game_lib.logics.game_config import client_config_dict,system_simple,publish_config_extra
from game_lib.db.database import c_cache as cache

from game_lib.logics import game_config
from game_lib.common import utils
from game_lib.libs.model import Serializer
from game_lib.models.main import UserZone
from game_lib.logics import notice_config
from game_lib.logics import notice_cache

#打印内存占用的库
# from memory_profiler import profile

def push_to_configs(if_push=1):
    rpc_data = {}
    # config_data = dict([(key, getattr(game_config, key)) for key in [item[0] for item in reduce(lambda x, y: x+y, game_config.all_config_list, [])] if
    #         key not in ['pf_system_simple', 'client_config']
    #         ])
    config_data = dict([(key, getattr(game_config, key)) for key in [item[0] for item in reduce(lambda x, y: x+y, game_config.all_config_list, [])] if
            key in game_config.js_push_config_list
            ])
    config_data['version'] = game_config.version
    rpc_data['params'] = [if_push,config_data]
    
    rpc_data['method'] = 'sync_configs'
    cache.set(settings.CACHE_PRE+'if_push_%s' % game_config.version, if_push,60*60*10)

    
    try:
        json_params = json.dumps(rpc_data['params'][1],default=Serializer.json_default)
        for item in settings.BATTLE_SERVER:
            req = urllib2.Request(item+"/sync_configs/", json_params, {'content-type': 'application/json'})
            res = urllib2.urlopen(req, timeout=300).read()

    except:
        utils.print_err()


@login_permission_required('publish')
def jump_config_version(request):
    admin_user = request.session['admin_user']['username']
    take_config_type = CacheTable.get('take_config_type', 'setting')
    if take_config_type == 'setting':
        ConfigModel = Configs
    else:
        ConfigModel = TestConfigs

    config = ConfigModel.get('disp')
    config_value = eval(config.config_value)

    config.sub_time = datetime.datetime.now()
    config.admin_user = admin_user

    config_value['modify_config_list'] = []
    config_value['last_sub_time'] = config.sub_time-datetime.timedelta(minutes=1)

    configs_md5 = {}
    for k in get_publish_config_list():
        configs_md5[k] = get_config_md5(get_publish_config_dict()[k][1], take_config_type)
    config_value['configs_md5'] = configs_md5

    config.config_value = str(config_value)

    config.save()

    config_cache.update()
    config_cache.judge()

    AdminLog.add_adminlog(admin_user, 'jump_config_version', str(config_value))
    push_to_configs()
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('publish')
def force_update_config(request):
    config_cache.update()
    config_cache.judge()
    push_to_configs(if_push=0)
    return HttpResponse(json.dumps({'state':'success'}))

def get_config_md5(key, config_type='setting'):
    if config_type == 'setting':
        ConfigModel = Configs
    else:
        ConfigModel = TestConfigs
    if key == 'zone':
        return Zones.get_current_md5()
    else:
        return hashlib.md5(ConfigModel.get(key).config_value.strip()).hexdigest()

@login_permission_required('publish')
def push_server_config(request):
    config_cache.judge()
    zone = request.POST.get('zone')
    if zone:
        try:
            UserZone.push_server_config(zone)
            if zone.find(':') != -1:
                return HttpResponse(json.dumps({'state':zone.split(':')[1]}))
            else:
                return HttpResponse(json.dumps({'state':'success'}))
        except:
            utils.print_err()
            return HttpResponse(json.dumps({'state':'error'}))
    else:
        return HttpResponse(json.dumps({'state':'error'}))

@login_permission_required('publish')
def get_server_status(request):
    try:
        config_cache.judge()
        zone = request.GET['zone']
        cache_res = CacheTable.get(settings.CACHE_PRE+'srv_status%s%s' % (game_config.version,zone), None)
        if not cache_res:
            server_res = UserZone.call_server_api(zone, 'get_server_status', {}, timeout=1)
        else:
            server_res = cache_res
        res = ['red','red']

        if server_res[0] == game_config.version:
            res[0] = 'green'
        if server_res[1]:
            res[1] = 'green'
    except:
        res = ['gray','gray']
    if not cache_res and res[0] == 'green' and res[1] == 'green':
        CacheTable.set(settings.CACHE_PRE+'srv_status%s%s' % (game_config.version,zone), server_res, 60*60*24)
    return HttpResponse(json.dumps(res))

@login_permission_required('publish')
def get_server_list(request):
    config_cache.judge()
    kick = request.GET.get('kick')
    server_list = []
    item_list = []
    zone_list = UserZone.get_zone_list('running')
    for item in zone_list:
        try:
            cache_res = CacheTable.get(settings.CACHE_PRE+'srv_status%s%s' % (game_config.version,item[0]), None)
            if not cache_res:
                server_res = UserZone.call_server_api(item[0], 'get_server_status', {}, timeout=1)
            else:
                server_res = cache_res
            if kick == '2':
                server_res[0] = game_config.version
                res = ['green', 'green']
            else:
                res = ['red','red']

                if server_res[0] == game_config.version:
                    res[0] = 'green'
                if server_res[1]:
                    res[1] = 'green'
        except:
            res = ['gray','gray']
        if not cache_res and res[0] == 'green' and res[1] == 'green':
            CacheTable.set(settings.CACHE_PRE+'srv_status%s%s'% (game_config.version,item[0]), server_res, 60*60*24)
        item += res
        item_list.append(item)
        if len(item_list) >= 10:
            server_list.append(item_list)
            item_list = []
    else:
        server_list.append(item_list)
    server_list_body = loader.render_to_string('admin/publish/server_list_body.html', {
        'server_list': server_list
        },
        RequestContext(request))
    return HttpResponse(json.dumps({'server_list_body': server_list_body}))


@login_permission_required('update_notice', ajax=True)
def publish_notice(request):
    admin_user = request.session['admin_user']['username']
    notice_cache.update()
    notice_cache.judge()
    AdminLog.add_adminlog(admin_user, 'publish_notice', {})
    return HttpResponse(json.dumps({'state':'success'}))

def get_publish_config_list():
    return client_config_dict.keys() + publish_config_extra.keys()

def get_publish_config_dict():
    _config_dict = {}
    _config_dict.update(client_config_dict)
    _config_dict.update(publish_config_extra)
    return _config_dict

@login_permission_required('publish')
# @profile(precision=4, stream=open('memory_profilter.log', 'w+'))
def publish(request):
    config_cache.judge()
    last_publish = {
            'version': u'None',
            'time': u'未曾发布过',
            'color': 'gree',
            'admin_user': None,
            'modify_config_list': '',
            'last_version': '',
            }
    config_value = {
            }
    current_modify_config_list = get_publish_config_list()

    take_config_type = CacheTable.get('take_config_type', 'setting')
    if take_config_type == 'setting':
        ConfigModel = Configs
    else:
        ConfigModel = TestConfigs

    config = ConfigModel.get('disp')
    if config:
        if config.sub_time:
            last_publish['version'] = config.sub_time.strftime('%Y%m%d%H%M%S')
        config_v = eval(config.config_value)
        last_publish['time'] = str(config.sub_time)[:19]
        if config_v.get('color'):
            last_publish['color'] = str(config_v['color'])
        config_value = eval(config.config_value)


        last_publish['admin_user'] = config.admin_user
        last_publish['modify_config_list'] = '['+', '.join([get_publish_config_dict()[k][0] for k in config_value.get('modify_config_list', []) if k in get_publish_config_list()])+']'
        config.sub_time.strftime('%Y%m%d%H%M%S')
        last_publish['last_version'] = config_value['last_sub_time'].strftime('%Y%m%d%H%M%S') if config_value.get('last_sub_time') else None
        
        current_modify_config_list = []
        last_md5 = config_value.get('configs_md5', {})
        for k in get_publish_config_list():
            if k == 'notice':
                continue
            current_md5 = get_config_md5(get_publish_config_dict()[k][1], config_type=take_config_type)
            if k not in last_md5 or last_md5[k]!=current_md5:
                current_modify_config_list.append(k)
        if config_value.get('change_config_type', False):
            push_to_configs()
            config_value['change_config_type'] = False
            config.config_value = str(config_value)
            config.save()

    current_modify_config_dict = {}
    for k in get_publish_config_list():
        if k == 'notice':
            continue
        if k in current_modify_config_list:
            current_modify_config_dict[k] = (get_publish_config_dict()[k][0], True)
        else:
            current_modify_config_dict[k] = (get_publish_config_dict()[k][0], False)

    if request.POST:
        admin_user = request.session['admin_user']['username']
        color = 'red'
        if last_publish['color'] == 'red':
            color = 'gree'

        kick = int(request.POST.get('kick', 0))

        modify_config_list = request.POST.get('modify_config_list').strip().encode('utf-8')
        if not modify_config_list:
            return HttpResponse(json.dumps({'state':'error', 'msg': '配置文件没有被修改过'}))
        else:
            modify_config_list = modify_config_list.split(',')

        if set(modify_config_list)!=set(current_modify_config_list):
            return HttpResponse(json.dumps({'state':'error', 'msg': '发布过程中配置文件被修改'}))

        config_value = {}
        config_value['color'] = color
        config_value['modify_config_list'] = modify_config_list
        config_value['last_sub_time'] = None
        config_value['kick'] = kick

        #update configs md5
        configs_md5 = {}
        for k in get_publish_config_list():
            configs_md5[k] = get_config_md5(get_publish_config_dict()[k][1], config_type=take_config_type)
        config_value['configs_md5'] = configs_md5
        #end

        if not config:
            config = ConfigModel('disp')
            config_value['history_version'] = []
        else:
            config_value['last_sub_time'] = config.sub_time
            history_version = config_v.get('history_version', [])
            last_kick = config_v.get('kick', 1)
            #last_version = ''.join([str(item) for item in config.sub_time.timetuple()[:6]])
            last_version = config.sub_time.strftime('%Y%m%d%H%M%S')

            history_version.append((last_version, last_kick))
            config_value['history_version'] = history_version[-5:]
        config.config_value = str(config_value)
        config.sub_time = datetime.datetime.now()
        config.admin_user = admin_user
        config.save()


        config_cache.update()
        config_value['version'] = last_publish['version']
        config_value['take_config_type'] = take_config_type
        AdminLog.add_adminlog(admin_user, 'publish', str(config_value))
        config_cache.judge()

        ## kick为2的时候只发布短链配置，不推送js
        if kick != 2:
            push_to_configs(if_push=kick)
        return HttpResponse(json.dumps({'state':'success'}))


    json_params = json.dumps({}, default=Serializer.json_default)
    t = g = 0
    for item in settings.BATTLE_SERVER:
        t += 1
        try:
            req = urllib2.Request(item+"/get_version/", json_params, {'content-type': 'application/json'})
            res = urllib2.urlopen(req, timeout=3).read()
            res = json.loads(res)
            if res==game_config.version:
                g += 1
        except:
            utils.print_err()
            continue
    current_modify_config_dict_list = []
    for _item in game_config.all_config_list:
        for item in _item:
            v = current_modify_config_dict.get(item[0],None)
            if v:
                current_modify_config_dict_list.append([item[0],v])
    render_dict = {
        'take_config_type': take_config_type,
        'last_publish': last_publish,
        'current_modify_config_dict': current_modify_config_dict_list,
        't': t, 'g': g,
        }
    kick = request.GET.get('kick')
    if kick is not None:
        render_dict['kick'] = kick

    return render_to_response('admin/publish/publish.html', render_dict, 
        RequestContext(request))

def upload_config_cdn(disp_config):
    """
    上传配到CDN目录
    """
    config_path = settings.CONFIG_CDN_PATH
    if not config_path:
        return False
    if not os.path.exists(config_path):
        os.mkdir(config_path)
    if not disp_config or not disp_config.sub_time:
        return False
    version = disp_config.sub_time.strftime('%Y%m%d%H%M%S')
    version_path = os.path.join(config_path, version)
    if os.path.exists(version_path):
        return False
    os.mkdir(version_path)
    for k in game_config.client_config_dict:
        if k in ['pf_system_simple', 'client_config', 'help_msg']:
            continue

@login_permission_required('publish')
def get_publish_log(request):
    take_config_type = CacheTable.get('take_config_type', 'setting')
    publish_log_type = request.GET.get("publish_log_type", take_config_type)
    admin_logs = []
    for log in AdminLog.acquire_adminlogs('publish'):
        item = {}
        content = eval(str(log.content))
        if content.get('take_config_type', 'setting') != publish_log_type:
            continue
        modify_config_list = []
        for k in content.get('modify_config_list', []):
            if k in get_publish_config_list():
                modify_config_list.append([get_publish_config_dict()[k][0], k])
            else:
                if k == 'change_take_config_type':
                    if content['take_config_type'] == 'setting':
                        modify_config_list.append([u'切换正式配置', 'switch_setting'])
                    else:
                        modify_config_list.append([u'切换测试配置', 'switch_setting_test'])
        item['modify_config_list'] = modify_config_list
        item['subtime'] = str(log.subtime)[:19]
        item['admin_user'] = log.admin_user
        admin_logs.append(item)
    publish_log_body = loader.render_to_string('admin/publish/publish_log.html', {
        'admin_logs': admin_logs,
        'take_config_type': take_config_type
        },
        RequestContext(request))
    return HttpResponse(json.dumps({'publish_log_body': publish_log_body}))

@login_permission_required('publish')
def service_submit(request):
    service_notice = request.POST.get('service_notice').encode('utf-8').replace('\r','').strip()
    service_status = int(request.POST.get('service_status', 0))
    service_dict = {
            'service_status': service_status,
            'service_notice': service_notice,
            }
    cache.set(settings.CACHE_PRE+'server_service', service_dict, 60*60*10)

    service_log = Configs.get('service_log')
    if not service_log:
        service_log = Configs('service_log')
    admin_user = request.session['admin_user']['username']
    service_log.admin_user = admin_user
    service_log.sub_time = datetime.datetime.now()
    service_log.save()

    # rpc_data = {}
    # rpc_data['params'] = service_dict
    # rpc_data['method'] = 'push_to_service'
    # TcpChannel.send_data(rpc_data)

    return HttpResponse(json.dumps({'state':'success'}))



@login_permission_required('publish')
def publish_duplicate(request):
    config_cache.judge()
    server_list = []
    item_list = []
    manager_server_list = []
    duplicate_config = game_config.duplicate
    take_config_type = CacheTable.get('take_config_type', 'setting')
    port, server_port_list, manager_servers = game_config.system_simple['server_port']
    for manager_server in manager_servers:
        manager_server_addr = '%s:%s' % tuple(manager_server)
        manager_server_status = manager_server[::-1]
        try:
            res = UserZone.call_duplicate_server_api(manager_server_addr, 'get_server_version', {})
            if res[0] == game_config.version:
                manager_server_status.append('green')
            else:
                manager_server_status.append('red')
        except:
            manager_server_status.append('red')
        manager_server_list.append(manager_server_status)

    for item in server_port_list:
        for i in range(item[0]):
            server_addr = '%s:%s' % (item[1], port)
            item_res = [port, item[1]]
            try:
                res = UserZone.call_duplicate_server_api(server_addr, 'get_server_version', {})
                if res[0] == game_config.version:
                    item_res.append('green')
                else:
                    item_res.append('red')
            except:
                item_res.append('red')
            item_list.append(item_res)
            if len(item_list) >= 10:
                server_list.append(item_list)
                item_list = []
            port += 1
    else:
        server_list.append(item_list)


    return render_to_response('admin/publish/publish_duplicate.html', {
        'take_config_type': take_config_type,
        'server_list': server_list,
        'manager_server_list': manager_server_list
        }, 
        RequestContext(request))






















