#-*- coding: utf-8 -*-
import time
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from admin.logic import login_permission_required
import datetime
from game_lib.models.cache import CacheTable
from db.database import pay_records_table as ASP
from game_lib.logics import game_config
from sqlalchemy import *
from game_lib.common import utils
from game_lib.models.main import UserZone
import hashlib

def get_pf_list(pfs = []):
    pf_list = [] 
    item_list = []
    check_all = True
    for pf in game_config.system_simple['pfs']:
        chk = 1
        if pfs and pf not in pfs:
            chk = 0
            check_all = False
        item_list.append([pf,chk])
        if len(item_list) >= 10:
            pf_list.append(item_list)
            item_list = []
    else:
        pf_list.append(item_list)
    if check_all:
        pfs_str = 'all'
        pfs_key = 'all'
    else:
        pfs_str = '|'.join(pfs)
        pfs_key = hashlib.md5(pfs_str).hexdigest()
    return pf_list,pfs_key,pfs_str

def _goods_sort_key(x):
    return game_config.pay_config[x[1]['pay_id']][0], int(x[0][2:])

@login_permission_required('pay_record')
def pay_record(request):
    from_date = request.REQUEST.get('from_date')
    add_date = int(request.REQUEST.get('add_date',30))
    search_zone_list = request.POST.getlist('search_zone_list')
    session_user = request.session.get('admin_user')
    run_zone_list = UserZone.get_zone_list('all', session_user=session_user)
    search_goods_id = request.REQUEST.getlist('search_goods_id')

    if not search_zone_list and session_user['username'] == 'admin':
        search_zone_list = []
        zone = 'all'
    else:
	if not search_zone_list:
            search_zone_list = [v[0] for v in run_zone_list]
        if len(search_zone_list) == len(run_zone_list):
            zone = 'all'
        else:
            zone = '|'.join(search_zone_list)

    if not search_goods_id:
        search_goods_id = 'all'
        goods_ids = 'all'
    else:
        goods_ids = '|'.join(search_goods_id)

    zone_list = []
    for item in run_zone_list:
        checked = 0
        if item[0] in search_zone_list:
            checked = 'checked'
        zone_list.append([item[0], item[1], checked])

    goods_list = []
    for k, v in sorted(game_config.pay_config.iteritems(), key=lambda x:int(x[0][3:])):
        if k == 'pf':
            continue
        goods_list.append([k, '充值%s--%s' % (k, v[0]), 'checked'])
    for k, v in sorted(game_config.goods.iteritems(), key=_goods_sort_key):
        goods_list.append([k, '%s--%s' % (k, game_config.return_msg.get(v['info'], v['info'])), 'checked'])

    goods_all = True
    for item in goods_list:
        if search_goods_id == 'all':
            continue
        if item[0] in search_goods_id:
            continue
        item[2] = 'unchecked'
        goods_all = False
    if search_goods_id and goods_all:
        search_goods_id = 'all'
        goods_ids = 'all'

    country = request.REQUEST.get('country', 'all')
    pfs = request.REQUEST.getlist('pfs') 
    pf_list,pfs_key,pfs_str = get_pf_list(pfs)
    add_date_list = [1,3,7,14,30,60,90]
    if not from_date:
        to_date = datetime.date.today()+datetime.timedelta(days=1)
        from_date = to_date - datetime.timedelta(days=add_date-0)
    else:
        from_date = datetime.date(*[int(item) for item in from_date.split('-')])
        to_date = from_date + datetime.timedelta(days=add_date-1)
        if to_date > datetime.date.today():
            to_date = datetime.date.today()
    date_list = utils.date_range(from_date,to_date) 
    record_list = []

    total = {'day':'total','times':0,'pay_money':0, 'pf_pay_money': 0, 'pay_coin': 0}
    if zone:
        for item in date_list:
            kkk = 'pay_record_%s_%s_%s_%s_%s' % (str(item),zone,country,pfs_key,goods_ids)
            c_kkk = hashlib.md5(kkk).hexdigest()
            # ct = CacheTable.get('pay_record_%s_%s_%s_%s' % (str(item),zone,country,pfs_key))
            ct = CacheTable.get(c_kkk)
            if ct:
                if ct['times']:
                    total['times'] += ct['times']
                    total['pay_money'] += ct['pay_money']
                    total['pf_pay_money'] += ct.get('pf_pay_money',0)
                    total['pay_coin'] += ct['pay_coin']
                    record_list.append(ct)
                continue

            begin = datetime.datetime.strptime(str(item), '%Y-%m-%d')
            end = begin + datetime.timedelta(days=1)
            where = and_(ASP.c.pay_time > begin,ASP.c.pay_time < end)
            if zone != 'all':
                where = and_(where,ASP.c.zone.in_(search_zone_list))
            if country != 'all':
                where = and_(where,ASP.c.country==int(country))
            if pfs_str != 'all':
                where = and_(where,ASP.c.pf.in_(pfs))
            if search_goods_id != 'all':
                where = and_(where, ASP.c.goods_id.in_(search_goods_id))

            ps_set = set()
            cc = {
                'day': item,
                'times': 0,
                'pay_money': 0,
                'pf_pay_money': 0,
                'pay_coin': 0
            }
            records = select([ASP.c.uid, ASP.c.pay_money, ASP.c.pf_pay_money, ASP.c.pay_coin],where).execute().fetchall()
            if records:
                for r in records:
                    uid, pay_money, pf_pay_money, pay_coin = r
                    ps_set.add(uid)
                    cc['times'] += 1
                    cc['pay_money'] += pay_money
                    cc['pf_pay_money'] += pf_pay_money
                    cc['pay_coin'] += pay_coin
                    total['times'] += 1
                    total['pay_money'] += pay_money
                    total['pf_pay_money'] += pf_pay_money
                    total['pay_coin'] += pay_coin
                cc['ps'] = len(ps_set)
                record_list.append(cc)


            if item<datetime.date.today():
                CacheTable.set(c_kkk, cc, 33600*24*10000)

    record_list.sort(key = lambda x: x['day'],reverse=True)
    record_list.append(total)
    #zone_list = sorted([[k, u'%s区-%s' % (k,v[0])] for k,v in game_config.zone.items()],key=lambda x:x[0])
    c_list = [('0', u'魏'),('1', u'蜀'),('2',u'吴')]
    return render_to_response('admin/pay_record/pay_record.html', {
        'from_date': str(from_date),
        'add_date': add_date,
        'add_date_list': add_date_list,
        'record_list': record_list,
        'zone_list': zone_list,
        'country': country,
        'c_list': c_list,
        'pf_list': pf_list,
        'pfs_str': pfs_str,
        'zone': zone,
        'goods_list': goods_list,
        'goods_ids': goods_ids,
        }, 
        RequestContext(request))


@login_permission_required('pay_record')
def pay_record_day(request,y,m,d):
    c_dict = {0: '魏', 1:'蜀', 2: '吴'}
    begin = datetime.datetime(int(y),int(m),int(d))
    country = request.REQUEST.get('country', 'all')
    pfs_str = request.REQUEST.get('pfs_str', 'all')
    end = begin + datetime.timedelta(days=1) 
    zone = request.REQUEST.get('search_zones', 'all')
    goods_ids = request.REQUEST.get('goods_ids', 'all')
    status = request.REQUEST.get('status')

    where = and_(ASP.c.pay_time >= begin,ASP.c.pay_time< end)
    if zone != 'all':
        search_zone_list = zone.split('|')
        where = and_(where,ASP.c.zone.in_(search_zone_list))
    if country != 'all':
        where = and_(where,ASP.c.country==int(country))
    if pfs_str != 'all':
        pfs = pfs_str.split('|')
        where = and_(where,ASP.c.pf.in_(pfs))
    if goods_ids != 'all':
        where = and_(where, ASP.c.goods_id.in_(goods_ids.split('|')))
    if status is not None:
        where = and_(where, ASP.c.status == int(status))


    day_list = ASP.select(order_by=ASP.c.pay_time.desc()).where(where).execute().fetchall()
    record_list = []
    total = {'id': 'total', 'pay_money': 0, 'pf_pay_money': 0, 'pay_coin': 0}
    for item in day_list:
        _item = dict(item)
        _item['country'] = c_dict.get(item['country'],None)
        _item['pay_money'] = item['pay_money']
        total['pay_money'] += _item['pay_money']
        _item['pf_pay_money'] = item['pf_pay_money'] or 0
        total['pf_pay_money'] += _item['pf_pay_money'] or 0
        total['pay_coin'] += _item['pay_coin']
        record_list.append(_item)
    record_list.append(total)
    day = '%s-%s-%s' % (y,m,d)
    return render_to_response('admin/pay_record/pay_record_day.html', {
        'record_list': record_list,
        'day': day,
        }, 
        RequestContext(request))

@login_permission_required('pay_user_record')
def user_record(request):
    c_dict = {0: '魏', 1:'蜀', 2: '吴'}
    uid = request.REQUEST.get('uid',None)
    session_user = request.session.get('admin_user')
    record_list = []
    if uid:
        uid = utils.to_uid(uid)
        operable_zone_list = [item[0] for item in UserZone.get_zone_list('all', session_user=session_user)]
        pay_list = ASP.select(order_by=ASP.c.pay_time.desc()).where(and_(ASP.c.uid==uid, ASP.c.zone.in_(operable_zone_list))).execute().fetchall()
        total = {'id': 'total', 'pay_money': 0, 'pf_pay_money': 0, 'pay_coin': 0}
        for item in pay_list: 
            _item = dict(item)
            _item['country'] = c_dict.get(item['country'],None)
            _item['pay_money'] = item['pay_money']
            total['pay_money'] += _item['pay_money']
            _item['pf_pay_money'] = item['pf_pay_money'] or 0
            total['pf_pay_money'] += _item['pf_pay_money'] or 0
            total['pay_coin'] += _item['pay_coin']
            record_list.append(_item)
        record_list.append(total)
    
    return render_to_response('admin/pay_record/pay_user_record.html', {
        'uid': uid or '',
        'record_list': record_list,
        }, 
        RequestContext(request))
        













