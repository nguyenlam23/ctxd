#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, Context, loader
from django.conf import settings
import datetime
from admin.logic import login_permission_required
import json
from game_lib.models.main import AdminLog
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
from game_lib.db.database import c_cache as cache
from game_lib.models.main import UserZone,Waiter
from db.database import admin_table
import cPickle as pickle



@login_permission_required('view_waiter') 
def view_waiter(request):
    zone_list = UserZone.get_zone_list('old')
    zone_dict = {}
    for k,v in zone_list:
        zone_dict[k] = v
    waiter_list = []
    params = {}
    for item in Waiter.query({'status': 0}):
        user_zone = UserZone.get(item.waiter_id)
        item_zone_list = []
        for z in item.zone_list:
            if z not in user_zone.zone_login:
                continue
            merge_zone = user_zone.zone_login[z]['merge_zone']
            if not zone_dict.has_key(z):
                continue
            if game_config.zone[merge_zone][8]:
                waiter_id = UserZone.get_new_uid(item.waiter_id, z)
            else:
                waiter_id = item.waiter_id
            item_zone_list.append([z,item.waiter_id,zone_dict[z],waiter_id,merge_zone])
            params.setdefault(merge_zone, [])
            params[merge_zone].append(waiter_id)
        item.zone_list = item_zone_list
        waiter_list.append(item)
    online_dict = {}
    for k,v in params.items():
        try:
            online_dict[k] = UserZone.call_server_api(k, 'user_online_log', {'uids':v})
        except:
            pass
    for item in waiter_list:
        for _item in item.zone_list:
            zone,uid,x,new_uid,merge_zone = _item
            online_log = online_dict.get(merge_zone,{}).get(new_uid,{})
            ooo = {'is_online': online_log.get('is_online',False)}
            if online_log.get('t',None):
                ooo['t'] = utils.format_time(online_log['t'])

            _item.append(ooo)

    log_list = []
    for item in AdminLog.query({'func_name': 'edit_waiter'}, order_by='-subtime',limit=20):
        item.content = eval(str(item.content))
        log_list.append(item)
    return render_to_response('admin/waiter/view_waiter.html', {
        'zone_list': zone_list,
        'waiter_list': waiter_list,
        'log_list': log_list,
        },
        RequestContext(request))

@login_permission_required('edit_waiter') 
def edit_waiter(request):
    waiter_id = request.REQUEST.get('waiter_id',None)
    waiter = None
    admin_user = ''
    sql_list = admin_table.select(and_(admin_table.c.username <> 'admin')).execute().fetchall()
    admin_user_list = []
    for item in sql_list:
        admin_user_list.append(item['username'])
    admin_user_list.append('admin')
    zone_list = UserZone.get_zone_list('old')
    if waiter_id:
        user_zone_uid = check_waiter_id(waiter_id)
        if not user_zone_uid:
            raise
        waiter = Waiter.get(user_zone_uid)
        waiter = waiter.dumps(shallow=True)
        for item in zone_list:
            if item[0] in waiter['zone_list']:
                item.append(1)
    return render_to_response('admin/waiter/edit_waiter.html', {
        'waiter': waiter,
        'zone_list': zone_list,
        'admin_user_list': admin_user_list,
        },
        RequestContext(request))

def check_waiter_id(waiter_id):
    try:
        if waiter_id[:2] != 'wt':
            return False
        if int(waiter_id[2:]) > 9999 or int(waiter_id[2:]) < 1000:
            return False
        return int(waiter_id[2:])
    except:
        return False


@login_permission_required('edit_waiter') 
def edit_waiter_p(request):
    waiter_id = request.POST.get('waiter_id',None)
    user_zone_uid = check_waiter_id(waiter_id)
    if not user_zone_uid:
        return HttpResponse('<script>alert("游戏帐号错误");history.go(-1);</script>')
    waiter_pwd = request.POST.get('waiter_pwd',None)
    if not waiter_pwd:
        return HttpResponse('<script>alert("请填写游戏密码");history.go(-1);</script>')
    try:
        waiter_lv = int(request.POST.get('waiter_lv', None))
        if waiter_lv >9 or waiter_lv<1:
            raise
    except:
        return HttpResponse('<script>alert("Waiter等级错误");history.go(-1);</script>')
    new_waiter = request.POST.get('new_waiter',None)
    zone_list = request.POST.getlist('zone_id')
    admin_user = request.POST.get('admin_user',None)
    waiter = Waiter.get(user_zone_uid)
    if new_waiter:
        if not waiter:
            waiter = Waiter(int(user_zone_uid))
        else:
            if waiter.status == 0:
                return HttpResponse('<script>alert("已有帐号");history.go(-1);</script>')
            waiter.status = 0
        content = [u'新建']
    else:
        if not waiter:
            return HttpResponse('<script>alert("无效的帐号");history.go(-1);</script>')
        content = [u'修改']
    waiter.waiter_pwd = waiter_pwd
    waiter.waiter_lv = waiter_lv
    waiter.admin_user = admin_user
    waiter.zone_list = zone_list
    user_zone = UserZone.get(user_zone_uid)
    user_zone.pf_pwd = waiter_pwd
    user_zone.save()
    waiter.save()

    content.append([waiter.waiter_id,waiter.waiter_pwd,waiter.waiter_lv,waiter.admin_user,waiter.zone_list])
    if admin_user != 'admin':
        user = select([admin_table],and_(admin_table.c.username==admin_user)).execute().fetchone()
        admin_zone_list = pickle.loads(str(user.zone_list))
        admin_zone_list = list(set(admin_zone_list+zone_list))
        admin_table.update(admin_table.c.username==admin_user).execute(zone_list=pickle.dumps(admin_zone_list))

    edit_admin_user = request.session['admin_user']['username']
    AdminLog.add_adminlog(edit_admin_user, 'edit_waiter', repr(content))


    return view_waiter(request)

@login_permission_required('edit_waiter') 
def del_waiter(request):

    waiter_id = request.GET.get('waiter_id',None)
    user_zone_uid = check_waiter_id(waiter_id)
    if not user_zone_uid:
        return HttpResponse('<script>alert("无效的帐号");history.go(-1);</script>')
    waiter = Waiter.get(user_zone_uid)
    if not waiter:
        return HttpResponse('<script>alert("无效的帐号");history.go(-1);</script>')
    waiter.status = 1
    waiter.save()
    admin_user = request.session['admin_user']['username']
    content = [u'删除',[waiter.waiter_id,waiter.waiter_pwd,waiter.waiter_lv,waiter.admin_user,waiter.zone_list]]
    AdminLog.add_adminlog(admin_user, 'edit_waiter', repr(content))



    return view_waiter(request)


def check_waiter(request,waiter_id,zone):
    user_zone_uid = check_waiter_id(waiter_id)
    if not user_zone_uid:
        return False
    waiter = Waiter.get(user_zone_uid)
    admin_user = request.session['admin_user']['username']
    if not waiter or waiter.admin_user != admin_user or waiter.status != 0 or zone not in waiter.zone_list:
        return False
    return waiter


@login_permission_required('waiter_game') 
def waiter_game(request):
    admin_user = request.session['admin_user']['username']
    zone_list = UserZone.get_zone_list('old')
    zone_dict = {}
    for k,v in zone_list:
        zone_dict[k] = v
    waiter_list = []
    for item in Waiter.query({'status': 0, 'admin_user': admin_user}):
        item_zone_list = []
        for z in item.zone_list:
            item_zone_list.append([z,zone_dict[z]])
        item.zone_list = item_zone_list
        waiter_list.append(item)



    waiter_id = request.GET.get('waiter_id',None)
    zone = request.GET.get('zone',None)
    uid = ''
    pay_ids = []
    mod_user = None
    pay_list = []
    admin_pay_list = []
    limit_dict = {}
    if waiter_id and zone:
        waiter = check_waiter(request,waiter_id,zone)
        if not waiter:
            return HttpResponse('<script>alert("无效的帐号");history.go(-1);</script>')
        app_user = UserZone.call_server_api(zone, 'get_user', {'uid': waiter.waiter_id})

        if not app_user:
            return HttpResponse('<script>alert("无效的帐号");history.go(-1);</script>')
        limit_dict = waiter.get_limit_dict(zone)
        waiter.check_zone_log(zone)
        for k,v in limit_dict.items():
            limit_dict[k] = [waiter.zone_log[zone][k],v]
        uid = waiter.waiter_id

        uname = app_user.get('uname')
        pay_ids = app_user['records']['pay_ids']
        now = datetime.datetime.now()
        mod_user = [
            ['uid', u'Uid'],
            ['uname', u'Uname'],
            ['building_lv', u'官邸等级'],
            ['country', u'国家'],
            ['office', u'爵位等级'],
            ['official', u'官职'],
            ['login_time', u'最后登录时间'],
            ['pay_money', u'实际充值'],
            ['admin_pay', u'虚拟充值'],

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
            ]
        pay_config = game_config.pay_config
        admin_pay_list = []
        admin_pay = 0
        for pay_id in app_user['records']['pay_ids']:
            if str(pay_id).startswith('pay'):
                pid,tt = pay_id.split('|')[:2]
                if pay_config.has_key(pid):
                    admin_pay += pay_config[pid][0]
                    admin_pay_list.append('|'.join([pid,str(pay_config[pid][0]),tt]))
        admin_pay_list = '\n'.join(admin_pay_list)

        for item in mod_user:
            if item[0] == 'login_time':
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
            elif item[0] == 'pay_money':
                item.append(app_user['records']['pay_money']-admin_pay)
            elif item[0] == 'admin_pay':
                item.append(admin_pay)
            elif item[0] == 'power_hero_list':
                hero = ''
                for h in app_user['power_hero_list']:
                    hero+=u'%s%s，' % (h[2],h[1])
                item.append(hero)
                del app_user['power_hero_list']
            else:
                item.append(app_user.get(item[0]))
        pay_list = []
        for k,v in pay_config.items():
            pay_list.append([k,v[0]])

    return render_to_response('admin/waiter/waiter_game.html', {
        'zone_list': zone_list,
        'waiter_list': waiter_list,

        'limit_dict': limit_dict,
        'uid': uid,
        'pay_ids': pay_ids,
        'mod_user': mod_user,
        'admin_user': request.session['admin_user']['username'],
        'zone': zone,
        'pay_config': sorted(pay_list),
        'admin_pay_list': admin_pay_list,
        },
        RequestContext(request))

@login_permission_required('waiter_game',ajax=True)
def waiter_pay(request):
    try:
        waiter_id = request.POST.get('waiter_id')
        zone = request.POST.get('zone')
        waiter = check_waiter(request,waiter_id,zone)
        if not waiter:
            return HttpResponse(json.dumps({'state':'error', 'msg': '无效帐号'}))
        limit_dict = waiter.get_limit_dict(zone)
        waiter.check_zone_log(zone)
        pay_config = game_config.pay_config
        pid = request.POST.get('pid')
        pay_money = pay_config[pid][0]
        if waiter.zone_log[zone]['pay'] + pay_money > limit_dict['pay']:
            return HttpResponse(json.dumps({'state':'error', 'msg': '超出今日额度上限'}))
        if waiter.zone_log[zone]['pay_all'] + pay_money > limit_dict['pay_all']:
            return HttpResponse(json.dumps({'state':'error', 'msg': '超出累计额度上限'}))
        v = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        admin_user = request.session['admin_user']['username']
        pay_id = '%s|%s|%s' % (pid,v,admin_user)

        pay_result = UserZone.call_server_api(zone, 'user_pay', {'uid': waiter.waiter_id, 'pid': pid, 'pay_id': pay_id})
        if pay_result['succ'] != 1:
            return HttpResponse(json.dumps({'state':'error', 'msg': '充值失败'}))
        pay_ids = pay_result['pay_ids']
        content = '%s_%s' % (pay_id,zone)
        AdminLog.add_adminlog(admin_user,'admin_pay',content)
        waiter.zone_log[zone]['pay_all'] += pay_money
        waiter.zone_log[zone]['pay'] += pay_money
        waiter.save()



    except Exception, e:
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success','pay_ids': pay_ids}))


@login_permission_required('waiter_game',ajax=True)
def admin_waiter(request):
    try:

        waiter_id = request.POST.get('waiter_id')
        zone = request.POST.get('zone')
        method = request.POST.get('method')
        waiter = check_waiter(request,waiter_id,zone)
        if not waiter:
            return HttpResponse(json.dumps({'state':'error', 'msg': '无效帐号'}))
        params = {'uid': waiter.waiter_id, 'method': method}
        if method not in ['coin','building','office','gtask','effort','pve']:
            return HttpResponse(json.dumps({'state':'error', 'msg': '暂未开放'}))
        if method == 'coin':
            limit_dict = waiter.get_limit_dict(zone)
            waiter.check_zone_log(zone)
            if waiter.zone_log[zone]['coin'] >= limit_dict['coin']:
                return HttpResponse(json.dumps({'state':'error', 'msg': '超出今日Coin额度'}))
            params['add_coin'] = limit_dict['coin']-waiter.zone_log[zone]['coin']
            waiter.zone_log[zone]['coin'] = limit_dict['coin']



        waiter_result = UserZone.call_server_api(zone, 'admin_waiter', params)
        if waiter_result['succ'] != 1:
            return HttpResponse(json.dumps({'state':'error', 'msg': '操作失败'}))

        if method == 'coin':
            waiter.save()


    except Exception, e:
        print e
        return HttpResponse(json.dumps({'state':'error', 'msg': str(e)}))
    return HttpResponse(json.dumps({'state':'success'}))


