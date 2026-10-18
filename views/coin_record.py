#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from admin.pager import Pager
from admin.logic import login_permission_required
from game_lib.common.utils import date_range
import datetime
from sqlalchemy import *
from game_lib.models.main import User,CoinRecord
from game_lib.db.database import CoinRecords_table as CR
from game_lib.db.database import CoinRecordsBak_table as CRB
from game_lib.logics import game_config
from copy import deepcopy as copy
zone_config = dict([(k, (v[0]['cn'], v[1], v[2], v[3])) for k, v in game_config.zone.items()])

@login_permission_required('buy_record')
def buy_record(request):
    from_date = request.REQUEST.get('from_date')
    to_date = request.REQUEST.get('to_date')
    zone = request.REQUEST.get('zone', 0)
    free = request.REQUEST.get('free', 'all')
    first = int(request.REQUEST.get('first', 0))
    if not to_date or not from_date:
        to_date = datetime.date.today()
        from_date = to_date - datetime.timedelta(days=30)
    else:
        from_date = datetime.date(*[int(item) for item in from_date.split('-')])
        to_date = datetime.date(*[int(item) for item in to_date.split('-')])
    date_list = date_range(from_date,to_date)

    if len(date_list) > 31:
        return HttpResponse('<script>alert("查询不允许超过30天");history.go(-1);</script>')
    record_list = None
    zone_name = None
    now = datetime.datetime.now()
    if zone:
        record_list = {'coin':[],'score':[],'medal':[]}
        for k,v in record_list.items():
            total = {'day':'total','times':0,'amount':0}
            for item in date_list:
                cc = {}
                begin = datetime.datetime.strptime(str(item), '%Y-%m-%d')
                end = begin + datetime.timedelta(days=1)
                if zone == 'all':
                    where = and_(CR.c.subtime > begin,CR.c.subtime < end, CR.c.pay_type==k,)
                else:
                    zone_name = zone_config[zone][0]
                    where = and_(CR.c.subtime > begin,CR.c.subtime < end, CR.c.pay_type==k,CR.c.zone==zone)
                if free == '0':
                    where = and_(CR.c.coin_num != 0,where)
                elif free == '1':
                    where = and_(CR.c.coin_num == 0,where)
                if first == 1:
                    where = and_(CR.c.first == 1,where)
                ckey_list = [k,str(item),zone,str(free),str(first)]
                ckey = '|'.join(ckey_list)
                if begin.date() != now.date():
                    bak_res = select([CRB],and_(CRB.c.ckey==ckey)).execute().fetchone()
                    if bak_res:
                        cc['times'] = bak_res.times
                        cc['amount'] = bak_res.amount
                        cc['ulen'] = bak_res.ulen
                if cc:
                    total['times'] += cc['times']
                    total['amount'] += cc['amount']
                    cc['day'] = item
                    record_list[k].append(cc)
                else:
                    cc['times'] = select([func.count(CR.c.id).label('cc')],where).execute().fetchone()['cc']
                    if cc['times']:
                        cc['amount'] = select([func.sum(CR.c.coin_num).label('cc')],where).execute().fetchone()['cc']
                        cc['ulen'] = len(select([CR.c.uid],where, group_by=[CR.c.uid]).execute().fetchall())
                        if begin.date() != now.date():
                            cc ['ckey'] = ckey
                            q = CRB.insert().execute(**cc)
                        total['times'] += cc['times']
                        total['amount'] += cc['amount']
                        cc['day'] = item
                        record_list[k].append(cc)
            record_list[k].sort(key = lambda x: x['day'],reverse=True)
            record_list[k].append(total)
    zone_list = zone_config.items()
    zone_list.sort(key= lambda x:x[0])
    return render_to_response('admin/coin_record/buy_record.html', {
        'zone': zone,
        'free': str(free),
        'first': str(first),
        'zone_name': zone_name,
        'zone_list': zone_list,
        'from_date': str(from_date),
        'to_date': str(to_date),
        'record_list': record_list,
        }, 
        RequestContext(request))

@login_permission_required('buy_record')
def export_buy_record_day(request,y,m,d): 
    ptype = request.GET.get('ptype',None)
    zone = request.REQUEST.get('zone', 0)
    wp_type_desc = CoinRecord.wp_type_desc
    begin = datetime.datetime(int(y),int(m),int(d))
    end = begin + datetime.timedelta(days=1)
    zone_name = None
    free = request.REQUEST.get('free', 'all')
    first = int(request.REQUEST.get('first', 0))
    if zone == 'all':
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype) 
    else:
        zone_name = zone_config[zone][0]
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype, CR.c.zone==zone) 
    if free == '0':
        where = and_(CR.c.coin_num != 0,where)
    elif free == '1':
        where = and_(CR.c.coin_num == 0,where)
    if first == 1:
        where = and_(CR.c.first == 1,where)

    day_list = CR.select(order_by=CR.c.subtime.desc()).where(where).execute().fetchall() 
    record_list = []
    total = {'id': 'total', 'wp_num': 0, 'coin_num': 0}
    ctype = u'金砖'
    if ptype == 'score':
        ctype = u'基点'
    day = '%s-%s-%s' % (y,m,d)
    cstr = u'%s,消费记录(%s),%s\n' % (day, ctype, zone_name)
    cstr += u'ID,用户ID,用户等级,消费种类,物品名称,单价,消费数量,消费金额(%s),首次付费,消费时间,所在区,所在渠道\n' % ctype
    total_coin_num = 0
    total_wp_num = 0
    for _item in day_list:
        item = dict(_item)
        item['wp_type_cn'] = wp_type_desc[_item.wp_type]
        total_wp_num += _item.wp_num
        total_coin_num += _item.coin_num

        first = u'否'
        if item['first'] == 1:
            first = u'是'
        s = '%s' % item['wp_type_cn']
        s = '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' % (
                str(item['id']),
                str(item['uid']),
                str(item['user_lv']),
                item['wp_type_cn'],
                item['wpname_cn'],
                str(item['wp_price']),
                str(item['wp_num']),
                str(item['coin_num']),
                first,
                str(item['subtime']),
                str(item['zone'])+u'区',
                str(item['pf'] or ''),
                )
        cstr += s
    cstr += u'总计,,,,,,%s,%s,,,,' % (str(total_wp_num), str(total_coin_num))
    resp = HttpResponse(content_type='text/csv')
    resp.write(cstr.encode('gbk'))
    return resp


@login_permission_required('buy_record')
def buy_record_day(request,y,m,d): 
    ptype = request.GET.get('ptype',None)
    zone = request.REQUEST.get('zone', 0)
    page = int(request.GET.get('page','1')) 
    wp_type_desc = CoinRecord.wp_type_desc
    begin = datetime.datetime(int(y),int(m),int(d))
    end = begin + datetime.timedelta(days=1)
    zone_name = None
    free = request.REQUEST.get('free', 'all')
    first = int(request.REQUEST.get('first', 0))
    if zone == 'all':
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype) 
    else:
        zone_name = zone_config[zone][0]
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype, CR.c.zone==zone) 
    if free == '0':
        where = and_(CR.c.coin_num != 0,where)
    elif free == '1':
        where = and_(CR.c.coin_num == 0,where)
    if first == 1:
        where = and_(CR.c.first == 1,where)
    parameter = {
            'ptype': ptype,
            'zone': zone,
            'free': free,
            'first': first,
            }
    page_size = 10
    page_list_num = 10
    total = select([func.count(CR.c.id)],where).execute().fetchone()[0]
    offset = page_size*(page-1)
    p = Pager(total, page_size, page, page_list_num,parameter=parameter) 

    day_list = CR.select(order_by=CR.c.subtime.desc()).where(where).offset(offset).limit(page_size).execute().fetchall() 
    record_list = []
    total = {'id': 'total', 'wp_num': 0, 'coin_num': 0}
    for item in day_list:
        _item = dict(item)
        _item['wp_type_cn'] = wp_type_desc[item.wp_type]
        n = _item['wpname_cn'].find('^')
        if n != -1:
            _item['wpname_cn'] = _item['wpname_cn'][n+1:]
        total['wp_num'] += item.wp_num
        total['coin_num'] += item.coin_num
        record_list.append(_item)
    record_list.sort(key = lambda x: x['subtime'],reverse=True)
    record_list.append(total)
    day = '%s-%s-%s' % (y,m,d)
    return render_to_response('admin/coin_record/buy_record_day.html', {
        'zone': zone,
        'zone_name': zone_name,
        'record_list': record_list,
        'day': day,
        'ptype': ptype,
        'p': p,
        }, 
        RequestContext(request))

@login_permission_required('buy_record')
def coin_ana_day(request,y,m,d): 
    def _get_lv_step(user_lv):
        lv = 5
        while True:
            if user_lv <= lv:
                break
            lv += 5
            if lv>300:
                break
        step = "%s-%s" % (str(lv-4),str(lv))
        return step



    ptype = request.GET.get('ptype',None)
    zone = request.GET.get('zone',0)
    free = request.GET.get('free','all')
    first = int(request.REQUEST.get('first', 0))
    wp_type_desc = CoinRecord.wp_type_desc
    begin = datetime.datetime(int(y),int(m),int(d))
    end = begin + datetime.timedelta(days=1)
    #where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype) 
    zone_name = None
    if zone == 'all':
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype) 
    else:
        zone_name = zone_config[zone][0]
        where =and_(CR.c.subtime >= begin,CR.c.subtime <end,CR.c.pay_type == ptype, CR.c.zone==zone) 
    if free == '0':
        where = and_(CR.c.coin_num != 0,where)
    elif free == '1':
        where = and_(CR.c.coin_num == 0,where)

    if first == 1:
        where = and_(CR.c.first == 1,where)
    title_dict = copy(wp_type_desc)
    title_dict['zz_coin_total'] = u'总金额'
    title_dict['zz_time_total'] = u'总次数'
    #title_list = sorted(title_list.items(),key=lambda x:x[0])
    record_dict = {}
    zz_coin_total_dict = {}
    zz_time_total_dict = {}
    for k in wp_type_desc.keys():
        zz_coin_total_dict[k] = [0, 'blue']
        zz_time_total_dict[k] = [0, 'blue']

    day_list = CR.select(order_by=CR.c.subtime.desc()).where(where).execute().fetchall() 
    for item in day_list:
        step = _get_lv_step(item.user_lv)
        if record_dict.has_key(step):
            record_dict[step][item.wp_type][0] += item.coin_num
            record_dict[step]['zz_coin_total'][0] += item.coin_num
            record_dict[step]['zz_time_total'][0] += 1
        else:
            record_dict[step] = {}
            for k in wp_type_desc.keys():
                record_dict[step][k] = [0,0]
            record_dict[step][item.wp_type] = [item.coin_num, 0]
            record_dict[step]['zz_coin_total'] = [item.coin_num, '#FF6600']
            record_dict[step]['zz_time_total'] = [1, '#FF6600']
        zz_coin_total_dict[item.wp_type][0] += item.coin_num
        zz_time_total_dict[item.wp_type][0] += 1
    record_dict['0-0'] = title_dict
    record_dict[u'888-1'] = zz_coin_total_dict
    record_dict[u'999-1'] = zz_time_total_dict
    for k,v in record_dict.items():
        _v = v.items()
        record_dict[k] = sorted(_v, key=lambda x: x[0])
    record_list = sorted(record_dict.items(),key=lambda x:int(x[0].split('-')[0]))
    day = '%s-%s-%s' % (y,m,d)
    return render_to_response('admin/coin_record/coin_ana_day.html', {
        'zone': zone,
        'zone_name': zone_name,
        'record_list': record_list,
        'day': day,
        'ptype': ptype,
        }, 
        RequestContext(request))


@login_permission_required('coin_user_record')
def user_record(request):
    uid = request.REQUEST.get('uid',None)
    record_list = []
    record_list = {'coin':[],'score':[], 'medal': []}
    if uid:
        user = User.get(uid)
        wp_type_desc = CoinRecord.wp_type_desc
        sql_list = CR.select(order_by=CR.c.subtime.desc()).where(and_(CR.c.uid == uid)).execute().fetchall()
        total_score = {'id': 'total', 'wp_num': 0, 'coin_num': 0}
        total_coin = {'id': 'total', 'wp_num': 0, 'coin_num': 0}
        total_medal = {'id': 'total', 'wp_num': 0, 'coin_num': 0}
        for item in sql_list: 
            if item.pay_type== 'score':
                _item = dict(item)
                _item['wp_type_cn'] = wp_type_desc.get(item.wp_type, '--')
                n = _item['wpname_cn'].find('^')
                if n != -1:
                    _item['wpname_cn'] = _item['wpname_cn'][n+1:]
                total_score['wp_num'] += item.wp_num
                total_score['coin_num'] += item.coin_num
                record_list['score'].append(_item)
            elif item.pay_type == 'medal':
                _item = dict(item)
                _item['wp_type_cn'] = wp_type_desc.get(item.wp_type, '--')
                n = _item['wpname_cn'].find('^')
                if n != -1:
                    _item['wpname_cn'] = _item['wpname_cn'][n+1:]
                total_medal['wp_num'] += item.wp_num
                total_medal['coin_num'] += item.coin_num
                record_list['medal'].append(_item)
            else:
                _item = dict(item)
                _item['wp_type_cn'] = wp_type_desc.get(item.wp_type,'--')
                n = _item['wpname_cn'].find('^')
                if n != -1:
                    _item['wpname_cn'] = _item['wpname_cn'][n+1:]
                total_coin['wp_num'] += item.wp_num
                total_coin['coin_num'] += item.coin_num
                record_list['coin'].append(_item)
        record_list['score'].append(total_score) 
        record_list['coin'].append(total_coin)
        record_list['medal'].append(total_medal)
    return render_to_response('admin/coin_record/coin_user_record.html', {
        'uid': uid or '',
        'record_list': record_list,
        }, 
        RequestContext(request))
        













