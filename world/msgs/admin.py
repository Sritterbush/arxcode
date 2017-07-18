#
# This sets up how models are displayed
# in the web admin interface.
#

from django.contrib import admin
from .models import Inform
from evennia.comms.models import Msg
from evennia.typeclasses.admin import TagInline
from evennia.objects.models import ObjectDB
from evennia.objects.admin import ObjectDBAdmin
from evennia.help.admin import HelpEntryAdmin
from evennia.help.models import HelpEntry


class InformAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'message', 'date_sent',
                    'week')
    list_display_links = ("id",)
    search_fields = ['id', 'date_sent', 'message']
admin.site.register(Inform, InformAdmin)


class MsgListFilter(admin.SimpleListFilter):
    title = ('Message Types',)
    parameter_name = 'msgfilters'

    def lookups(self, request, model_admin):
        return (
            ('dispwhite', 'White'),
            ('dispblack', 'Black'),
            ('dispmess', 'Messenger'),
            ('disprumor', 'Rumors'),
            ('dispgossip', 'Gossip'),
            ('dispvision', 'Visions'),
            ('dispevent', 'Events'),
            ('disposts', 'Board Posts'),
            )

    def queryset(self, request, queryset):
        if self.value() == 'dispwhite':
            return queryset.filter(db_tags__db_key="white_journal")
        if self.value() == "dispblack":
            return queryset.filter(db_tags__db_key="black_journal")
        if self.value() == "dispmess":
            return queryset.filter(db_tags__db_key="messenger")
        if self.value() == "disprumor":
            return queryset.filter(db_tags__db_key="rumor")
        if self.value() == "dispgossip":
            return queryset.filter(db_tags__db_key="gossip")
        if self.value() == "dispvision":
            return queryset.filter(db_tags__db_key="visions")
        if self.value() == "dispevent":
            return queryset.filter(db_tags__db_category="event")
        if self.value() == "disposts":
            return queryset.filter(db_tags__db_category="board",
                                   db_tags__db_key="Board Post")


class MsgTagInline(TagInline):
    """
    Defines inline descriptions of Tags (experimental)

    """
    model = Msg.db_tags.through
    related_field = "msg"
        

class MsgAdmin(admin.ModelAdmin):
    inlines = [MsgTagInline]
    list_display = ('id', 'db_date_created', 'get_senders', 'msg_receivers',
                    'message')
    list_display_links = ("id",)
    ordering = ["-db_date_created"]
    # readonly_fields = ['db_message', 'db_sender', 'db_receivers', 'db_channels']
    search_fields = ['db_sender_players__db_key',
                     "db_sender_objects__db_key", "db_receivers_objects__db_key",
                     'id', '^db_date_created']
    save_as = True
    save_on_top = True
    list_select_related = True
    raw_id_fields = ("db_sender_players", "db_receivers_players", "db_sender_objects", "db_receivers_objects",
                     "db_hide_from_players", "db_hide_from_objects")
    list_filter = (MsgListFilter,)
    exclude = ('db_tags',)

    @staticmethod
    def get_senders(obj):
        return ", ".join([p.key for p in obj.db_sender_objects.all()])

    @staticmethod
    def msg_receivers(obj):
        return ", ".join([p.key for p in obj.db_receivers_objects.all()])

    def get_queryset(self, request):
        return super(MsgAdmin, self).get_queryset(request).filter(db_receivers_channels__isnull=True).distinct()

    def message(self, obj):
        from web.help_topics.templatetags.app_filters import mush_to_html
        return mush_to_html(obj.db_message)
    message.allow_tags = True
admin.site.register(Msg, MsgAdmin)


class ArxObjectDBAdmin(ObjectDBAdmin):
    search_fields = ['id', 'db_key', 'db_location__db_key']

    
class ArxHelpDBAdmin(HelpEntryAdmin):
    search_fields = ['db_key', 'db_entrytext']
    
    
admin.site.unregister(ObjectDB)
admin.site.register(ObjectDB, ArxObjectDBAdmin)
admin.site.unregister(HelpEntry)
admin.site.register(HelpEntry, ArxHelpDBAdmin)
