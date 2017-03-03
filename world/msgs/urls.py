#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
from . import views


urlpatterns = [
    url(r'^journals/list/$', views.JournalListView.as_view(), name="list_journals"),
    url(r'^journals/list/read/$', views.JournalListReadView.as_view(), name="list_read_journals"),
    url(r'^journals/list/api/$', views.journal_list_json, name="journal_list_json")
]
