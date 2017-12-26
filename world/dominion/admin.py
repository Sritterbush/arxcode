"""
Admin for Dominion
"""
from django.contrib import admin
from .models import (PlayerOrNpc, Organization, Domain, Agent, AgentOb, Minister,
                     AssetOwner, Region, Land, Castle,
                     Ruler, Army, Orders, MilitaryUnit, Member, Task, OrgUnitModifiers,
                     CraftingRecipe, CraftingMaterialType, CraftingMaterials, CrisisActionAssistant,
                     RPEvent, AccountTransaction, AssignedTask, Crisis, CrisisAction, CrisisUpdate,
                     OrgRelationship, Reputation, TaskSupporter, InfluenceCategory,
                     Renown, SphereOfInfluence, TaskRequirement, ClueForOrg, ActionOOCQuestion,
                     PlotRoom, Landmark, Shardhaven, ShardhavenType, ShardhavenClue, ShardhavenDiscovery)

from web.help_topics.templatetags.app_filters import mush_to_html


class DomAdmin(admin.ModelAdmin):
    """Base admin class"""
    list_display = ('id', 'name')
    list_select_related = True
    save_as = True

    @staticmethod
    def name(obj):
        """For displaying name along with ID as a default/fallback"""
        return str(obj)


class ReputationInline(admin.TabularInline):
    """Character reputation with orgs admin"""
    model = Reputation
    raw_id_fields = ('player', 'organization')
    extra = 0


class PCAdmin(DomAdmin):
    """Admin for main model of dominion, PlayerOrNpc, an extension of AUTH_USER_MODEL"""
    search_fields = ['player__username', 'npc_name']
    filter_horizontal = ['parents', 'spouses']
    raw_id_fields = ('player', 'patron')
    list_select_related = (
        'player',
    )
    inlines = (ReputationInline,)


class MemberInline(admin.StackedInline):
    """Inline for displaying Org members"""
    model = Member
    extra = 0
    raw_id_fields = ('commanding_officer', 'player', 'organization')
    exclude = ('object', 'pc_exists', 'salary')
    readonly_fields = ('work_this_week', 'work_total')


class ClueForOrgInline(admin.TabularInline):
    """Inline for display clues orgs know"""
    model = ClueForOrg
    extra = 0
    raw_id_fields = ('clue', 'org', 'revealed_by')


class OrgUnitInline(admin.TabularInline):
    """Inline for display Unit modifiers that orgs have, creating special units unique to them"""
    model = OrgUnitModifiers
    extra = 0
    raw_id_fields = ('org',)


class OrgListFilter(admin.SimpleListFilter):
    """List filter for separating PC and NPC orgs"""
    title = 'PC or NPC'
    parameter_name = 'played'

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (
            ('pc', 'Has Players'),
            ('npc', 'NPCs Only'),
            )

    def queryset(self, request, queryset):
        """Specifies queryset we get based on selected options"""
        if self.value() == 'pc':
            return queryset.filter(members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(members__player__player__isnull=True).distinct()


class OrgAdmin(DomAdmin):
    """Admin for organizations"""
    list_display = ('id', 'name', 'category')
    ordering = ['name']
    search_fields = ['name', 'category', 'members__player__player__username']
    list_filter = (OrgListFilter,)
    filter_horizontal = ("theories",)
    inlines = [MemberInline, ClueForOrgInline, OrgUnitInline]


class Supporters(admin.TabularInline):
    """Inline for Task Supporters, players helping out on Tasks"""
    model = TaskSupporter
    extra = 0
    readonly_fields = ('rating', 'week',)


class AssignedTaskAdmin(DomAdmin):
    """Admin for display tasks players are working on"""
    list_display = ('member', 'org', 'task', 'finished', 'week', 'support_total')
    search_fields = ('member__player__player__username', 'task__name')
    inlines = [Supporters]

    @staticmethod
    def support_total(obj):
        """Total amount of support they've accumulated as an integer"""
        return obj.total

    @staticmethod
    def org(obj):
        """Displays the organization this task is for"""
        return obj.member.organization.name
    list_filter = ('finished',)
    list_select_related = ('member__player__player', 'member__organization', 'task')


class MinisterInline(admin.TabularInline):
    """Inline for ministers for a ruler"""
    model = Minister
    raw_id_fields = ('player', 'ruler')
    extra = 0


class RulerListFilter(OrgListFilter):
    """List filter for display PC or NPC rulers from orgs"""
    def queryset(self, request, queryset):
        """Modify OrgListFilter based on query"""
        if self.value() == 'pc':
            return queryset.filter(house__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(house__organization_owner__members__player__player__isnull=True).distinct()


class RulerAdmin(DomAdmin):
    """Admin for Ruler model, which runs domains"""
    list_display = ('id', 'house', 'liege', 'castellan')
    ordering = ['house']
    search_fields = ['house__organization_owner__name']
    raw_id_fields = ('castellan', 'house', 'liege')
    inlines = (MinisterInline,)
    list_filter = (RulerListFilter,)


class CastleInline(admin.TabularInline):
    """Inline for castles in domains"""
    model = Castle
    extra = 0


class DomainListFilter(OrgListFilter):
    """List filter for separating PC and NPC domains"""
    def queryset(self, request, queryset):
        """modifies orglistfilter query for domains"""
        if self.value() == 'pc':
            return queryset.filter(ruler__house__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(ruler__house__organization_owner__members__player__player__isnull=True).distinct()


class DomainAdmin(DomAdmin):
    """Admin for Domains, player/org offscreen holdings"""
    list_display = ('id', 'name', 'ruler', 'land')
    ordering = ['name']
    search_fields = ['name']
    raw_id_fields = ('ruler',)
    list_filter = (DomainListFilter,)
    inlines = (CastleInline,)


class MaterialTypeAdmin(DomAdmin):
    """Admin for Crafting Material Types, creating/changing the types that exist"""
    list_display = ('id', 'name', 'desc', 'value', 'category')
    ordering = ['value']
    search_fields = ['name', 'desc', 'category']
    list_filter = ('category',)


class RecipeAdmin(DomAdmin):
    """Admin for crafting recipes"""
    list_display = ('id', 'name', 'result', 'skill', 'ability', 'level', 'difficulty')
    ordering = ['ability', 'level', 'name']
    search_fields = ['name', 'ability', 'skill', 'result']
    list_filter = ('ability',)
    filter_horizontal = ['known_by', 'primary_materials', 'secondary_materials', 'tertiary_materials']


class EventAdmin(DomAdmin):
    """Admin for RP Events/PRPs/GM Events"""
    list_display = ('id', 'name', 'date')
    search_fields = ['name', 'hosts__player__username', 'participants__player__username', 'gms__player__username']
    ordering = ['date']
    raw_id_fields = ('location', 'actions', 'plotroom')
    filter_horizontal = ['hosts', 'participants', 'gms']


class SendTransactionInline(admin.TabularInline):
    """Inline for transactions we're sending"""
    model = AccountTransaction
    fk_name = 'sender'
    extra = 0
    raw_id_fields = ('receiver',)


class ReceiveTransactionInline(admin.TabularInline):
    """Inline for money we're receiving"""
    model = AccountTransaction
    fk_name = 'receiver'
    extra = 0
    raw_id_fields = ('sender',)


class MaterialsInline(admin.TabularInline):
    """Inline for amounts of materials an assetowner has"""
    model = CraftingMaterials
    extra = 0


class AssetAdmin(DomAdmin):
    """Admin for the assets of a player or organization"""
    list_display = ('id', 'ownername', 'vault', 'prestige', 'economic', 'military', 'social')
    search_fields = ['player__npc_name', 'player__player__username', 'organization_owner__name']
    inlines = [SendTransactionInline, ReceiveTransactionInline, MaterialsInline]
    raw_id_fields = ('player', 'organization_owner')

    @staticmethod
    def ownername(obj):
        """Gets the name of the entity we hold assets for"""
        return obj.owner


class AgentObInline(admin.TabularInline):
    """Inline for who agents are assigned to"""
    model = AgentOb
    raw_id_fields = ('dbobj', 'agent_class')
    readonly_fields = ('guarding',)
    extra = 0

    @staticmethod
    def guarding(obj):
        """Displays the player their dbobj Character instance is assigned to, if anyone"""
        if not obj.dbobj:
            return None
        return obj.dbobj.db.guarding


class TaskRequirementsInline(admin.TabularInline):
    """Inline that specifies requirements for a task"""
    model = TaskRequirement
    extra = 0
    raw_id_fields = ('task',)


class TaskAdmin(DomAdmin):
    """Admin for Tasks, abstracted things players do for money which are awful and need to be revamped"""
    list_display = ('id', 'name', 'orgs', 'category', 'active', 'difficulty')
    search_fields = ('name', 'org__name')
    inlines = [TaskRequirementsInline]

    @staticmethod
    def orgs(obj):
        """names of organizations involved"""
        return ", ".join([p.name for p in obj.org.all()])
    filter_horizontal = ['org']

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Limits queryset to orgs with players"""
        if db_field.name == "org":
            kwargs["queryset"] = Organization.objects.filter(members__player__player__isnull=False
                                                             ).distinct().order_by('name')
        return super(TaskAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)


class CrisisUpdateInline(admin.TabularInline):
    """Inline showing crisis updates"""
    model = CrisisUpdate
    extra = 0
    raw_id_fields = ('episode',)


class CrisisAdmin(DomAdmin):
    """Admin for Crises, macro-level events affecting the game/metaplot"""
    list_display = ('id', 'name', 'desc', 'end_date')
    filter_horizontal = ['orgs']
    raw_id_fields = ('required_clue', 'parent_crisis')
    inlines = (CrisisUpdateInline,)


class CrisisActionAssistantInline(admin.StackedInline):
    """Inline of someone helping out on an Action"""
    model = CrisisActionAssistant
    extra = 0
    raw_id_fields = ('crisis_action', 'dompc',)
    readonly_fields = ('ooc_intent',)
    fieldsets = [(None, {'fields': [('dompc', 'topic')]}),
                 ('Status', {'fields': [('editable', 'attending', 'traitor')], 'classes': ['collapse']}),
                 ('Story', {'fields': ['actions', 'secret_actions', 'ooc_intent'], 'classes': ['collapse']}),
                 ('Roll', {'fields': [('stat_used', 'skill_used', 'roll')], 'description': 'Stuff for roll and result',
                           'classes': ['collapse']}),
                 ('Resources', {'fields': ['silver', ('action_points', 'social'), ('military', 'economic')],
                                'classes': ['collapse']})
                 ]


class CrisisArmyOrdersInline(admin.TabularInline):
    """Inline of army orders for an action"""
    model = Orders
    show_change_link = True
    extra = 0
    raw_id_fields = ('army', 'target_land', 'assisting', 'action_assist')
    exclude = ('target_domain', 'target_character', 'type', 'week',)
    readonly_fields = ('troops_sent',)
    fieldsets = [
        ('Troops', {'fields': ['army', 'troops_sent']}),
        ('Costs', {'fields': ['coin_cost', 'food_cost']})
    ]
    
    
class ActionOOCQuestionInline(admin.StackedInline):
    """Inline of questions players are asking re: their action"""
    model = ActionOOCQuestion
    extra = 0
    readonly_fields = ('text_of_answers',)
    raw_id_fields = ('action_assist',)
    
    def get_queryset(self, request):
        """Limit queryset to things which aren't their OOC intentions - additional questions only"""
        qs = super(ActionOOCQuestionInline, self).get_queryset(request)
        return qs.filter(is_intent=False)
        
    fieldsets = [
        (None, {'fields': ['action', ('action_assist', 'is_intent')]}),
        ('Q&A', {'fields': ['text', 'text_of_answers'], 'classes': ['collapse']})]


class CrisisActionAdmin(DomAdmin):
    """Admin for @actions that players are taking, one of their primary ways of participating in the game's plot."""
    list_display = ('id', 'dompc', 'crisis', 'player_action', 'week', 'status')
    search_fields = ('crisis__name', 'dompc__player__username')
    list_filter = ('crisis', 'status')
    raw_id_fields = ('dompc', 'gemit', 'gm', 'crisis', 'update')
    readonly_fields = ('ooc_intent',)
    fieldsets = [(None, {'fields': [('dompc', 'topic')]}),
                 ('Status', {'fields': [('attending', 'traitor', 'prefer_offscreen'), ('status', 'public', 'editable'),
                                        ('crisis', 'update', 'gemit'), ('week', 'date_submitted')],
                             'classes': ['collapse'], 'description': 'Current ooc status of the action'}),
                 ('Story', {'fields': [('topic', 'category'), 'actions', 'secret_actions', 'story', 'secret_story',
                                       'ooc_intent'],
                            'description': "The player's story, and GM response to it.",
                            'classes': ['collapse']}),
                 ('Roll', {'fields': [('stat_used', 'skill_used', 'roll', 'difficulty'), 'outcome_value'],
                           'description': 'Stuff for roll and result', 'classes': ['collapse']}),
                 ('Resources', {'fields': ['silver', ('action_points', 'social'), ('military', 'economic')],
                                'classes': ['collapse']})
                 ]
    inlines = (CrisisActionAssistantInline, CrisisArmyOrdersInline, ActionOOCQuestionInline)

    @staticmethod
    def player_action(obj):
        """Reformats what they've written without ansi markup"""
        return mush_to_html(obj.actions)


class OrgRelationshipAdmin(DomAdmin):
    """Admin for showing relationships orgs have with one another. Not really used at present, but should be."""
    filter_horizontal = ['orgs']


class ReputationAdmin(DomAdmin):
    """Admin for reputation players have with organizations."""
    list_display = ('player', 'organization', 'affection', 'respect')
    raw_id_fields = ('player', 'organization')
    search_fields = ('player__player__username', 'organization__name')


class SpheresInline(admin.TabularInline):
    """Showing npc groups that orgs have influence over"""
    model = SphereOfInfluence
    extra = 0
    raw_id_fields = ('org',)

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """Limit queryset to orgs that have players"""
        if db_field.name == "org":
            kwargs["queryset"] = Organization.objects.filter(members__player__player__isnull=False
                                                             ).distinct().order_by('name')
        return super(SpheresInline, self).formfield_for_foreignkey(db_field, request, **kwargs)


class RenownInline(admin.TabularInline):
    """Inline showing renown, a player's influence with npc groups"""
    model = Renown
    extra = 0


class InfluenceCategoryAdmin(DomAdmin):
    """Showing the different npc groups organizations/players can have influence with, and that tasks use"""
    list_display = ('name', 'organizations', 'task_requirements')
    ordering = ['name']
    search_fields = ['name', 'orgs__name', 'tasks__name']

    @staticmethod
    def organizations(obj):
        """Display name of orgs"""
        return ", ".join([p.name for p in obj.orgs.all().order_by('name')])

    @staticmethod
    def task_requirements(obj):
        """Display name of tasks"""
        return ", ".join([p.name for p in obj.tasks.all().order_by('name')])
    inlines = [SpheresInline, TaskRequirementsInline]


class AgentAdmin(DomAdmin):
    """Admin for agents, npcs owned by players or orgs"""
    list_display = ('id', 'name', 'quantity', 'quality', 'owner')
    raw_id_fields = ('owner',)
    search_fields = ('name', 'owner__player__player__username', 'owner__organization_owner__name')
    inlines = [AgentObInline]


class MilitaryUnitInline(admin.TabularInline):
    """Inline for showing military units in an army"""
    model = MilitaryUnit
    extra = 0
    raw_id_fields = ('origin', 'commander', 'orders')


class ArmyListFilter(OrgListFilter):
    """List filter for display armies owned by pcs or npcs"""
    def queryset(self, request, queryset):
        """Modifies query of OrgListFilter for armies"""
        if self.value() == 'pc':
            return queryset.filter(owner__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(owner__organization_owner__members__player__player__isnull=True).distinct()


class ArmyAdmin(DomAdmin):
    """Admin for armies owned by organizations or players"""
    list_display = ('id', 'name', 'owner', 'domain')
    raw_id_fields = ('owner', 'domain', 'land', 'castle', 'general', 'temp_owner', 'group')
    search_fields = ('name', 'domain__name', 'owner__player__player__username', 'owner__organization_owner__name')
    inlines = (MilitaryUnitInline,)
    list_filter = (ArmyListFilter,)


class OrdersAdmin(DomAdmin):
    """Admin for orders of armies"""
    list_display = ('id', 'army', 'type', 'action', 'complete')
    raw_id_fields = ('army', 'action', 'action_assist', 'assisting', 'target_land', 'target_domain', 'target_character')
    list_filter = ('complete',)


class RegionFilter(admin.SimpleListFilter):
    """List filter for plot rooms, letting us see what regions they're in"""
    title = "Region"
    parameter_name = "region"

    def lookups(self, request, model_admin):
        """Get lookup names derived from Regions"""
        regions = Region.objects.all().order_by('name')
        result = []
        for region in regions:
            result.append((region.id, region.name))
        return result

    def queryset(self, request, queryset):
        """Filter queryset by Region selection"""
        if not self.value():
            return queryset

        try:
            region_id = int(self.value())
            region = Region.objects.get(id=region_id)
        except (ValueError, Region.DoesNotExist):
            region = None

        if not region:
            return queryset

        return self.finish_queryset_by_region(queryset, region)

    def finish_queryset_by_region(self, queryset, region):
        """Finishes modifying the queryset. Overridden in subclasses"""
        qs1 = queryset.filter(domain__isnull=False).filter(domain__land__region=region)
        qs2 = queryset.filter(land__isnull=False).filter(land__region=region)
        return qs1 | qs2


class PlotRoomAdmin(DomAdmin):
    """Admin for plotrooms, templates that can be used repeatedly for temprooms for events"""
    list_display = ('id', 'domain', 'land', 'name', 'public')
    search_files = ('name', 'description')
    raw_id_fields = ('creator', 'land', 'domain')
    list_filter = ('public', RegionFilter)


class LandRegionFilter(RegionFilter):
    """List filter for Land by Regions"""
    def finish_queryset_by_region(self, queryset, region):
        """Finishes modifying the queryset. Overridden in subclasses"""
        return queryset.filter(land__region=region)


class LandmarkAdmin(DomAdmin):
    """Admin for Landmarks found ni the world"""
    list_display = ('id', 'name', 'landmark_type', 'land')
    search_fields = ('name', 'description')
    raw_id_fields = ('land',)
    list_filter = ('landmark_type', LandRegionFilter,)


class LandAdmin(DomAdmin):
    """Admin for Land Squares that make up the global map"""
    list_display = ('id', 'name', 'terrain', 'domain_names', 'dungeons', 'landmarks')
    search_fields = ('name', 'region__name', 'domains__name')
    list_filter = ('region', 'landlocked')

    @staticmethod
    def domain_names(obj):
        """Names of domains in this space"""
        return ", ".join(str(ob) for ob in obj.domains.all())

    @staticmethod
    def dungeons(obj):
        """Names of shardhavens in this space"""
        return ", ".join(str(ob) for ob in obj.shardhavens.all())

    @staticmethod
    def landmarks(obj):
        """Names of landmarks in this space"""
        return ", ".join(str(ob) for ob in obj.landmarks.all())


class ShardhavenClueInline(admin.TabularInline):
    """Inline for Clues about Shardhavens"""
    model = ShardhavenClue
    raw_id_fields = ('clue',)
    extra = 0


class ShardhavenDiscoveryInline(admin.TabularInline):
    """Inline for players knowing about Shardhaven locations"""
    model = ShardhavenDiscovery
    raw_id_fields = ('player',)
    extra = 0


class ShardhavenAdmin(DomAdmin):
    """Admin for shardhavens, Arx's very own abyssal-corrupted dungeons. Happy adventuring!"""
    list_display = ('id', 'name', 'land', 'haven_type')
    search_fields = ('name', 'description')
    raw_id_fields = ('land',)
    inlines = (ShardhavenClueInline,)
    list_filter = ('haven_type', LandRegionFilter,)


class ShardhavenTypeAdmin(DomAdmin):
    """Admin for specifying types of Shardhavens"""
    list_display = ('id', 'name')
    search_fields = ('name',)


class ShardhavenDiscoveryAdmin(DomAdmin):
    """Non-inline admin for Shardhaven discoveries"""
    list_display = ('id', 'player', 'shardhaven')
    search_fields = ('player__name', 'shardhaven__name')


# Register your models here.
admin.site.register(PlayerOrNpc, PCAdmin)
admin.site.register(Organization, OrgAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Agent, AgentAdmin)
admin.site.register(AssetOwner, AssetAdmin)
admin.site.register(Army, ArmyAdmin)
admin.site.register(Orders, OrdersAdmin)
admin.site.register(Region, DomAdmin)
admin.site.register(Land, LandAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(Ruler, RulerAdmin)
admin.site.register(CraftingRecipe, RecipeAdmin)
admin.site.register(CraftingMaterialType, MaterialTypeAdmin)
admin.site.register(RPEvent, EventAdmin)
admin.site.register(Crisis, CrisisAdmin)
admin.site.register(CrisisAction, CrisisActionAdmin)
admin.site.register(OrgRelationship, OrgRelationshipAdmin)
admin.site.register(Reputation, ReputationAdmin)
admin.site.register(AssignedTask, AssignedTaskAdmin)
admin.site.register(InfluenceCategory, InfluenceCategoryAdmin)
admin.site.register(PlotRoom, PlotRoomAdmin)
admin.site.register(Landmark, LandmarkAdmin)
admin.site.register(Shardhaven, ShardhavenAdmin)
admin.site.register(ShardhavenType, ShardhavenTypeAdmin)
admin.site.register(ShardhavenDiscovery, ShardhavenDiscoveryAdmin)
