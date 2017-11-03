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
    url(r'^active/$', views.ActiveRosterListView.as_view(), name="active_roster"),
    url(r'^available/$', views.AvailableRosterListView.as_view(), name="available_roster"),
    url(r'^incomplete/$', views.IncompleteRosterListView.as_view(), name="incomplete_roster"),
    url(r'^unavailable/$', views.UnavailableRosterListView.as_view(), name="unavailable_roster"),
    url(r'^inactive/$', views.InactiveRosterListView.as_view(), name="inactive_roster"),
    url(r'^gone/$', views.GoneRosterListView.as_view(), name="gone_roster"),
    url(r'^story/$', views.ChapterListView.as_view(), name="current_story"),
    url(r'^story/episodes/(?P<ep_id>\d+)/$', views.episode, name='episode'),
    url(r'^sheet/(?P<object_id>\d+)/$', views.sheet, name="sheet"),
    url(r'^sheet/(?P<object_id>\d+)/comment$', views.comment, name="comment"),
    url(r'^sheet/(?P<object_id>\d+)/upload$', views.upload, name="upload"),
    url(r'^sheet/(?P<object_id>\d+)/upload/complete$', views.direct_upload_complete, name="direct_upload_complete"),
    url(r'^sheet/(?P<object_id>\d+)/gallery$', views.gallery, name="gallery"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/select_portrait$', views.select_portrait, name="select_portrait"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/edit_photo$', views.edit_photo, name="edit_photo"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/delete_photo$', views.delete_photo, name="delete_photo"),
    url(r'^sheet/(?P<object_id>\d+)/story$', views.ActionListView.as_view(), name="character_story"),
    url(r'^api/$', views.character_list, name="character_list")
]
