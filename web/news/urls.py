"""
This structures the url tree for the news application.
It is imported from the root handler, game.web.urls.py.
"""

from django.conf.urls import *
from . import views

urlpatterns = [
     (r'^show/(?P<entry_id>\d+)/$', views.show_news),
     (r'^archive/$', views.news_archive),
     (r'^search/$', views.search_form),
     (r'^search/results/$', views.search_results),
]
