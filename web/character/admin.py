"""
Admin models for Character app
"""
from django.contrib import admin
from django.forms import ModelForm
from .models import (Roster, RosterEntry, Photo, DISCO_MULT, SearchTag, FlashbackPost, Flashback,
                     Story, Chapter, Episode, StoryEmit, LoreTopic,
                     Milestone, FirstContact,
                     PlayerAccount, AccountHistory, InvestigationAssistant,
                     Mystery, Revelation, Clue, Investigation,
                     MysteryDiscovery, RevelationDiscovery, ClueDiscovery,
                     RevelationForMystery, ClueForRevelation, Theory,
                     )
from django.db.models import F, Subquery, OuterRef, IntegerField, ExpressionWrapper, Q


class BaseCharAdmin(admin.ModelAdmin):
    """Base admin settings"""
    list_select_related = True
    save_as = True


class NoDeleteAdmin(BaseCharAdmin):
    """Prevent deletion in Base Admin for some critical models"""
    def get_actions(self, request):
        """Disable delete"""
        actions = super(BaseCharAdmin, self).get_actions(request)
        try:
            del actions['delete_selected']
        except KeyError:
            pass
        return actions

    def has_delete_permission(self, request, obj=None):
        """Disable delete"""
        return False


class EntryForm(ModelForm):
    """Form for RosterEntry admin. Used to limit profile picture queryset"""
    def __init__(self, *args, **kwargs):
        super(EntryForm, self).__init__(*args, **kwargs)
        self.fields['profile_picture'].queryset = Photo.objects.filter(owner=self.instance.character)


class PhotoAdmin(BaseCharAdmin):
    """Admin for Cloudinary photos"""
    list_display = ('id', 'title', 'owner', 'alt_text')
    raw_id_fields = ('owner',)


class AccountHistoryInline(admin.TabularInline):
    """Inline for AccountHistory"""
    model = AccountHistory
    can_delete = False
    extra = 0
    raw_id_fields = ('account', 'entry')


class AccountAdmin(BaseCharAdmin):
    """Admin for AccountHistory"""
    list_display = ('id', 'email', 'player_characters')
    search_fields = ('email', 'characters__character__db_key')
    inlines = [AccountHistoryInline]

    @staticmethod
    def player_characters(obj):
        """List names of our characters for list display"""
        return ", ".join([str(ob) for ob in obj.characters.all()])


class EmitInline(admin.TabularInline):
    """Inline admin of Gemits"""
    list_display = ('id',)
    model = StoryEmit
    extra = 0
    raw_id_fields = ('sender',)


class ChapterAdmin(BaseCharAdmin):
    """Admin for chapters"""
    list_display = ('id', 'name', 'story', 'synopsis', 'start_date', 'end_date')
    inlines = [EmitInline]


class EpisodeAdmin(BaseCharAdmin):
    """Admin for episodes"""
    list_display = ('id', 'name', 'chapter', 'synopsis', 'date')
    inlines = [EmitInline]


class RevForMystInline(admin.TabularInline):
    """Inline of revelations required for a mystery"""
    model = RevelationForMystery
    extra = 0
    raw_id_fields = ('revelation', 'mystery',)


class MystDiscoInline(admin.TabularInline):
    """Inline of mysteries discovered"""
    model = MysteryDiscovery
    extra = 0
    raw_id_fields = ('character', 'investigation', 'mystery')


class MysteryAdmin(BaseCharAdmin):
    """Admin of mystery"""
    list_display = ('id', 'name')
    inlines = [RevForMystInline, MystDiscoInline]


class ClueForRevInline(admin.TabularInline):
    """Inline of clues required for a revelation"""
    model = ClueForRevelation
    extra = 0
    raw_id_fields = ('clue', 'revelation',)


class RevDiscoInline(admin.TabularInline):
    """Inline of revelation discoveries"""
    model = RevelationDiscovery
    extra = 0
    raw_id_fields = ('character', 'investigation', 'revealed_by', 'revelation',)


class RevelationAdmin(BaseCharAdmin):
    """Admin for revelations"""
    list_display = ('id', 'name', 'known_by', 'used_for')
    inlines = [ClueForRevInline, RevDiscoInline]
    search_fields = ('id', 'name', 'characters__character__db_key', 'mysteries__name')

    @staticmethod
    def known_by(obj):
        """Names of people who've discovered this revelation"""
        return ", ".join([str(ob.character) for ob in obj.discoveries.all()])

    @staticmethod
    def used_for(obj):
        """Names of mysteries this revelation is used for"""
        return ", ".join([str(ob) for ob in obj.mysteries.all()])


class ClueDiscoInline(admin.TabularInline):
    """Inline of Clue Discoveries"""
    model = ClueDiscovery
    extra = 0
    raw_id_fields = ("clue", "character", "investigation", "revealed_by",)


class ClueAdmin(BaseCharAdmin):
    """Admin for Clues"""
    list_display = ('id', 'name', 'rating', 'used_for')
    search_fields = ('id', 'name', 'characters__character__db_key', 'revelations__name', 'search_tags__name')
    inlines = (ClueForRevInline,)
    filter_horizontal = ('search_tags',)
    raw_id_fields = ('event',)

    @staticmethod
    def used_for(obj):
        """Names of revelations this clue is used for"""
        return ", ".join([str(ob) for ob in obj.revelations.all()])

    readonly_fields = ('event_gms',)

    @staticmethod
    def event_gms(obj):
        """Names of hosts from event that spawned this clue"""
        return ", ".join(str(obj) for obj in obj.creators)


class ClueDiscoveryListFilter(admin.SimpleListFilter):
    """List filter for showing whether clues are discovered or not"""
    title = 'Discovered'
    parameter_name = 'discovered'

    def lookups(self, request, model_admin):
        """values for GET and their display"""
        return (
            ('unfound', 'Undiscovered'),
            ('found', 'Discovered'),
            )

    def queryset(self, request, queryset):
        """How we modify the queryset based on the lookups values"""
        if self.value() == 'unfound':
            return queryset.filter(roll__lt=F('clue__rating') * DISCO_MULT)
        if self.value() == 'found':
            return queryset.filter(roll__gte=F('clue__rating') * DISCO_MULT)


class ClueDiscoveryAdmin(BaseCharAdmin):
    """Admin for ClueDiscoveries"""
    list_display = ('id', 'clue', 'character', 'roll', 'discovered')
    search_fields = ('id', 'clue__name', 'character__character__db_key')
    raw_id_fields = ('clue', 'character', 'investigation', 'revealed_by')
    list_filter = (ClueDiscoveryListFilter,)

    @staticmethod
    def discovered(obj):
        """Whether the clue is discovered"""
        return obj.roll >= obj.clue.rating * DISCO_MULT


class MystForEntry(MystDiscoInline):
    """Inline for mystery discoveries"""
    fk_name = 'character'
    raw_id_fields = ('character', 'mystery')


class RevForEntry(RevDiscoInline):
    """Inline of revelation discoveries"""
    fk_name = 'character'
    raw_id_fields = ('character', 'revelation', 'investigation', 'revealed_by')


class EntryAdmin(NoDeleteAdmin):
    """The primary admin model, the RosterEntry/Character Sheet for a player/character combination"""
    list_display = ('id', 'character', 'roster', 'current_alts')
    ordering = ['roster', 'character__db_key']
    search_fields = ['character__db_key', 'roster__name']
    raw_id_fields = ("current_account", "profile_picture",)
    readonly_fields = ('character', 'player',)
    list_filter = ('roster', 'frozen', 'inactive')
    form = EntryForm
    inlines = [MystForEntry, RevForEntry, AccountHistoryInline]

    @staticmethod
    def current_alts(obj):
        """Names of alts for the RosterEntry"""
        return ", ".join([str(ob) for ob in obj.alts])


class InvestigationAssistantInline(admin.TabularInline):
    """Inline showing assistants for an investigation"""
    model = InvestigationAssistant
    extra = 0
    raw_id_fields = ("investigation", "char",)


class InvestigationListFilter(admin.SimpleListFilter):
    """List filter for showing whether an investigation will finish this week or not"""
    title = "Progress"
    parameter_name = "progress"

    def lookups(self, request, model_admin):
        """Values for the GET request and how they display"""
        return (
            ('finishing', 'Will Finish'),
            ('not_finishing', "Won't Finish")
        )

    def queryset(self, request, queryset):
        """
        So the queryset for this will be heavily annotated using django's Subquery and OuterRef classes.
        Basically we annotate the values of the total progress we need, how much progress is stored in
        the investigation's ClueDiscovery, and then determine if the total progress of our roll plus
        the clue's saved progress is high enough to meet that goal.
        Args:
            request: the HttpRequest object
            queryset: the Investigation queryset

        Returns:
            queryset that can be modified to either show those finishing or those who won't.
        """
        qs = queryset.filter(clue_target__isnull=False).annotate(goal=F('clue_target__rating') * DISCO_MULT)
        clues = ClueDiscovery.objects.filter(investigation__isnull=False)
        qs = qs.annotate(clue_roll=Subquery(clues.filter(investigation=OuterRef('id')).values('roll')[:1],
                                            output_field=IntegerField()))
        qs = qs.annotate(total_progress=ExpressionWrapper(F('roll') + F('clue_roll'), output_field=IntegerField()))
        if self.value() == "finishing":
            # checking roll by itself in case there isn't a ClueDiscovery yet and would finish in one week
            return qs.filter(Q(total_progress__gte=F('goal')) | Q(roll__gte=F('goal')))
        if self.value() == "not_finishing":
            return qs.filter(Q(total_progress__lt=F('goal')) & ~Q(roll__gte=F('goal')))


class InvestigationAdmin(BaseCharAdmin):
    """Admin class for Investigations"""
    list_display = ('id', 'character', 'topic', 'clue_target', 'active',
                    'ongoing', 'automate_result')
    list_filter = ('active', 'ongoing', 'automate_result', InvestigationListFilter)
    search_fields = ('character__character__db_key', 'topic', 'clue_target__name')
    inlines = [MystDiscoInline, RevDiscoInline, ClueDiscoInline, InvestigationAssistantInline]
    raw_id_fields = ('clue_target', 'character',)
    readonly_fields = ('clue_progress',)

    @staticmethod
    def clue_progress(obj):
        """Progress made toward discovering a clue"""
        return "%s/%s" % (obj.progress, obj.completion_value)


class TheoryAdmin(BaseCharAdmin):
    """Admin class for Theory"""
    list_display = ('id', 'creator', 'topic', 'description', 'shared_with')
    filter_horizontal = ('known_by', 'related_clues', 'related_theories')

    @staticmethod
    def shared_with(obj):
        """Who knows the theory"""
        return ", ".join(str(ob) for ob in obj.known_by.all())

    def description(self, obj):
        """Formatted description"""
        from web.help_topics.templatetags.app_filters import mush_to_html
        return mush_to_html(obj.desc)
    description.allow_tags = True


class StoryEmitAdmin(BaseCharAdmin):
    """Admin for Gemits"""
    list_display = ('id', 'chapter', 'episode', 'text', 'sender')


class LoreTopicAdmin(BaseCharAdmin):
    """Admin for Lore topics - the OOC knowledge base for GMs of game lore"""
    list_display = ('id', 'name')
    search_fields = ('id', 'name', 'desc')


class FirstContactAdmin(BaseCharAdmin):
    """Admin for First Impressions"""
    list_display = ('id', 'from_name', 'summary', 'to_name')
    search_fields = ('id', 'from_account__entry__player__username', 'to_account__entry__player__username')
    readonly_fields = ('from_account', 'to_account')

    @staticmethod
    def from_name(obj):
        """name of the sender"""
        return str(obj.from_account.entry)

    @staticmethod
    def to_name(obj):
        """Name of the receiver"""
        return str(obj.to_account.entry)


class PostInline(admin.StackedInline):
    """Inline for Flashback Posts"""
    model = FlashbackPost
    extra = 0
    exclude = ('read_by', 'db_date_created')
    raw_id_fields = ('poster',)
    fieldsets = [(None, {'fields': ['poster']}),
                 ('Story', {'fields': ['actions'], 'classes': ['collapse']}),
                 ]


class FlashbackAdmin(BaseCharAdmin):
    """Admin for Flashbacks"""
    list_display = ('id', 'title', 'owner',)
    search_fields = ('id', 'title', 'owner__player__username')
    raw_id_fields = ('owner',)
    inlines = [PostInline]
    fieldsets = [(None, {'fields': [('owner', 'title'), 'summary']})]

# Register your models here.
admin.site.register(Roster, BaseCharAdmin)
admin.site.register(RosterEntry, EntryAdmin)
admin.site.register(FirstContact, FirstContactAdmin)
admin.site.register(Photo, PhotoAdmin)
admin.site.register(Story, BaseCharAdmin)
admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Episode, EpisodeAdmin)
admin.site.register(Milestone, BaseCharAdmin)
admin.site.register(PlayerAccount, AccountAdmin)
admin.site.register(StoryEmit, StoryEmitAdmin)
admin.site.register(Mystery, MysteryAdmin)
admin.site.register(Revelation, RevelationAdmin)
admin.site.register(Clue, ClueAdmin)
admin.site.register(ClueDiscovery, ClueDiscoveryAdmin)
admin.site.register(Investigation, InvestigationAdmin)
admin.site.register(Theory, TheoryAdmin)
admin.site.register(LoreTopic, LoreTopicAdmin)
admin.site.register(Flashback, FlashbackAdmin)
