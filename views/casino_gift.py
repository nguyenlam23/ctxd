#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
import datetime, random
from admin.logic import login_permission_required
from copy import deepcopy as copy
import json
from sqlalchemy import *
from game_lib.common import utils
import xlrd 
from hashlib import md5
import time
import cPickle as pickle
from admin.pager import Pager
from game_lib.logics import game_config
from game_lib.db.database import CasinoGift_table as CGtable
from game_lib.db.database import CasinoUser_table as CUtable
from game_lib.models.cache import CacheTable

@login_permission_required('send_casino_gift')
def send_casino_gift(request):
    gift_type_dict = {}
    return_msg_config = game_config.return_msg
    for k,v in game_config.shop['casino_real_shop']['casino_object'].items():
        msg_id = v[1]
        msg = return_msg_config[msg_id]
        gift_type_dict[k] = [v[0],msg]
    id = int(request.REQUEST.get('id'))
    sql = CGtable.select(and_(CGtable.c.id==id,CGtable.c.status==1)).execute().fetchone()
    casino_gift_dict = dict(sql)
    casino_gift_dict['gift_type'] = gift_type_dict[sql.gift_type][1]

    return render_to_response('admin/casino_gift/send_casino_gift.html', {
        'cg': casino_gift_dict,
        }, 
        RequestContext(request))

@login_permission_required('send_casino_gift')
def send_casino_gift_p(request):
    id = int(request.REQUEST.get('id'))
    order_num = request.REQUEST.get('order_num')
    up_dict = {'order_num': order_num}
    CGtable.update(and_(CGtable.c.id==id)).execute(**up_dict)
    CUtable.update(and_(CUtable.c.cgid==id)).execute(**up_dict)
    return casino_gift_records(request)

@login_permission_required('add_casino_gift')
def del_casino_gift(request):
    id = int(request.REQUEST.get('id'))
    up_dict = {'status': -1}
    CGtable.update(and_(CGtable.c.id==id,CGtable.c.status==0)).execute(**up_dict)
    return HttpResponse(json.dumps({'state':'success'}))
    
    



@login_permission_required('add_casino_gift')
def add_casino_gift(request):
    gift_type_list = []
    return_msg_config = game_config.return_msg
    for k,v in game_config.shop['casino_real_shop']['casino_object'].items():
        msg_id = v[1]
        msg = return_msg_config[msg_id]
        gift_type_list.append([k,v[0],msg])

    return render_to_response('admin/casino_gift/add_casino_gift.html', {
        'gift_type_list': gift_type_list,
        }, 
        RequestContext(request))

@login_permission_required('add_casino_gift')
def add_casino_gift_p(request):
    gift_type = request.REQUEST.get('gift_type')
    gt = game_config.shop['casino_real_shop']['casino_object'][gift_type][0]
    now = datetime.datetime.now()
    admin_user = request.session['admin_user']['username']
    if gt == 1:
        return_msg_config = game_config.return_msg
        msg_id = game_config.shop['casino_real_shop']['casino_object'][gift_type][1]
        msg = return_msg_config[msg_id]
        gift_num = request.REQUEST.get('gift_num')
        version = now.strftime('%Y%m%d%H%M%S')
        for item in range(int(gift_num)):
            kami = u'%s【%s-%s】' % (msg,version,item)
            casino_gift = {
                    'gift_type' : gift_type,
                    'kami' : kami,
                    'admin_user' : admin_user,
                    'add_time' : now,
                    'status' : 0,
                    'order_num' : '',
                    }
            CGtable.insert().execute(**casino_gift)

    else:
        kami_content = request.REQUEST.get('kami_content')
        kami_content = kami_content.replace('\r\n','')
        kami_content = kami_content.replace(' ','')
        kami_content = kami_content.replace("'","")
        kami_content = kami_content.replace('"','')
        kami_list = []
        for item in kami_content.split(','):
            if item:
                sql = CGtable.select(and_(CGtable.c.kami==item)).execute().fetchone()
                if sql:
                    return HttpResponse(u'<script>alert("重复的卡密（%s）");history.go(-1);</script>' % item)
                kami_list.append(item)
        if not kami_list:
            return HttpResponse(u'<script>alert("请填写卡密（逗号分割）");history.go(-1);</script>')
        for item in kami_list:
            casino_gift = {
                    'gift_type' : gift_type,
                    'kami' : item,
                    'admin_user' : admin_user,
                    'add_time' : now,
                    'status' : 0,
                    'order_num' : '',
                    }
            CGtable.insert().execute(**casino_gift)


    return casino_gift_records(request)




@login_permission_required('casino_gift_records')
def casino_gift_records(request):
    gift_type = request.REQUEST.get('gift_type','all')
    gift_type_dict = {}
    return_msg_config = game_config.return_msg
    for k,v in game_config.shop['casino_real_shop']['casino_object'].items():
        msg_id = v[1]
        msg = return_msg_config[msg_id]
        gift_type_dict[k] = [v[0],msg]
    cond = and_(CGtable.c.status != -1)
    parameter = {}
    if gift_type != 'all':
        cond = and_(cond, CGtable.c.gift_type ==gift_type)
        parameter['gift_type'] = gift_type

    uid = request.REQUEST.get('uid',None)
    if uid:
        uid = int(uid.strip())
        cond = and_(cond, CGtable.c.uid==uid)
        parameter['uid'] = uid

    admin_user = request.REQUEST.get('admin_user',None)
    if admin_user:
        admin_user= admin_user.strip()
        cond = and_(cond, CGtable.c.admin_user==admin_user)
        parameter['admin_user'] = admin_user

    order_num = request.REQUEST.get('order_num',None)
    if order_num:
        order_num= order_num.strip()
        cond = and_(cond, CGtable.c.order_num==order_num)
        parameter['order_num'] = order_num.encode('utf-8')

    kami = request.REQUEST.get('kami',None)
    if kami:
        kami = kami.strip()
        cond = and_(cond, CGtable.c.kami==kami)
        #parameter['kami'] = kami

    status = request.REQUEST.get('status', -1)
    if status:
        status = int(status)
        if status != -1:
            if status == 0:
                cond = and_(cond, CGtable.c.status==status)
            elif status == 1:
                cond = and_(cond, CGtable.c.status==status,CGtable.c.order_num!='')
            elif status == 2:
                cond = and_(cond, CGtable.c.status==1,CGtable.c.order_num=='')

            parameter['status'] = status


    page = int(request.REQUEST.get('page','1')) 
    p = None

    page_size =  20
    page_list_num = 10

    total = CGtable.count(cond).execute().fetchone()[0]
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,parameter=parameter) 



    sql_list = CGtable.select(cond,offset=offset,limit=page_size).execute().fetchall()
    casino_gift_list = []
    for item in sql_list:
        _item = dict(item)
        _item['gift_type'] = gift_type_dict[item['gift_type']]
        casino_gift_list.append(_item)

    return render_to_response('admin/casino_gift/casino_gift_records.html', {
        'gift_type_dict': gift_type_dict,
        'casino_gift_list': casino_gift_list,
        'p': p,
        'page': page,

        'gift_type': gift_type,
        'uid': uid,
        'kami': kami,
        'status': status,
        'admin_user': admin_user,
        'order_num': order_num,
        }, 
        RequestContext(request))



@login_permission_required('casino_user_records')
def casino_user_records(request):
    from_date = request.REQUEST.get('from_date')
    to_date = request.REQUEST.get('to_date')
    if not to_date or not from_date:
        to_date = datetime.date.today()
        from_date = to_date - datetime.timedelta(days=30)
    else:
        from_date = datetime.date(*[int(item) for item in from_date.split('-')])
        to_date = datetime.date(*[int(item) for item in to_date.split('-')])
    date_list = utils.date_range(from_date,to_date) 
    if len(date_list) > 31:
        return HttpResponse('<script>alert("查询不允许超过30天");history.go(-1);</script>')
    record_list = []

    total = {'day':'total','times':0,'pay_cchip':0}
    for item in date_list:
        ct = CacheTable.get('casino_user_'+str(item))
        if ct:
            if ct['times']:
                total['times'] += ct['times']
                total['pay_cchip'] += ct['pay_cchip']
                record_list.append(ct)
            continue

        cc = {}
        begin = datetime.datetime.strptime(str(item), '%Y-%m-%d')
        end = begin + datetime.timedelta(days=1)
        where = and_(CUtable.c.add_time > begin,CUtable.c.add_time < end)

        cc['times'] = select([func.count(CUtable.c.id).label('cc')],where).execute().fetchone()['cc']
        if cc['times']:
            cc['ps'] = len(select([CUtable.c.uid],where,group_by=[CUtable.c.uid]).execute().fetchall())
            cc['pay_cchip'] = select([func.sum(CUtable.c.cchip).label('cc')],where).execute().fetchone()['cc']
            total['times'] += cc['times']
            total['pay_cchip'] += cc['pay_cchip']
            cc['day'] = item
            record_list.append(cc)
        if item<datetime.date.today():
            CacheTable.set('casino_user_'+str(item), cc, 33600*24*10000)

    record_list.sort(key = lambda x: x['day'],reverse=True)
    record_list.append(total)
    return render_to_response('admin/casino_gift/casino_user_records.html', {
        'from_date': str(from_date),
        'to_date': str(to_date),
        'record_list': record_list,
        }, 
        RequestContext(request))




@login_permission_required('casino_user_records_day')
def casino_user_records_day(request,y,m,d):
    begin = datetime.datetime(int(y),int(m),int(d))
    end = begin + datetime.timedelta(days=1) 
    where = and_(CUtable.c.add_time >= begin,CUtable.c.add_time< end)

    day_list = CUtable.select(order_by=CUtable.c.add_time.desc()).where(where).execute().fetchall()

    gift_type_dict = {}
    return_msg_config = game_config.return_msg
    for k,v in game_config.shop['casino_real_shop']['casino_object'].items():
        msg_id = v[1]
        msg = return_msg_config[msg_id]
        gift_type_dict[k] = [v[0],msg]

    record_list = []
    total = {'id': 'total', 'pay_cchip': 0}
    for item in day_list:
        _item = dict(item)
        _item['gift_type'] = gift_type_dict[item['gift_type']]
        _item['pay_cchip'] = item['cchip']
        total['pay_cchip'] += _item['cchip']
        record_list.append(_item)
    record_list.append(total)
    day = '%s-%s-%s' % (y,m,d)
    return render_to_response('admin/casino_gift/casino_user_day.html', {
        'record_list': record_list,
        'day': day,
        }, 
        RequestContext(request))

@login_permission_required('user_casino_user_records')
def user_casino_user_records(request):
    uid = request.REQUEST.get('uid',None)
    record_list = []
    if uid:
        uid = utils.to_uid(uid)
        gift_type_dict = {}
        return_msg_config = game_config.return_msg
        for k,v in game_config.shop['casino_real_shop']['casino_object'].items():
            msg_id = v[1]
            msg = return_msg_config[msg_id]
            gift_type_dict[k] = [v[0],msg]
        pay_list = CUtable.select(order_by=CUtable.c.add_time.desc()).where(and_(CUtable.c.uid==uid)).execute().fetchall()
        total = {'id': 'total', 'pay_cchip': 0}
        for item in pay_list: 
            _item = dict(item)
            _item['gift_type'] = gift_type_dict[item['gift_type']]
            _item['pay_cchip'] = item['cchip']
            total['pay_cchip'] += _item['cchip']
            record_list.append(_item)
        record_list.append(total)
    
    return render_to_response('admin/casino_gift/user_casino_user_records.html', {
        'uid': uid or '',
        'record_list': record_list,
        }, 
        RequestContext(request))






