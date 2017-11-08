"""
Url definition file to redistribute incoming URL requests to django
views. Search the Django documentation for "URL dispatcher" for more
help.

"""
import django
from django.conf.urls import url, include
from django.contrib import admin
from django.conf import settings
from django.views.static import serve

# default evennia patterns
from evennia.web.urls import urlpatterns
from web.website.views import to_be_implemented


urlpatterns = [
    # User Authentication
    url(r'^accounts/login',  django.contrib.auth.views.LoginView.as_view(template_name="login.html"), name='login'),
    url(r'^accounts/logout', django.contrib.auth.views.logout),

    # Front page
    url(r'^', include('web.website.urls')),
    # News stuff
    url(r'^news/', include('web.news.urls')),

    # Page place-holder for things that aren't implemented yet.
    url(r'^tbi/', to_be_implemented),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),

    # ajax stuff
     url(r'^webclient/',include('web.website.webclient_urls',
         namespace='webclient', app_name='webclient')),

    url(r'^character/', include('web.character.urls',
                                namespace='character', app_name='character')),

    url(r'^topics/', include('web.help_topics.urls',
                                namespace='help_topics', app_name='help_topics')),
    url(r'^dom/', include('world.dominion.urls',
                          namespace='dominion', app_name='dominion')),
    url(r'^comms/', include('world.msgs.urls',
                          namespace='msgs', app_name='msgs')),
    url(r'^static/(?P<path>.*)$', serve,
        {'document_root': settings.STATIC_ROOT}),
    url(r'^support/', include('web.helpdesk.urls')),
                       
]

# This sets up the server if the user want to run the Django
# test server (this should normally not be needed).
if settings.SERVE_MEDIA:
    urlpatterns += [
        (r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        
    ]

if settings.DEBUG:
    try:
        import debug_toolbar
    except ImportError:
        debug_toolbar = None
        print "Django toolbar not installed. Please use pip install django-debug-toolbar"
    if debug_toolbar:
        urlpatterns += [
            url(r'^__debug__/', include(debug_toolbar.urls)),
    ]