"""
Url definition file to redistribute incoming URL requests to django
views. Search the Django documentation for "URL dispatcher" for more
help.

"""
from django.conf.urls import url, include, patterns
from django.contrib import admin
from django.conf import settings

# default evennia patterns
from evennia.web.urls import urlpatterns

### eventual custom patterns
##custom_patterns = [
##    # url(r'/desired/url/', view, name='example'),
##]
##
### this is required by Django.
##urlpatterns = custom_patterns + urlpatterns


urlpatterns = patterns('',
    # User Authentication
    url(r'^accounts/login',  'django.contrib.auth.views.login'),
    url(r'^accounts/logout', 'django.contrib.auth.views.logout'),

    # Front page
    url(r'^', include('web.website.urls')),
    # News stuff
    url(r'^news/', include('web.news.urls')),

    # Page place-holder for things that aren't implemented yet.
    url(r'^tbi/', 'web.website.views.to_be_implemented'),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),

##    # favicon
##    url(r'^favicon\.ico$',  RedirectView.as_view(url='/media/images/favicon.ico', permanent=False)),

    # ajax stuff
    url(r'^webclient/',include('evennia.web.webclient.urls',
        namespace='webclient', app_name='webclient')),

    url(r'^character/', include('web.character.urls',
                                namespace='character', app_name='character')),

    url(r'^topics/', include('web.help_topics.urls',
                                namespace='help_topics', app_name='help_topics')),
    url(r'^dom/', include('world.dominion.urls',
                          namespace='dominion', app_name='dominion')),
    url(r'^comms/', include('world.msgs.urls',
                          namespace='msgs', app_name='msgs')),
    url(r'^static/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.STATIC_ROOT}),
    url(r'^support/', include('web.helpdesk.urls')),
                       
)

# This sets up the server if the user want to run the Django
# test server (this should normally not be needed).
if settings.SERVE_MEDIA:
    urlpatterns += patterns('',
        (r'^media/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.MEDIA_ROOT}),
        
    )
