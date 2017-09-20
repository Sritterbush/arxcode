#
# This sets up how models are displayed
# in the web admin interface.
#

from django.contrib import admin
from evennia.comms.models import Msg
from .models import Inform, Messenger, Post, Journal, Vision, Rumor
from evennia.typeclasses.admin import TagInline
from evennia.objects.models import ObjectDB
from evennia.objects.admin import ObjectDBAdmin
from evennia.help.admin import HelpEntryAdmin
from evennia.help.models import HelpEntry


class InformAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'organization', 'message', 'date_sent', 'category')
    list_display_links = ("id",)
    search_fields = ['id', 'player__username', 'organization__name', 'message', 'category']
admin.site.register(Inform, InformAdmin)


class MsgListFilter(admin.SimpleListFilter):
    title = 'Journal Type'
    parameter_name = 'msgfilters'

    def lookups(self, request, model_admin):
        return (
            ('dispwhite', 'White'),
            ('dispblack', 'Black'),
            )

    def queryset(self, request, queryset):
        if self.value() == 'dispwhite':
            return queryset.filter(db_tags__db_key="white_journal")
        if self.value() == "dispblack":
            return queryset.filter(db_tags__db_key="black_journal")


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
    search_fields = ['db_sender_players__db_key',
                     "db_sender_objects__db_key", "db_receivers_objects__db_key",
                     'id', '^db_date_created']
    save_as = True
    save_on_top = True
    list_select_related = True
    raw_id_fields = ("db_sender_players", "db_receivers_players", "db_sender_objects", "db_receivers_objects",
                     )

    # Tags require a special inline, and others aren't used for our proxy models
    exclude = ('db_tags', 'db_receivers_channels', 'db_hide_from_channels', "db_hide_from_players",
               "db_hide_from_objects")

    @staticmethod
    def get_senders(obj):
        return ", ".join([p.key for p in obj.db_sender_objects.all()])

    @staticmethod
    def msg_receivers(obj):
        return ", ".join([p.key for p in obj.db_receivers_objects.all()])

    def message(self, obj):
        from web.help_topics.templatetags.app_filters import mush_to_html
        return mush_to_html(obj.db_message)
    message.allow_tags = True


class JournalAdmin(MsgAdmin):
    list_filter = (MsgListFilter,)

admin.site.register(Messenger, MsgAdmin)
admin.site.register(Journal, JournalAdmin)
admin.site.register(Vision, MsgAdmin)
admin.site.register(Post, MsgAdmin)
admin.site.register(Rumor, MsgAdmin)


class ArxObjectDBAdmin(ObjectDBAdmin):
    search_fields = ['id', 'db_key', 'db_location__db_key']

    
class ArxHelpDBAdmin(HelpEntryAdmin):
    search_fields = ['db_key', 'db_entrytext']
    
    
admin.site.unregister(ObjectDB)
admin.site.register(ObjectDB, ArxObjectDBAdmin)
admin.site.unregister(HelpEntry)
admin.site.register(HelpEntry, ArxHelpDBAdmin)
