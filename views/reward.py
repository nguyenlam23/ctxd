#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
import settings
import datetime, random
from admin.logic import login_permission_required
from copy import deepcopy as copy
import json
from sqlalchemy import *
from game_lib.logics import game_config, reward_cache, reward_config
from game_lib.common import utils
from game_lib.models.main import AdminLog, UserZone, SendUcoinLog
from game_lib.models.reward import Rewards,RewardCode
from game_lib.db.database import AdminLog_table, RewardCode_table, send_ucoin_log_table as ul
import xlrd 
from hashlib import md5
import time
import cPickle as pickle
from admin.pager import Pager
import urllib2
import zlib

input_key_list = [
        ['coin', u'Coin', '1000000'],
        ['gold', u'钱', '1000000'],
        ['food', u'粮', '1000000'],
        ['wood', u'木', '1000000'],
        ['iron', u'铁', '1000000'],
        ['merit', u'功勋', '1000000'],
        ]

## 道具奖励最小与最大数量
if settings.WHERE in ['local', 'war_local']:
    reward_count_limit = {
        'sale_depot': [1, 10000],
        'star': [1, 10000],
        'prop': [1, 1000000],
        'soul': [1, 10000],
        'native': [1, 10000],
    }
else:
    reward_count_limit = {
        'sale_depot': [1, 100],
        'star': [1, 100],
        'prop': [1, 10000],
        'soul': [1, 100],
        'native': [1, 100],
    }

def push_to_reward_config():
    return False



def get_reward_permission_level(request, reward_type):
    """
    获取奖励编辑的最高级别权限
    :param request:
    :param reward_type: 发奖类型
            reward_edit_admin：邮件发奖
            reward_edit_common：一般奖励
            reward_edit_code：兑奖码
    :return: level
            None: 未分配权限
            1 一级权限
            2 二级权限
            3 三级权限（最高）
    """
    session_user = request.session.get('admin_user')
    reward_permission_levels = []
    if session_user['username'] == 'admin':
        return 3
    for p in session_user['permissions']:
        if p.startswith(reward_type):
            reward_permission_levels.append(int(p.split('|')[1]))
    if len(reward_permission_levels) == 0:
        return None
    else:
        return max(reward_permission_levels)

def check_item_permission(item_id, item_type, user_level):
    item_level = game_config.help_msg['right'][item_type].get(item_id)
    if user_level is None:
        checked = False
    else:
        if user_level == 3:
            checked = True
        else:
            if item_level is not None and user_level >= item_level:
                checked = True
            else:
                checked = False
    return checked

def check_edit_reward_permission(request, reward_type, reward_items):
    user_level = get_reward_permission_level(request, reward_type)
    can_edit = True
    if user_level == 3:
        return can_edit
    for item_id in reward_items.keys():
        if item_id in ['wood', 'iron', 'gold', 'food', 'coin', 'merit']:
            continue
        if item_id.startswith('saledepot'):
            right_config = game_config.help_msg['right']['saledepot']
        elif item_id.startswith('star'):
            right_config = game_config.help_msg['right']['star']
        elif item_id.startswith('item'):
            right_config = game_config.help_msg['right']['prop']
        elif item_id.startswith('equip'):
            right_config = game_config.help_msg['right']['equip']
        elif item_id.startswith('title'):
            right_config = game_config.help_msg['right']['title']
        elif item_id.startswith('soul'):
            right_config = game_config.help_msg['right']['soul']
        else:
            right_config = {}
        item_level = right_config.get(item_id)
        if user_level is None or item_level is None or user_level < item_level:
            can_edit = False
            break
    return can_edit

def get_reward_content(request, reward_type, rewards_dict={}):
    """

    :param rewards_dict:
    :param kwargs:
            session_user: {}
            reward_type: 发奖类型
    :return:
    """
    user_reward_level = get_reward_permission_level(request, reward_type)
    sale_list = get_sale_list(user_reward_level, rewards_dict)
    star_list = get_star_list(user_reward_level, rewards_dict)
    soul_list = get_soul_list(user_reward_level, rewards_dict)
    prop_list = get_prop_list(user_reward_level, rewards_dict)
    face_list = get_face_list(user_reward_level, rewards_dict)
    native_list = get_native_list(user_reward_level, rewards_dict)
    equip_list = []
    if rewards_dict.has_key('equip'):
        equip_list = rewards_dict['equip']
    equip_list = get_equip_list(user_reward_level, equip_list)

    title_list = []
    if rewards_dict.has_key('title'):
        title_list = rewards_dict['title']
    title_list = get_title_list(user_reward_level, title_list)
    return {
        'title_list': title_list,
        'equip_list': equip_list,
        'star_list': star_list,
        'sale_list': sale_list,
        'soul_list': soul_list,
        'face_list': face_list,
        'all_prop_list': prop_list,
        'native_list': native_list,
        'input_list': get_input_content(request=None,dt=rewards_dict),
        }

def get_sale_list(user_level, dt={}):
    """

    :param user_level:
    :param dt:
    :return:
        0: 可发送道具的数量
        1: 单次发送数量限制
        2: 道具列表
    """
    sale_list = []
    item_list = []
    pay_config = game_config.pay_config
    config_list = sorted(game_config.system_simple['sale_depot'].items(), key=lambda x:x[0])
    sale_pay_config = game_config.system_simple['sale_pay']
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'saledepot', user_level):
            continue
        for x,y in sale_pay_config.items():
            if v[0] == y[1]:
                old_pid = y[0]
                new_pid = x
                break
        old_pay_money = pay_config[old_pid][0]
        new_pay_money = pay_config[new_pid][0]
        a_list = [k, "%s`%s-%s" % (k, old_pay_money,old_pay_money-new_pay_money)]
        if k in dt.keys():
            a_list.append(dt[k])
        item_list.append(a_list)
        if len(item_list) >= 5:
            sale_list.append(item_list)
            item_list = []
    else:
        sale_list.append(item_list)

    return sum([len(i) for i in sale_list]), sale_list, reward_count_limit['sale_depot']

def get_soul_list(user_level, dt={}):
    soul_list = []
    item_list = []
    config_list = sorted(game_config.soul.items(), key=lambda x:x[0])
    return_msg_config = game_config.return_msg
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'soul', user_level):
            continue
        name = return_msg_config.get(k, k)
        a_list = [k, "%s`%s" % (k,name)]
        soul_k = '%s01' % k
        if soul_k in dt.keys():
            a_list.append(dt[soul_k])
        item_list.append(a_list)
        if len(item_list) >= 5:
            soul_list.append(item_list)
            item_list = []
    else:
        soul_list.append(item_list)

    return sum([len(i) for i in soul_list]), soul_list, reward_count_limit['star']

def get_star_list(user_level, dt={}):
    star_list = []
    item_list = []
    config_list = sorted(game_config.star.items(), key=lambda x:x[0])
    return_msg_config = game_config.return_msg
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'star', user_level):
            continue
        name = return_msg_config.get(v['name'], k)
        a_list = [k, "%s`%s" % (k,name)]
        star_k = '%s01' % k
        if star_k in dt.keys():
            a_list.append(dt[star_k])
        item_list.append(a_list)
        if len(item_list) >= 5:
            star_list.append(item_list)
            item_list = []
    else:
        star_list.append(item_list)

    return sum([len(i) for i in star_list]), star_list, reward_count_limit['star']

def get_native_list(user_level, dt={}):
    native_list = []
    item_list = []
    config_list = sorted(game_config.native.items(), key=lambda x:(x[1]['type'], x[0]))
    return_msg_config = game_config.return_msg
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'native', user_level):
            continue
        name = return_msg_config.get('%s_name' % k, k)
        a_list = [k, "%s`%s" % (k,name)]
        if k in dt.keys():
            a_list.append(dt[k])
        item_list.append(a_list)
        if len(item_list) >= 5:
            native_list.append(item_list)
            item_list = []
    else:
        native_list.append(item_list)

    return sum([len(i) for i in native_list]), native_list, reward_count_limit['native']

def get_prop_list(user_level, dt={}):
    prop_dict = {}
    item_list_dict = {}
    return_msg_config = game_config.return_msg
    config_list = sorted(game_config.prop.items(), key=lambda x:int(x[0][4:]))
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'prop', user_level):
            continue
        name = return_msg_config.get(v['name'], k)
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
    prop_list = sorted(prop_dict.items(), key=lambda x:x[0])

    return sum([len(i) for i in prop_list]), prop_list, reward_count_limit['prop']

def get_equip_list(user_level, dt=[]):
    equip_list = []
    item_list = []
    config_list = sorted(game_config.equip.items(), key=lambda x:x[0])
    return_msg_config = game_config.return_msg
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'equip', user_level):
            continue
        name = return_msg_config.get(v['name'], k)
        chk = 0
        if k in dt:
            chk = 1
        a_list = [k, "%s`%s" % (k,name), chk]
        item_list.append(a_list)
        if len(item_list) >= 5:
            equip_list.append(item_list)
            item_list = []
    else:
        equip_list.append(item_list)

    return sum([len(i) for i in equip_list]), equip_list

def get_title_list(user_level, dt=[]):
    title_list = []
    item_list = []
    config_list = sorted(game_config.title.items(), key=lambda x:x[0])
    return_msg_config = game_config.return_msg
    for k,v in config_list:
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(k, 'title', user_level):
            continue
        name = return_msg_config.get(k, k)
        chk = 0
        if k in dt:
            chk = 1
        a_list = [k, "%s`%s" % (k,name), chk]
        item_list.append(a_list)
        if len(item_list) >= 5:
            title_list.append(item_list)
            item_list = []
    else:
        title_list.append(item_list)

    return sum([len(i) for i in title_list]), title_list

def get_face_list(user_level, dt=[]):
    face_list = []
    item_list = []
    config_list = sorted(game_config.title.items(), key=lambda x:x[0])
    return_msg_config = game_config.return_msg
    for face_id in game_config.system_simple['cfg_face'].get('3', {}).get('ids', {}):
        ## 检测用户是否有该道具的发送权限
        if not check_item_permission(face_id, 'face', user_level):
            continue
        name = return_msg_config.get('face_%s' % face_id, face_id)
        chk = 0
        if face_id in dt:
            chk = 1
        a_list = [face_id, "%s`%s" % (face_id,name), chk]
        item_list.append(a_list)
        if len(item_list) >= 5:
            face_list.append(item_list)
            item_list = []
    else:
        face_list.append(item_list)

    return sum([len(i) for i in face_list]), face_list


@login_permission_required('code_rewards')
def get_reward_code_list(request):
    rid = request.REQUEST.get('id')
    reward = Rewards.get(rid)
    code_num = reward.obj_content['code_num']
    if reward.obj_content['repeat_use']:
        code_num = 1
    key = reward.obj_content['key']
    res = ''
    for item in range(1, code_num+1):
        item = str(item)
        s = '%s%s' % (key,item)
        ms = md5(s).hexdigest()
        n = 14-len(item)-len(str(rid))
        code = '%s-%s-%s' % (rid,ms[:n],item)
        res += '%s</br>' % code
    return HttpResponse(res)


@login_permission_required('code_rewards')
def code_rewards(request):
    now = datetime.datetime.now()
    view_delete = int(request.GET.get('view_delete', 0))
    content_open = int(request.GET.get('content_open', 0))
    order_by = request.GET.get('order_by', None)
    rewards = Rewards.get_admin_code_rewards(view_delete, order_by=order_by)
    rewards = list(rewards)
    p_params = {'view_delete': view_delete}
    if order_by is not None:
        p_params['order_by'] = order_by

    page = int(request.GET.get('page','1')) 
    page_size = 30
    page_list_num = 10
    total = len(rewards)
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num, parameter=p_params)
    rewards = rewards[offset:offset+page_size]
    rewards_list = []
    language_config = game_config.system_simple['language']
    for item in rewards:
        pos = 0
        _item = item.dumps(shallow=True)
        if _item['reward_obj'] == 'code_reward':
            _item['reward_obj_cn'] = u'兑奖码发奖'
        for lan in language_config:
            item_name_info = _item['name_info'].get(lan[0], None)
            if item_name_info:
                _item['name'], _item['info_title'] = item_name_info
                _item['info'] = _item['info_title'][:3]
                break
        rewards_dict_info = parse_properties_str(_item['rewards_dict'])
        _item['rewards_dict_info'] = rewards_dict_info[:3]
        _item['rewards_dict_info_title'] = rewards_dict_info
        pfs_str = ','.join(item.pfs)
        _item['pfs'] = pfs_str
        _item['pfs_info'] = pfs_str[:3]

        obj_content = item.obj_content
        table = RewardCode_table
        if obj_content['repeat_use']:
            code = select([table], and_(table.c.rid==item.id)).execute().fetchone()
            if code:
                used_times = code['uid']
            else:
                used_times = 0
            rest_times = obj_content['code_num'] - used_times
                
            _item['count'] = u'可重复使用,剩余(%s)次' % rest_times
        else:
            a = select([func.count(table.c.code).label('cc')], and_(table.c.rid==item.id)).execute().fetchone()['cc']
            b = obj_content['code_num']
            _item['count'] =  '%s/%s/%s%%' % (a, b, '%.2f' % (a*1.0/b*100))

        if item.status != 2 and item.end_time < now:
            ## 已过期
            _item['status'] = 4
        rewards_list.append(_item)
    return render_to_response('admin/reward/code_rewards.html', {
        'rewards':rewards_list,
        'p': p,
        'page':page,
        'view_delete': view_delete,
        'content_open': content_open,
        }, 
        RequestContext(request))


@login_permission_required('reward_edit_code')
def edit_reward_code_p(request):
    code_num = request.POST.get('code_num')
    repeat_use = request.POST.get('repeat_use')
    name = request.POST.get('name') 
    info = request.POST.get('info')
    icon = request.POST.get('icon', '')
    try:
        group = int(request.POST.get('group', '').strip() or -1)
        assert group==-1 or group>0
    except Exception, e: 
        return HttpResponse(u'<script>alert("分组只能是大于0的数字");history.go(-1);</script>')

    user_ip = request.META['HTTP_X_FORWARDED_FOR'].split(",")[0] if 'HTTP_X_FORWARDED_FOR' in request.META else request.META.get('REMOTE_ADDR', '')
    add_time= start_time = datetime.datetime.now()

    end_date = request.POST.get('end_date') 
    end_hour = request.POST.get('end_hour')
    end_minute = request.POST.get('end_minute') 
    end_time = utils.parse_time_str('%s %s:%s:00' % (end_date,end_hour,end_minute)) 



    try:
        if code_num:
            code_num = int(code_num)
        if code_num <=0:
            raise
    except:
        return HttpResponse(u'<script>alert("请正确填写兑奖码数量");history.go(-1);</script>')



    status, rewards_dict = get_rewards_dict(request)
    if not status:
        return HttpResponse(u'<script>alert("%s");history.go(-1);</script>' % rewards_dict)
    nafo_error,name_info = get_name_info(request)
    if nafo_error:
        return name_info
    input_error,input_dict = get_input_content(request)
    if input_error:
        return input_dict
    if input_dict:
        rewards_dict.update(input_dict)


    if not rewards_dict:
        return HttpResponse(u'<script>alert("请选择发奖励内容");history.go(-1);</script>')
    pfs = request.POST.getlist('pfs')
    if not pfs:
        return HttpResponse(u'<script>alert("请勾选pf");history.go(-1);</script>')

    id = request.POST.get('id', None)
    if not id:
        obj_content = {'key': str(int(time.time())),'group': group, 'code_num': code_num, 'repeat_use': repeat_use}
    else:
        reward = Rewards.get(int(id))
        obj_content = reward.obj_content
        obj_content['group'] = group
        obj_content['code_num'] = code_num
        obj_content['repeat_use'] = repeat_use

    if not check_edit_reward_permission(request, 'reward_edit_code', rewards_dict):
        return HttpResponse(u'<script type=\'text/javascript\'>alert("有超出权限的道具存在，不可操作！");history.go(-1);</script>')
    rid = Rewards.save_reward(id,name_info,pfs,'code_reward',obj_content,start_time,end_time,request.session['admin_user']['username'],rewards_dict,user_ip, add_time)
    reward_cache.update()
    reward_cache.judge()
    push_to_reward_config()
    return HttpResponseRedirect(settings.BASE_URL+'/admin/reward/code_rewards/')



@login_permission_required('reward_edit_code')
def edit_reward_code(request):
    id = request.GET.get('id', None)
    reward = None

    rewards_dict = {}
    pfs = []
    name_info = {}
    code_len = None
    if id:
        reward = Rewards.get(int(id))
        end_time_str = utils.get_time_str(reward.end_time)
        reward.end_date = end_time_str[:10]
        reward.end_hour = end_time_str[11:13]
        reward.end_minute = end_time_str[14:16]
        rewards_dict = reward.rewards_dict

        name_info = reward.name_info
        pfs = reward.pfs

        if not check_edit_reward_permission(request, 'reward_edit_common', reward.rewards_dict):
            return HttpResponse(u'<script type=\'text/javascript\'>alert("有超出权限的道具存在，不可操作！");history.go(-1);</script>')


    return_dict = {
        'hours': ['%02d' % item for item in xrange(0,24)],
        'minutes': ['%02d' % item for item in xrange(0,60)],
        'reward': reward,
        'code_len': code_len,
        'pf_list': get_pf_list(pfs),
        'nafo_list': get_nafo_list(name_info),
        }
    reward_content_dict = get_reward_content(request, 'reward_edit_code', rewards_dict=rewards_dict)
    return_dict.update(reward_content_dict)
    


    return render_to_response('admin/reward/edit_reward_code.html', return_dict, 
        RequestContext(request))

@login_permission_required('reward_edit_common')
def edit_reward(request):
    id = request.GET.get('id', None)
    reward = None
    user_lv_chk = False
    effort_lv_chk = False
    login_time_chk = False
    add_time_chk = False
    rewards_dict = {}
    pfs = []
    name_info = {}
    if id:
        reward = Rewards.get(int(id))
        pfs = reward.pfs
        name_info = reward.name_info
        if reward.obj_content.has_key('zone_list'):
            reward.zone_list = ','.join(reward.obj_content['zone_list'])
        else:
            reward.zone_list = 'all'
        if reward.reward_obj == 'user':
            reward.obj_content['uids_len'] = len(reward.obj_content['uids'])
            reward.obj_content['uids'] = ','.join(reward.obj_content['uids'])
            reward.show_uid_txt = '1'
        

        if reward.reward_obj == 'condition': 
            if reward.obj_content['condition'].has_key('user_lv'):
                user_lv_chk = True
            if reward.obj_content['condition'].has_key('effort_lv'):
                effort_lv_chk = True
            if reward.obj_content['condition'].has_key('login_time'):
                login_time_chk = True
                cond_login_time_str = reward.obj_content['condition']['login_time']['condition_f'] 
                cond_login_time_str = utils.get_time_str(cond_login_time_str) 
                reward.cond_login_date = cond_login_time_str[:10]
                reward.cond_login_hour = cond_login_time_str[11:13]
                reward.cond_login_minute = cond_login_time_str[14:16]

            if reward.obj_content['condition'].has_key('add_time'):
                add_time_chk = True
                cond_add_time_str_f = reward.obj_content['condition']['add_time']['condition_f'] 
                cond_add_time_str_f = utils.get_time_str(cond_add_time_str_f) 
                reward.cond_add_date_f = cond_add_time_str_f[:10]
                reward.cond_add_hour_f = cond_add_time_str_f[11:13]
                reward.cond_add_minute_f = cond_add_time_str_f[14:16]

                cond_add_time_str_t = reward.obj_content['condition']['add_time']['condition_t'] 
                cond_add_time_str_t = utils.get_time_str(cond_add_time_str_t) 
                reward.cond_add_date_t = cond_add_time_str_t[:10]
                reward.cond_add_hour_t = cond_add_time_str_t[11:13]
                reward.cond_add_minute_t = cond_add_time_str_t[14:16]
        if not check_edit_reward_permission(request, 'reward_edit_common', reward.rewards_dict):
            return HttpResponse(u'<script type=\'text/javascript\'>alert("有超出权限的道具存在，不可操作！");history.go(-1);</script>')

        start_time_str = utils.get_time_str(reward.start_time)
        reward.start_date = start_time_str[:10]
        reward.start_hour = start_time_str[11:13]
        reward.start_minute = start_time_str[14:16]

        end_time_str = utils.get_time_str(reward.end_time)
        reward.end_date = end_time_str[:10]
        reward.end_hour = end_time_str[11:13]
        reward.end_minute = end_time_str[14:16]

        rewards_dict = reward.rewards_dict
    return_dict = {
        'hours': ['%02d' % item for item in xrange(0,24)],
        'minutes': ['%02d' % item for item in xrange(0,60)],
        'reward': reward,
        'pf_list': get_pf_list(pfs),
        'nafo_list': get_nafo_list(name_info),
        'user_lv_chk': user_lv_chk,
        'effort_lv_chk': effort_lv_chk,
        'login_time_chk': login_time_chk,
        'add_time_chk': add_time_chk,
        }
    reward_content_dict = get_reward_content(request, 'reward_edit_common', rewards_dict)
    return_dict.update(reward_content_dict)



    return render_to_response('admin/reward/edit_reward.html', return_dict, 
        RequestContext(request))


@login_permission_required('reward_edit_common')
def edit_reward_p(request):
    now = datetime.datetime.now()

    reward_obj = request.POST.get('reward_obj')

    cond_login_date = request.POST.get('cond_login_date') 
    cond_login_hour = request.POST.get('cond_login_hour')
    cond_login_minute = request.POST.get('cond_login_minute') 

    end_date = request.POST.get('end_date') 
    start_date = request.POST.get('start_date') 
    end_hour = request.POST.get('end_hour')
    start_hour= request.POST.get('start_hour')
    end_minute = request.POST.get('end_minute') 
    start_minute = request.POST.get('start_minute') 

    end_time = utils.parse_time_str('%s %s:%s:00' % (end_date,end_hour,end_minute)) 
    start_time = utils.parse_time_str('%s %s:%s:00' % (start_date,start_hour,start_minute)) 
    user_ip = request.META['HTTP_X_FORWARDED_FOR'].split(",")[0] if 'HTTP_X_FORWARDED_FOR' in request.META else request.META.get('REMOTE_ADDR', '')
    now = datetime.datetime.now()
    cond_login_time = None
    if cond_login_date:
        cond_login_time = utils.parse_time_str('%s %s:%s:00' % (cond_login_date,cond_login_hour,cond_login_minute)) 
        if cond_login_time >= now: 
            return HttpResponse(u'<script>alert("《上次登录时间早于》不能大于现在");history.go(-1);</script>')
    obj_content = {}
    zone_list = request.POST.get('zone_list', None) 
    if not zone_list:
        return HttpResponse(u'<script>alert("请添加分区列表");history.go(-1);</script>')
    if zone_list != 'all':
        zone_list = zone_list.split(',')
        for item in zone_list:
            if not game_config.zone.has_key(item):
                return HttpResponse(u'<script>alert("分区id填写错误");history.go(-1);</script>')
        obj_content['zone_list'] = zone_list

    if reward_obj == 'user': # in ['user','session_key']:
        ff = request.FILES.get('user_file',None)
        try:
            uids = request.POST.get('uids')
            uids = uids.replace('\r\n','')
            uids = uids.replace(' ','')
            uids = uids.replace("'","")
            uids = uids.replace('"','')
            uids = uids.split(',')
            #uids = [str(uid) for uid in uids]
            obj_content['uids'] = []
            for ustr in uids:
                #uid = utils.to_uid(ustr)
                #if uid != -1:
                obj_content['uids'].append(str(ustr))

            if ff:
                bk = xlrd.open_workbook(file_contents=ff.read())
                sh = bk.sheets()[0]
                nrows = sh.nrows
                for item in xrange(nrows):
                    row_data = sh.row_values(item)
                    for ustr in row_data:
                        if ustr:
                            ustr = str(ustr).strip()
                            #uid = utils.to_uid(ustr)
                            #if uid != -1:
                            obj_content['uids'].append(ustr)
                obj_content['uids'] = set(obj_content['uids'])
        except Exception,e:
            return HttpResponse(u'<script>alert("请确认导入文件为excel 97-2003 xls文件且文件中uid全为数字 %s");history.go(-1);</script>' % e.message)
    elif reward_obj == 'condition':
        cond_ts = request.POST.getlist('condition_type')
        cond_dict = {}
        if not cond_ts:
            return HttpResponse(u'<script>alert("请选择条件");history.go(-1);</script>' )
        if 'user_lv' in cond_ts:
            condition_f = int(request.POST.get('condition_f_user_lv',0) or 0)
            condition_t = int(request.POST.get('condition_t_user_lv',0) or 0)
            obj_content['condition'] = {'user_lv':{'condition_f':condition_f,'condition_t':condition_t}}
            cond_dict['user_lv'] = {'condition_f':condition_f,'condition_t':condition_t}
        if 'effort_lv' in cond_ts:
            condition_f = int(request.POST.get('condition_f_effort_lv',0) or 0)
            condition_t = int(request.POST.get('condition_t_effort_lv',0) or 0)
            cond_dict['effort_lv'] = {'condition_f':condition_f,'condition_t':condition_t}
        if 'login_time' in cond_ts:
            if type(cond_login_time) != datetime.datetime:
                return HttpResponse(u'<script>alert("请选择时间");history.go(-1);</script>')
            cond_dict['login_time'] = {'condition_f':cond_login_time}

        if 'add_time' in cond_ts:
            cond_add_date_f = request.POST.get('cond_add_date_f') 
            cond_add_hour_f = request.POST.get('cond_add_hour_f')
            cond_add_minute_f = request.POST.get('cond_add_minute_f') 
            condition_f = utils.parse_time_str('%s %s:%s:00' % (cond_add_date_f,cond_add_hour_f,cond_add_minute_f)) 

            cond_add_date_t = request.POST.get('cond_add_date_t') 
            cond_add_hour_t = request.POST.get('cond_add_hour_t')
            cond_add_minute_t = request.POST.get('cond_add_minute_t') 
            condition_t = utils.parse_time_str('%s %s:%s:00' % (cond_add_date_t,cond_add_hour_t,cond_add_minute_t)) 

            cond_dict['add_time'] = {'condition_f':condition_f,'condition_t':condition_t}



        obj_content['condition'] = cond_dict

    status, rewards_dict = get_rewards_dict(request)
    if not status:
        return HttpResponse(u'<script>alert("%s");history.go(-1);</script>' % rewards_dict)
    nafo_error,name_info = get_name_info(request)
    if nafo_error:
        return name_info
    input_error,input_dict = get_input_content(request)
    if input_error:
        return input_dict
    if input_dict:
        rewards_dict.update(input_dict)


    if not rewards_dict:
        return HttpResponse(u'<script>alert("请选择发奖励内容");history.go(-1);</script>')
    pfs = request.POST.getlist('pfs')
    if not pfs:
        return HttpResponse(u'<script>alert("请勾选pf");history.go(-1);</script>')

    if not check_edit_reward_permission(request, 'reward_edit_common', rewards_dict):
        return HttpResponse(u'<script type=\'text/javascript\'>alert("有超出权限的道具存在，不可操作！");history.go(-1);</script>')
    id = request.POST.get('id', None)
    Rewards.save_reward(id,name_info,pfs,reward_obj,obj_content,start_time,end_time,request.session['admin_user']['username'],rewards_dict,user_ip, now)
    reward_cache.update()
    reward_cache.judge()
    push_to_reward_config()
    return HttpResponseRedirect(settings.BASE_URL+'/admin/reward/rewards/')




def get_input_content(request=None, dt={}):
    if request and request.POST:
        input_dict = {}
        for item in input_key_list:
            item_key, item_name, item_num =  item
            item_value = int(request.POST.get(item_key, 0) or 0)
            if item_value:
                if item_value not in xrange(1,int(item[2])+1):
                    return 1,HttpResponse(u'<script>alert("%s数量错误");history.go(-1);</script>' % item_name)
                input_dict[item_key] = item_value
        return 0,input_dict

    else:
        input_list = copy(input_key_list)
        for item in input_list:
            if dt.has_key(item[0]):
                item.append(dt[item[0]])
    return input_list

def get_rewards_dict(request):
    rewards_dict = {}

    for item in game_config.system_simple['sale_depot'].keys():
        a_num = request.POST.get(item, None)
        if a_num:
            limit = reward_count_limit['sale_depot']
            if int(a_num) not in xrange(limit[0], limit[1]+1):
                return False, u'【%s】超出发送数量限制' % item
            rewards_dict[item] = int(a_num)

    for item in game_config.star.keys():
        a_num = request.POST.get(item, None)
        if a_num:
            limit = reward_count_limit['star']
            if int(a_num) not in xrange(limit[0], limit[1]+1):
                return False, u'【%s】超出发送数量限制' % item
            rewards_dict['%s01' % item] = int(a_num)

    for item in game_config.prop.keys():
        a_num = request.POST.get(item, None)
        if a_num:
            limit = reward_count_limit['prop']
            if int(a_num) not in xrange(limit[0], limit[1]+1):
                return False, u'【%s】超出发送数量限制' % item
            rewards_dict[item] = int(a_num)
    equip = request.POST.getlist('equip')
    if equip:
        equip_config = game_config.equip
        for item in equip:
            if item not in equip_config.keys():
                return False, u'【%s】在宝物配置中不存在' % item
        rewards_dict['equip'] = equip

    title = request.POST.getlist('title')
    if title:
        title_config = game_config.title
        for item in title:
            if item not in title_config.keys():
                return False, u'【%s】在称号配置中不存在' % item
        rewards_dict['title'] = title

    for item in game_config.soul.keys():
        a_num = request.POST.get(item, None)
        if a_num:
            limit = reward_count_limit['soul']
            if int(a_num) not in xrange(limit[0], limit[1]+1):
                return False, u'【%s】超出发送数量限制' % item
            rewards_dict['%s01' % item] = int(a_num)
    face = request.POST.getlist('face')
    if face:
        for face_id in face:
            if face_id not in game_config.system_simple['cfg_face']['3']['ids']:
                return False, u'【%s】在特殊表情配置中不存在' % face_id
        rewards_dict['face'] = face
    for item in game_config.native.keys():
        a_num = request.POST.get(item, None)
        if a_num:
            limit = reward_count_limit['native']
            if int(a_num) not in xrange(limit[0], limit[1]+1):
                return False, u'【%s】超出发送数量限制' % item
            rewards_dict[item] = int(a_num)
    return True, rewards_dict


def get_name_info(request):
    name_info = {}
    language_config= game_config.system_simple['language']
    first_lan = None
    for item in language_config:
        item_name = request.POST.get('name_%s' % item[0], None)
        item_info = request.POST.get('info_%s' % item[0], None)
        if first_lan is None:
            first_lan = item[0]
            if not item_name or not item_info:
                return 1,HttpResponse(u'<script>alert("%s正文标题不能为空");history.go(-1);</script>' % item)
        if item_name and item_info:
            name_info[item[0]] = [item_name, item_info]
    return 0,name_info

def get_nafo_list(nafo_dt={}):
    nafo = []
    language_config= game_config.system_simple['language']
    for item in language_config:
        item_name = ''
        item_info = ''
        item_content = nafo_dt.get(item[0], None)
        if item_content:
            item_name, item_info = item_content

        nafo.append([item[0], item_name, item_info])
    return nafo

def get_pf_list(pfs=[]):
    pf_list = []
    pf_config = game_config.system_simple['pfs']
    for item in pf_config:
        chk = False
        if item in pfs:
            chk = True
        pf_list.append([item, chk])
    return pf_list







@login_permission_required('admin_gift_msg')
def admin_gift_msg(request):
    """
    邮件奖励列表查看
    :param request:
    :return:
    """
    now = datetime.datetime.now()
    msgs_list = []
    page = int(request.GET.get('page','1'))
    order_by = request.GET.get('order_by', None)
    content_open = int(request.GET.get('content_open','0'))
    p_params = {}
    if order_by is None:
        order_by = '-subtime'
    else:
        p_params['order_by'] = order_by
    p = None
    page_size = 30
    page_list_num = 10
    total = AdminLog.count({'func_name': 'admin_gift_msg', 'status_not': -1})
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num, parameter=p_params)
    rewards = AdminLog.query({'func_name': 'admin_gift_msg', 'status_not': -1}, order_by=order_by, offset=offset, limit=page_size)
    reward_list = []
    language_config= game_config.system_simple['language']
    for item in rewards:
        try:
            content = pickle.loads(str(item.content))
        except:
            continue
        for lan in language_config:
            item_name_info = content['name_info'].get(lan[0], None)
            if item_name_info:
                content['name_title'],content['info_title'] = item_name_info
                content['name'] = content['name_title'][:5]
                content['info'] = content['info_title'][:20]
                if len(content['name_title']) != len(content['name']):
                    content['name_ic'] = 1
                if len(content['info_title']) != len(content['info']):
                    content['info_ic'] = 1
                break
        content['reward_obj'] = []
        for zone_id, uids in content['zone_uids'].items():
            if zone_id not in game_config.zone:
                continue
            zone_name = game_config.zone[zone_id][0]
            _uids = []
            for i in uids:
                if not isinstance(i, list):
                    _uids.append([i, ''])
                else:
                    _uids.append(i)
            content['reward_obj'].append([zone_id, zone_name, _uids])
        if not content['reward_obj']:
            continue
        content['reward_obj_expand'] = False
        if len(content['reward_obj']) == 0:
            continue
        elif len(content['reward_obj']) > 1:
            content['reward_obj_expand'] = True
        else:
            if len(content['reward_obj'][0][2]) > 1:
                content['reward_obj_expand'] = True
        content['rewards_dict_info'] = parse_properties_str(content['rewards_dict'])
        content['rewards_dict_info_cn'] = (content['rewards_dict_info'][:30], len(content['rewards_dict_info']) > 30)
        if len(content['rewards_dict_info']) != len(content['rewards_dict_info_cn']):
            content['ric'] = 1
        reward_list.append({
            'id': item.id,
            'status': item.status,
            'subtime': item.subtime,
            'admin_user': item.admin_user,
            'content': content,
            })

    return render_to_response('admin/reward/admin_gift_msg.html', {
        'reward_list': reward_list,
        'p': p,
        'page':page,
        'content_open': content_open,
        }, 
        RequestContext(request))

@login_permission_required('admin_gift_msg')
def send_admin_gift_msg(request):
    """
    已发送邮件奖励查看
    :param request:
    :return:
    """

    id = request.REQUEST.get('id', None)
    zone_config = game_config.zone
    reward = AdminLog.get(id)
    reward_content = pickle.loads(str(reward.content))
    zone_uids = []
    for k,v in reward_content['zone_uids'].items():
        # zone_uids.append([zone_config[k][0],','.join(v)])
        item = [k, zone_config[k][0]]
        uids = []
        for u in v:
            if not isinstance(u, list):
                uids.append([u, ''])
            else:
                uids.append(u)
        item.append(uids)
        zone_uids.append(item)
    reward_content['rewards_dict_info'] = parse_properties_str(reward_content['rewards_dict'])
    nafo_list = get_nafo_list(reward_content['name_info'])
    name_info = reward_content['name_info']
    rewards_dict = reward_content['rewards_dict']
    language_config= game_config.system_simple['language']
    deft_name_info = name_info[language_config[0][0]]
    return render_to_response('admin/reward/send_admin_gift_msg.html', {
        'zone_uids': zone_uids,
        'reward': reward,
        'reward_content': reward_content,
        'nafo_list': nafo_list,
        },
        RequestContext(request))


@login_permission_required('reward_edit_admin')
def del_reward_to_user(request):
    rid = request.POST.get('id')
    reward = AdminLog.get(rid)
    if reward.status==0 and reward.func_name=='admin_gift_msg':
        reward.status = -1
        reward.save()
        return HttpResponse(json.dumps({'state':'success'}))
    else:
        return HttpResponse(json.dumps({'state':'err', 'msg': '不能删除'}))

@login_permission_required('reward_edit_admin')
def set_reward_to_user_p(request):
    """
    邮件奖励添加
    :param request:
    :return:
    """

    if request.POST:
        nafo_error,name_info = get_name_info(request)
        if nafo_error:
            return name_info

        status, rewards_dict = get_rewards_dict(request)
        if not status:
            return HttpResponse(u'<script>alert("%s");history.go(-1);</script>' % rewards_dict)

        input_error,input_dict = get_input_content(request)
        if input_error:
            return input_dict
        rewards_dict.update(input_dict)

        if not rewards_dict:
            return HttpResponse(u'<script>alert("请选择奖励内容");history.go(-1);</script>')
        if not check_edit_reward_permission(request, 'reward_edit_admin', rewards_dict):
            return HttpResponse(u'<script type=\'text/javascript\'>alert("有超出权限的道具存在，不可操作！");history.go(-1);</script>')
        zone_uids = {}
        uids = request.POST.get('uids')
        if not uids:
            return HttpResponse(u'<script>alert("请填写发奖户用uid");history.go(-1);</script>')
        uids = uids.split(',')
        error_uids = []
        for uid in uids:
            old_uid = int(uid)%settings.UIDADD
            old_zone = str(int(uid)/settings.UIDADD)
            user_zone = UserZone.get(old_uid)
            if old_zone not in user_zone.zone_login:
                error_uids.append(uid)
                continue
            merge_zone = user_zone.zone_login[old_zone]['merge_zone']

            if game_config.zone[merge_zone][8]:
                s_uid = uid
            else:
                s_uid = old_uid
            user = UserZone.call_server_api(old_zone, 'get_user', {'uid': old_uid})
            if not user:
                error_uids.append(uid)
                continue
            zone_uids.setdefault(merge_zone, [])
            zone_uids[merge_zone].append([uid, user['uname']])
        if error_uids:
            return HttpResponse(u'<script>alert("存在不合法uid（%s）");history.go(-1);</script>' % ','.join(error_uids))

        content = {
                'zone_uids': zone_uids,
                'rewards_dict': rewards_dict,
                'name_info': name_info,
                }
        content = pickle.dumps(content, -1)
        ## status: 0已发送，1待发送
        AdminLog.add_adminlog(request.session['admin_user']['username'], 'admin_gift_msg', content, status=1)
        return HttpResponseRedirect(settings.BASE_URL+'/admin/reward/admin_gift_msg/')
@login_permission_required('reward_edit_admin')
def set_reward_to_user(request):
    """
    邮件奖励添加
    :param request:
    :return:
    """
    uid = request.GET.get('uid', None)
    uids = ''
    name_info = {}
    if uid is not None:
        uids = uid

    return_dict = {
        'uids': uids,
        'nafo_list': get_nafo_list(name_info)
        }
    reward_content_dict = get_reward_content(request, 'reward_edit_admin', {})
    return_dict.update(reward_content_dict)

    return render_to_response('admin/reward/set_reward_to_user.html',
            return_dict,
        RequestContext(request))

@login_permission_required('reward_edit_admin')
def do_admin_gift_msg(request):
    id = request.POST.get('id')
    zone_config = game_config.zone
    reward = AdminLog.get(id)
    if reward.status == 0:
        return HttpResponse(json.dumps({'state':'error', 'msg': u'奖励已经发送'}))
    reward.status = 0
    reward.update(['status'])
    reward_content = pickle.loads(str(reward.content))
    name_info = reward_content['name_info']
    for zone,uids in reward_content['zone_uids'].items():
        if game_config.zone[zone][8]:
            _uids = [i[0] for i in uids]
        else:
            _uids = [UserZone.get_old_uid(i[0], zone) for i in uids]
        UserZone.call_server_api(zone, 'admin_gift_msg', {'name_info': reward_content['name_info'], 'gift_dict': reward_content['rewards_dict'], 'uids': _uids})
    return HttpResponse(json.dumps({'state':'success'}))


''' 奖励 '''
@login_permission_required('rewards')
def rewards(request):
    now = datetime.datetime.now()
    view_delete = int(request.GET.get('view_delete', 0))
    content_open = int(request.GET.get('content_open', 0))
    order_by = request.GET.get('order_by', None)
    rewards = Rewards.get_admin_rewards(view_delete=view_delete, order_by=order_by)
    rewards_list = []
    return_msg_config = game_config.return_msg
    pf_config = game_config.system_simple['pfs']
    language_config= game_config.system_simple['language']
    for item in rewards:
        _item = item.dumps(shallow=True)
        if _item['reward_obj'] == 'all':
            _item['reward_obj_cn'] = u'全服'
            zone_list = _item['obj_content'].get('zone_list')
            if zone_list:
                # _item['reward_obj_cn'] = u'全服(%s)' % '|'.join(zone_list)
                _item['reward_obj_zones'] = zone_list
        if _item['reward_obj'] == 'code_reward':
            _item['reward_obj_cn'] = u'兑奖码发奖'
        elif _item['reward_obj'] == 'user':
            _item['reward_obj_cn'] = u'指定用户'
            _item['obj_content_info'] = _item['obj_content']['uids']
        elif _item['reward_obj'] == 'condition':
            _item['reward_obj_cn'] = u'条件'
            _item['obj_content_info'] = u''
            if _item['obj_content']['condition'].has_key('user_lv'):
                _item['obj_content_info'] += '%s<=User.levle<=%s\n' % (_item['obj_content']['condition']['user_lv']['condition_f'],_item['obj_content']['condition']['user_lv']['condition_t'])
            if _item['obj_content']['condition'].has_key('effort_lv'):
                _item['obj_content_info'] += '%s<=User.effort_lv<=%s\n' % (_item['obj_content']['condition']['effort_lv']['condition_f'],_item['obj_content']['condition']['effort_lv']['condition_t'])
            if _item['obj_content']['condition'].has_key('login_time'):
                _item['obj_content_info'] += u'上次登录时间早于%s' % _item['obj_content']['condition']['login_time']['condition_f']
        for lan in language_config:
            item_name_info =  _item['name_info'].get(lan[0], None)
            if item_name_info:
                _item['name'], _item['info_title'] = item_name_info
                _item['info'] = _item['info_title'][:3]
                break

        rewards_dict_info = parse_properties_str(_item['rewards_dict'])
        _item['rewards_dict_info'] = rewards_dict_info[:3]
        _item['rewards_dict_info_title'] = rewards_dict_info
        pfs_str = ','.join(item.pfs)
        _item['pfs_info'] = pfs_str[:30]
        _item['pfs'] = pfs_str
        if item.status == 1:
            if item.start_time > now:
                ## 已计划
                _item['status'] = 3
            elif item.end_time < now:
                ## 已过期
                _item['status'] = 4
        rewards_list.append(_item)
    return render_to_response('admin/reward/rewards.html', {
        'rewards': rewards_list,
        'pf_list': get_pf_list(),
        'view_delete': view_delete,
        'content_open': content_open,
        }, 
        RequestContext(request))


            

@login_permission_required('reward_edit_code', ajax=True)
def do_code_reward(request):
    id = request.POST.get('id')
    status = int(request.POST.get('status'))
    reward = Rewards.get(id)
    if not check_edit_reward_permission(request, 'reward_edit_code', reward.rewards_dict):
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'"有超出权限的道具存在，不可操作！'}))
    reward.status= status
    reward.update(['status'])
    #删除兑奖码
    #if reward.reward_obj == 'code_reward':
    #    if status == 2:
    #        db_code = RewardCode.query({'rid': reward.id})
    #        for item in db_code:
    #            reward_code = RewardCode.get(item.code)
    #            reward_code.delete()
    reward_cache.update()
    reward_cache.judge()
    push_to_reward_config()


    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('reward_edit_common', ajax=True)
def do_reward(request):
    now = datetime.datetime.now()
    id = request.POST.get('id')
    status = int(request.POST.get('status'))
    reward = Rewards.get(id)
    if not check_edit_reward_permission(request, 'reward_edit_common', reward.rewards_dict):
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'"有超出权限的道具存在，不可操作！'}))
    reward.status= status
    reward.update(['status'])
    #删除兑奖码
    #if reward.reward_obj == 'code_reward':
    #    if status == 2:
    #        db_code = RewardCode.query({'rid': reward.id})
    #        for item in db_code:
    #            reward_code = RewardCode.get(item.code)
    #            reward_code.delete()
    reward_cache.update()
    reward_cache.judge()
    push_to_reward_config()

    status = reward.status
    if status == 1:
        if reward.start_time > now:
            ## 已计划
            status = 3
        elif reward.end_time < now:
            ## 已过期
            status = 4


    return HttpResponse(json.dumps({'state':'success', 'status': status}))

def parse_properties_str(dt):
    p_str = ''
    star_config = game_config.star
    prop_config = game_config.prop
    equip_config = game_config.equip
    soul_config = game_config.soul
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
            if k not in prop_config:
                continue
            msg_id = prop_config[k]['name']
            prop_name = return_msg_config.get(str(msg_id), k)
            p_str += u'%s×%s,' % (prop_name,v)
        elif k == 'title':
            for tid in v:
                title_name = return_msg_config.get(str(tid), str(tid))
                p_str += u'%s,' % title_name
        elif k == 'equip':
            for eid in v:
                try:
                    msg_id = equip_config[eid]['name']
                    equip_name = return_msg_config[str(msg_id)]
                except KeyError:
                    equip_name = eid
                p_str += u'%s,' % equip_name
        elif k.startswith('soul'):
            soul_name = return_msg_config[k[:-2]]
            p_str += u'%sx%s,' % (soul_name, v)
        elif k == 'face':
            for face_id in v:
                p_str += u'%s(%s)' % (game_config.return_msg['face_%s' % face_id], face_id)
        elif k.startswith('tc') or k.startswith('scheme'):
            if k not in native_config:
                continue
            native_name = return_msg_config['%s_name' % k]
            p_str += u'%sx%s,' % (native_name, v)



    return p_str


def weixin_reward_code(request):
    pwd = game_config.ploy_system_simple['weixin_code']['pwd']
    password = request.POST.get('password', None)
    rid = request.POST.get('rid', None)
    if password is None:
        return HttpResponse('None password')
    if password != pwd:
        return HttpResponse('Error password')
    if rid is None:
        return HttpResponse('None rid')
    add_time = datetime.datetime.now()

    t = time.time()

    code_num = 1
    n = 0
    p = ''
    while n < code_num:
        code_str = str(rid) + str(t) + str(n) + p
        code = md5(code_str).hexdigest()[8:-14]
        if code.startswith('0'):
            p = str(random.randint(1, 10))
            continue
        else:
            p = ''
        reward_code = RewardCode(code)
        reward_code.rid = int(rid)
        try:
            reward_code.save()
        except:
            p = str(random.randint(1, 10))
            continue
        else:
            p = ''

        n += 1
    reward_cache.update()
    reward_cache.judge()
    push_to_reward_config()
    return HttpResponse('["%s", "%s"]' % (reward_code.code, rid))







@login_permission_required('edit_push_notice')
def edit_push_notice(request):
    pfs = []
    user_lv_chk = False
    rank_score_chk = False
    add_time_chk = False
    id = request.GET.get('id', None)
    push_notice = None

    if id:
        push_notice = PushNotice.get(int(id))
        pfs = push_notice.pfs
        condition = push_notice.condition
        if condition:
            if condition.has_key('user_lv'):
                user_lv_chk = True
            if condition.has_key('rank_score'):
                rank_score_chk = True


            if condition.has_key('add_time'):
                add_time_chk = True
                cond_add_time_str_f = condition['add_time']['condition_f'] 
                cond_add_time_str_f = utils.get_time_str(cond_add_time_str_f) 
                push_notice.cond_add_date_f = cond_add_time_str_f[:10]
                push_notice.cond_add_hour_f = cond_add_time_str_f[11:13]
                push_notice.cond_add_minute_f = cond_add_time_str_f[14:16]

                cond_add_time_str_t = condition['add_time']['condition_t'] 
                cond_add_time_str_t = utils.get_time_str(cond_add_time_str_t) 
                push_notice.cond_add_date_t = cond_add_time_str_t[:10]
                push_notice.cond_add_hour_t = cond_add_time_str_t[11:13]
                push_notice.cond_add_minute_t = cond_add_time_str_t[14:16]

        start_time_str = utils.get_time_str(push_notice.start_time)
        push_notice.start_date = start_time_str[:10]
        push_notice.start_hour = start_time_str[11:13]
        push_notice.start_minute = start_time_str[14:16]

        end_time_str = utils.get_time_str(push_notice.end_time)
        push_notice.end_date = end_time_str[:10]
        push_notice.end_hour = end_time_str[11:13]
        push_notice.end_minute = end_time_str[14:16]


    return render_to_response('admin/reward/edit_push_notice.html', {
        'hours': ['%02d' % item for item in xrange(0,24)],
        'minutes': ['%02d' % item for item in xrange(0,60)],
        'pf_list': get_pf_list(pfs),
        'user_lv_chk': user_lv_chk,
        'rank_score_chk': rank_score_chk,
        'add_time_chk': add_time_chk,
        'push_notice': push_notice,
        }, 
        RequestContext(request))

@login_permission_required('edit_push_notice')
def edit_push_notice_p(request):
    now = datetime.datetime.now()
    content = request.REQUEST.get('content', None)
    if not content:
        return HttpResponse(u'<script>alert("请填写正文");history.go(-1);</script>')
    pfs = request.POST.getlist('pfs')
    if not pfs:
        return HttpResponse(u'<script>alert("请勾选pf");history.go(-1);</script>')
    cond_ts = request.POST.getlist('condition_type')
    condition = {}
    if cond_ts:
        if 'user_lv' in cond_ts:
            condition_f = int(request.POST.get('condition_f_user_lv',0) or 0)
            condition_t = int(request.POST.get('condition_t_user_lv',0) or 0)
            if condition_f >= condition_t:
                return HttpResponse(u'<script>alert("请填写正确《用户等级》区间");history.go(-1);</script>')
            condition['user_lv'] = {'condition_f':condition_f,'condition_t':condition_t}
        if 'rank_score' in cond_ts:
            condition_f = int(request.POST.get('condition_f_rank_score',0) or 0)
            condition_t = int(request.POST.get('condition_t_rank_score',0) or 0)
            if condition_f >= condition_t:
                return HttpResponse(u'<script>alert("请填写正确《段位积分》区间");history.go(-1);</script>')
            condition['rank_score'] = {'condition_f':condition_f,'condition_t':condition_t}

        if 'add_time' in cond_ts:
            cond_add_date_f = request.POST.get('cond_add_date_f') 
            cond_add_hour_f = request.POST.get('cond_add_hour_f')
            cond_add_minute_f = request.POST.get('cond_add_minute_f') 
            condition_f = utils.parse_time_str('%s %s:%s:00' % (cond_add_date_f,cond_add_hour_f,cond_add_minute_f)) 

            cond_add_date_t = request.POST.get('cond_add_date_t') 
            cond_add_hour_t = request.POST.get('cond_add_hour_t')
            cond_add_minute_t = request.POST.get('cond_add_minute_t') 
            condition_t = utils.parse_time_str('%s %s:%s:00' % (cond_add_date_t,cond_add_hour_t,cond_add_minute_t)) 
            if condition_f >= condition_t:
                return HttpResponse(u'<script>alert("请填写正确《注册时间》区间");history.go(-1);</script>')

            condition['add_time'] = {'condition_f':condition_f,'condition_t':condition_t}


    end_date = request.POST.get('end_date') 
    start_date = request.POST.get('start_date') 
    end_hour = request.POST.get('end_hour')
    start_hour= request.POST.get('start_hour')
    end_minute = request.POST.get('end_minute') 
    start_minute = request.POST.get('start_minute') 

    end_time = utils.parse_time_str('%s %s:%s:00' % (end_date,end_hour,end_minute)) 
    start_time = utils.parse_time_str('%s %s:%s:00' % (start_date,start_hour,start_minute)) 
    if end_time <= start_time:
        return HttpResponse(u'<script>alert("请填写正确《有效期》区间");history.go(-1);</script>')

    user_ip = request.META['HTTP_X_FORWARDED_FOR'].split(",")[0] if 'HTTP_X_FORWARDED_FOR' in request.META else request.META.get('REMOTE_ADDR', '')

    id = request.POST.get('id', None)
    interval = int(request.POST.get('interval', 0))
    admin_user = request.session['admin_user']['username']
    PushNotice.save_push_notice(id, content,pfs,condition,interval,start_time,end_time,admin_user,user_ip, now)
    if id:
        reward_cache.update()
    return HttpResponseRedirect(settings.BASE_URL+'/admin/reward/push_notice/')


@login_permission_required('push_notice')
def push_notice(request):
    pf = request.POST.get('pf', 'all')
    push_notice_all = PushNotice.get_admin_push_notice()
    push_notice_list = []
    pf_config = game_config.system_simple['pfs']
    for item in push_notice_all:
        _item = item.dumps(shallow=True)
        if pf != 'all' and pf not in _item['pfs']:
            continue
        push_notice_list.append(_item)
    return render_to_response('admin/reward/push_notice.html', {
        'push_notice_list': push_notice_list,
        'pf_list': get_pf_list(),
        'pf': pf,
        }, 
        RequestContext(request))


@login_permission_required('edit_push_notice', ajax=True)
def do_push_notice(request):
    id = request.POST.get('id')
    status = int(request.POST.get('status'))

    push_notice= PushNotice.get(id)
    push_notice.status= status
    push_notice.update(['status'])
    reward_cache.update()


    return HttpResponse(json.dumps({'state':'success'}))






@login_permission_required('publish_reward')
def publish_reward(request):
    reward_cache.judge()
    server_list = []
    item_list = []
    zone_list = UserZone.get_zone_list('running') 
    for item in zone_list:
        try:
            res = UserZone.call_server_api(item[0], 'get_server_reward_version', {})
            if res[0] == reward_config.version:
                res[0] = 'green'
            else:
                res[0] = 'red'
        except:
            res = ['red']
        item += res
        item_list.append(item)
        if len(item_list) >= 10:
            server_list.append(item_list)
            item_list = []
    else:
        server_list.append(item_list)


    return render_to_response('admin/reward/publish_reward.html', {
        'server_list': server_list,
        }, 
        RequestContext(request))

@login_permission_required('publish_reward')
def push_server_reward_config(request):
    reward_cache.judge()
    zone = request.POST.get('zone')
    if zone:
        try:
            UserZone.push_server_reward_config(zone)
            return HttpResponse(json.dumps({'state':'success'}))
        except:
            utils.print_err()
            return HttpResponse(json.dumps({'state':'error'}))
    else:
        return HttpResponse(json.dumps({'state':'error'}))

def get_admin_rewards(start_at, end_at):
    data = list(AdminLog.query({'func_name': 'admin_gift_msg',
                                'status_not': -1,
                                'subtime_gte': start_at,
                                'subtime_lt': end_at}, order_by='-subtime'))
    language_config = game_config.system_simple['language']
    _data = []
    for item in data:
        _item = {
            'title': None,
            'reward_type': [u'邮件发奖', '#d2691e'],
            'add_time': item.subtime,
            'update_time': item.subtime,
            'rewards': None,
            'admin_user': item.admin_user,
            'status': '--',
            'access_period': '--'
        }
        content = pickle.loads(str(item.content))
        for lan in language_config:
            item_name_info = content['name_info'].get(lan[0], None)
            if item_name_info:
                _item['title'] = item_name_info[0]
                break
        _item['rewards'] = content['rewards_dict']
        _data.append(_item)
    return _data

def get_common_rewards(start_at, end_at):
    data = list(Rewards.query({'reward_obj_not': 'code_reward',
                               'status_not': 2,
                               'add_time_gte': start_at,
                               'add_time_lt': end_at}, order_by='-add_time'))
    language_config = game_config.system_simple['language']
    _data = []
    for item in data:
        item = item.dumps(shallow=True)
        _item = {
            'title': None,
            'reward_type': [u'一般奖励', '#3C57C4'],
            'add_time': item['add_time'],
            'update_time': item['update_time'] or item['add_time'],
            'rewards': None,
            'admin_user': item['admin_user'],
            'status': item['status'],
            'access_period': '%s - %s' % (str(item['start_time']), str(item['end_time']))
        }
        for lan in language_config:
            item_name_info =  item['name_info'].get(lan[0], None)
            if item_name_info:
                _item['title'] = item_name_info[0]
                break
        _item['rewards'] = item['rewards_dict']
        _data.append(_item)
    return _data


def get_code_rewards(start_at, end_at):
    data = list(Rewards.query({'reward_obj': 'code_reward',
                               'status_not': 2,
                               'add_time_gte': start_at,
                               'add_time_lt': end_at}, order_by='-add_time'))
    language_config = game_config.system_simple['language']
    _data = []
    for item in data:
        item = item.dumps(shallow=True)
        _item = {
            'title': None,
            'reward_type': [u'兑奖码', '#3CC472'],
            'add_time': item['add_time'],
            'update_time': item['update_time'] or item['add_time'],
            'rewards': None,
            'admin_user': item['admin_user'],
            'status': item['status'],
            'access_period': str(item['end_time'])
        }
        for lan in language_config:
            item_name_info = item['name_info'].get(lan[0], None)
            if item_name_info:
                _item['title'] = item_name_info[0]
                break
        _item['rewards'] = item['rewards_dict']
        _data.append(_item)
    return _data

@login_permission_required('search_rewards')
def search_rewards(request):
    from_date = request.REQUEST.get('from_date')
    add_date = int(request.REQUEST.get('add_date',30))
    reward_type = request.REQUEST.get('reward_type', 'all')
    search_item_id = request.REQUEST.get('search_item_id', '')
    add_date_list = [1,3,7,14,30,60,90]
    reward_type_list = [
        ['admin_reward', u'邮件发奖'],
        ['common_reward', u'一般奖励'],
        ['code_reward', u'兑奖码'],
    ]
    if not from_date:
        to_date = datetime.date.today()+datetime.timedelta(days=1)
        from_date = to_date - datetime.timedelta(days=add_date-0)
    else:
        from_date = datetime.date(*[int(item) for item in from_date.split('-')])
        to_date = from_date + datetime.timedelta(days=add_date-1)
        if to_date > datetime.date.today():
            to_date = datetime.date.today()
    start_at = datetime.datetime(*from_date.timetuple()[:6])
    end_at = datetime.datetime(*to_date.timetuple()[:6])
    reward_list = []
    if request.method == 'POST':
        if reward_type in ['all', 'admin_reward']:
            reward_list += get_admin_rewards(start_at, end_at)
        if reward_type in ['all', 'common_reward']:
            reward_list += get_common_rewards(start_at, end_at)
        if reward_type in ['all', 'code_reward']:
            reward_list += get_code_rewards(start_at, end_at)
    filter_reward_list = []
    for item in sorted(reward_list, key=lambda x: x['update_time'], reverse=True):
        if search_item_id and search_item_id not in item['rewards'].keys():
            continue
        rewards = item.pop('rewards')
        item['content'] = parse_properties_str(rewards)
        filter_reward_list.append(item)

    return render_to_response('admin/reward/search_rewards.html', {
            'search_item_id': search_item_id,
            'from_date': str(from_date),
            'add_date': add_date,
            'add_date_list': add_date_list,
            'reward_type': reward_type,
            'reward_type_list': reward_type_list,
            'reward_list': filter_reward_list
        },
        RequestContext(request))

@login_permission_required('send_ucoin')
def add_ucoin_reward(request):
    if request.method == 'POST':
        uids = request.POST.get('uids')
        remark = request.POST.get('remark')
        ucoin = int(request.POST.get('ucoin', 0))
        if not uids:
            return HttpResponse(u'<script>alert("请填写用户uid");history.go(-1);</script>')
        if not remark:
            return HttpResponse(u'<script>alert("请填写备注信息");history.go(-1);</script>')
        if ucoin <= 0:
            return HttpResponse(u'<script>alert("萌币数量必须是大于0的数字");history.go(-1);</script>')
        user_zones = []
        for uid in uids.split(','):
            user_zone = UserZone.get(uid)
            if not user_zone:
                return HttpResponse(u'<script>alert("【%s】此UID不合法");history.go(-1);</script>' % uid)
            user_zones.append(user_zone)
        l = SendUcoinLog()
        l.uids = uids
        l.ucoin = ucoin
        l.admin_user = request.session['admin_user']['username']
        l.remark = remark
        l.save()
        return HttpResponseRedirect(settings.BASE_URL+'/admin/reward/view_ucoin_reward/')

    return render_to_response('admin/reward/add_ucoin_reward.html', {

    }, RequestContext(request))

@login_permission_required('send_ucoin', ajax=True)
def send_ucoin_reward(request):
    reward_id = request.POST.get('reward_id')
    if not reward_id:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'非法请求'}))
    reward = SendUcoinLog.get(reward_id)
    if not reward:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'奖励ID错误'}))
    if reward.status != 0:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'奖励已发送'}))
    for uid in reward.uids.split(','):
        user_zone = UserZone.get(uid)
        user_zone.ucoin += reward.ucoin
        user_zone.save()
    reward.status = 1
    reward.save()
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('send_ucoin')
def view_ucoin_reward(request):
    """
    萌币奖励列表查看
    :param request:
    :return:
    """
    page = int(request.REQUEST.get('page','1'))
    search_uid = request.REQUEST.get('search_uid')
    order_by = request.REQUEST.get('order_by', None)
    filters = []
    p_params = {}
    if order_by is None:
        order_by = '-subtime'
    else:
        p_params['order_by'] = order_by
    if search_uid:
        filters.append(ul.c.uids.like("%{uid}%".format(uid=search_uid)))
        p_params['search_uid'] = search_uid
    p = None
    page_size = 30
    page_list_num = 10
    total = SendUcoinLog.count()
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num, parameter=p_params)
    # rewards = AdminLog.query({}, order_by=order_by, offset=offset, limit=page_size)
    if order_by.startswith('-'):
        _order_by = ul.c[order_by[1:]].desc()
    else:
        _order_by = ul.c[order_by]
    rewards = ul.select(and_(*filters)).order_by(_order_by).offset(offset).limit(page_size).execute().fetchall()
    reward_list = []
    for item in rewards:
        _dic = dict(item)
        _dic['uids'] = [uid for uid in item.uids.split(',')]
        reward_list.append(_dic)

    return render_to_response('admin/reward/view_ucoin_reward.html', {
        'reward_list': reward_list,
        'p': p,
        'page':page,
        'search_uid': search_uid
        },
        RequestContext(request))
