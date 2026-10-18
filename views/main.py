#-*- coding: utf-8 -*-
import time
import random, string
import datetime
from hashlib import md5
import cPickle as pickle

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from game_lib.libs.verify_code import make as make_verify_code

from sqlalchemy import *
from db.database import admin_table, role_table, pay_records_table as ASP
from admin.menus import MENUS
from admin.permissions import PERMISSIONS
from admin.logic import login_permission_required, role_super_check
from game_lib.logics import game_config
import json
LEVEL_KEY = lambda x:str(((x-1)/5)*5+1) + '_' + str((((x-1)/5)*5+5))
DEFAULT_PASSWORD = u'meng2013'
from copy import deepcopy as copy
from game_lib.models.main import UserZone

from game_lib.db.database import c_cache as cache
from game_lib.common.tencentcloud import send_sms
from game_lib.models.main import AdminLog, AdminPayRecord
from game_lib.models.cache import CacheTable

nocache = lambda :md5(str(random.random()**random.random()*time.time())).hexdigest()

def img_verify_code(request):
    verify_code = '%04d' % random.randint(0, 8888)
    content = make_verify_code(verify_code)
    request.session['verify_code'] = verify_code
    r = HttpResponse(content)
    r._headers['content-type'] = ('Content-type','image/jpeg')
    return r

def sms_verify_code(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    password = md5(password.strip()).hexdigest()
    data = {
        'status': 'success',
        'msg': '',
    }
    user = admin_table.select(and_(admin_table.c.username == username.strip(), admin_table.c.status != 1)).execute().fetchone()
    if not user:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'用户不存在'}))
    if user['password'] != password:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'密码错误'}))
    if not user['phone']:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'该账号没有绑定手机号'}))
    if user['phone'] == 'free':
        return HttpResponse(json.dumps({'state': 'success', 'verify_type': 'img_code'}))
    cache_code = {
        'code': '%04d' % random.randint(0, 8899),
        'expire': int(time.time()) + (60*15)
    }
    for phone in user['phone'].split(','):
        send_sms.send_admin_sign(phone, cache_code['code'], settings.WHERE, username)
    cache_key = settings.CACHE_PRE+str(request.POST.get('username'))+'_admin_login'
    cache.set(cache_key, cache_code)
    return HttpResponse(json.dumps({'state': 'success', 'verify_type': 'sms_code'}))

def verify_sms_code(username, verify_code):
    cache_key = settings.CACHE_PRE + str(username) + '_admin_login'
    code_data = cache.get(cache_key)
    cache.delete(cache_key)
    if not code_data:
        return False
    if code_data['expire'] <= int(time.time()):
        return False
    return verify_code == code_data['code']

def verify_img_code(request, verify_code):
    img_code = request.session['verify_code']
    del request.session['verify_code']
    return img_code == verify_code

def index(request):
    if request.POST:
        username = request.POST.get('username')
        password = request.POST.get('password')

        verify_code = request.POST.get('verify_code')
        if not username or not password:
            return HttpResponseRedirect(settings.BASE_URL + '/admin/')
        password = md5(password.strip()).hexdigest()
        user = select([admin_table],and_(admin_table.c.username==username.strip(),admin_table.c.status<>1)).execute().fetchone()

        if getattr(settings, 'LOGIN_CODE_AUTH', True):
            if not verify_code:
                return HttpResponseRedirect(settings.BASE_URL + '/admin/')
            if user['phone'] == 'free':
                verify_checked = verify_img_code(request, verify_code)
            else:
                verify_checked = verify_sms_code(username, verify_code)
            if not verify_checked:
                return render_to_response('admin/login.html', {
                    'error': 'err_verify_code',
                    'nocache':nocache()
                    },
                    RequestContext(request))
        if not user:
            return render_to_response('admin/login.html', {
                'error': 'null_username',
                'nocache':nocache()
                }, 
                RequestContext(request))
        if user['password'] <> password:
            return render_to_response('admin/login.html', {
                'error': 'err_userpass',
                'nocache':nocache()
                }, 
                RequestContext(request))
        user_role = role_table.select(and_(role_table.c.name == user.role_id)).execute().fetchone()
        permissions = pickle.loads(str(user.permissions))
        if user_role:
            if user_role.name == 'admin':
                ## 超管角色权限，手动添加用户管理权限
                role_permissions = [item[0] for item in PERMISSIONS if item[0] != 'admin_waiter_pay']
                role_permissions.append('super')
                permissions.extend(role_permissions)
            else:
                permissions.extend(pickle.loads(str(user_role.permissions)))
        session_user = {
            'username': user['username'],
            'nickname': user['nickname'] or user['username'],
            'password': user['password'],
            'permissions': list(set(permissions)),
            'is_super': True if user.username == 'admin' else False,
            'role_super': True if user_role and user_role.name == 'admin' else False
        }
        if user['zone_list']:
            session_user['zone_list'] = pickle.loads(str(user['zone_list']))
        else:
            session_user['zone_list'] = []
        if user['zone_group_list']:
            session_user['zone_group_list'] = pickle.loads(str(user['zone_group_list']))
        else:
            session_user['zone_group_list'] = []
        request.session['admin_user'] = session_user
        admin_table.update(admin_table.c.username == user['username']).execute(last_login_time=datetime.datetime.now(),last_login_ip=request.META['REMOTE_ADDR'])
        request.auth.login(session_user)
            
        return render_to_response('admin/index.html', {
            }, 
            RequestContext(request))
    lk = request.GET.get('lk', None)
    where = 'login'
    if request.auth.logged:
        where = 'index'
    return render_to_response('admin/%s.html' % where, {
                            'nocache':nocache()
        }, 
        RequestContext(request))

def logout(request):
    if request.auth.logged:
        del request.session['admin_user']
        request.auth.logout()
    return render_to_response('admin/login.html', {
                            'nocache':nocache()
        }, 
        RequestContext(request))



@login_permission_required()
def left(request):
    session_user = request.session['admin_user']
    user_permissions = list(set([p.split('|')[0] for p in session_user['permissions']]))
    menus = []
    if not session_user['is_super']:
        for item in MENUS:
            _item = item.copy()
            _item['menus'] = []
            for p in item['menus']:
                if p[1] is None or p[1] in user_permissions:
                    _item['menus'].append(p)
            if _item['menus']:
                menus.append(_item)
    else:
        menus = MENUS
    take_config_type = CacheTable.get('take_config_type', 'setting')  # 使用的正是配置setting/测试配置test_setting
    return render_to_response('admin/left.html', {
        'menus': menus,
        'username': session_user['username'],
        'take_config_type': take_config_type,
        }, 
        RequestContext(request))


@login_permission_required()
def welcome(request):
    return render_to_response('admin/welcome.html', {
        }, 
        RequestContext(request))

@login_permission_required('super')
def admin(request):
    admin_list = []
    sql_list = admin_table.select(and_(admin_table.c.username <> 'admin')).execute().fetchall()
    for item in sql_list:
        _item = dict(item)
        _item['default_pwd'] = False
        if _item['password'] == md5(DEFAULT_PASSWORD).hexdigest():
            _item['default_pwd'] = True
        permissions = pickle.loads(str(item.permissions))
        user_role = role_table.select(role_table.c.name == item.role_id).execute().fetchone()
        if user_role:
            if user_role.name == 'admin':
                role_permissions = [i[0] for i in PERMISSIONS]
            else:
                role_permissions = pickle.loads(str(user_role.permissions))
            user_per_count = len(set(permissions).difference(set(role_permissions)))
            role_name = '%s+%s' % (user_role.cname, user_per_count)
            permissions.extend(role_permissions)
            role_priority = user_role.priority
        else:
            role_name = ''
            role_priority = 0
            user_per_count = 0
        _item['role'] = role_name
        _item['permission_rate'] = '%.2f%%' % (len(list(set(permissions)))*1.0/len(PERMISSIONS)*100)
        zone_list = pickle.loads(str(_item['zone_list'])) if _item['zone_list'] else []
        zone_group_list = pickle.loads(str(_item['zone_group_list'])) if _item['zone_group_list'] else []
        _item['zone_count'] = len(zone_list)
        _item['zone_groups'] = ','.join(zone_group_list)
        _item['role_priority'] = role_priority
        _item['user_pre_count'] = user_per_count
        _item['pay_money'] = AdminPayRecord.sum('pay_money', condition={'admin_user': item.username})
        admin_list.append(_item)
    admin_list = sorted(admin_list, key=lambda x: (x['role_priority'], x['user_pre_count'], x['username']), reverse=True)
    return render_to_response('admin/admin.html', {
        'admin_list':admin_list,
        'de_pwd': DEFAULT_PASSWORD,
        }, 
        RequestContext(request))

@login_permission_required('super')
@role_super_check()
def edit_add_admin(request):
    admin_user = None
    session_user = request.session['admin_user']
    username = request.GET.get('username',None)
    user_roles = [
        {'name': '', 'cname': '无角色', 'checked': False, 'permissions': [], 'info': ''}
    ]
    for role in role_table.select().order_by(role_table.c.priority.desc()).execute().fetchall():
        if session_user['username'] != username and (not session_user['is_super'] and role.name == 'admin'):
            continue
        if role.name == 'admin':
            role_permissions = [item[0] for item in PERMISSIONS if item[0] != 'admin_waiter_pay']
            role_permissions.append('super')
        else:
            role_permissions = pickle.loads(str(role.permissions))
        user_roles.append({
            'name': role.name,
            'cname': role.cname,
            'info': role.info,
            'permissions': role_permissions,
            'checked': False
        })
    role_permissions = []
    if username:
        user = select([admin_table],and_(admin_table.c.username == username)).execute().fetchone()
        admin_user = {'username': user.username, 'permissions':pickle.loads(str(user.permissions))}
        if user.zone_list:
            admin_user['zone_list'] = pickle.loads(str(user.zone_list))
        else:
            admin_user['zone_list'] = []
        if user.zone_group_list:
            admin_user['zone_group_list'] = pickle.loads(str(user.zone_group_list))
        else:
            admin_user['zone_group_list'] = []
        if user.role_id:
            for role in user_roles:
                _role_permissions = role.pop('permissions')
                if role['name'] != user.role_id:
                    continue
                role['checked'] = True
                role_permissions = _role_permissions
                admin_user['role_info'] = role['info']
                break
        admin_user['permissions'].extend(role_permissions)
    permissions = copy(PERMISSIONS)
    for item in permissions:
        if admin_user and item[0] in admin_user['permissions']:
            item.insert(2, 'checked')
        else:
            item.insert(2, 'unchecked')

        # 判断是否是角色权限
        if item[0] in role_permissions:
            item.insert(3, True)
        else:
            item.insert(3, False)
    zone_list = UserZone.get_zone_list('all')
    for item in zone_list:
        if admin_user and item[0] in admin_user['zone_list']:
            item.insert(2,'checked')
        else:
            item.insert(2,'unchecked')
    zone_group_list = UserZone.get_zone_group_list()
    for item in zone_group_list:
        if admin_user and item['id'] in admin_user['zone_group_list']:
            item['checked'] = 'checked'
        else:
            item['checked'] = 'unchecked'
    return render_to_response('admin/edit_add_admin.html', {
        'permissions':permissions,
        'admin_user': admin_user,
        'de_pwd': DEFAULT_PASSWORD,
        'zone_list': zone_list,
        'zone_group_list': zone_group_list,
        'user_roles': user_roles
        }, 
        RequestContext(request))

@login_permission_required('super')
@role_super_check()
def edit_add_admin_p(request):
    session_user = request.session['admin_user']['username']
    username = request.POST.get('username').strip()
    permissions = request.POST.getlist('permissions')
    zone_list = request.POST.getlist('zone_list')
    zone_group_list = request.POST.getlist('zone_group_list')
    action = request.POST.get('action')
    role_name = request.POST.get('role_name')
    import re
    m = re.match(r"([\w]{3,15})", username)
    if m is None:
        return HttpResponse(u'<script>alert("换个昵称吧");history.go(-1);</script>')
    if not username:
        return HttpResponse(u'<script>alert("请填写用户名");history.go(-1);</script>')
    admin_user = admin_table.select(admin_table.c.username==username).execute().fetchone()
    if action == 'add':
        if admin_user:
            return HttpResponse(u'<script>alert("该用户已存在");history.go(-1);</script>')
        else:
            values = {'username': username, 'nickname': username}
            values['role_id'] = role_name
            values['password'] = md5(DEFAULT_PASSWORD).hexdigest()
            values['permissions'] = pickle.dumps(permissions)
            values['zone_list'] = pickle.dumps(zone_list)
            values['zone_group_list'] = pickle.dumps(zone_group_list)
            admin_table.insert().execute(**values)
    elif action == 'edit':
        if not admin_user:
            return HttpResponse(u'<script>alert("该用户不存在");history.go(-1);</script>')
        else:
            admin_table.update(admin_table.c.username==admin_user.username).execute(
                    role_id=role_name,
                    permissions=pickle.dumps(permissions),
                    zone_list=pickle.dumps(zone_list),
                    zone_group_list=pickle.dumps(zone_group_list)
                    )
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': '%s_user' % action,
                                                         'data': {
                                                             'role_name': role_name,
                                                             'username': username,
                                                             'permissions': permissions,
                                                             'zone_list': zone_list,
                                                             'zone_group_list': zone_group_list
                                                         }}))
    return HttpResponseRedirect(settings.BASE_URL+ '/admin/admin/')

@login_permission_required()
def get_role_permissions(request):
    role_name = request.GET['role_name']
    role = role_table.select(role_table.c.name == role_name).execute().fetchone()
    if role:
        if role_name == 'admin':
            role_permissions = [item[0] for item in PERMISSIONS if item[0] != 'admin_waiter_pay']
        else:
            role_permissions = pickle.loads(str(role.permissions))
        info = role.info
    else:
        role_permissions = []
        info = ''
    role = {'info': info, 'permissions': role_permissions}
    return HttpResponse(json.dumps(role))

@login_permission_required()
def change_password(request):
    session_user = request.session['admin_user']
    return render_to_response('admin/change_password.html', {
        'nickname': session_user['nickname']
        }, 
        RequestContext(request))

@login_permission_required(ajax=True)
def change_password_p(request):
    nickname = request.POST.get('nickname')
    old_password = request.POST.get('old_password')
    new_password = request.POST.get('new_password')
    if not nickname:
        return HttpResponse(json.dumps({'state':'error','msg':u'请填写昵称'}))
    if not old_password or not new_password:
        return HttpResponse(json.dumps({'state':'error','msg':u'请填写原密码和新密码'}))
    session_user = request.session['admin_user']
    if md5(old_password).hexdigest() != session_user['password']:
        return HttpResponse(json.dumps({'state':'error','msg':u'原密码不正确'}))
    admin_table.update(admin_table.c.username == session_user['username']).execute(nickname=nickname, password=md5(new_password).hexdigest()) 
    session_user['password'] = md5(new_password).hexdigest()
    session_user['nickname'] = nickname
    request.session['admin_user'] = session_user
    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('super')
@role_super_check(ajax=True)
def reset_password(request):
    session_user = request.session['admin_user']['username']
    username = request.POST.get('username')
    admin_table.update(admin_table.c.username == username).execute(password = md5(DEFAULT_PASSWORD).hexdigest())
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'reset_password', 'data': {'username': username}}))

    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('super')
@role_super_check(ajax=True)
def reset_password2(request):
    session_user = request.session['admin_user']['username']
    username = request.POST.get('username')
    new_password = request.POST.get('new_password').strip()
    if not new_password:
        new_password = ''.join(random.sample(string.ascii_letters+string.digits, 10))
    admin_table.update(admin_table.c.username == username).execute(password = md5(new_password).hexdigest())
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'reset_password2', 'data': {'username': username}}))

    return HttpResponse(json.dumps({'state':'success', 'new_password': new_password}))

@login_permission_required('super')
@role_super_check(ajax=True)
def del_admin(request):
    session_user = request.session['admin_user']['username']
    username = request.POST.get('username')
    if session_user == username:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'不能删除自己账号'}))
    admin_table.delete(admin_table.c.username == username).execute()
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'del_admin', 'data': {'username': username}}))

    return HttpResponse(json.dumps({'state':'success'}))

@login_permission_required('super', ajax=True)
@role_super_check(ajax=True)
def reset_phone_num(request):
    session_user = request.session['admin_user']['username']
    username = request.POST.get('username')
    phone = request.POST.get('phone')
    for p in phone.split(','):
        if p and p != 'free' and len(p) != 11:
            return HttpResponse(json.dumps({'state': 'error', 'msg': u'{phone}手机号格式不正确'.format(phone=p)}))
    admin_table.update(admin_table.c.username == username).execute(phone=phone)
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'reset_phone_num', 'data': {'username': username,
                                                                                                'phone': phone}}))
    return HttpResponse(json.dumps({'state': 'success'}))


@login_permission_required('super')
def admin_op_logs(request):
    permission_maps = dict(PERMISSIONS)
    op_type_maps = {
        'reset_phone_num': u'绑定手机号',
        'del_admin': u'删除用户',
        'reset_password2': u'设置密码',
        'reset_password': u'重置为默认密码',
        'edit_user': u'编辑用户',
        'add_user': u'新增用户',
        'logout_user': u'用户退出登录'
    }
    logs = []
    for log in AdminLog.acquire_adminlogs('admin_op'):
        item = {
            'op_user': log.admin_user,
            'subtime': str(log.subtime)[:19],
        }
        content = eval(str(log.content))
        item['op_type'] = op_type_maps.get(content['op_type'], content['op_type'])
        if content['op_type'] in ['edit_user', 'add_user']:
            data = copy(content['data'])
            data['permissions'] = [permission_maps.get(k, k) for k in data['permissions']]
        else:
            data = content['data']
        item['data'] = json.dumps(data, indent=2, ensure_ascii=False)
        logs.append(item)
    return render_to_response('admin/admin_log.html', {
        'logs': logs
    },
    RequestContext(request))

@login_permission_required('super')
def admin_pay_records(request):
    username = request.GET['username']
    order_by = request.GET.get('order_by', '-pay_money')
    show_real = int(request.GET.get('show_real', 0))
    records = []
    for r in AdminPayRecord.query(condition={'admin_user': username}, order_by=order_by):
        r_dict = r.dumps()
        user_zone = UserZone.get(r.uid)
        r_dict['real_pay_money'] = user_zone.pay_money
        r_dict['pf'] = user_zone.pf
        r_dict['pf_key'] = user_zone.pf_key
        if show_real:
            pay_records = ASP.select(and_(ASP.c.uid == r.uid)).order_by(ASP.c.pay_time).execute().fetchall()
            r_dict['real_first_time'] = pay_records[0].pay_time if pay_records else None
            r_dict['real_last_time'] = pay_records[-1].pay_time if pay_records else None
            r_dict['lv20_count'] = 0
            r_dict['first_real'] = 0
            if r_dict['real_first_time'] and r_dict['real_first_time'] < r_dict['first_time']:
                r_dict['first_real'] = 1
            for zone in user_zone.zone_login.keys():
                if not zone:
                    continue
                if zone not in game_config.zone:
                    continue
                app_user = UserZone.call_server_api(zone, 'get_user', {'uid': r.uid})
                if not app_user:
                    continue
                lv = app_user['home']['building001']['lv']
                if lv >= 20:
                    r_dict['lv20_count'] += 1
        records.append(r_dict)
    return render_to_response('admin/admin_pay_records.html', {
        'records': records,
        'username': username,
        'show_real': show_real
    },
    RequestContext(request))

@login_permission_required('role_super')
def get_roles(request):
    roles = []
    role_items = role_table.select(and_(role_table.c.name != 'admin')).order_by(role_table.c.priority.desc()).execute().fetchall()
    for role in role_items:
        role_permissions = pickle.loads(str(role.permissions))
        _role = {
            'name': role.name,
            'cname': role.cname,
            'info': role.info,
            'priority': role.priority,
            'permission_rate': '%.2f%%' % (len(role_permissions)*1.0/len(PERMISSIONS)*100)
        }
        roles.append(_role)
    return render_to_response('admin/roles.html', {
        'roles': roles
    }, RequestContext(request))

@login_permission_required('role_super')
def edit_add_role(request):
    role_name = request.REQUEST.get('role_name')
    permissions = copy(PERMISSIONS)
    role = None
    if role_name:
        role = role_table.select(role_table.c.name == role_name).execute().fetchone()
        role_permissions = pickle.loads(str(role.permissions))
        for item in permissions:
            if item[0] in role_permissions:
                item.insert(2,'checked')
            else:
                item.insert(2,'unchecked')

    return render_to_response('admin/edit_add_role.html', {
        'permissions': permissions,
        'role': role
    }, RequestContext(request))

@login_permission_required('role_super')
def edit_add_role_p(request):
    action = request.POST.get('action')
    name = request.POST.get('name')
    cname = request.POST.get('cname')
    info = request.POST.get('info')
    priority = request.POST.get('priority')
    permissions = request.POST.getlist('permissions')
    if action == 'create':
        role = role_table.select(role_table.c.name == name).execute().fetchone()
        if role:
            return HttpResponse(u'<script>alert("角色名重复");history.go(-1);</script>')
        values = {
            'name': name,
            'cname': cname,
            'info': info,
            'priority': priority,
            'permissions': pickle.dumps(permissions)
        }
        role_table.insert().execute(**values)
    elif action == 'modify':
        role_name = request.POST.get('role_name')
        role = role_table.select(role_table.c.name == role_name).execute().fetchone()
        if not role:
            return HttpResponse(u'<script>alert("角色不存在");history.go(-1);</script>')
        if role.name != name:
            role = role_table.select(role_table.c.name == name).execute().fetchone()
            if role:
                return HttpResponse(u'<script>alert("角色名重复");history.go(-1);</script>')
        role_table.update(role_table.c.name == role_name).execute(
            name=name,
            cname=cname,
            info=info,
            priority=priority,
            permissions=pickle.dumps(permissions),
            )
    session_user = request.session['admin_user']
    AdminLog.add_adminlog(session_user['username'], 'admin_op', str({'op_type': '%s_role' % action,
                                                         'data': {
                                                             'name': name,
                                                             'cname': cname,
                                                             'info': info,
                                                             'permissions': permissions
                                                         }}))
    return HttpResponseRedirect(settings.BASE_URL + '/admin/roles/')

@login_permission_required('role_super')
def delete_role(request):
    session_user = request.session['admin_user']['username']
    role_name = request.POST.get('role_name')
    role_table.delete(role_table.c.name == role_name).execute()
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'del_role', 'data': {'role_name': role_name}}))

    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('logout_user', ajax=True)
def force_logout_user(request):
    session_user = request.session['admin_user']['username']
    from django.core.cache import get_cache
    cache = get_cache(settings.CACHE_BACKEND)
    username = request.POST.get('username', None)
    if not username:
        return HttpResponse(json.dumps({'state': 'error', 'msg': '缺少参数'}))
    if username == 'all':
        for user in admin_table.select().execute().fetchall():
            login_key = '%slogin_info_%s' % (settings.CACHE_PRE, user.username)
            cache.delete(login_key)
    else:
        login_key = '%slogin_info_%s' % (settings.CACHE_PRE, username)
        cache.delete(login_key)
    AdminLog.add_adminlog(session_user, 'admin_op', str({'op_type': 'logout_user', 'data': {'username': username}}))
    return HttpResponse(json.dumps({'state': 'success'}))
