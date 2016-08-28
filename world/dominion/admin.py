from django.contrib import admin
from .models import (PlayerOrNpc, Organization, Domain, Agent, AgentOb,
                                  AssetOwner, Region, Land, DomainProject, Castle,
                                  Ruler, Army, Orders, MilitaryUnit, Member, Task,
                                  CraftingRecipe, CraftingMaterialType, CraftingMaterials,
                                  RPEvent, AccountTransaction, AssignedTask, Crisis,
                                  OrgRelationship, Reputation, TaskSupporter, InfluenceCategory,
                                  Renown, SphereOfInfluence, TaskRequirement)
from django.db.models import Sum

class DomAdmin(admin.ModelAdmin):
##    def get_actions(self, request):
##        #Disable delete
##        actions = super(DomAdmin, self).get_actions(request)
##        del actions['delete_selected']
##        return actions
##
##    def has_delete_permission(self, request, obj=None):
##        #Disable delete
##        return False
    list_select_related = True
    save_as = True

class PCAdmin(DomAdmin):
    search_fields = ['player__username', 'npc_name']
    filter_horizontal = ['parents', 'spouses']
    raw_id_fields = ('player',)
    list_select_related = (
        'player',
    )

class MemberInline(admin.StackedInline):
    model = Member
    extra = 0
    raw_id_fields = ('commanding_officer',)
    exclude = ('object','pc_exists', 'salary')
    readonly_fields = ('work_this_week', 'work_total')

class OrgAdmin(DomAdmin):
    list_display = ('name', 'membership')
    ordering = ['name']
    search_fields = ['name']
    def membership(self, obj):
        return ", ".join([str(p) for p in obj.members.filter(deguilded=False)])
    inlines = [MemberInline]

    

class Assignments(admin.StackedInline):
    model = AssignedTask
    extra = 0

class Supporters(admin.TabularInline):
    model = TaskSupporter
    extra = 0
    readonly_fields = ('rating','week',)

class AssignedTaskAdmin(DomAdmin):
    list_display = ('member', 'org', 'task', 'finished', 'week', 'support_total')
    search_fields = ('member__player__player__username', 'task__name')
    inlines = [Supporters]
    def support_total(self, obj):
        return obj.total
    def org(self, obj):
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
    def typename(self, obj):
        return obj.type
    list_filter = ('army',)

class RulerAdmin(DomAdmin):
    list_display = ('house', 'liege', 'castellan')
    ordering = ['house']
    search_fields = ['house__organization_owner__name']
    raw_id_fields = ('castellan',)

class DomainAdmin(DomAdmin):
    list_display = ('name', 'ruler', 'land')
    ordering = ['name']
    search_fields = ['name']

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
    ordering = ['date']
    raw_id_fields = ('location',)
    filter_horizontal = ['hosts', 'participants', 'gms']

class TransactionInline(admin.TabularInline):
    model = AccountTransaction
    fk_name = 'sender'
    extra = 0
    raw_id_fields = ('receiver',)

class AssetAdmin(DomAdmin):
    list_display = ('ownername', 'vault', 'prestige', 'economic', 'military', 'social')
    search_fields = ['player__npc_name', 'player__player__username', 'organization_owner__name']
    inlines = [TransactionInline]
    raw_id_fields = ('player',)
    def ownername(self, obj):
        return obj.owner

class AgentObAdmin(DomAdmin):
    list_display = ('agent_class', 'dbobj', 'quantity', 'guarding')
    raw_id_fields = ('dbobj',)
    def guarding(self, obj):
        if not obj.dbobj:
            return None
        return obj.dbobj.db.guarding

class TaskAdmin(DomAdmin):
    list_display = ('id', 'name', 'orgs', 'category', 'active', 'difficulty')
    search_fields = ('name', 'org__name')
    def orgs(self, obj):
        return ", ".join([p.name for p in obj.org.all()])
    filter_horizontal = ['org']

class CrisisAdmin(DomAdmin):
    filter_horizontal = ['orgs']

class OrgRelationshipAdmin(DomAdmin):
    filter_horizontal = ['orgs']

class ReputationAdmin(DomAdmin):
    list_display = ('player', 'organization', 'affection', 'respect')
    raw_id_fields = ('player',)

class SpheresInline(admin.TabularInline):
    model = SphereOfInfluence
    extra = 0

class RenownInline(admin.TabularInline):
    model = Renown
    extra = 0

class TaskRequirementsInline(admin.TabularInline):
    model = TaskRequirement
    extra = 0

class InfluenceCategoryAdmin(DomAdmin):
    list_display = ('name', 'Orgs', 'Tasks')
    ordering = ['name']
    search_fields = ['name', 'orgs__name', 'tasks__name']
    def Orgs(self, obj):
        return ", ".join([p.name for p in obj.orgs.all().order_by('name')])
    def Tasks(self, obj):
        return ", ".join([p.name for p in obj.tasks.all().order_by('name')])
    inlines = [SpheresInline, TaskRequirementsInline, RenownInline]
  
# Register your models here.
admin.site.register(PlayerOrNpc, PCAdmin)
admin.site.register(Organization, OrgAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Agent, DomAdmin)
admin.site.register(AgentOb, AgentObAdmin)
admin.site.register(AssetOwner, AssetAdmin)
admin.site.register(Army, DomAdmin)
admin.site.register(Orders, DomAdmin)
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
admin.site.register(OrgRelationship, OrgRelationshipAdmin)
admin.site.register(Reputation, ReputationAdmin)
admin.site.register(AssignedTask, AssignedTaskAdmin)
admin.site.register(InfluenceCategory, InfluenceCategoryAdmin)
