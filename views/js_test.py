#-*- coding: utf-8 -*-

import os
import urllib2
import cPickle as pickle
import json
import datetime
from tornado.httpclient import HTTPClient
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.conf import settings
from admin.logic import login_permission_required
from game_lib.db.mongo import get_dbengine
from game_lib.libs.model import Serializer
from game_lib.models.main import CallInterfaceRecord

@login_permission_required('js_test')
def js_api_test(request):
    battle_id = request.GET.get('battle_id')
    days = request.GET.get('days', '7')
    if battle_id:
        db = get_dbengine()
        fight = db['fight_logs'].find_one({"battle_id": battle_id})
        if fight:
            fight['initJS'] = pickle.loads(str(fight['initJS']))
    else:
        fight = {}
    if fight:
        js_req_data = json.dumps(fight,sort_keys=True,indent=4,default=Serializer.json_default)
    else:
        js_req_data = ''
    call_records = []
    stop_at = datetime.datetime.now()
    start_at = stop_at - datetime.timedelta(days=int(days))
    for item in CallInterfaceRecord.query({'time_gte': start_at, 'time_lte':
        stop_at}, limit=50, order_by='-id'):
        _item = {
            'id': item.id,
            'time': item.time,
            'op_user': item.op_user
            }
        if len(item.op_user.split('|')) == 2:
            _item['uid'] = item.op_user.split('|')[0]
        call_records.append(_item)
    # js文件版本
    req = urllib2.Request(settings.BATTLE_URL+"/getVersion/", json.dumps({}), {'content-type': 'application/json'})
    js_version = urllib2.urlopen(req, timeout=3).read()
    return render_to_response('admin/js_test/js_test.html', {
        'js_req_data': js_req_data,
        'do_method': 'testFight',
        'call_records': call_records,
        'days': days,
        'js_version': js_version,
    }, RequestContext(request))

@login_permission_required('js_test', ajax=True)
def call_js_interface(request):
    req_data = request.POST['req_data']
    if not req_data:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'缺少战斗数据'}))
    do_method = request.POST.get('do_method', 'testFight')
    url = settings.BATTLE_URL + "/%s/" % do_method
    http_client = HTTPClient()
    resp = http_client.fetch(url, method="POST", body=req_data)
    if do_method.startswith('test'):
        data = json.loads(resp.body)
    else:
        data = resp.body
    return HttpResponse(data)

@login_permission_required('js_test', ajax=True)
def save_call_interface(request):
    req_data = request.POST['req_data']
    rsp_data = request.POST['rsp_data']
    op_user = request.session.get('admin_user')['username']
    if not req_data:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'缺少战斗数据'}))
    CallInterfaceRecord.save_record(op_user, req_data, rsp_data)
    return HttpResponse(json.dumps({'state': 'success'}))

@login_permission_required('js_test', ajax=True)
def get_call_record_data(request):
    call_id = request.GET['call_id']
    call = CallInterfaceRecord.get(call_id)
    if not call:
        return HttpResponse(json.dumps({'state': 'error', 'msg': u'ID错误'}))
    return HttpResponse(json.dumps({'state': 'success', 'req_data': call.req_data, 'rsp_data': call.rsp_data}))


@login_permission_required('js_test', ajax=True)
def download_js(request):
    service_path = settings.BASEROOT.split('/')
    service_path = service_path[:-2]
    service_path.append('service')
    js_file = os.path.join('/'.join(service_path), 'LayaSample.max.js')

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
        response = HttpResponse(file_iterator(js_file))
        # 以流的形式下载文件,这样可以实现任意格式的文件下载
        response['Content-Type'] = 'application/octet-stream'
        # Content-Disposition就是当用户想把请求所得的内容存为一个文件的时候提供一个默认的文件名
        response['Content-Disposition'] = 'attachment;filename=%s_%s.js' % (settings.WHERE, 'laya')
        return response
    except:
        return HttpResponse('Download Error')
