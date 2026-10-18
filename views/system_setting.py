# -*- coding: utf-8 -*-
import re
import urllib2
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from admin.logic import login_permission_required
from game_lib.models.config import Configs, ConfigLog, TestConfigs, TestConfigLog
from game_lib.models.cache import CacheTable
from game_lib.logics import game_config, config_cache
import os
import zipfile
import json, hashlib
import datetime, time
from game_lib.db.database import c_cache as cache
from game_lib.models.main import AdminLog
from game_lib.libs.model import Serializer
from game_lib.common import utils

from publish import get_publish_config_list, get_config_md5, get_publish_config_dict


@login_permission_required(None, ajax=True)
def get_config_log(request):
    cid = request.POST.get('cid')
    config_type = request.POST.get('config_type')
    import time
    time.sleep(0.5)
    if config_type == 'setting':
        ConfigLogModel = ConfigLog
    else:
        ConfigLogModel = TestConfigLog
    config_log = ConfigLogModel.get(cid)
    return HttpResponse(json.dumps({'config_type': config_type, 'config_value': str(config_log.cval)}))


@login_permission_required(None, ajax=True)
def get_config_value(request):
    config_name = request.GET.get('config_name')
    config_type = request.GET.get('config_type')
    if config_type == 'test_setting':
        ConfigModel = TestConfigs
    else:
        ConfigModel = Configs
    config = ConfigModel.get(config_name)
    return HttpResponse(json.dumps({'config_type': config_type, 'config_value': str(config.config_value)}))


@login_permission_required(None)
def download_configs(request):
    config_type = request.GET.get('config_type', 'setting')
    now = datetime.datetime.now().strftime('%Y%m%d%H%M')
    if config_type == 'test_setting':
        ConfigModel = TestConfigs
        dir_name = 'test_configs_%s' % now
    else:
        ConfigModel = Configs
        dir_name = 'configs_%s' % now
    config_path = os.path.join(settings.BASEROOT, 'download')
    if not os.path.exists(config_path):
        os.makedirs(config_path)
    for i in os.listdir(config_path):
        p = os.path.join(config_path, i)
        if os.path.isdir(p):
            for f in os.listdir(p):
                os.remove(os.path.join(p, f))
            os.rmdir(p)
        else:
            os.remove(os.path.join(config_path, i))
    file_path = os.path.join(config_path, dir_name)
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    zip_filename = os.path.join(config_path, '%s_%s.zip' % (settings.WHERE, dir_name))
    zipf = zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED)
    for item in game_config.all_config_list:
        for tip in item:
            if tip[0] == 'zone':
                continue
            config = ConfigModel.get(tip[0])
            if not config:
                continue
            config_value = config.config_value
            filename = os.path.join(file_path, '%s(%s).txt' % (tip[0], tip[1]))
            f = open(filename, 'w+')
            f.write(config_value)
            f.close()
            zipf.write(filename, '%s(%s).txt' % (tip[0], tip[1]))
    zipf.close()

    def file_iterator(file_path, chunk_size=512):
        """
        文件生成器,防止文件过大，导致内存溢出
        :param file_path: 文件绝对路径
        :param chunk_size: 块大小
        :return: 生成器
        """
        with open(file_path, mode='rb') as f:
            while True:
                c = f.read(chunk_size)
                if c:
                    yield c
                else:
                    break

    # 设置响应头
    try:
        response = HttpResponse(file_iterator(zip_filename))
        # 以流的形式下载文件,这样可以实现任意格式的文件下载
        response['Content-Type'] = 'application/octet-stream'
        # Content-Disposition就是当用户想把请求所得的内容存为一个文件的时候提供一个默认的文件名
        response['Content-Disposition'] = 'attachment;filename=%s_%s.zip' % (settings.WHERE, dir_name)
        return response
    except:
        return HttpResponse('Download Error')


@login_permission_required('switch_setting', ajax=True)
def change_take_config_type(request):
    admin_user = request.session['admin_user']['username']
    t = time.time()
    take_config_type = request.POST['take_config_type']
    CacheTable.set('take_config_type', take_config_type, 60 * 60 * 24 * 365 * 100)
    if take_config_type == 'setting':
        ConfigsModel = Configs
    else:
        ConfigsModel = TestConfigs
    config = ConfigsModel.get('disp')
    if config:
        config_value = eval(config.config_value)
    else:
        config_value = {}
    last_md5 = config_value.get('configs_md5', {})
    modify_config_list = []
    for k in get_publish_config_list():
        if k == 'notice':
            continue
        current_md5 = get_config_md5(get_publish_config_dict()[k][1], config_type=take_config_type)
        if k not in last_md5 or last_md5[k] != current_md5:
            modify_config_list.append(k)
    if modify_config_list:
        configs_md5 = {}
        for k in get_publish_config_list():
            configs_md5[k] = get_config_md5(get_publish_config_dict()[k][1], config_type=take_config_type)
        config_value['configs_md5'] = configs_md5
        config_value['last_sub_time'] = None
    config_value['modify_config_list'] = modify_config_list
    if config:
        config_value['last_sub_time'] = config.sub_time
        history_version = config_value.get('history_version', [])
        last_kick = config_value.get('kick', 1)
        last_version = config.sub_time.strftime('%Y%m%d%H%M%S')

        history_version.append((last_version, last_kick))
        config_value['history_version'] = history_version[-5:]
    else:
        config = ConfigsModel('disp')
        config_value['history_version'] = []
    config_value['change_config_type'] = True
    config.config_value = str(config_value)
    config.sub_time = datetime.datetime.now()
    config.admin_user = request.session['admin_user']['username']
    config.save()
    config_value['modify_config_list'].insert(0, 'change_take_config_type')
    config_value['take_config_type'] = take_config_type
    AdminLog.add_adminlog(admin_user, 'publish', str(config_value))
    config_cache.update()
    config_cache.judge()
    return HttpResponse(json.dumps({'state': 'success'}))


@login_permission_required('system_setting')
def setting(request):
    return _setting(request, where='system')


@login_permission_required('system_setting')
def test_setting(request):
    return _setting(request, where='system', config_type='test_setting')


@login_permission_required('update_notice')
def setting_notice(request):
    return _setting(request, where='notice')


@login_permission_required(None, ajax=True)
def setting_p(request):
    return _setting_p(request, where='system')


@login_permission_required('test_setting', ajax=True)
def test_setting_p(request):
    return _setting_p(request, where='system', config_type='test_setting')


@login_permission_required(None, ajax=True)
def setting_p_notice(request):
    return _setting_p(request, where='notice')


def _setting_p(request, where='system', config_type='setting'):
    try:
        if where == 'flash':
            config_name_list = game_config.flash_config_name_list
        elif where == 'system':
            config_name_list = game_config.system_config_name_list
        elif where == 'notice':
            config_name_list = [[('notice', u'更新公告', 0), ]]

        config_name = request.REQUEST.get('config_name')
        if config_type == 'test_setting':
            ConfigModel = TestConfigs
        else:
            ConfigModel = Configs
        config = ConfigModel.get(config_name)

        session_user = request.session['admin_user']
        if session_user['username'] != 'admin' and config_type == 'setting':
            if 'system_setting_p' not in session_user['permissions']:
                if config_name in ['notice'] and 'update_notice' in session_user['permissions']:
                    pass
                else:
                    if 'system_setting_p2' not in session_user['permissions']:
                        return HttpResponse(json.dumps({'state': 'error', 'msg': u'permissions required'}))
                    else:
                        if config_name not in ['return_msg', 'return_msg_en', 'notice', 'ploy',
                                               'ope_msg', 'ope_msg_en', 'ope_msg_tw', 'ope_msg_viet',
                                               'ope_msg_ja', 'ope_msg_kr', 'ope_msg_th', 'ope_msg_ar']:
                            return HttpResponse(json.dumps({'state': 'error', 'msg': u'permissions required'}))

        now = datetime.datetime.now()
        if config:
            cks = []
            for item in config_name_list:
                for ck, cv, i in item:
                    cks.append(ck)
                    if config_name == ck:
                        config.desc = cv
            if request.POST:
                if config_name not in cks:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'permissions required'}))
                ch_version = request.POST.get('ch_version')
                if ch_version != hashlib.md5(config.config_value).hexdigest():
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'其他管理员已修改此配置，请刷新重来'}))
                config_value = request.POST.get('config_value').encode('utf-8').replace('\r', '').strip()
                if ch_version == hashlib.md5(config_value).hexdigest():
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'配置未修改'}))
                if not config_name or not config_value:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'请填写完整'}))
                try:
                    py_val = eval(config_value)
                    if config_name == 'zone':
                        port_list = []
                        for k, v in py_val.items():
                            if v[1] and v[1][1]:
                                if v[1][1] in port_list:
                                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'存在重复的分区端口'}))
                                port_list.append(v[1][1])
                    from pyamf.amf3 import ByteArray
                    byte = ByteArray()
                    byte.writeObject(py_val)
                except Exception, e:
                    # from game_lib.common import utils
                    utils.print_err()
                    try:
                        return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.text}))
                    except:
                        return HttpResponse(json.dumps({'state': 'error', 'msg': 'invalid syntax:%s' % e.message}))
                if not config:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'该配置不存在'}))
                config.config_value = config_value
                config.sub_time = now
                config.admin_user = request.session['admin_user']['username']
                # AdminLog.add_adminlog(config.admin_user, 'edit_setting', str({'setting': config_name, 'md5': hashlib.md5(config_value).hexdigest()}))
                # AdminLog.add_adminlog(config.admin_user, 'edit_setting', str({'setting': config_name, 'config_value': eval(config_value)}))
                system_simple_key_list = ['system_simple', 'pf_system_simple', 'client_config']
                if config_name in system_simple_key_list:
                    sys_config_value = eval(config_value)
                    for sk in system_simple_key_list:
                        if config_name == sk:
                            continue
                        sk_config_value = eval(ConfigModel.get(sk).config_value)
                        for k in sys_config_value.keys():
                            if k in sk_config_value.keys():
                                return HttpResponse(
                                    json.dumps({'state': 'error', 'msg': u'系统杂项类配置key重复:%s----%s' % (config.desc, k)}))
                config.save()
                if config_type == 'setting':
                    ConfigLogModel = ConfigLog
                else:
                    ConfigLogModel = TestConfigLog
                config_log = ConfigLogModel()
                config_log.cname = config_name
                config_log.cval = config_value
                config_log.sub_time = now
                config_log.admin_user = request.session['admin_user']['username']
                config_log.save()
                new_ch_version = hashlib.md5(config.config_value).hexdigest()
                return HttpResponse(json.dumps({'state': 'success', 'ch_version': new_ch_version}))
        return HttpResponse(json.dumps({'error': u'配置不存在'}))
    except:
        utils.print_err()


def _setting(request, where='system', config_type='setting'):
    if where == 'flash':
        config_name_list = game_config.flash_config_name_list
    elif where == 'system':
        config_name_list = game_config.system_config_name_list
    elif where == 'notice':
        config_name_list = [[('notice', u'更新公告', 0), ]]
    config_name = request.REQUEST.get('config_name')
    log_limit = request.REQUEST.get('log_limit', None)
    if log_limit is None:
        log_limit = 0
        _limit = 20
    else:
        log_limit = int(log_limit) + 1
        _limit = log_limit * 200
    if config_type == 'test_setting':
        ConfigModel = TestConfigs
    else:
        ConfigModel = Configs
    session_user = request.session['admin_user']
    if settings.TEST_CONFIG_ENABLE and 'switch_setting' in session_user['permissions']:
        can_switch_setting = True
    else:
        can_switch_setting = False
    take_config_type = CacheTable.get('take_config_type', 'setting')  # 使用正式配置setting/测试配置test_setting
    config = ConfigModel.get(config_name)
    log_list = []
    log_dropdown = []

    ch_version = None
    if config:
        to_json = request.REQUEST.get('to_json')
        if to_json:
            c_value = eval(config.config_value)
            jc_value = json.dumps(c_value, default=Serializer.json_default)
            return HttpResponse(jc_value)
        cks = []
        for item in config_name_list:
            for ck, cv, i in item:
                cks.append(ck)
                if config_name == ck:
                    config.desc = cv
        if config_type == 'setting':
            ConfigLogModel = ConfigLog
        else:
            ConfigLogModel = TestConfigLog
        config_log_list = ConfigLogModel.query(attrs=['id', 'sub_time', 'admin_user'], condition={'cname': config_name,},
                                          order_by='-sub_time', limit=_limit)
        for item in config_log_list:
            item['version'] = '%s-%s' % (item['sub_time'].strftime('%Y%m%d|%H%M%S'), item['admin_user'])
            log_list.append(item)
        ch_version = hashlib.md5(config.config_value).hexdigest()
    config_len = 0
    if config:
        config_len = len(json.dumps(eval(config.config_value), default=Serializer.json_default).encode('utf-8'))
    redbag_cache = cache.get(settings.CACHE_PRE + '_redbag', {})
    redbag_cache_len = len(redbag_cache)
    redbag_cache2 = cache.get(settings.CACHE_PRE + '_redbag2', [])
    redbag_cache2_len = len(redbag_cache2)
    server_raise_msg_list = []
    return_msg_list = []
    ope_msg_list = []
    ploy_list = []
    map_list = []
    city_list = []
    # 修正配置列表，追加更新时是否导入标识， 0不导入，1导入
    correct_config_name_list = []
    for item in config_name_list:
        _config = []
        for _item in item:
            _item = list(_item)
            if _item[0] == 'zone':
                continue
            if _item[0] in game_config.ignore_export_config_list:
                _item.append(0)
            else:
                _item.append(1)
            if _item[0] == 'server_raise_msg':
                _item.append(server_raise_msg_list)
            elif _item[0] == 'return_msg':
                _item.append(return_msg_list)
            elif _item[0] == 'ope_msg':
                _item.append(ope_msg_list)
            elif _item[0] == 'ploy':
                _item.append(ploy_list)
            elif _item[0] == 'city':
                _item.append(city_list)
            elif _item[0] == 'map':
                _item.append(map_list)
            else:
                _item.append('no')
            if _item[0].startswith('server_raise_msg_'):
                _item[1] = _item[1].split('-')[-1][0]
                server_raise_msg_list.append(_item)
                continue
            elif _item[0].startswith('return_msg_'):
                _item[1] = _item[1].split('-')[-1][0]
                return_msg_list.append(_item)
                continue
            elif _item[0].startswith('ope_msg_'):
                _item[1] = _item[1].split('-')[-1][0]
                ope_msg_list.append(_item)
                continue
            elif _item[0].startswith('ploy_'):
                _item[1] = '%s%s' % (_item[1].split('-')[0][0], _item[1].split('-')[1])
                ploy_list.append(_item)
                continue
            elif re.match(r'city_\d{1}', _item[0]):
                _item[1] = '%s%s' % (_item[1][0], _item[1][-1])
                city_list.append(_item)
                continue
            elif re.match(r'map_\d{1}', _item[0]):
                _item[1] = _item[1][1:]
                map_list.append(_item)
                continue
            _config.append(_item)
        correct_config_name_list.append(_config)
    config_name_list1 = correct_config_name_list[:3]
    if where != 'notice':
        config_name_list2 = [correct_config_name_list[3]]
        config_name_list3 = [correct_config_name_list[4]]
    else:
        config_name_list2 = []
        config_name_list3 = []

    ## 更新公告发布日志
    admin_logs = []
    if where == 'notice':
        for log in AdminLog.acquire_adminlogs('publish_notice'):
            content = eval(str(log.content))
            item = {}
            item['subtime'] = str(log.subtime)[:19]
            item['admin_user'] = log.admin_user
            admin_logs.append(item)
    return render_to_response('admin/system_setting/system_setting.html', {
        'can_switch_setting': can_switch_setting,  #配置切换功能是否开启并拥有权限
        'take_config_type': take_config_type,
        'config_type': config_type,
        'config_name_list1': config_name_list1,
        'config_name_list2': config_name_list2,
        'config_name_list3': config_name_list3,
        'log_list': log_list,
        'log_limit': log_limit,
        'log_dropdown': log_dropdown,
        'config': config,
        'where': where,
        'ch_version': ch_version,
        'config_len': config_len,
        'redbag_cache': redbag_cache,
        'redbag_cache_len': redbag_cache_len,
        'redbag_cache2': redbag_cache2,
        'redbag_cache2_len': redbag_cache2_len,
        'admin_logs': admin_logs,
    },
                              RequestContext(request))
