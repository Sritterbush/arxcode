from django.contrib import admin
from django.forms import ModelForm
from .models import (Roster, RosterEntry, Photo,
                     Story, Chapter, Episode, StoryEmit,
                     Milestone, Participant, Comment,
                     PlayerAccount, AccountHistory,
                     Mystery, Revelation, Clue, Investigation,
                     MysteryDiscovery, RevelationDiscovery, ClueDiscovery,
                     RevelationForMystery, ClueForRevelation, Theory,
                     )
from django.db.models import F


class BaseCharAdmin(admin.ModelAdmin):
    list_select_related = True
    save_as = True


class NoDeleteAdmin(BaseCharAdmin):
    def get_actions(self, request):
        # Disable delete
        actions = super(BaseCharAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

    def has_delete_permission(self, request, obj=None):
        # Disable delete
        return False


class EntryForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(EntryForm, self).__init__(*args, **kwargs)
        self.fields['profile_picture'].queryset = Photo.objects.filter(owner=self.instance.character)


class PhotoAdmin(BaseCharAdmin):
    list_display = ('id', 'title', 'owner', 'alt_text')
    raw_id_fields = ('owner',)


class AccountHistoryInline(admin.TabularInline):
    model = AccountHistory
    can_delete = False
    extra = 0


class AccountAdmin(BaseCharAdmin):
    list_display = ('id', 'email', 'player_characters')
    search_fields = ('email', 'characters__character__db_key')
    inlines = [AccountHistoryInline]

    @staticmethod
    def player_characters(obj):
        return ", ".join([str(ob) for ob in obj.characters.all()])


class EmitInline(admin.TabularInline):
    list_display = ('id',)
    model = StoryEmit
    extra = 0
    raw_id_fields = ('sender',)


class ChapterAdmin(BaseCharAdmin):
    list_display = ('id', 'name', 'story', 'synopsis', 'start_date', 'end_date')
    inlines = [EmitInline]


class EpisodeAdmin(BaseCharAdmin):
    list_display = ('id', 'name', 'chapter', 'synopsis', 'date')
    inlines = [EmitInline]


class RevForMystInline(admin.TabularInline):
    model = RevelationForMystery
    extra = 0


class MystDiscoInline(admin.TabularInline):
    model = MysteryDiscovery
    extra = 0


class MysteryAdmin(BaseCharAdmin):
    list_display = ('id', 'name')
    inlines = [RevForMystInline, MystDiscoInline]


class ClueForRevInline(admin.TabularInline):
    model = ClueForRevelation
    extra = 0


class RevDiscoInline(admin.TabularInline):
    model = RevelationDiscovery
    extra = 0


class RevelationAdmin(BaseCharAdmin):
    list_display = ('id', 'name', 'known_by', 'used_for')
    inlines = [ClueForRevInline, RevDiscoInline]
    search_fields = ('id', 'name', 'characters__character__db_key', 'mysteries__name')

    @staticmethod
    def known_by(obj):
        return ", ".join([str(ob.character) for ob in obj.discoveries.all()])

    @staticmethod
    def used_for(obj):
        return ", ".join([str(ob) for ob in obj.mysteries.all()])


class ClueDiscoInline(admin.TabularInline):
    model = ClueDiscovery
    extra = 0
    raw_id_fields = ("clue", "character",)


class ClueAdmin(BaseCharAdmin):
    list_display = ('id', 'name', 'rating', 'known_by', 'used_for')
    search_fields = ('id', 'name', 'characters__character__db_key', 'revelations__name')

    @staticmethod
    def known_by(obj):
        return ", ".join([str(ob.character) for ob in obj.discoveries.all() if ob.roll >= obj.rating])

    @staticmethod
    def used_for(obj):
        return ", ".join([str(ob) for ob in obj.revelations.all()])


class ClueDiscoveryListFilter(admin.SimpleListFilter):
    title = 'Discovered'
    parameter_name = 'discovered'

    def lookups(self, request, model_admin):
        return (
            ('unfound', 'Undiscovered'),
            ('found', 'Discovered'),
            )

    def queryset(self, request, queryset):
        if self.value() == 'unfound':
            return queryset.filter(roll__lt=F('clue__rating'))
        if self.value() == 'found':
            return queryset.filter(roll__gte=F('clue__rating'))


class ClueDiscoveryAdmin(BaseCharAdmin):
    list_display = ('id', 'clue', 'character', 'roll', 'discovered')
    search_fields = ('id', 'clue__name', 'character__character__db_key')
    list_filter = (ClueDiscoveryListFilter,)

    @staticmethod
    def discovered(obj):
        return obj.roll >= obj.clue.rating


class MystForEntry(MystDiscoInline):
    fk_name = 'character'


class RevForEntry(RevDiscoInline):
    fk_name = 'character'


class EntryAdmin(NoDeleteAdmin):
    list_display = ('id', 'character', 'roster', 'current_alts')
    ordering = ['roster', 'character__db_key']
    search_fields = ['character__db_key', 'roster__name']
    raw_id_fields = ("character", "player", "current_account")
    list_filter = ('roster', 'frozen', 'inactive')
    form = EntryForm
    inlines = [MystForEntry, RevForEntry]

    @staticmethod
    def current_alts(obj):
        return ", ".join([str(ob) for ob in obj.alts])


class InvestigationAdmin(BaseCharAdmin):
    list_display = ('id', 'character', 'topic', 'clue_target', 'clue_progress', 'current_assistants', 'active',
                    'ongoing', 'automate_result')
    list_filter = ('active', 'ongoing', 'automate_result')
    inlines = [MystDiscoInline, RevDiscoInline, ClueDiscoInline]
    raw_id_fields = ('clue_target',)

    @staticmethod
    def clue_progress(obj):
        return obj.progress

    @staticmethod
    def current_assistants(obj):
        return ", ".join(str(ob.char) for ob in obj.active_assistants)


class TheoryAdmin(BaseCharAdmin):
    list_display = ('id', 'creator', 'topic', 'description', 'shared_with')
    filter_horizontal = ('known_by', 'related_clues', 'related_theories')

    @staticmethod
    def shared_with(obj):
        return ", ".join(str(ob) for ob in obj.known_by.all())

    def description(self, obj):
        from web.help_topics.templatetags.app_filters import mush_to_html
        return mush_to_html(obj.desc)
    description.allow_tags = True


class StoryEmitAdmin(BaseCharAdmin):
    list_display = ('id', 'chapter', 'episode', 'text', 'sender')

# Register your models here.
admin.site.register(Roster, BaseCharAdmin)
admin.site.register(RosterEntry, EntryAdmin)
admin.site.register(Photo, PhotoAdmin)
admin.site.register(Story, BaseCharAdmin)
admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Episode, EpisodeAdmin)
admin.site.register(Milestone, BaseCharAdmin)
admin.site.register(Participant, BaseCharAdmin)
admin.site.register(Comment, BaseCharAdmin)
admin.site.register(PlayerAccount, AccountAdmin)
admin.site.register(StoryEmit, StoryEmitAdmin)
admin.site.register(Mystery, MysteryAdmin)
admin.site.register(Revelation, RevelationAdmin)
admin.site.register(Clue, ClueAdmin)
admin.site.register(ClueDiscovery, ClueDiscoveryAdmin)
admin.site.register(Investigation, InvestigationAdmin)
admin.site.register(Theory, TheoryAdmin)
