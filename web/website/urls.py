"""
This structures the (simple) structure of the
webpage 'application'.
"""

from django.conf.urls import *

urlpatterns = patterns('web.website.views',
     (r'^$', 'page_index'),
)
