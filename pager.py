#-*- coding: utf-8 -*-
import math
import json

class Pager(object):
    def __init__(self, total, pageSize, page, page_list_num = 10,parameter = None):
        pageCount = int(math.ceil((total+0.0)/pageSize))
        if page < 1:
            page = 1
        if page > pageCount:
            page = pageCount

        offset = 2
       
        if page_list_num > pageCount:
            from_page = 1
            to_page = pageCount
        else:
            from_page = page - offset
            to_page = from_page + page_list_num -1
            if from_page < 1:
                to_page = page + 1 - from_page
                from_page = 1
                if to_page - from_page < page_list_num:
                    to_page = page_list_num
            elif to_page > pageCount:
                from_page = pageCount - page_list_num + 1
                to_page = pageCount
        
        if page - offset >1 and pageCount > page_list_num:
            show_first = True
        else:
            show_first = False
        
        if page > 1:
            show_pre = True
        else:
            show_pre = False
        
        if page < pageCount:
            show_next = True
        else:
            show_next = False
        
        if to_page < pageCount:
            show_end = True
        else:
            show_end = False

        self.total = total
        self.pageSize = pageSize
        self.page = page
        self.pageCount = pageCount
        self.from_page = from_page
        self.to_page = to_page
        self.page_list = range(from_page, to_page+1)

        self.show_first = show_first
        self.show_end = show_end
        self.show_pre = show_pre
        self.show_next = show_next
        self.parameter = parameter

    def render(self, link=''):
        html = []
        pager = self
        page_parameter = ''
        if self.parameter:
            for k,v in self.parameter.items():
                if isinstance(v, unicode):
                    v = v.encode('utf-8')
                elif isinstance(v, int):
                    v = str(v)
                if page_parameter:
                    page_parameter += '&' + str(k) + '=' + v
                else:
                    page_parameter = '&' + str(k) + '=' + v
        html.append('共%s条' % pager.total)
        
        if link == '':
            link = '?'
        else:
            if link.find('?') == -1:
                link += '?'
            else:
                link += '&'

        if pager.show_pre:
            html.append('<a href="%spage=%s%s">上一页</a>' % (link, pager.page-1,page_parameter))
        else:
            html.append('<span class="disabled">上一页</span>')
        
        if pager.show_first:
            html.append('<a href="%spage=1%s">1</a>...' % (link,page_parameter))

        for p in pager.page_list:
            if p == pager.page:
                html.append('<span class="current">%s</span>' % pager.page)
            else:
                html.append('<a href="%spage=%s%s">%s</a>' % (link, p, page_parameter, p))

        if pager.show_end :
            html.append('...<a href="%spage=%s%s">%s</a>' % (link, pager.pageCount,page_parameter, pager.pageCount))

        if pager.show_next:
            html.append('<a href="%spage=%s%s">下一页</a>' % (link, pager.page + 1,page_parameter))
        else:
            html.append('<span class="disabled">下一页</span>')
        
        return ''.join(html)
    
    

    def render_onclick(self):
        html = []
        pager = self
        page_parameter = json.dumps(self.parameter)
        html.append('共%s条' % pager.total)

        if pager.show_pre:
            html.append('<a href="javascript:void(0)" onclick=\'page_turning(%s, %s)\'>上一页</a>' % (pager.page - 1, page_parameter))
        else:
            html.append('<span class="disabled">上一页</span>')
        
        if pager.show_first:
            html.append('<a href="javascript:void(0)" onclick=\'page_turning(%s, %s)\'>1</a>...' % (1, page_parameter))

        for p in pager.page_list:
            if p == pager.page:
                html.append('<span class="current">%s</span>' % pager.page)
            else:
                html.append('<a href="javascript:void(0)" onclick=\'page_turning(%s, %s)\'>%s</a>' % (p, page_parameter, p))

        if pager.show_end :
            html.append('...<a href="javascript:void(0)" onclick=\'page_turning(%s, %s)\'>%s</a>' % (pager.pageCount, page_parameter, pager.pageCount))

        if pager.show_next:
            html.append('<a href="javascript:void(0)" onclick=\'page_turning(%s, %s)\'>下一页</a>' % (pager.page + 1, page_parameter))
        else:
            html.append('<span class="disabled">下一页</span>')
        
        return ''.join(html)
    
    def render_tpl(self):
        return """
          共{{ pager.total }}条

          {% if pager.show_pre %}
          <a href="?page={{ pager.page|add:"-1" }}">上一页</a>
          {% else %}
          <span class="disabled">上一页</span>
          {% endif %}

          {% if pager.show_first %}
          <a href="?page=1">1</a>...
          {% endif %}

          {% for p in pager.page_list %}
            {% ifequal p pager.page %}
            <span class="current">{{ pager.page }}</span>
            {% else %}
            <a href="?page={{ p }}">{{ p }}</a>
            {% endifequal %}
          {% endfor %}

          {% if pager.show_end %}
          ...<a href="?page={{ pager.pageCount }}">{{ pager.pageCount }}</a>
          {% endif %}

          {% if pager.show_next %}
          <a href="?page={{ pager.page|add:"1" }}">下一页</a>
          {% else %}
          <span class="disabled">下一页</span>
          {% endif %}
        """
