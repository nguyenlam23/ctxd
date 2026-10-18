#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from copy import deepcopy as copy
from admin.logic import login_permission_required
from admin.pager import Pager
import datetime
from sqlalchemy import *
from game_lib.models.main import BugMsg, UserZone, CountryNotice
from game_lib.db.database import BugMsg_table 
from game_lib.common import utils
from game_lib.logics import game_config
import json
import cPickle as pickle
import urllib, urllib2


@login_permission_required('re_msg')
def pass_msg(request):
    try:
        uid = request.REQUEST.get('uid_zone', None)
        session_user = request.session['admin_user']
        admin_user = session_user['username']
        bug_msg = BugMsg.install(uid)

        if bug_msg.status != 1:
            content = u'%s|忽略问题' % admin_user
            bug_msg.add_bug_msg(content,st=3)

        
        return msg_view_user(request)
    except Exception, e:
        return HttpResponse(json.dumps({'state': 'error', 'msg': e.message}))

@login_permission_required('re_msg')
def mark_msg(request):
    try:
        uid = request.REQUEST.get('uid_zone', None)
        session_user = request.session['admin_user']
        admin_user = session_user['username']
        bug_msg = BugMsg.install(uid)


        if bug_msg.status != 2:
            content = u'%s|疑难问题' % admin_user
            bug_msg.add_bug_msg(content,st=2)


        return msg_view_user(request)
    except Exception, e:
        return HttpResponse(json.dumps({'state': 'error', 'msg': e.message}))


@login_permission_required('re_msg')
def re_msg(request):
    content = request.POST.get('content', None)
    uid = request.POST.get('uid_zone', None)
    if not content:
        return HttpResponse('<script>alert("怎么着也得说点啥吧");history.go(-1);</script>')
    if len(content) > 150:
        return HttpResponse('<script>alert("就不能一次少说点么？");history.go(-1);</script>')
    session_user = request.session['admin_user']
    admin_user = session_user['username']
    bug_msg = BugMsg.install(uid)
    if not bug_msg:
        return HttpResponse(u'<script>alert("用户不存在");history.go(-1);</script>')
    content = '%s|%s' % (admin_user,content)
    bug_msg.add_bug_msg(content,st=1)
    userid,zone = uid.split('|')
    UserZone.call_server_api(zone, 'bug_msg', {'uid': userid})
    return msg_view_user(request)



@login_permission_required('msg_view')
def msg_view(request):
    now = datetime.datetime.now()
    status = int(request.REQUEST.get('status',0))
    zone_group = request.REQUEST.get('zone_group')
    if zone_group:
        zone_group = zone_group.split('|')
    session_user = request.session.get('admin_user')
    zone_group_list = []
    for item in UserZone.get_zone_group_list():
        if not session_user['is_super'] and not session_user['role_super'] and session_user['zone_group_list'] and item['id'] not in session_user['zone_group_list']:
            continue
        if zone_group and item['id'] in zone_group:
            item['checked'] = 'checked'
        else:
            item['checked'] = 'unchecked'
        zone_group_list.append(item)
    msgs_list = []
    parameter = {}
    page = int(request.GET.get('page','1')) 
    p = None
    operable_zone_list = []
    for z in [item[0] for item in UserZone.get_zone_list('all', session_user=session_user)]:
        if zone_group and not UserZone.belong_to_zone_groups(z, zone_group):
            continue
        operable_zone_list.append(z)
    parameter = {'status': status}
    if zone_group:
        parameter['zone_group'] = '|'.join(zone_group)
    page_size = 20
    page_list_num = 10
    cond = {'status': status, 'zone_in': operable_zone_list}
    total = BugMsg.count(cond)
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,parameter=parameter) 
    msgs_list = BugMsg.query(cond,
                             order_by='-time',
                             limit=page_size,
                             offset=offset,
                             attrs=['uid', 'time', 'content']
                             )
    data = []
    for item in msgs_list:
        user_zone = UserZone.get(item['uid'].split('|')[0])
        item['pf'] = user_zone.pf
        data.append(item)
    request.session['bug_msg_status'] = status
    return render_to_response('admin/msg/msg.html', {
        'msgs_list': data,
        'p': p,
        'parameter': parameter,
        'page':page,
        'zone_group_list': zone_group_list
        }, 
        RequestContext(request))

@login_permission_required('msg_view_user')
def msg_view_user(request):
    uid_zone = request.REQUEST.get('uid_zone', None)
    next_uid = None
    up_uid = None
    bug_msg = None
    if uid_zone:
        bug_msg = BugMsg.install(uid_zone)
        if not bug_msg:
            return HttpResponse(u'<script>alert("用户不存在");history.go(-1);</script>')
        view_uid = request.REQUEST.get('view_uid', None)
        if view_uid:
            if bug_msg.status == -1:
                request.session['bug_msg_status'] = 0
            else:
                request.session['bug_msg_status'] = bug_msg.status

        status = request.session.get('bug_msg_status',0)
        if bug_msg.data:
            bug_msg.data.sort(key= lambda x:x['time'], reverse=True)

            next_info = list(BugMsg.query({'status': status, 'time_lt': bug_msg.time},order_by='-time', limit=1,attrs=['uid']))
            if next_info:
                next_uid = next_info[0]['uid']
            up_info = list(BugMsg.query({'status': status, 'time_gt': bug_msg.time},order_by='time', limit=1,attrs=['uid']))
            if up_info:
                up_uid = up_info[0]['uid']
            for item in bug_msg.data:
                item['time'] = str(item['time'])[:19]


    #gift_list.sort(key= lambda x:x['time'], reverse=True)
    return render_to_response('admin/msg/msg_user.html', {
        'bug_msg': bug_msg,
        'up_uid' : up_uid,
        'next_uid': next_uid,
        }, 
        RequestContext(request))

@login_permission_required('msg_view')
def country_notice_view(request):
    c_country_maps = {0: u'魏', 1: u'蜀', 2: u'吴'}
    page = int(request.GET.get('page','1'))
    session_user = request.session.get('admin_user')
    p = None
    operable_zone_list = [item[0] for item in UserZone.get_zone_list('running', session_user=session_user)]
    zone_cids = []
    for zone in operable_zone_list:
        for i in xrange(3):
            zone_cids.append('%s|%s' % (zone, i))
    page_size = 50
    page_list_num = 10
    cond = {'zone_cid_in': zone_cids}
    total = CountryNotice.count(cond)
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,)
    notices = CountryNotice.query(cond,
                                  order_by='-update_time',
                                  limit=page_size,
                                  offset=offset
                                  )
    notice_list = []
    for c in notices:
        zone,cid = c.zone_cid.split('|')
        notice_list.append({
            'zone': zone,
            'country': c_country_maps[int(cid)],
            'update_time': str(c.update_time),
            'content': c.content
        })
    return render_to_response('admin/msg/country_notice_view.html', {
        'notice_list': notice_list,
        'p': p,
        'page':page,
    }, RequestContext(request))
