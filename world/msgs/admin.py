#
# This sets up how models are displayed
# in the web admin interface.
#

from django.contrib import admin
from .models import Inform
from evennia.comms.models import Msg


class InformAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'message', 'date_sent',
                    'week')
    list_display_links = ("id",)
    search_fields = ['id', 'date_sent', 'message']
admin.site.register(Inform, InformAdmin)

class MsgListFilter(admin.SimpleListFilter):
    title = ('Message Types')
    parameter_name = 'msgfilters'
    def lookups(self, request, model_admin):
        return (
            ('dispwhite', ('White')),
            ('dispblack', ('Black')),
            ('dispmess', ('Messenger')),
            ('disprumor', ('Rumors')),
            ('dispgossip', ('Gossip')),
            ('dispvision', ('Visions')),
            ('dispevent', ('Events')),
            )
    def queryset(self, request, queryset):
        if self.value() == 'dispwhite':
            return queryset.filter(db_header__icontains="white_journal")
        if self.value() == "dispblack":
            return queryset.filter(db_header__icontains="black_journal")
        if self.value() == "dispmess":
            return queryset.filter(db_header__icontains="messenger")
        if self.value() == "disprumor":
            return queryset.filter(db_header__icontains="rumor")
        if self.value() == "dispgossip":
            return queryset.filter(db_header__icontains="gossip")
        if self.value() == "dispvision":
            return queryset.filter(db_header__icontains="visions")
        if self.value() == "dispevent":
            return queryset.filter(event__isnull=False)
        
class MsgAdmin(admin.ModelAdmin):
    list_display = ('id', 'db_date_sent', 'get_senders', 'msg_receivers',
                    'db_message')
    list_display_links = ("id",)
    ordering = ["db_date_sent"]
    #readonly_fields = ['db_message', 'db_sender', 'db_receivers', 'db_channels']
    search_fields = ['db_sender_players__db_key',"db_receivers_players__db_key",
                     "db_sender_objects__db_key", "db_receivers_objects__db_key",
                     'id', '^db_date_sent', '^db_message']
    save_as = True
    save_on_top = True
    list_select_related = True
    raw_id_fields = ("db_sender_players", "db_receivers_players", "db_sender_objects", "db_receivers_objects",
                     "db_hide_from_players", "db_hide_from_objects")
    list_filter = (MsgListFilter,)
    def msg_receivers(self, obj):
        return ", ".join([p.key for p in obj.db_receivers_objects.all()])
    def get_queryset(self, request):
        return super(MsgAdmin, self).get_queryset(request).filter(db_receivers_channels__isnull=True).distinct()
admin.site.register(Msg, MsgAdmin)


