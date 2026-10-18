#-*- coding: utf-8 -*-
import re
from django.conf import settings
from django.http import HttpResponse
import json
import urllib2
import cPickle as pickle
from sqlalchemy import and_
from game_lib.logics import game_config
from game_lib.models.main import UserZone

from db.database import admin_table, role_table

def login_permission_required(permission=None, ajax=False):
    def decorate(view_func):
        def _func(request,*args,**kwargs):
            if not request.auth.logged:
                if ajax:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'请登录操作'}))
                else:
                    return HttpResponse(u'<script>alert("请登录操作");top.location.href="%s/admin/";</script>' % settings.BASE_URL)
            session_user = request.session.get('admin_user')
            user_permissions = list(set([p.split('|')[0] for p in session_user['permissions']]))
            is_super = session_user['is_super']
            if permission and not is_super:
                if permission not in user_permissions:
                    if ajax:
                        return HttpResponse(json.dumps({'state': 'error', 'msg': u'"permissions.%s" 无权限' % permission}))
                    else:
                        return HttpResponse(u'<script type=\'text/javascript\'>alert("permission %s required");history.go(-1);</script>' % permission)
            zone = request.REQUEST.get('zone',None)
            if not zone:
                uid_zone = request.REQUEST.get('uid_zone', None)
                if not uid_zone:
                    zone = None
                else:
                    zone = uid_zone.split('|')[-1]

            if zone and zone.find(':') == -1 and not is_super:
                if session_user['zone_list']:
                    if zone not in session_user['zone_list']:
                        if ajax:
                            return HttpResponse(json.dumps({'state': 'error', 'msg': u'"分区.%s" 无权限' % zone}))
                        else:
                            return HttpResponse(u'<script>alert("permission-zone %s required");history.go(-1);</script>' % zone)
                elif session_user['zone_group_list']:
                    if not UserZone.belong_to_zone_groups(zone, session_user['zone_group_list']):
                        if ajax:
                            return HttpResponse(json.dumps({'state': 'error', 'msg': u'"分区.%s" 无权限' % zone}))
                        else:
                            return HttpResponse(u'<script>alert("permission-zone %s required");history.go(-1);</script>' % zone)
            return view_func(request,*args,**kwargs)
        _func.__doc__ = view_func.__doc__
        _func.__dict__ = view_func.__dict__
        return _func
    return decorate


def role_super_check(ajax=False):
    """
    超管权限检查：
    权限A：新建、指定删除超管，编辑超管的手机号、权限、密码等
    权限B：查看管理员管理页面，新建、指定删除非超管用户，编辑非超管的手机号、权限、密码等

    admin有权限AB
    超管只有权限B

    超管拥有除【仅限waiter充值】以外的所有权限
    :param ajax:
    :return:
    """
    def decorate(view_func):
        def _func(request,*args,**kwargs):
            can_action = True
            session_user = request.session.get('admin_user')
            is_super = session_user['is_super']
            if is_super:
                return view_func(request, *args, **kwargs)
            username = request.REQUEST.get('username')
            role_name = request.POST.get('role_name')
            if session_user['username'] == username:
                return view_func(request, *args, **kwargs)
            if role_name and role_name == 'admin':
                if ajax:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'无权限指定超管！'}))
                else:
                    return HttpResponse(u'<script>alert("无权限指定超管！");history.go(-1);</script>')


            ## 被编辑的用户角色
            modify_user_role = role_table.select(and_(admin_table.c.username == username, role_table.c.name == admin_table.c.role_id)).execute().fetchone()
            if modify_user_role and modify_user_role.name == 'admin':
                if ajax:
                    return HttpResponse(json.dumps({'state': 'error', 'msg': u'无权限修改超管数据！'}))
                else:
                    return HttpResponse(u'<script>alert("无权限修改超管数据！");history.go(-1);</script>')
            return view_func(request,*args,**kwargs)
        _func.__doc__ = view_func.__doc__
        _func.__dict__ = view_func.__dict__
        return _func
    return decorate

