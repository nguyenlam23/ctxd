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
from game_lib.models.main import AdminHead
from game_lib.db.database import AdminHead_table

from game_lib.logics import game_config
import json

@login_permission_required('view_head')
def view_head(request):
    now = datetime.datetime.now()
    status = int(request.REQUEST.get('status',0))
    parameter = {}
    page = int(request.GET.get('page','1')) 
    p = None



    parameter = {'status': status}
    page_size = 10
    page_list_num = 10


    offset = page_size*(page-1)
    subtime_cond = '-subtime'
    if status == 0:
        subtime_cond = '-subtime'
    head_res = AdminHead.query({'status': status}, order_by=subtime_cond, limit=page_size,offset=offset)
    total = AdminHead.count({'status': status})
    p = Pager(total, page_size, page, page_list_num,parameter=parameter) 
    head_url = game_config.system_simple['head_url']
    return render_to_response('admin/admin_head/view_head.html', {
        'head_res': list(head_res),
        'p': p,
        'head_url': head_url,
        'parameter': parameter,
        'page':page,
        }, 
        RequestContext(request))

@login_permission_required('pass_head')
def pass_head(request):
    pass_hids = request.POST.getlist('pass')
    lose_hids = request.POST.getlist('lose')
    if len(pass_hids) > 20 or len(lose_hids) > 20:
        raise
    session_user = request.session['admin_user']
    now = datetime.datetime.now()
    
    AdminHead_table.update(and_(AdminHead_table.c.id.in_(pass_hids))).execute(status=1,admin_user=session_user['username'],subtime=now)
    AdminHead_table.update(and_(AdminHead_table.c.id.in_(lose_hids))).execute(status=-1,admin_user=session_user['username'],subtime=now)

    return view_head(request)

@login_permission_required('mod_head_status',ajax=True)
def mod_head_status(request):
    try:
        session_user = request.session['admin_user']
        now = datetime.datetime.now()
        hid = request.POST.get('hid', None)
        status = request.POST.get('status', None)
        AdminHead_table.update(and_(AdminHead_table.c.id==hid)).execute(status=status,admin_user=session_user['username'],subtime=now)
    except Exception:
        return HttpResponse(json.dumps({'state': 'error', 'msg': e.message}))

    return HttpResponse(json.dumps({'state': 'success'}))





















