from django.contrib import admin
from .models import (PlayerOrNpc, Organization, Domain, Agent, AgentOb, Minister,
                     AssetOwner, Region, Land, DomainProject, Castle,
                     Ruler, Army, Orders, MilitaryUnit, Member, Task, OrgUnitModifiers,
                     CraftingRecipe, CraftingMaterialType, CraftingMaterials, CrisisActionAssistant,
                     RPEvent, AccountTransaction, AssignedTask, Crisis, CrisisAction, CrisisUpdate,
                     OrgRelationship, Reputation, TaskSupporter, InfluenceCategory,
                     Renown, SphereOfInfluence, TaskRequirement, ClueForOrg, ActionOOCQuestion)


class DomAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    list_select_related = True
    save_as = True

    @staticmethod
    def name(obj):
        return str(obj)


class ReputationInline(admin.TabularInline):
    model = Reputation
    raw_id_fields = ('player', 'organization')
    extra = 0


class PCAdmin(DomAdmin):
    search_fields = ['player__username', 'npc_name']
    filter_horizontal = ['parents', 'spouses']
    raw_id_fields = ('player', 'patron')
    list_select_related = (
        'player',
    )
    inlines = (ReputationInline,)


class MemberInline(admin.StackedInline):
    model = Member
    extra = 0
    raw_id_fields = ('commanding_officer', 'player', 'organization')
    exclude = ('object', 'pc_exists', 'salary')
    readonly_fields = ('work_this_week', 'work_total')


class ClueForOrgInline(admin.TabularInline):
    model = ClueForOrg
    extra = 0
    raw_id_fields = ('clue', 'org', 'revealed_by')


class OrgUnitInline(admin.TabularInline):
    model = OrgUnitModifiers
    extra = 0
    raw_id_fields = ('org',)


class OrgListFilter(admin.SimpleListFilter):
    title = 'PC or NPC'
    parameter_name = 'played'

    def lookups(self, request, model_admin):
        return (
            ('pc', 'Has Players'),
            ('npc', 'NPCs Only'),
            )

    def queryset(self, request, queryset):
        if self.value() == 'pc':
            return queryset.filter(members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(members__player__player__isnull=True).distinct()


class OrgAdmin(DomAdmin):
    list_display = ('id', 'name', 'category')
    ordering = ['name']
    search_fields = ['name', 'category', 'members__player__player__username']
    list_filter = (OrgListFilter,)
    filter_horizontal = ("theories",)

    # @staticmethod
    # def membership(obj):
    #     return ", ".join([str(p) for p in obj.members.filter(deguilded=False)])
    inlines = [MemberInline, ClueForOrgInline, OrgUnitInline]

    
class Assignments(admin.StackedInline):
    model = AssignedTask
    extra = 0


class Supporters(admin.TabularInline):
    model = TaskSupporter
    extra = 0
    readonly_fields = ('rating', 'week',)


class AssignedTaskAdmin(DomAdmin):
    list_display = ('member', 'org', 'task', 'finished', 'week', 'support_total')
    search_fields = ('member__player__player__username', 'task__name')
    inlines = [Supporters]

    @staticmethod
    def support_total(obj):
        return obj.total

    @staticmethod
    def org(obj):
        return obj.member.organization.name
    list_filter = ('finished',)
    list_select_related = ('member__player__player', 'member__organization', 'task')


class MemberAdmin(DomAdmin):
    list_display = ('player', 'organization', 'rank')
    ordering = ['player', 'organization', 'rank']
    search_fields = ['player__player__username', 'organization__name']
    list_filter = ('organization', 'player')
    raw_id_fields = ('object', 'player',)
    inlines = [Assignments]
    list_select_related = ('player__player', 'organization')


class UnitAdmin(DomAdmin):
    list_display = ('typename', 'army', 'quantity')
    ordering = ['army']
    search_fields = ['army__name']

    @staticmethod
    def typename(obj):
        return obj.type
    list_filter = ('army',)


class MinisterInline(admin.TabularInline):
    model = Minister
    raw_id_fields = ('player', 'ruler')
    extra = 0


class RulerListFilter(OrgListFilter):
    def queryset(self, request, queryset):
        if self.value() == 'pc':
            return queryset.filter(house__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(house__organization_owner__members__player__player__isnull=True).distinct()


class RulerAdmin(DomAdmin):
    list_display = ('id', 'house', 'liege', 'castellan')
    ordering = ['house']
    search_fields = ['house__organization_owner__name']
    raw_id_fields = ('castellan', 'house', 'liege')
    inlines = (MinisterInline,)
    list_filter = (RulerListFilter,)


class DomainListFilter(OrgListFilter):
    def queryset(self, request, queryset):
        if self.value() == 'pc':
            return queryset.filter(ruler__house__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(ruler__house__organization_owner__members__player__player__isnull=True).distinct()


class DomainAdmin(DomAdmin):
    list_display = ('id', 'name', 'ruler', 'land')
    ordering = ['name']
    search_fields = ['name']
    raw_id_fields = ('ruler',)
    list_filter = (DomainListFilter,)


class MaterialTypeAdmin(DomAdmin):
    list_display = ('id', 'name', 'desc', 'value', 'category')
    ordering = ['value']
    search_fields = ['name', 'desc', 'category']
    list_filter = ('category',)


class RecipeAdmin(DomAdmin):
    list_display = ('id', 'name', 'result', 'skill', 'ability', 'level', 'difficulty')
    ordering = ['ability', 'level', 'name']
    search_fields = ['name', 'ability', 'skill', 'result']
    list_filter = ('ability',)
    filter_horizontal = ['known_by', 'primary_materials', 'secondary_materials', 'tertiary_materials']


class MaterialsAdmin(DomAdmin):
    list_display = ('owner', 'type', 'amount')
    ordering = ['owner']
    search_fields = ['owner__player__player__username', 'type__name']
    list_filter = ('type',)


class EventAdmin(DomAdmin):
    list_display = ('id', 'name', 'date')
    search_fields = ['name', 'hosts__player__username', 'participants__player__username', 'gms__player__username']
    ordering = ['date']
    raw_id_fields = ('location',)
    filter_horizontal = ['hosts', 'participants', 'gms']


class SendTransactionInline(admin.TabularInline):
    model = AccountTransaction
    fk_name = 'sender'
    extra = 0
    raw_id_fields = ('receiver',)


class ReceiveTransactionInline(admin.TabularInline):
    model = AccountTransaction
    fk_name = 'receiver'
    extra = 0
    raw_id_fields = ('sender',)


class AssetAdmin(DomAdmin):
    list_display = ('id', 'ownername', 'vault', 'prestige', 'economic', 'military', 'social')
    search_fields = ['player__npc_name', 'player__player__username', 'organization_owner__name']
    inlines = [SendTransactionInline, ReceiveTransactionInline]
    raw_id_fields = ('player', 'organization_owner')

    @staticmethod
    def ownername(obj):
        return obj.owner


class AgentObAdmin(DomAdmin):
    list_display = ('agent_class', 'dbobj', 'quantity', 'guarding')
    raw_id_fields = ('dbobj',)

    @staticmethod
    def guarding(obj):
        if not obj.dbobj:
            return None
        return obj.dbobj.db.guarding


class TaskRequirementsInline(admin.TabularInline):
    model = TaskRequirement
    extra = 0
    raw_id_fields = ('task',)


class TaskAdmin(DomAdmin):
    list_display = ('id', 'name', 'orgs', 'category', 'active', 'difficulty')
    search_fields = ('name', 'org__name')
    inlines = [TaskRequirementsInline]

    @staticmethod
    def orgs(obj):
        return ", ".join([p.name for p in obj.org.all()])
    filter_horizontal = ['org']

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == "org":
            kwargs["queryset"] = Organization.objects.filter(members__player__player__isnull=False
                                                             ).distinct().order_by('name')
        return super(TaskAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)


class CrisisUpdateInline(admin.TabularInline):
    model = CrisisUpdate
    extra = 0
    raw_id_fields = ('episode',)


class CrisisAdmin(DomAdmin):
    list_display = ('id', 'name', 'desc', 'end_date')
    filter_horizontal = ['orgs']
    raw_id_fields = ('required_clue', 'parent_crisis')
    inlines = (CrisisUpdateInline,)


class CrisisActionAssistantInline(admin.StackedInline):
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
    model = ActionOOCQuestion
    extra = 0
    readonly_fields = ('text_of_answers',)
    raw_id_fields = ('action_assist',)
    
    def get_queryset(self, request):
        qs = super(ActionOOCQuestionInline, self).get_queryset(request)
        return qs.filter(is_intent=False)
        
    fieldsets = [
        (None, {'fields': ['action', ('action_assist', 'is_intent')]}),
        ('Q&A', {'fields': ['text', 'text_of_answers'], 'classes': ['collapse']})]


class CrisisActionAdmin(DomAdmin):
    list_display = ('id', 'dompc', 'crisis', 'player_action', 'week', 'status')
    search_fields = ('crisis__name', 'dompc__player__username')
    list_filter = ('crisis', 'status')
    raw_id_fields = ('dompc', 'gemit', 'gm', 'crisis', 'update',)
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
        from web.help_topics.templatetags.app_filters import mush_to_html
        return mush_to_html(obj.actions)


class OrgRelationshipAdmin(DomAdmin):
    filter_horizontal = ['orgs']


class ReputationAdmin(DomAdmin):
    list_display = ('player', 'organization', 'affection', 'respect')
    raw_id_fields = ('player', 'organization')
    search_fields = ('player__player__username', 'organization__name')


class SpheresInline(admin.TabularInline):
    model = SphereOfInfluence
    extra = 0
    raw_id_fields = ('org',)

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == "org":
            kwargs["queryset"] = Organization.objects.filter(members__player__player__isnull=False
                                                             ).distinct().order_by('name')
        return super(SpheresInline, self).formfield_for_foreignkey(db_field, request, **kwargs)


class RenownInline(admin.TabularInline):
    model = Renown
    extra = 0


class InfluenceCategoryAdmin(DomAdmin):
    list_display = ('name', 'organizations', 'task_requirements')
    ordering = ['name']
    search_fields = ['name', 'orgs__name', 'tasks__name']

    @staticmethod
    def organizations(obj):
        return ", ".join([p.name for p in obj.orgs.all().order_by('name')])

    @staticmethod
    def task_requirements(obj):
        return ", ".join([p.name for p in obj.tasks.all().order_by('name')])
    inlines = [SpheresInline, TaskRequirementsInline]


class AgentAdmin(DomAdmin):
    list_display = ('id', 'name', 'quantity', 'quality', 'owner')
    raw_id_fields = ('owner',)
    search_fields = ('name', 'owner__player__player__username', 'owner__organization_owner__name')


class MilitaryUnitInline(admin.TabularInline):
    model = MilitaryUnit
    extra = 0
    raw_id_fields = ('origin', 'commander', 'orders')


class ArmyListFilter(OrgListFilter):
    def queryset(self, request, queryset):
        if self.value() == 'pc':
            return queryset.filter(owner__organization_owner__members__player__player__isnull=False).distinct()
        if self.value() == 'npc':
            return queryset.filter(owner__organization_owner__members__player__player__isnull=True).distinct()


class ArmyAdmin(DomAdmin):
    list_display = ('id', 'name', 'owner', 'domain')
    raw_id_fields = ('owner', 'domain', 'land', 'castle', 'general', 'temp_owner', 'group')
    search_fields = ('name', 'domain__name', 'owner__player__player__username', 'owner__organization_owner__name')
    inlines = (MilitaryUnitInline,)
    list_filter = (ArmyListFilter,)


class OrdersAdmin(DomAdmin):
    list_display = ('id', 'army', 'type', 'action', 'complete')
    raw_id_fields = ('army', 'action', 'action_assist', 'assisting', 'target_land', 'target_domain', 'target_character')
    list_filter = ('complete',)


# Register your models here.
admin.site.register(PlayerOrNpc, PCAdmin)
admin.site.register(Organization, OrgAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Agent, AgentAdmin)
admin.site.register(AgentOb, AgentObAdmin)
admin.site.register(AssetOwner, AssetAdmin)
admin.site.register(Army, ArmyAdmin)
admin.site.register(Orders, OrdersAdmin)
admin.site.register(MilitaryUnit, UnitAdmin)
admin.site.register(Region, DomAdmin)
admin.site.register(Land, DomAdmin)
admin.site.register(DomainProject, DomAdmin)
admin.site.register(Castle, DomAdmin)
admin.site.register(Member, MemberAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(Ruler, RulerAdmin)
admin.site.register(CraftingRecipe, RecipeAdmin)
admin.site.register(CraftingMaterialType, MaterialTypeAdmin)
admin.site.register(CraftingMaterials, MaterialsAdmin)
admin.site.register(RPEvent, EventAdmin)
admin.site.register(Crisis, CrisisAdmin)
admin.site.register(CrisisAction, CrisisActionAdmin)
admin.site.register(OrgRelationship, OrgRelationshipAdmin)
admin.site.register(Reputation, ReputationAdmin)
admin.site.register(AssignedTask, AssignedTaskAdmin)
admin.site.register(InfluenceCategory, InfluenceCategoryAdmin)
