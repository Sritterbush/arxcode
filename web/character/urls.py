#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
from src.web.character import views

urlpatterns = [
    url(r'^$', views.list_characters, name="list_characters"),
    url(r'^story/$', views.current_story, name="current_story"),
    url(r'^story/episodes/(?P<ep_id>\d+)/$', views.episode, name='episode'),
    url(r'^sheet/(?P<object_id>\d+)/$', views.sheet, name="sheet"),
    url(r'^sheet/(?P<object_id>\d+)/comment$', views.comment, name="comment"),
    url(r'^sheet/(?P<object_id>\d+)/upload$', views.upload, name="upload"),
    url(r'^sheet/(?P<object_id>\d+)/upload/complete$', views.direct_upload_complete, name="direct_upload_complete"),
    url(r'^sheet/(?P<object_id>\d+)/gallery$', views.gallery, name="gallery"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/select_portrait$', views.select_portrait, name="select_portrait"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/edit_photo$', views.edit_photo, name="edit_photo"),
    url(r'^sheet/(?P<object_id>\d+)/gallery/delete_photo$', views.delete_photo, name="delete_photo"),
]