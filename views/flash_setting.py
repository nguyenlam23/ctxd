#-*- coding: utf-8 -*-
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from admin.logic import login_permission_required
from game_lib.logics import game_config
import json
import datetime
from admin.views.system_setting import _setting,_setting_p


@login_permission_required('flash_setting')
def setting(request):
    return _setting(request, where='flash')

@login_permission_required('flash_setting_p', ajax=True)
def setting_p(request):
    return _setting_p(request, where='flash')

@login_permission_required('flash_api')
def api(request):
    a = open('/data/server/trunk/game_lib/game_lib/api.txt','r')
    try:
        txt = a.read()
    except:
        pass
    finally:
        a.close()
    return HttpResponse("""
            <!DOCTYPE html>
            <html lang="en-US">
            <head>
            <title>TDSheep API</title>
            <link REL="stylesheet" href="%s/css/default.css" TYPE="text/css">
            <script src="%s/js/highlight.pack.js" type="text/javascript"></script>
            <script>
                hljs.tabReplace = '    ';
                hljs.initHighlightingOnLoad();
            </script>
            <body>
            <pre><code>%s</code></pre>
            </body>
            </html>
    """%(settings.MEDIA_URL, settings.MEDIA_URL, txt))
