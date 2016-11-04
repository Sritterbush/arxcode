from django.contrib import admin
from django.forms import ModelForm
from .models import (Roster, RosterEntry, Photo,
                     Story, Chapter, Episode, StoryEmit,
                     Milestone, Participant, Comment,
                     PlayerAccount, AccountHistory,
                     Mystery, Revelation, Clue, Investigation,
                     MysteryDiscovery, RevelationDiscovery, ClueDiscovery,
                     RevelationForMystery, ClueForRevelation,
                     )


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
    list_display = ('id', 'email', 'Characters')
    search_fields = ('email', 'characters__character__db_key')
    inlines = [AccountHistoryInline]

    def Characters(self, obj):
        return ", ".join([str(ob) for ob in obj.characters.all()])


class EmitInline(admin.TabularInline):
    list_display = ('id',)
    model = StoryEmit
    extra = 0
    raw_id_fields = ('sender',)


class ChapterAdmin(BaseCharAdmin):
    list_display = ('id',)
    inlines = [EmitInline]


class EpisodeAdmin(BaseCharAdmin):
    list_display = ('id',)
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

    def known_by(self, obj):
        return ", ".join([str(ob.character) for ob in obj.discoveries.all()])

    def used_for(self, obj):
        return ", ".join([str(ob) for ob in obj.mysteries.all()])


class ClueDiscoInline(admin.TabularInline):
    model = ClueDiscovery
    extra = 0


class ClueAdmin(BaseCharAdmin):
    list_display = ('id', 'name', 'known_by', 'used_for')
    inlines = [ClueDiscoInline]
    search_fields = ('id', 'name', 'characters__character__db_key', 'revelations__name')

    def known_by(self, obj):
        return ", ".join([str(ob.character) for ob in obj.discoveries.all() if ob.roll >= obj.rating])

    def used_for(self, obj):
        return ", ".join([str(ob) for ob in obj.revelations.all()])


class ClueForEntry(ClueDiscoInline):
    fk_name = 'character'


class MystForEntry(MystDiscoInline):
    fk_name = 'character'


class RevForEntry(RevDiscoInline):
    fk_name = 'character'


class EntryAdmin(NoDeleteAdmin):
    list_display = ('id', 'character', 'roster', 'current_alts')
    ordering = ['roster', 'character__db_key']
    search_fields = ['character__db_key', 'roster__name']
    raw_id_fields = ("character", "player")
    list_filter = ('roster', 'frozen', 'inactive')
    form = EntryForm
    inlines = [MystForEntry, RevForEntry, ClueForEntry]

    def current_alts(self, obj):
        return ", ".join([str(ob) for ob in obj.alts])


class InvestigationAdmin(BaseCharAdmin):
    list_display = ('id', 'character', 'topic', 'clue_target', 'clue_progress', 'active', 'ongoing', 'automate_result')
    list_filter = ('active', 'ongoing', 'automate_result')
    inlines = [MystDiscoInline, RevDiscoInline, ClueDiscoInline]

    def clue_progress(self, obj):
        return obj.progress


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
admin.site.register(StoryEmit, BaseCharAdmin)
admin.site.register(Mystery, MysteryAdmin)
admin.site.register(Revelation, RevelationAdmin)
admin.site.register(Clue, ClueAdmin)
admin.site.register(Investigation, InvestigationAdmin)

