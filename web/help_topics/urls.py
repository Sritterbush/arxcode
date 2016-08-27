#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
from src.web.help_topics.views import topic
from src.web.help_topics.views import list_topics, list_recipes, display_org

urlpatterns = [
    url(r'^recipes/', list_recipes, name="list_recipes"),
    url(r'^org/(?P<object_id>[\w\s]+)/$', display_org, name="display_org"),
    url(r'^(?P<object_key>[\w\s]+)/$', topic, name="topic"),  
    url(r'^$', list_topics, name="list_topics")
]