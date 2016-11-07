"""
So, what is Dominion?

Dominion is the design for making the world come alive in an immersive way.
The classic problem most MMOs and MUSHes have is ultimately limiting how
much a player can impact the world. It's understandable, of course - an
MMO would be utterly broken if a single player gets to call the shots. But
MUSHes are a different animal in that we're much smaller, and trying to
create an immersive RP experience that's similar to tabletop RPGs, just
with much more people involved. So what Dominion is attempting to do is
create consequences for player characters interacting with the economy,
owning land, leading armies, or having NPCs in their organizations that
will do their bidding. Dominion is the power and influence that a character
can exert that isn't directly tied to their stats or what they carry on
their person - it's what you can order npcs to do, how the world can
change based on your choices, and ultimately attempts to make the world
feel much more 'real' as a result.

Dominion consists of several moving parts. First is the economy - it's
to try to represent how having wealth can directly translate into power,
and will try to create a fairly believable (albeit abstract) economic
model for the world. With the economy, all forms of wealth, income,
debts, and holdings should be represented for every inhabitant in the
game world.

The second part is organizations, and giving who obey you orders, and
trying to represent how those orders are obeyed. It's where we establish
ranks, relationships such as loyalty and morale, and give strong
consequences to social systems such as prestiege or your reputation
because it will determine how npcs will react to a character on a macro
level.

The last part is military might - a war system for controlling armies,
and the effects of war on the world as a whole.

Models for Dominion:

For the economy, we have: AssetOwner, Ledger, AccountTransaction, and
Domain. AssetOwner receives income from Ledger and Domain objects, with
AccountTransaction handling positive/negative income/debt adjustments to
a Ledger.

For the world map, we have: Region and Land. Player-held Domain objects
will be positioned in Land squares, limited by available area.

For domains, we have: Domain, DomainProject, Castle, and Military. Domain
represents everything within a lord/noble's holding - the people, economy,
military, etc. It is situated within a given Land square.

Every week, a script is called that will run execute_orders() on every
Army, and then do weekly_adjustment() in every assetowner. So only domains
that currently have a ruler designated will change on a weekly basis.
"""
from django.db import models
from django.db.models import Q
from django.conf import settings
from . import unit_types
from .reports import WeeklyReport
from .explore import Exploration
from .battle import Battle
from .agenthandler import AgentHandler
from server.utils.utils import get_week
from evennia.locks.lockhandler import LockHandler
import traceback
from django.core.urlresolvers import reverse

# Dominion constants
BASE_WORKER_COST = 0.10
SILVER_PER_BUILDING = 225.00
FOOD_PER_FARM = 100.00
# each point in a dominion skill is a 5% bonus
BONUS_PER_SKILL_POINT = 0.05
# number of workers for a building to be at full production
SERFS_PER_BUILDING = 20.0
# population cap for housing
POP_PER_HOUSING = 1000
BASE_POP_GROWTH = 0.01
DEATHS_PER_LAWLESS = 0.0025
LAND_SIZE = 10000
LIFESTYLES = {
    0: (-100, -1000),
    1: (0, 0),
    2: (100, 2000),
    3: (200, 3000),
    4: (500, 4000),
    5: (1500, 7000),
    6: (5000, 10000),
    }

PAGEROOT = "http://play.arxgame.org"


# Create your models here.
class PlayerOrNpc(models.Model):
    """
    This is a simple model that represents that the entity can either be a PC
    or an NPC who has no presence in game, and exists only as a name in the
    database.
    """
    player = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='Dominion', blank=True, null=True)
    npc_name = models.CharField(blank=True, null=True, max_length=255)
    parents = models.ManyToManyField("self", symmetrical=False, related_name='children', blank=True)
    spouses = models.ManyToManyField("self", blank=True)
    alive = models.BooleanField(default=True, blank=True)
    patron = models.ForeignKey('self', related_name='proteges', null=True, blank=True,
                               on_delete=models.SET_NULL)
    lifestyle_rating = models.PositiveSmallIntegerField(default=1, blank=1)
    # --- Dominion skills----
    # bonus to population growth
    population = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to income sources
    income = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to harvests
    farming = models.PositiveSmallIntegerField(default=0, blank=0)
    # costs for projects/commands
    productivity = models.PositiveSmallIntegerField(default=0, blank=0)
    # upkeep costs
    upkeep = models.PositiveSmallIntegerField(default=0, blank=0)
    # loyalty mod of troops/serfs
    loyalty = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to all military combat commands
    warfare = models.PositiveSmallIntegerField(default=0, blank=0)

    def __str__(self):
        if self.player:
            name = self.player.key.capitalize()
            if not self.alive:
                name += "(RIP)"
            return name
        name = self.npc_name
        if not self.alive:
            name += "(RIP)"
        return name
    
    def _get_siblings(self):
        return PlayerOrNpc.objects.filter(Q(parents__in=self.all_parents) &
                                          ~Q(id=self.id)).distinct()

    def _parents_and_spouses(self):
        return PlayerOrNpc.objects.filter(Q(children__id=self.id) | Q(spouses__children__id=self.id)).distinct()
    all_parents = property(_parents_and_spouses)

    @property
    def grandparents(self):
        return PlayerOrNpc.objects.filter(Q(children__children=self) | Q(spouses__children__children=self) |
                                          Q(children__spouses__children=self) |
                                          Q(spouses__children__children__spouses=self) |
                                          Q(children__children__spouses=self) |
                                          Q(spouses__children__spouses__children=self)).distinct()

    @property
    def greatgrandparents(self):
        return PlayerOrNpc.objects.filter(Q(children__in=self.grandparents) | Q(spouses__children__in=self.grandparents)
                                          ).distinct()

    @property
    def second_cousins(self):
        return PlayerOrNpc.objects.filter(~Q(id=self.id) & ~Q(id__in=self.cousins) &
                                          ~Q(id__in=self.siblings)
                                          & (
                                            Q(parents__parents__parents__in=self.greatgrandparents) |
                                            Q(parents__parents__parents__spouses__in=self.greatgrandparents) |
                                            Q(parents__parents__spouses__parents__in=self.greatgrandparents) |
                                            Q(parents__spouses__parents__parents__in=self.greatgrandparents)
                                          )).distinct()

    def _get_cousins(self):
        return PlayerOrNpc.objects.filter((Q(parents__parents__in=self.grandparents) |
                                           Q(parents__parents__spouses__in=self.grandparents) |
                                           Q(parents__spouses__parents__in=self.grandparents)) & ~Q(id=self.id)
                                          & ~Q(id__in=self.siblings) & ~Q(id__in=self.spouses.all())).distinct()

    cousins = property(_get_cousins)
    siblings = property(_get_siblings)
    
    def display_immediate_family(self):
        ggparents = self.greatgrandparents
        grandparents = []
        parents = self.all_parents
        unc_or_aunts = []
        if parents:
            for parent in parents:
                grandparents += list(parent.all_parents)
                for sibling in parent.siblings:
                    unc_or_aunts.append(sibling)
                    for spouse in sibling.spouses.all():
                        unc_or_aunts.append(spouse)
            unc_or_aunts = set(unc_or_aunts)
            grandparents = set(grandparents)
        else:
            parents = ''
        spouses = self.spouses.all() or ''
        siblings = self.siblings
        neph_or_nieces = []
        if siblings:
            for sib in siblings:
                neph_or_nieces += list(sib.children.all())
            neph_or_nieces = set(neph_or_nieces)
        else:
            siblings = ''
        children = self.children.all()
        grandchildren = []
        if children:
            for child in children:
                grandchildren += list(child.children.all())
            grandchildren = set(grandchildren)
        else:
            children = ''
        cousins = self.cousins or ''
        second_cousins = self.second_cousins or ''
        if ggparents:
            ggparents = "{wGreatgrandparents{n: %s\n" % (", ".join(str(ggparent) for ggparent in ggparents))
        else:
            ggparents = ''
        if grandparents:
            grandparents = "{wGrandparents{n: %s\n" % (", ".join(str(gparent) for gparent in grandparents))
        else:
            grandparents = ''
        if parents:
            parents = "{wParents{n: %s\n" % (", ".join(str(parent) for parent in parents))
        if spouses:
            spouses = "{wSpouses{n: %s\n" % (", ".join(str(spouse) for spouse in spouses))
        if unc_or_aunts:
            unc_or_aunts = "{wUncles/Aunts{n: %s\n" % (", ".join(str(unc) for unc in unc_or_aunts))
        else:
            unc_or_aunts = ''
        if siblings:
            siblings = "{wSiblings{n: %s\n" % (", ".join(str(sib) for sib in siblings))
        if neph_or_nieces:
            neph_or_nieces = "{wNephews/Nieces{n: %s\n" % (", ".join(str(neph) for neph in neph_or_nieces))
        else:
            neph_or_nieces = ''
        if children:
            children = "{wChildren{n: %s\n" % (", ".join(str(child) for child in children))
        if grandchildren:
            grandchildren = "{wGrandchildren{n: %s\n" % (", ".join(str(gchild) for gchild in grandchildren))
        else:
            grandchildren = ''
        if cousins:
            cousins = "{wCousins{n: %s\n" % (", ".join(str(cousin) for cousin in cousins))
        if second_cousins:
            second_cousins = "{wSecond Cousins{n: %s\n" % (", ".join(str(seco) for seco in second_cousins))
        return (ggparents + grandparents + parents + unc_or_aunts + spouses + siblings
                + children + neph_or_nieces + cousins + second_cousins + grandchildren)

    def msg(self, *args, **kwargs):
        self.player.msg(*args, **kwargs)

    def gain_reputation(self, org, affection, respect):
        try:
            reputation = self.reputations.get(organization=org)
            reputation.affection += affection
            reputation.respect += respect
            reputation.save()
        except Reputation.DoesNotExist:
            self.reputations.create(organization=org, affection=affection, respect=respect)

    @property
    def current_orgs(self):
        org_ids = self.memberships.filter(deguilded=False).values_list('organization', flat=True)
        return Organization.objects.filter(id__in=org_ids)

    def pay_lifestyle(self, report=None):
        try:
            assets = self.assets
        except AttributeError:
            return False
        life_lvl = self.lifestyle_rating      
        cost = LIFESTYLES.get(life_lvl, (0, 0))[0]
        prestige = LIFESTYLES.get(life_lvl, (0, 0))[1]
        
        def pay_and_adjust(payer):
            payer.vault -= cost
            payer.save()
            assets.adjust_prestige(prestige)
            payname = "You" if payer == assets else str(payer)
            if report:
                report.lifestyle_msg = "%s paid %s for your lifestyle and you gained %s prestige.\n" % (payname, cost,
                                                                                                        prestige)
        if assets.vault > cost:
            pay_and_adjust(assets)
            return True
        orgs = [ob for ob in self.current_orgs if ob.access(self.player, 'withdraw')]
        if not orgs:
            return False
        for org in orgs:
            if org.assets.vault > cost:
                pay_and_adjust(org.assets)
                return True
        # no one could pay for us
        if report:
            report.lifestyle_msg = "You were unable to afford to pay for your lifestyle.\n"
        return False

    @property
    def support_cooldowns(self):
        if not hasattr(self, 'cached_support_cooldowns'):
            return self.calc_support_cooldowns()
        return self.cached_support_cooldowns
    
    def calc_support_cooldowns(self):
        """Calculates support used in last three weeks, builds a dictionary"""
        self.cached_support_cooldowns = {}
        cdowns = self.cached_support_cooldowns
        try:
            week = get_week()
        except Exception:
            import traceback
            traceback.print_exc()
            return cdowns
        try:
            max_support = self.player.db.char_ob.max_support
        except AttributeError:
            import traceback
            traceback.print_exc()
            return cdowns
        qs = SupportUsed.objects.select_related('supporter__task__member__player').filter(Q(supporter__player=self) &
                                                                                          Q(supporter__fake=False))

        def process_week(qset, week_offset=0):
            qset = qset.filter(week=week + week_offset)
            for used in qset:
                member = used.supporter.task.member
                pc = member.player.player.db.char_ob
                points = cdowns.get(pc.id, max_support)
                points -= used.rating
                cdowns[pc.id] = points
            if week_offset:
                for name in cdowns.keys():
                    cdowns[name] += max_support/3
                    if max_support % 3:
                        cdowns[name] += 1
                    if cdowns[name] >= max_support:
                        del cdowns[name]
        for offset in range(-3, 1):
            process_week(qs, offset)
        return cdowns

    @property
    def remaining_points(self):
        """
        Calculates how many points we've spent this week, and returns how
        many points we should have remaining.
        """
        week = get_week()
        try:
            max_support = self.player.db.char_ob.max_support
            points_spent = sum(SupportUsed.objects.filter(Q(week=week) & Q(supporter__player=self) &
                                                          Q(supporter__fake=False)).values_list('rating', flat=True))

        except (ValueError, TypeError, AttributeError):
            return 0
        return max_support - points_spent


class AssetOwner(models.Model):
    """
    This model describes the owner of an asset, such as money
    or a land resource. The owner can either be an in-game object
    and use the object_owner field, or an organization and use
    the organization_owner field. The 'owner' property will check
    for an object first, then an organization, and return None if
    it's not owned by either. An organization or character will
    access this model with object.assets, and their income will
    be adjusted on a weekly basis with object.assets.do_weekly_adjustment().
    """
    player = models.OneToOneField('PlayerOrNpc', related_name="assets", blank=True, null=True)
    organization_owner = models.OneToOneField('Organization', related_name='assets', blank=True, null=True)
    
    # money stored in the bank
    vault = models.PositiveIntegerField(default=0, blank=0)
    # prestige we've earned
    prestige = models.IntegerField(default=0, blank=0)
    # resources
    economic = models.PositiveIntegerField(default=0, blank=0)
    military = models.PositiveIntegerField(default=0, blank=0)
    social = models.PositiveIntegerField(default=0, blank=0)
       
    def _get_owner(self):
        if self.player:
            return self.player
        if self.organization_owner:
            return self.organization_owner
        return None
    owner = property(_get_owner)
    
    def __unicode__(self):
        return "%s" % self.owner

    def __repr__(self):
        return "<Owner (#%s): %s>" % (self.id, self.owner)

    def _total_prestige(self):
        if self.organization_owner:
            return self.prestige
        bonus = 0
        if self.player.patron and self.player.patron.assets:
            bonus = self.player.patron.assets.total_prestige / 10
        for member in self.player.memberships.filter(Q(deguilded=False) &
                                                     Q(secret=False) &
                                                     Q(organization__secret=False)
                                                     & Q(rank__lte=5)):
            mult = (12 - (2*member.rank))/100.0
            org = member.organization
            try:
                bonus += int(org.assets.prestige * mult)
            except AttributeError:
                print "Org %s lacks asset_owner instance!" % org
        return bonus + self.prestige
    total_prestige = property(_total_prestige)

    def adjust_prestige(self, value):
        """
        Adjusts our prestige. Returns list of all affected entities.
        """
        affected = []
        if self.organization_owner:
            self.prestige += value
            self.save()
            return [self.organization_owner]
        if self.player.patron and self.player.patron.assets:
            # transfer 5% of our prestige gained to our patron
            transfer = value/20
            value -= transfer
            self.player.patron.assets.adjust_prestige(transfer)
            affected.append(self.player.patron)
        for member in self.player.memberships.filter(secret=False, organization__secret=False, deguilded=False):
            # transfer a percentage of our prestige gained to our orgs, based on rank
            mult = (12 - member.rank)/200.0
            org = member.organization
            transfer = int(value * mult)
            org.assets.prestige += transfer
            org.assets.save()
            affected.append(org)
            value -= transfer
        affected.append(self.player)
        self.prestige += value
        self.save()
        return affected
    
    def _income(self):
        income = 0
        if hasattr(self, 'cached_income'):
            return self.cached_income
        if self.organization_owner:
            income += self.organization_owner.amount
        for amt in self.incomes.filter(do_weekly=True):
            income += amt.weekly_amount
        if not hasattr(self, 'estate'):
            return income
        for domain in self.estate.holdings.all():
            income += domain.total_income
        self.cached_income = income
        return income
    
    def _costs(self):
        costs = 0
        if hasattr(self, 'cached_costs'):
            return self.cached_costs
        for debt in self.debts.filter(do_weekly=True):
            costs += debt.weekly_amount
        if not hasattr(self, 'estate'):
            return costs
        for domain in self.estate.holdings.all():
            costs += domain.costs
        self.cached_costs = costs
        return costs
    
    def _net_income(self):
        return self.income - self.costs
    
    income = property(_income)
    net_income = property(_net_income)
    costs = property(_costs)

    @property
    def inform_target(self):
        """
        Determines who should get some sort of inform for this assetowner
        """
        player = None
        if self.player and self.player.player:
            player = self.player.player
        else:
            # if we're an organization, we see if we have a player Castellan to send reports
            if (hasattr(self, 'estate') and self.estate.castellan and self.estate.castellan.player
                and hasattr(self.estate.castellan.player, 'roster') and self.estate.castellan.player.roster.roster and
                    self.estate.castellan.player.roster.roster == "Active"):
                player = self.estate.castellan.player
            elif self.organization_owner:  # otherwise send it to the highest ranked active player
                members = self.organization_owner.members.filter(player__player__roster__roster__name="Active"
                                                                 ).order_by('rank')
                if members:
                    player = members[0].player.player
        return player
        
    def do_weekly_adjustment(self, week):
        amount = 0
        report = None
        player = self.inform_target
        if self.player and self.player.player:
            # if we're a player, send them the report
            for member in self.player.memberships.filter(deguilded=False):
                member.work_this_week = 0
                member.save()
        if player:
            report = WeeklyReport(player, week, self)
        if hasattr(self, 'estate'):
            for domain in self.estate.holdings.all():
                amount += domain.do_weekly_adjustment(week, report)
        for agent in self.agents.all():
            amount -= agent.cost
        # WeeklyTransactions
        for income in self.incomes.filter(do_weekly=True):
            amount += income.process_payment(report)
            income.post_repeat()
        if self.organization_owner:
            # record organization's income
            amount += self.organization_owner.amount
            # organization prestige decay
            self.prestige -= self.prestige/400
        else:
            # player prestige decay
            self.prestige -= self.prestige/100
        # debts that won't be processed by someone else's income, since they have no receiver
        for debt in self.debts.filter(receiver__isnull=True, do_weekly=True):
            amount -= debt.amount
        self.vault += amount
        self.save()
        if (self.player and self.player.player and hasattr(self.player.player, 'roster')
                and self.player.player.roster.roster.name == "Active"):
            self.player.pay_lifestyle(report)
        if report:
            report.record_income(self.vault, amount)
            report.send_report()
        return amount

    def display(self):
        msg = "{wName{n: %s\n" % self.owner
        msg += "{wVault{n: %s\n" % self.vault
        msg += "{wPrestige{n: %s\n" % self.total_prestige
        if hasattr(self, 'estate'):
            msg += "{wHoldings{n: %s\n" % ", ".join(str(dom) for dom in self.estate.holdings.all())
        msg += "{wAgents{n: %s\n" % ", ".join(str(agent) for agent in self.agents.all())
        return msg

    def clear_cache(self):
        if hasattr(self, 'cached_income'):
            del self.cached_income
        if hasattr(self, 'cached_costs'):
            del self.cached_costs
        
    def save(self, *args, **kwargs):
        self.clear_cache()
        super(AssetOwner, self).save(*args, **kwargs)

    def inform_owner(self, text, category=None, append=False):
        player = self.inform_target
        week = get_week()
        if player:
            player.inform(text, category=category, week=week, append=append)

    def access(self, accessing_obj, access_type='agent', default=False):
        if self.organization_owner:
            return self.organization_owner.access(accessing_obj, access_type, default)
        # it's a player, check if it's our player
        if hasattr(accessing_obj, 'character'):
            return self.player.player == accessing_obj
        # it's a character, check if it's the character of our player
        try:
            return accessing_obj.db.player_ob == self.player.player
        except AttributeError:
            return default


class AccountTransaction(models.Model):
    """
    Represents both income and costs that happen on a weekly
    basis. This is stored in those receiving the money as
    object.Dominion.assets.incomes, and the object who is sending
    the money as object.Dominion.assets.debts. During weekly adjustment,
    those who have it stored as an income have the amount added to
    their bank_amount stored in assets.money.bank_amount, and those
    have it as a debt have the same value subtracted.
    """
    receiver = models.ForeignKey('AssetOwner', related_name='incomes', blank=True, null=True)
    
    sender = models.ForeignKey('AssetOwner', related_name='debts', blank=True, null=True)
    # quick description of the type of transaction. taxes between liege/vassal, etc
    category = models.CharField(blank=True, null=True, max_length=255)
    
    weekly_amount = models.PositiveIntegerField(default=0, blank=0)

    # if this is false, this is a debt that continues to accrue
    do_weekly = models.BooleanField(default=True, blank=True)

    repetitions_left = models.SmallIntegerField(default=-1, blank=-1)

    def post_repeat(self):
        if self.repetitions_left > 0:
            self.repetitions_left -= 1
        elif self.repetitions_left < 0:
            return
        if self.repetitions_left == 0:
            self.delete()
        else:
            self.save()
    
    def _get_amount(self):
        return self.weekly_amount
    
    def __unicode__(self):
        receiver = self.receiver
        if receiver:
            receiver = receiver.owner
        sender = self.sender
        if sender:
            sender = sender.owner
        return "%s -> %s. Amount: %s" % (sender, receiver, self.weekly_amount)

    def process_payment(self, report=None):
        """
        If sender can't pay, return 0. Else, subtract their money
        and return the amount paid.
        """
        sender = self.sender
        if not sender:
            return self.weekly_amount
        if self.can_pay:
            if report:
                report.add_payment(self)
            sender.vault -= self.weekly_amount
            sender.save()
            return self.weekly_amount
        else:
            if report:
                report.payment_fail(self)
            return 0
    
    amount = property(_get_amount)
    
    @property
    def can_pay(self):
        return self.sender.vault >= self.weekly_amount

    def save(self, *args, **kwargs):
        super(AccountTransaction, self).save(*args, **kwargs)
        if self.sender:
            self.sender.clear_cache()
        if self.receiver:
            self.receiver.clear_cache()
        

class Region(models.Model):
    """
    A region of Land squares. The 'origin' x,y coordinates are by our convention
    the 'southwest' corner of the region, though builders will not be held to that
    constraint - it's just to get a feel for where each region is situated without
    precise list of their dimensions.
    """
    name = models.CharField(max_length=80, blank=True, null=True)
    # the Southwest corner of the region
    origin_x_coord = models.SmallIntegerField(default=0, blank=0)
    origin_y_coord = models.SmallIntegerField(default=0, blank=0)

    def __unicode__(self):
        return self.name or "Unnamed Region (#%s)" % self.id

    def __repr__(self):
        return "<Region: %s(#%s)>" % (self.name, self.id)
    
    
class Land(models.Model):
    """
    A Land square on the world grid. It contains coordinates of its map space,
    the type of terrain it has, and is part of a region. It can contain many
    different domains of different lords, all of which have their own economies
    and militaries. It is a 100 square mile area, with domains taking up free space
    within the square.
    """
    # region types
    COAST = 1
    DESERT = 2
    GRASSLAND = 3
    HILL = 4
    MOUNTAIN = 5
    OCEAN = 6
    PLAINS = 7
    SNOW = 8
    TUNDRA = 9
    FOREST = 10
    JUNGLE = 11
    MARSH = 12
    ARCHIPELAGO = 13
    FLOOD_PLAINS = 14
    ICE = 15
    LAKES = 16
    OASIS = 17   
    
    TERRAIN_CHOICES = (
        (COAST, 'Coast'),
        (DESERT, 'Desert'),
        (GRASSLAND, 'Grassland'),
        (HILL, 'Hill'),
        (MOUNTAIN, 'Mountain'),
        (OCEAN, 'Ocean'),
        (PLAINS, 'Plains'),
        (SNOW, 'Snow'),
        (TUNDRA, 'Tundra'),
        (FOREST, 'Forest'),
        (JUNGLE, 'Jungle'),
        (MARSH, 'Marsh'),
        (ARCHIPELAGO, 'Archipelago'),
        (FLOOD_PLAINS, 'Flood Plains'),
        (ICE, 'Ice'),
        (LAKES, 'Lakes'),
        (OASIS, 'Oasis'),
        )
    
    name = models.CharField(max_length=80, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    x_coord = models.SmallIntegerField(default=0, blank=0)
    y_coord = models.SmallIntegerField(default=0, blank=0)
    
    terrain = models.PositiveSmallIntegerField(choices=TERRAIN_CHOICES, default=PLAINS)
    
    region = models.ForeignKey('Region', on_delete=models.SET_NULL, blank=True, null=True)
    # whether we can have boats here
    landlocked = models.BooleanField(default=True, blank=True)

    def _get_farming_mod(self):
        """
        Returns an integer that is a percent modifier for farming.
        100% means no change. 0% would imply that farming fails here.
        Food production isn't strictly farming per se, but also includes
        hunting, so 0% would only be accurate if there's nothing living
        there at all that could be hunted.
        """
        min_farm = (Land.DESERT, Land.SNOW, Land.ICE)
        low_farm = (Land.TUNDRA, Land.MARSH, Land.MOUNTAIN)
        # 'farm' also refers to fishing for coast
        high_farm = (Land.COAST, Land.LAKES, Land.PLAINS, Land.GRASSLAND, Land.FLOOD_PLAINS)
        if self.terrain in min_farm:
            return 25
        if self.terrain in low_farm:
            return 50
        if self.terrain in high_farm:
            return 125
        return 100

    def _get_mining_mod(self):
        high_mine = (Land.HILL, Land.MOUNTAIN)
        if self.terrain in high_mine:
            return 125
        return 100

    def _get_lumber_mod(self):
        # may add more later. comma is necessary to make it a tuple, otherwise not iterable
        high_lumber = (Land.FOREST,)
        if self.terrain in high_lumber:
            return 125
        return 100
    farm_mod = property(_get_farming_mod)
    mine_mod = property(_get_mining_mod)
    lumber_mod = property(_get_lumber_mod)

    def _get_occupied_area(self):
        total_area = 0
        for domain in self.domains.all():
            total_area += domain.area
        return total_area
    occupied_area = property(_get_occupied_area)

    def _get_hostile_area(self):
        total_area = 0
        for hostile in self.hostiles.all():
            total_area += hostile.area
        return total_area
    hostile_area = property(_get_hostile_area)

    def _get_free_area(self):
        return LAND_SIZE - (self.occupied_area + self.hostile_area)
    free_area = property(_get_free_area)

    def __unicode__(self):
        return self.name

    def __repr__(self):
        name = self.name or "(%s, %s)" % (self.x_coord, self.y_coord)
        return "<Land (#%s): %s>" % (self.id, name)


class HostileArea(models.Model):
    """
    This is an area on a land square that isn't a domain, but is
    also considered uninhabitable. It could be because of a group
    of bandits, a massive monster, fell magic, dead and barren
    land, whatever. If we contain hostile units, then they're contained
    in the self.hostiles property.
    """
    land = models.ForeignKey('Land', related_name='hostiles', blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    from django.core.validators import MaxValueValidator
    area = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=0)
    # the type of hostiles controlling this area
    type = models.PositiveSmallIntegerField(default=0, blank=0)
    # we'll have HostileArea.units.all() to describe any military forces we have

    def _get_units(self):
        return self.units.all()
    hostiles = property(_get_units)


class Domain(models.Model):
    """
    A domain owned by a noble house that resides on a particular Land square on
    the map we'll generate. This model contains information specifically to
    the noble's holding, with all the relevant economic data. All of this is
    assumed to be their property, and its income is drawn upon as a weekly
    event. It resides in a specific Land square, but a Land square can hold
    several domains, up to a total area.

    A player may own several different domains, but each should be in a unique
    square. Conquering other domains inside the same Land square should annex
    them into a single domain.
    """    
    # 'grid' square where our domain is. More than 1 domain can be on a square
    land = models.ForeignKey('Land', on_delete=models.SET_NULL, related_name='domains', blank=True, null=True)
    # The house that rules this domain
    ruler = models.ForeignKey('Ruler', on_delete=models.SET_NULL, related_name='holdings', blank=True, null=True)
    # cosmetic info
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    title = models.CharField(blank=True, null=True, max_length=255)
    destroyed = models.BooleanField(default=False, blank=False)
    
    # how much of the territory in our land square we control
    from django.core.validators import MaxValueValidator
    area = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=0)
    
    # granaries, food for emergencies, etc
    stored_food = models.PositiveIntegerField(default=0, blank=0)
    
    # food from other sources - trade, other holdings of player, etc
    # this is currently 'in transit', and will be added to food_stored if it arrives
    shipped_food = models.PositiveIntegerField(default=0, blank=0)
    
    # percentage out of 100
    tax_rate = models.PositiveSmallIntegerField(default=10, blank=10)
    
    # our economic resources
    num_mines = models.PositiveSmallIntegerField(default=0, blank=0)
    num_lumber_yards = models.PositiveSmallIntegerField(default=0, blank=0)
    num_mills = models.PositiveSmallIntegerField(default=0, blank=0)
    num_housing = models.PositiveIntegerField(default=0, blank=0)
    num_farms = models.PositiveSmallIntegerField(default=0, blank=0)
    # workers who are not currently employed in a resource
    unassigned_serfs = models.PositiveIntegerField(default=0, blank=0)
    # what proportion of our serfs are slaves and will have no money upkeep
    slave_labor_percentage = models.PositiveSmallIntegerField(default=0, blank=0)
    # workers employed in different buildings
    mining_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    lumber_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    farming_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    mill_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    
    # causes mo' problems.
    lawlessness = models.PositiveSmallIntegerField(default=0, blank=0)
    amount_plundered = models.PositiveSmallIntegerField(default=0, blank=0)
    income_modifier = models.PositiveSmallIntegerField(default=100, blank=100)
        
    # All income sources are floats for modifier calculations. We'll convert to int at the end
    def _get_tax_income(self):
        if hasattr(self, 'cached_tax_income'):
            return self.cached_tax_income
        tax = float(self.tax_rate)/100.0
        if tax > 1.00:
            tax = 1.00
        tax *= float(self.total_serfs)
        if self.ruler:
            vassals = self.ruler.vassals.all()
            for vassal in vassals:
                try:
                    for domain in vassal.holdings.all():
                        amt = domain.liege_taxed_amt
                        tax += amt
                except (AttributeError, TypeError, ValueError):
                    pass
        self.cached_tax_income = tax       
        return tax

    @staticmethod
    def required_worker_mod(buildings, workers):
        """
        Returns what percentage (as a float between 0.0 to 100.0) we have of
        the workers needed to run these number of buildings at full strength.
        """
        req = buildings * SERFS_PER_BUILDING
        # if we have more than enough workers, we're at 100%
        if workers >= req:
            return 100.0
        # percentage of our efficiency
        return workers/req
    
    def get_resource_income(self, building, workers):
        base = SILVER_PER_BUILDING * building
        worker_req = self.required_worker_mod(building, workers)
        return base * worker_req             
        
    def _get_mining_income(self):
        base = self.get_resource_income(self.num_mines, self.mining_serfs)
        if self.land:
            base = (base * self.land.mine_mod)/100.0
        return base
        
    def _get_lumber_income(self):
        base = self.get_resource_income(self.num_lumber_yards, self.lumber_serfs)
        if self.land:
            base = (base * self.land.lumber_mod)/100.0
        return base

    def _get_mill_income(self):
        base = self.get_resource_income(self.num_mills, self.mill_serfs)
        return base
    
    def _get_total_income(self):
        """
        Returns our total income after all modifiers. All income sources are
        floats, which we'll convert to an int once we're all done.
        """
        if hasattr(self, 'cached_total_income'):
            return self.cached_total_income
        amount = self.tax_income
        amount += self.mining_income
        amount += self.lumber_income
        amount += self.mill_income
        amount = (amount * self.income_modifier)/100.0
        if self.ruler and self.ruler.castellan:
            bonus = (self.ruler.castellan.income * BONUS_PER_SKILL_POINT) * amount
            amount += bonus
        self.cached_total_income = int(amount)
        # we'll dump the remainder
        return int(amount)
    
    def _get_liege_tax(self):
        if not self.ruler:
            return 0
        if not self.ruler.liege:
            return 0
        if self.ruler.liege.holdings.all():
            return self.ruler.liege.holdings.all()[0].tax_rate
        return 0
    
    def worker_cost(self, number):
        """
        Cost of workers, reduced if they are slaves
        """
        if self.slave_labor_percentage > 99:
            return 0
        cost = BASE_WORKER_COST * number
        cost *= (100 - self.slave_labor_percentage)/100
        if self.ruler and self.ruler.castellan:
            # every point in upkeep skill is 5% discount to costs
            reduction = (self.ruler.castellan.upkeep * BONUS_PER_SKILL_POINT) * cost
            cost -= reduction
        return int(cost)
        
    def _get_costs(self):
        """
        Costs/upkeep for all of our production.
        """
        if hasattr(self, 'cached_total_costs'):
            return self.cached_total_costs
        costs = 0
        for army in self.armies.all():
            costs += army.costs
        costs += self.worker_cost(self.mining_serfs)
        costs += self.worker_cost(self.lumber_serfs)
        costs += self.worker_cost(self.mill_serfs)
        costs += self.amount_plundered
        costs += self.liege_taxed_amt
        self.cached_total_costs = costs
        return costs

    def _get_liege_taxed_amt(self):
        return (self.total_income * self.liege_taxes)/100
    
    def _get_food_production(self):
        """
        How much food the region produces.
        """
        mod = self.required_worker_mod(self.num_farms, self.farming_serfs)
        amount = (self.num_farms * FOOD_PER_FARM) * mod
        if self.ruler and self.ruler.castellan:
            bonus = (self.ruler.castellan.farming * BONUS_PER_SKILL_POINT) * amount
            amount += bonus
        return int(amount)
    
    def _get_food_consumption(self):
        """
        How much food the region consumes from workers. Armies/garrisons will
        draw upon stored food during do_weekly_adjustment.
        """
        return self.total_serfs
    
    def _get_max_pop(self):
        """
        Maximum population.
        """
        return self.num_housing * POP_PER_HOUSING
    
    def _get_employed_serfs(self):
        """
        How many serfs are currently working on a field.
        """
        return self.mill_serfs + self.mining_serfs + self.farming_serfs + self.lumber_serfs

    def _get_total_serfs(self):
        """
        Total of all serfs
        """
        return self.employed + self.unassigned_serfs
    
    def kill_serfs(self, deaths, serf_type=None):
        """
        Whenever we lose serfs, we need to lose some that are employed in some field.
        If serf_type is specified, then we kill serfs who are either 'farming' serfs,
        'mining' serfs, 'mill' serfs, or 'lumber' sefs. Otherwise, we kill whichever
        field has the most employed.
        """
        if serf_type == "farming":
            worker_type = "farming_serfs"
        elif serf_type == "mining":
            worker_type = "mining_serfs"
        elif serf_type == "mill":
            worker_type = "mill_serfs"
        elif serf_type == "lumber":
            worker_type = "lumber_serfs"
        else:
            # if we have more deaths than unemployed serfs
            more_deaths = deaths - self.unassigned_serfs
            if more_deaths < 1:  # only unemployed die
                self.unassigned_serfs -= deaths
                self.save()
                return
            # gotta kill more
            worker_types = ["farming_serfs", "mining_serfs", "mill_serfs", "lumber_serfs"]
            # sort it from most to least
            worker_types.sort(key=lambda x: getattr(self, x), reverse=True)
            worker_type = worker_types[0]
            # now we'll kill the remainder after killing unemployed above
            self.unassigned_serfs = 0
            deaths = more_deaths
        num_workers = getattr(self, worker_type, 0)
        if num_workers:
            num_workers -= deaths
        if num_workers < 0:
            num_workers = 0
        setattr(self, worker_type, num_workers)
        self.save()

    def plundered_by(self, army, week):
        """
        An army has successfully pillaged us. Determine the economic impact.
        """
        print "%s plundered during week %s" % (self, week)
        max_pillage = army.size/10
        pillage = self.total_income
        if pillage > max_pillage:
            pillage = max_pillage
        self.amount_plundered = pillage
        self.lawlessness += 10
        self.save()
        return pillage
    
    def annex(self, target, week, army):
        """
        Absorbs the target domain into this one. We'll take all buildings/serfs
        from the target, then delete old domain.
        """
        # add stuff from target domain to us
        self.area += target.area
        self.stored_food += target.stored_food
        self.unassigned_serfs += target.unassigned_serfs
        self.mill_serfs += target.mill_serfs
        self.lumber_serfs += target.lumber_serfs
        self.mining_serfs += target.mining_serfs
        self.farming_serfs += target.farming_serfs
        self.num_farms += target.num_farms
        self.num_housing += target.num_housing
        self.num_lumber_yards += target.num_lumber_yards
        self.num_mills += target.num_mills
        self.num_mines += target.num_mines
        for castle in target.castles.all():
            castle.domain = self
            castle.save()
        # now get rid of annexed domain and save changes
        target.fake_delete()
        self.save()
        army.domain = self
        army.save()
        print "%s annexed during week %s" % (self, week)

    def fake_delete(self):
        """
        Makes us an inactive domain without a presence in the world, but kept for
        historical reasons (such as description/name).
        """
        self.destroyed = True
        self.area = 0
        self.stored_food = 0
        self.unassigned_serfs = 0
        self.mill_serfs = 0
        self.lumber_serfs = 0
        self.mining_serfs = 0
        self.farming_serfs = 0
        self.num_farms = 0
        self.num_housing = 0
        self.num_lumber_yards = 0
        self.num_mills = 0
        self.num_mines = 0
        self.castles.clear()
        self.armies.clear()
        self.save()

    def adjust_population(self):
        """
        Increase or decrease population based on our housing and lawlessness.
        """
        base_growth = (BASE_POP_GROWTH * self.total_serfs) + 1
        deaths = 0
        # if we have no food or no room, population cannot grow
        if self.stored_food <= 0 or self.total_serfs >= self.max_pop:
            base_growth = 0
        else:  # bonuses for growth
            # bonus for having a lot of room to grow
            bonus = float(self.max_pop)/self.total_serfs
            if self.ruler and self.ruler.castellan:
                bonus += bonus * (self.ruler.castellan.population * BONUS_PER_SKILL_POINT)
            bonus = int(bonus) + 1
            base_growth += bonus
        if self.lawlessness > 0:
            # at 100% lawlessness, we have a 5% death rate per week
            deaths = (self.lawlessness * DEATHS_PER_LAWLESS) * self.total_serfs
            deaths = int(deaths) + 1
        adjustment = base_growth - deaths
        if adjustment < 0:
            self.kill_serfs(adjustment)
        else:
            self.unassigned_serfs += adjustment
    
    food_production = property(_get_food_production)
    food_consumption = property(_get_food_consumption)
    costs = property(_get_costs)
    tax_income = property(_get_tax_income)
    mining_income = property(_get_mining_income)
    lumber_income = property(_get_lumber_income)
    mill_income = property(_get_mill_income)
    total_income = property(_get_total_income)
    max_pop = property(_get_max_pop)
    employed = property(_get_employed_serfs)
    total_serfs = property(_get_total_serfs)
    liege_taxes = property(_get_liege_tax)
    liege_taxed_amt = property(_get_liege_taxed_amt)
    
    def __unicode__(self):
        return "%s (#%s)" % (self.name or 'Unnamed Domain', self.id)
    
    def __repr__(self):
        return "<Domain (#%s): %s>" % (self.id, self.name or 'Unnamed')
    
    def do_weekly_adjustment(self, week, report=None):
        """
        Determine how much money we're passing up to the ruler of our domain. Make
        all the people and armies of this domain eat their food for the week. Bad
        things will happen if they don't have enough food.
        """
        self.stored_food += self.food_production
        self.stored_food += self.shipped_food
        hunger = self.food_consumption - self.stored_food
        loot = 0
        if hunger > 0:
            self.stored_food = 0
            self.lawlessness += 5
            # unless we have a very large population, we'll only lose 1 serf as a penalty
            lost_serfs = hunger/100 + 1
            self.kill_serfs(lost_serfs)
        else:  # hunger is negative, we have enough food for it
            self.stored_food += hunger
        for army in self.armies.all():
            army.do_weekly_adjustment(week, report)
            if army.plunder:
                loot += army.plunder
                army.plunder = 0
                army.save()
        self.adjust_population()
        for project in list(self.projects.all()):
            project.advance_project(report)
        total_amount = (self.total_income + loot) - self.costs
        # reset the amount of money that's been plundered from us
        self.amount_plundered = 0
        self.save()
        return total_amount
    
    def display(self):
        castellan = None
        liege = "Crownsworn"
        if self.ruler:
            castellan = self.ruler.castellan
            liege = self.ruler.liege
        mssg = "{wDomain{n: %s\n" % self.name
        mssg += "{wLand{n: %s\n" % self.land
        mssg += "{wHouse{n: %s\n" % str(self.ruler)
        mssg += "{wLiege{n: %s\n" % str(liege)
        mssg += "{wRuler{n: %s\n" % castellan
        mssg += "{wDesc{n: %s\n" % self.desc
        mssg += "{wArea{n: %s {wFarms{n: %s {wHousing{n: %s " % (self.area, self.num_farms, self.num_housing)
        mssg += "{wMines{n: %s {wLumber{n: %s {wMills{n: %s\n" % (self.num_mines, self.num_lumber_yards, self.num_mills)
        mssg += "{wTotal serfs{n: %s " % self.total_serfs
        mssg += "{wAssignments: Mines{n: %s {wMills{n: %s " % (self.mining_serfs, self.mill_serfs)
        mssg += "{wLumber yards:{n %s {wFarms{n: %s\n" % (self.lumber_serfs, self.farming_serfs)
        mssg += "{wTax Rate{n: %s {wLawlessness{n: %s " % (self.tax_rate, self.lawlessness)
        mssg += "{wCosts{n: %s {wIncome{n: %s {wLiege's tax rate{n: %s\n" % (self.costs, self.total_income,
                                                                             self.liege_taxes)
        mssg += "{wFood Production{n: %s {wFood Consumption{n: %s {wStored Food{n: %s\n" % (self.food_production,
                                                                                            self.food_consumption,
                                                                                            self.stored_food)
        mssg += "\n{wCastles:{n\n"
        mssg += "{w================================={n\n"
        for castle in self.castles.all():
            mssg += castle.display()
        mssg += "\n{wArmies:{n\n"
        mssg += "{w================================={n\n"
        for army in self.armies.all():
            mssg += army.display()
        return mssg

    def wipe_cached_data(self):
        if hasattr(self, 'cached_total_costs'):
            del self.cached_total_costs
        if hasattr(self, 'cached_tax_income'):
            del self.cached_tax_income
        if hasattr(self, 'cached_total_income'):
            del self.cached_total_income
        try:
            self.ruler.house.clear_cache()
        except (AttributeError, ValueError, TypeError):
            pass

    def save(self, *args, **kwargs):
        super(Domain, self).save(*args, **kwargs)
        self.wipe_cached_data()


class DomainProject(models.Model):
    """
    Construction projects with a domain. In general, each should take a week,
    but may come up with ones that would take more.
    """
    # project types
    BUILD_HOUSING = 1
    BUILD_FARMS = 2
    BUILD_MINES = 3
    BUILD_MILLS = 4
    BUILD_DEFENSES = 5
    BUILD_SIEGE_WEAPONS = 6
    MUSTER_TROOPS = 7
    BUILD_TROOP_EQUIPMENT = 9

    PROJECT_CHOICES = ((BUILD_HOUSING, 'Build Housing'),
                       (BUILD_FARMS, 'Build Farms'),
                       (BUILD_MINES, 'Build Mines'),
                       (BUILD_MILLS, 'Build Mills'),
                       (BUILD_DEFENSES, 'Build Defenses'),
                       (BUILD_SIEGE_WEAPONS, 'Build Siege Weapons'),
                       (MUSTER_TROOPS, 'Muster Troops'),
                       (BUILD_TROOP_EQUIPMENT, 'Build Troop Equipment'),)
    
    type = models.PositiveSmallIntegerField(choices=PROJECT_CHOICES, default=BUILD_HOUSING)
    amount = models.PositiveSmallIntegerField(blank=1, default=1)
    unit_type = models.PositiveSmallIntegerField(default=1, blank=1)
    time_remaining = models.PositiveIntegerField(default=1, blank=1)
    domain = models.ForeignKey("Domain", related_name="projects", blank=True, null=True)
    castle = models.ForeignKey("Castle", related_name="projects", blank=True, null=True)
    military = models.ForeignKey("Army", related_name="projects", blank=True, null=True)
    unit = models.ForeignKey("MilitaryUnit", related_name="projects", blank=True, null=True)
    
    def advance_project(self, report=None, increment=1):
        self.time_remaining -= increment
        if self.time_remaining < 1:
            self.finish_project(report)
        self.save()

    def finish_project(self, report=None):
        """
        Does whatever the project set out to do. For muster troops, we'll need to first
        determine if the unit type we're training more of already exists in the army.
        If so, we add to the value, and if not, we create a new unit.
        """
        if self.type == self.BUILD_HOUSING:
            self.domain.num_housing += self.amount
        if self.type == self.BUILD_FARMS:
            self.domain.num_farms += self.amount
        if self.type == self.BUILD_MINES:
            self.domain.num_mines += self.amount
        if self.type == self.BUILD_MILLS:
            self.domain.num_mills += self.amount
        if self.type < self.BUILD_DEFENSES:
            self.domain.save()
        if self.type == self.BUILD_DEFENSES:
            self.castle.level += self.amount
            self.castle.save()
        if self.type == self.MUSTER_TROOPS:
            existing_unit = self.military.find_unit(self.unit_type)
            if existing_unit:
                existing_unit.adjust_readiness(self.amount)
                existing_unit.quantity += self.amount
                existing_unit.save()
            else:
                self.military.units.create(unit_type=self.unit_type, quantity=self.amount)
        if self.type == self.TRAIN_TROOPS:
            self.unit.train(self.amount)
        if self.type == self.BUILD_TROOP_EQUIPMENT:
            self.unit.equipment += self.amount
            self.unit.save()
        if report:
            # add a copy of this project's data to the report
            report.add_project_report(self)
        # we're all done. goodbye, cruel world
        self.delete()


class Castle(models.Model):
    """
    Castles within a given domain. Although typically we would only have one,
    it's possible a player might have more than one in a Land square by annexing
    multiple domains within a square. Castles will have a defense level that augments
    the strength of any garrison.

    Currently, castles have no upkeep costs. Any costs for their garrison is paid
    by the domain that owns that army.
    """
    MOTTE_AND_BAILEY = 1
    TIMBER_CASTLE = 2
    STONE_CASTLE = 3
    CASTLE_WITH_CURTAIN_WALL = 4
    FORTIFIED_CASTLE = 5
    EPIC_CASTLE = 6
    
    FORTIFICATION_CHOICES = (
        (MOTTE_AND_BAILEY, 'Motte and Bailey'),
        (TIMBER_CASTLE, 'Timber Castle'),
        (STONE_CASTLE, 'Stone Castle'),
        (CASTLE_WITH_CURTAIN_WALL, 'Castle with Curtain Wall'),
        (FORTIFIED_CASTLE, 'Fortified Castle'),
        (EPIC_CASTLE, 'Epic Castle'))
    level = models.PositiveSmallIntegerField(default=MOTTE_AND_BAILEY)
    domain = models.ForeignKey("Domain", related_name="castles", blank=True, null=True)
    damage = models.PositiveSmallIntegerField(default=0, blank=0)
    # cosmetic info:
    name = models.CharField(null=True, blank=True, max_length=80)
    desc = models.TextField(null=True, blank=True)

    def display(self):
        msg = "{wName{n: %s {wLevel{n: %s (%s)\n" % (self.name, self.level, self.get_level_display())
        msg += "{wDescription{n: %s\n" % self.desc
        return msg

    def get_level_display(self):
        """
        Although we have FORTIFICATION_CHOICES defined, we're not actually using
        'choices' for the level field, because we don't want to have a maximum
        set for castle.level. So we're going to override the display method
        that choices normally adds in order to return the string value for the
        maximum for anything over that threshold value.
        """
        for choice in self.FORTIFICATION_CHOICES:
            if self.level == choice[0]:
                return choice[1]
        # if level is too high, return the last element in choices
        return self.FORTIFICATION_CHOICES[-1][1]

    def __unicode__(self):
        return "%s (#%s)" % (self.name or "Unnamed Castle", self.id)

    def __repr__(self):
        return "<Castle (#%s): %s>" % (self.id, self.name)


class Minister(models.Model):
    """
    A minister appointed to assist a ruler in a category.
    """
    POP = 0
    INCOME = 1
    FARMING = 2
    PRODUCTIVITY = 3
    UPKEEP = 4
    LOYALTY = 5
    WARFARE = 6
    MINISTER_TYPES = (
        (POP, 'Population'),
        (INCOME, 'Income'),
        (FARMING, 'Farming'),
        (PRODUCTIVITY, 'Productivity'),
        (UPKEEP, 'Upkeep'),
        (LOYALTY, 'Loyalty'),
        (WARFARE, 'Warfare'),
        )
    title = models.CharField(blank=True, null=True, max_length=255)
    player = models.ForeignKey("PlayerOrNpc", related_name="appointments", blank=True, null=True)
    ruler = models.ForeignKey("Ruler", related_name="ministers", blank=True, null=True)
    category = models.PositiveSmallIntegerField(choices=MINISTER_TYPES, default=INCOME)


class Ruler(models.Model):
    """
    This represents the ruling house/entity that controls a domain, along
    with the liege/vassal relationships. The Castellan is a PcOrNpc object
    that may be the ruler of the domain or someone they appointed in their
    place - in either case, they use the skills for governing. The house
    is the AssetOwner that actually owns the domain and gets the incomes
    from it - it's assumed to be an Organization. liege is how we establish
    the liege/vassal relationships between ruler objects.
    """
    # the person who's skills are used to govern the domain
    castellan = models.OneToOneField("PlayerOrNpc", blank=True, null=True)
    # the house that owns the domain
    house = models.OneToOneField("AssetOwner", on_delete=models.SET_NULL, related_name="estate", blank=True, null=True)
    # a ruler object that this object owes its alliegance to    
    liege = models.ForeignKey("self", on_delete=models.SET_NULL, related_name="vassals", blank=True, null=True)

    def _get_titles(self):
        return ", ".join(domain.title for domain in self.domains.all())
    titles = property(_get_titles)

    def __unicode__(self):
        if self.house:
            return str(self.house.owner)
        return str(self.castellan) or "Undefined Ruler (#%s)" % self.id

    def __repr__(self):
        if self.house:
            owner = self.house.owner
        else:
            owner = self.castellan
        return "<Ruler (#%s): %s>" % (self.id, owner)


class Crisis(models.Model):
    """
    A crisis affecting organizations
    """
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    orgs = models.ManyToManyField('Organization', related_name='crises', blank=True)
    parent_crisis = models.ForeignKey('self', related_name="child_crises", blank=True, null=True,
                                      on_delete=models.SET_NULL)
    escalation_points = models.SmallIntegerField(default=0, blank=0)
    results = models.TextField(blank=True, null=True)
    modifiers = models.TextField(blank=True, null=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Crises"


class OrgRelationship(models.Model):
    """
    The relationship between two or more organizations.
    """
    orgs = models.ManyToManyField('Organization', related_name='relationships', blank=True)
    status = models.SmallIntegerField(default=0, blank=0)


class Reputation(models.Model):
    """
    A player's reputation to an organization.
    """
    player = models.ForeignKey('PlayerOrNpc', related_name='reputations', blank=True, null=True)
    organization = models.ForeignKey('Organization', related_name='reputations', blank=True, null=True)
    # negative affection is dislike/hatred
    affection = models.IntegerField(default=0, blank=0)
    # positive respect is respect/fear, negative is contempt/dismissal
    respect = models.IntegerField(default=0, blank=0)
 

class Organization(models.Model):
    """
    An in-game entity, which may contain both player characters and
    non-player characters, the latter possibly not existing outside
    of the Dominion system. For purposes of the economy, an organization
    can substitute for an object as an asset holder. This allows them to
    have their own money, incomes, debts, etc.
    """
    name = models.CharField(blank=True, null=True, max_length=255)
    desc = models.TextField(blank=True, null=True)
    category = models.CharField(blank=True, null=True, default="noble", max_length=255)
    # In a RP game, titles are IMPORTANT. And we need to divide them by gender.
    rank_1_male = models.CharField(default="Prince", blank=True, null=True, max_length=255)
    rank_1_female = models.CharField(default="Princess", blank=True, null=True, max_length=255)
    rank_2_male = models.CharField(default="Voice", blank=True, null=True, max_length=255)
    rank_2_female = models.CharField(default="Voice", blank=True, null=True, max_length=255)
    rank_3_male = models.CharField(default="Noble Family", blank=True, null=True, max_length=255)
    rank_3_female = models.CharField(default="Noble Family", blank=True, null=True, max_length=255)
    rank_4_male = models.CharField(default="Trusted House Servants", blank=True, null=True, max_length=255)
    rank_4_female = models.CharField(default="Trusted House Servants", blank=True, null=True, max_length=255)
    rank_5_male = models.CharField(default="Noble Vassals", blank=True, null=True, max_length=255)
    rank_5_female = models.CharField(default="Noble Vassals", blank=True, null=True, max_length=255)
    rank_6_male = models.CharField(default="Vassals of Esteem", blank=True, null=True, max_length=255)
    rank_6_female = models.CharField(default="Vassals of Esteem", blank=True, null=True, max_length=255)
    rank_7_male = models.CharField(default="Known Commoners", blank=True, null=True, max_length=255)
    rank_7_female = models.CharField(default="Known Commoners", blank=True, null=True, max_length=255)
    rank_8_male = models.CharField(default="Sworn Commoners", blank=True, null=True, max_length=255)
    rank_8_female = models.CharField(default="Sworn Commoners", blank=True, null=True, max_length=255)
    rank_9_male = models.CharField(default="Forgotten Commoners", blank=True, null=True, max_length=255)
    rank_9_female = models.CharField(default="Forgotten Commoners", blank=True, null=True, max_length=255)
    rank_10_male = models.CharField(default="Serf", blank=True, null=True, max_length=255)
    rank_10_female = models.CharField(default="Serf", blank=True, null=True, max_length=255)
    npc_members = models.PositiveIntegerField(default=0, blank=0)
    income_per_npc = models.PositiveSmallIntegerField(default=0, blank=0)
    cost_per_npc = models.PositiveSmallIntegerField(default=0, blank=0)
    morale = models.PositiveSmallIntegerField(default=100, blank=100)
    # this is used to represent temporary windfalls or crises that must be resolved 
    income_modifier = models.PositiveSmallIntegerField(default=100, blank=100)
    # whether players can use the @work command
    allow_work = models.BooleanField(default=False, blank=False)
    # whether we can be publicly viewed
    secret = models.BooleanField(default=False, blank=False)
    # lockstring
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    special_modifiers = models.TextField(blank=True, null=True)
    motd = models.TextField(blank=True, null=True)
    # used for when resource gain
    economic_modifier = models.SmallIntegerField(default=0, blank=0)
    military_modifier = models.SmallIntegerField(default=0, blank=0)
    social_modifier = models.SmallIntegerField(default=0, blank=0)
    base_support_value = models.SmallIntegerField(default=5, blank=5)
    member_support_multiplier = models.SmallIntegerField(default=5, blank=5)
    
    def _get_npc_money(self):
        npc_income = self.npc_members * self.income_per_npc
        npc_income = (npc_income * self.income_modifier)/100.0
        npc_cost = self.npc_members * self.cost_per_npc
        return int(npc_income) - npc_cost
    amount = property(_get_npc_money)

    def __str__(self):
        return self.name or "Unnamed organization (#%s" % self.id

    def __unicode__(self):
        return self.name or "Unnamed organization (#%s)" % self.id

    def __repr__(self):
        return "<Org (#%s): %s>" % (self.id, self.name)
    
    def display_members(self, start=1, end=10, viewing_member=None):
        pcs = self.all_members
        active = self.active_members
        if viewing_member:
            # exclude any secret members that are higher in rank than viewing member
            pcs = pcs.exclude(Q(secret=True) & Q(rank__lte=viewing_member.rank) &
                              ~Q(id=viewing_member.id))
            
        msg = ""
        for rank in range(start, end+1):
            chars = pcs.filter(rank=rank)
            male_title = getattr(self, 'rank_%s_male' % rank)
            female_title = getattr(self, 'rank_%s_female' % rank)
            if male_title == female_title:
                title = male_title
            else:
                title = "%s/%s" % (male_title.capitalize(), female_title.capitalize())
            if len(chars) > 1:
                msg += "{w%s{n (Rank %s): %s\n" % (title, rank,
                                                   ", ".join(str(char) if char in active
                                                             else "(R)%s" % char for char in chars))
            elif len(chars) > 0:
                char = chars[0]
                name = str(char) if char in active else "(R)%s" % char
                char = char.player.player.db.char_ob
                gender = char.db.gender or "Male"
                if gender.lower() == "male":
                    title = male_title
                else:
                    title = female_title

                msg += "{w%s{n (Rank %s): %s\n" % (title, rank, name)
        return msg
    
    def display_public(self):
        msg = "\n{wName{n: %s\n" % self.name
        msg += "{wDesc{n: %s\n" % self.desc
        if not self.secret:
            msg += "\n{wLeaders of %s:\n%s\n" % (self.name, self.display_members(end=2))
        webpage = PAGEROOT + self.get_absolute_url()
        msg += "{wWebpage{n: %s\n" % webpage
        return msg
    
    def display(self, viewing_member=None):
        if hasattr(self, 'assets'):
            money = self.assets.vault
            prestige = self.assets.prestige
            if hasattr(self.assets, 'estate'):
                holdings = self.assets.estate.holdings.all()
            else:
                holdings = []
        else:
            money = 0
            prestige = 0
            holdings = []
        msg = self.display_public()
        if self.secret:
            # if we're secret, we display the leaders only to members. And then
            # only if they're not marked secret themselves
            start = 1
        else:
            start = 3
        members = self.display_members(start=start, end=10, viewing_member=viewing_member)
        if members:
            members = "{wMembers of %s:\n%s" % (self.name, members)
        msg += members
        msg += "\n{wMoney{n: %s\n" % money
        msg += "\n{wPrestige{n: %s\n" % prestige
        msg += "\n{wEconomic Mod:{n %s, {wMilitary Mod:{n %s, {wSocial Mod:{n %s\n" % (self.economic_modifier,
                                                                                       self.military_modifier,
                                                                                       self.social_modifier)
        msg += "{wSpheres of Influence:{n %s\n" % ", ".join("{w%s{n: %s" % (ob.category, ob.rating)
                                                            for ob in self.spheres.all())
        if holdings:
            msg += "{wHoldings{n: %s\n" % ", ".join(ob.name for ob in holdings)
        if viewing_member:
            msg += "\n{wMember stats for {c%s{n\n" % viewing_member
            msg += viewing_member.display()
        return msg
    
    def __init__(self, *args, **kwargs):
        super(Organization, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    def access(self, accessing_obj, access_type='read', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)
    
    def msg(self, message, *args, **kwargs):
        pcs = self.active_members
        for pc in pcs:
            pc.msg("%s organization-wide message: %s" % (self.name, message), *args, **kwargs)
        return
    
    @property
    def active_members(self):
        return self.members.filter(Q(player__player__roster__roster__name="Active") & Q(deguilded=False)).distinct()
    
    @property
    def all_members(self):
        return self.members.filter(deguilded=False)

    @property
    def support_pool(self):
        return self.base_support_value + (self.active_members.count()) * self.member_support_multiplier

    def save(self, *args, **kwargs):
        super(Organization, self).save(*args, **kwargs)
        try:
            self.assets.clear_cache()
        except (AttributeError, ValueError, TypeError):
            pass

    def get_absolute_url(self):
        return reverse('help_topics:display_org', kwargs={'object_id': self.id})


class Agent(models.Model):
    """
    Types of npcs that can be employed by a player or an organization. The
    Agent instance represents a class of npc - whether it's a group of spies,
    armed guards, hired assassins, a pet dragon, whatever. Type is an integer
    that will be defined elsewhere in an agent file. ObjectDB points to Agent
    as a foreignkey, and we access that set through self.agent_objects. 
    """
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    cost_per_guard = models.PositiveSmallIntegerField(default=0, blank=0)
    # unassigned agents
    quantity = models.PositiveIntegerField(default=0, blank=0)
    # level of our agents
    quality = models.PositiveSmallIntegerField(default=0, blank=0)
    # numerical type of our agents. 0==regular guards, 1==spies, etc
    type = models.PositiveSmallIntegerField(default=0, blank=0)
    # assetowner, so either a player or an organization
    owner = models.ForeignKey("AssetOwner", on_delete=models.SET_NULL, related_name="agents", blank=True, null=True)
    secret = models.BooleanField(default=False, blank=False)
    # if this class of Agent is a unique individual, and as such the quantity cannot be more than 1
    unique = models.BooleanField(default=False, blank=False)
    xp = models.PositiveSmallIntegerField(default=0, blank=0)
    modifiers = models.TextField(blank=True, null=True)
    loyalty = models.PositiveSmallIntegerField(default=100, blank=100)
    
    def _get_cost(self):
        return self.cost_per_guard * self.quantity
    cost = property(_get_cost)

    def _get_type_name(self):
        return self.npcs.get_type_name(self.type)
    typename = property(_get_type_name)

    # total of all agent obs + our reserve quantity
    def _get_total_num(self):
        return self.quantity + sum(self.agent_objects.values_list("quantity", flat=True))
    total = property(_get_total_num)

    def _get_active(self):
        return self.agent_objects.filter(quantity__gte=1)
    active = property(_get_active)

    def __unicode__(self):
        name = self.name or self.typename
        if self.unique or self.quantity == 1:
            return name
        return "%s %s" % (self.quantity, self.name)

    def __repr__(self):
        return "<Agent (#%s): %s>" % (self.id, self.name)

    def display(self, show_assignments=True):
        msg = "\n\n{wID{n: %s {wName{n: %s {wType:{n %s" % (
            self.id, self.name, self.typename)
        if not self.unique:
            msg += " {wUnassigned:{n %s\n" % self.quantity
        else:
            msg += "  {wXP:{n %s {wLoyalty{n: %s\n" % (self.xp, self.loyalty)
        if not show_assignments:
            return msg
        for agent in self.agent_objects.all():
            msg += agent.display()
        return msg

    def assign(self, targ, num):
        """
        Assigns num agents to target character object.
        """
        if num > self.quantity:
            raise ValueError("Agent only has %s to assign, asked for %s." % (self.quantity, num))
        self.npcs.assign(targ, num)

    def find_assigned(self, player):
        """
        Asks our agenthandler to find the AgentOb with a dbobj assigned
        to guard the given character. Returns the first match, returns None
        if not found.
        """
        return self.npcs.find_agentob_by_character(player.db.char_ob)

    @property
    def dbobj(self):
        """Return dbobj of an agent_ob when we are unique"""
        agentob = self.agent_objects.get(dbobj__isnull=False)
        return agentob.dbobj

    @property
    def buyable_abilities(self):
        try:
            return self.dbobj.buyable_abilities
        except AttributeError:
            return []

    def __init__(self, *args, **kwargs):
        super(Agent, self).__init__(*args, **kwargs)
        self.npcs = AgentHandler(self)

    def access(self, accessing_obj, access_type='agent', default=False):
        return self.owner.access(accessing_obj, access_type, default)

    def get_stat_cost(self, attr):
        return self.dbobj.get_stat_cost(attr)
    
    def get_skill_cost(self, attr):
        return self.dbobj.get_skill_cost(attr)

    def get_ability_cost(self, attr):
        return self.dbobj.get_ability_cost(attr)

    def get_attr_maximum(self, attr, category):
        if category == "level":
            if self.typename in attr:
                attr_max = 6
            else:
                attr_max = self.quality - 1
        elif category == "armor":
            attr_max = (self.quality * 15) + 10
        elif category == "stat":
            attr_max = self.dbobj.get_stat_maximum(attr)
        elif category == "skill":
            attr_max = self.dbobj.get_skill_maximum(attr)
        elif category == "ability":
            attr_max = self.dbobj.get_ability_maximum(attr)
        elif category == "weapon":
            if attr == 'weapon_damage':
                attr_max = (self.quality + 2) * 2
            elif attr == 'difficulty_mod':
                attr_max = (self.quality + 1) * 2
            else:
                raise ValueError("Undefined weapon attribute")
        else:
            raise ValueError("Undefined category")
        return attr_max


class AgentMission(models.Model):
    """
    Missions that AgentObs go on.
    """
    agentob = models.ForeignKey("AgentOb", related_name="missions", blank=True, null=True)
    active = models.BooleanField(default=True, blank=True)
    success_level = models.SmallIntegerField(default=0, blank=0)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(blank=True, null=True, max_length=80)
    mission_details = models.TextField(blank=True, null=True)
    results = models.TextField(blank=True, null=True)


class AgentOb(models.Model):
    """
    Allotment from an Agent class that has a representation in-game.
    """
    agent_class = models.ForeignKey("Agent", related_name="agent_objects", blank=True, null=True)
    dbobj = models.OneToOneField("objects.ObjectDB", blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0, blank=0)
    # whether they're imprisoned, by whom, difficulty to free them, etc
    status_notes = models.TextField(blank=True, null=True)
    
    def recall(self, num):
        """
        We try to pull out X number of agents from our dbobj. If it doesn't
        have enough, it returns the number it was able to get. It also calls
        unassign if it runs out of troops.
        """
        num = self.dbobj.lose_agents(num)
        self.agent_class.quantity += num
        self.agent_class.save()
        return num
            
    def unassign(self):
        """
        Called from our associated dbobj, already having done the work to
        disassociate the npc from whoever it was guarding. This just cleans
        up AgentOb and returns our agents to the agent class.
        """
        self.agent_class.quantity += self.quantity
        self.quantity = 0
        self.save()

    def reinforce(self, num):
        """
        Increase our troops by num.
        """
        if num < 0:
            raise ValueError("Must pass a positive number to reinforce.")
        self.quantity += num
        self.dbobj.gain_agents(num)
        self.save()
        return num

    def display(self):
        if not self.quantity:
            return ""
        return self.dbobj.display()

    def lose_agents(self, num):
        self.quantity -= num
        if self.quantity < 0:
            self.quantity = 0
        self.save()

    def access(self, accessing_obj, access_type='agent', default=False):
        return self.agent_class.access(accessing_obj, access_type, default)


class Army(models.Model):
    """
    Any collection of military units belonging to a given domain.
    """
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    # the domain that we obey the orders of. Not the same as who owns us, necessarily
    domain = models.ForeignKey("Domain", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True)
    # current location of this army
    land = models.ForeignKey("Land", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True)
    # if the army is located as a castle garrison
    castle = models.ForeignKey("Castle", on_delete=models.SET_NULL, related_name="garrison", blank=True, null=True)
    # The overall commander of this army. Units under his command may have their own commanders
    commander = models.ForeignKey("Member", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True)
    # an owner who may be the same person who owns the domain. Or not, in the case of mercs, sent reinforcements, etc
    owner = models.ForeignKey("AssetOwner", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True)
    # food we're carrying with us on transports or whatever
    stored_food = models.PositiveSmallIntegerField(default=0, blank=0)
    # whether the army is starving. 0 = not starving, 1 = starting to starve, 2 = troops dying/deserting
    starvation_level = models.PositiveSmallIntegerField(default=0, blank=0)
    morale = models.PositiveSmallIntegerField(default=100, blank=100)
    # how much booty an army is carrying.
    plunder = models.PositiveSmallIntegerField(default=0, blank=0)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Armies"
        
    def display(self):
        """
        Like domain.display(), returns a string for the mush of our
        different attributes.
        """
        # self.owner is an AssetOwner, so its string name is AssetOwner.owner
        owner = self.owner
        if owner:
            owner = owner.owner
        msg = "{wName{n: %s {wCommander{n: %s\n" % (self.name, self.commander)
        msg += "{wDomain{n: %s {wLocation{n: %s\n" % (self.domain, self.land)
        msg += "{wOwner{n: %s\n" % owner
        msg += "{wDescription{n: %s\n" % self.desc
        msg += "{wMorale{n: %s {wFood{n: %s {wStarvation Level{n: %s {wPlunder{n: %s\n" % (self.morale, self.plunder,
                                                                                           self.starvation_level,
                                                                                           self.plunder)
        msg += "{wUnits{n:\n"
        for unit in self.units.all():
            msg += unit.display() + "\n"
        return msg
    
    def find_unit(self, unit_type):
        """
        Find a unit that we have of the given unit_type. Armies should only have one of each unit_type
        of unit in them, so we can always just return the first match of the queryset.
        """
        qs = self.units.filter(unit_type=unit_type)
        if len(qs) < 1:
            return None
        return qs[0]
    
    def get_food_consumption(self):
        """
        Total food consumption for our army
        """
        hunger = 0
        for unit in self.units.all():
            hunger += unit.food_consumption
        return hunger
    
    def consume_food(self, report=None):
        """
        All units eat food. First food is consumed by any stored on the army,
        then stored in domain, and then from supply lines if we're far away. If
        we don't have enough food to feed the army, start raising starvation. If
        starvation level is 2, then we have desertion/starvation.
        """
        hunger = self.get_food_consumption()
        total_need = hunger
        if self.stored_food > 0:
            if hunger > self.stored_food:
                hunger -= self.stored_food
                self.stored_food = 0
            else:  # have enough stored food, so reduce it and done
                self.stored_food -= hunger
                if self.starvation_level > 0:
                    self.starvation_level = 0
                self.save()
                return
        # check if we're in land that our ruler owns
        qs = self.land.domains.filter(ruler__id=self.domain.ruler.id)
        if len(qs) > 0:
            near_domain = qs[0]
            if hunger > near_domain.stored_food:
                hunger -= near_domain.stored_food
                near_domain.stored_food = 0
                near_domain.save()
            else:
                near_domain.stored_food -= hunger
                near_domain.save()
                if self.starvation_level > 0:
                    self.starvation_level = 0
                self.save()
                return
        # if we have more than half the food we need, just a morale hit
        if hunger < total_need/2 and self.starvation_level < 2:
            self.morale -= hunger/5
            self.starvation_level += 1
        else:  # starvation process
            self.morale -= hunger/4
            self.starve()
        # to do, add starvation report later
        if report:
            print "Starvation report would go here for %s" % self

    def starve(self):
        """
        If our hunger is too great, troops start to die and desert.
        """
        for unit in self.units.all():
            unit.decimate()

    def countermand(self):
        """
        Erases our orders, refunds the value to our domain.
        """
        pass

    def execute_orders(self, week, report=None):
        """
        Execute our orders. This will be called from the Weekly Script,
        along with do_weekly_adjustment. Error checking on the validity
        of orders should be done at the player-command level, not here.
        """
        orders = self.orders.filter(complete=False)
        if not orders:
            self.morale += 1
            self.save()
            return
        for order in orders:
            if order.type == Orders.TRAIN:
                for unit in self.units.all():
                    unit.train()
                return
            if order.type == Orders.EXPLORE:
                explore = Exploration(self, self.land, self.domain, week)
                explore.event()
                return
            if order.type == Orders.RAID:
                if self.do_battle(order.target_domain, week):
                    # raid was successful
                    self.pillage(order.target_domain, week)
                else:
                    self.morale -= 10
                    self.save()
            if order.type == Orders.CONQUER:
                if self.do_battle(order.target_domain, week):
                    # conquest was successful
                    self.conquer(order.target_domain, week)
                else:
                    self.morale -= 10
                    self.save()
            if order.type == Orders.ENFORCE_ORDER:
                self.pacify(self.domain)
            if order.type == Orders.BESIEGE:
                # to be implemented later
                pass
            if order.type == Orders.MARCH:
                if order.target_domain:
                    self.domain = order.target_domain
                self.land = order.target_land
                self.save()
            # to do : add to report here
            if report:
                print "Placeholder for army orders report"
                
    def do_battle(self, tdomain, week):
        """
        Returns True iff attackers win, False if defenders
        win or if there was a stalemate/tie.
        """
        try:
            e_armies = tdomain.armies.filter(land_id=tdomain.land.id)
            if not e_armies:
                # No opposition. We win without a fight
                return True
            atkpc = self.commander
            defpc = None
            if self.domain and self.domain.ruler and self.domain.ruler.castellan:
                atkpc = self.domain.ruler.castellan
            if tdomain and tdomain.ruler and tdomain.ruler.castellan:
                defpc = tdomain.ruler.castellan
            battle = Battle(armies_atk=self, armies_def=e_armies, week=week,
                            pc_atk=atkpc, pc_def=defpc, atk_domain=self.domain, def_domain=tdomain)
            result = battle.begin_combat()
            # returns True if result shows ATK_WIN, False otherwise
            return result == Battle.ATK_WIN
        except (Exception):
            print "ERROR: Could not generate battle on domain."
            traceback.print_exc()

    def pillage(self, target, week):
        """
        Successfully pillaging resources from the target domain
        and adding them to our own domain.
        """
        loot = target.plundered_by(self, week)
        self.plunder += loot
        self.save()

    def pacify(self, target):
        percent = float(self.quantity)/target.total_serfs
        percent *= 100
        percent = int(percent)
        target.lawlessness -= percent
        target.save()
        self.morale -= 1
        self.save()
    
    def conquer(self, target, week):
        """
        Conquers a domain. If the army has a domain, that domain will
        absorb the target if they're bordering, or just change the rulers
        while keeping it intact otherwise. If the army has no domain, then
        the commander will be set as the ruler of the domain.
        """
        bordering = None
        ruler = None
        other_domains = None
        # send remaining armies to other domains
        if target.ruler:
            other_domains = Domain.objects.filter(ruler_id=target.ruler.id).exclude(id=target.id)
        if other_domains:
            for army in target.armies.all():
                army.domain = other_domains[0]
                army.save()
        else:  # armies have nowhere to go, so having their owning domain wiped
            target.armies.clear()
        for castle in target.castles.all():
            castle.garrison.clear()
        if not self.domain:
            # The commander becomes the ruler
            if self.owner:
                castellan = None
                if self.commander:
                    castellan = self.commander.player
                ruler_list = Ruler.objects.filter(house_id=self.owner)
                if ruler_list:
                    ruler = ruler_list[0]
                else:
                    ruler = Ruler.objects.create(house=self.owner, castellan=castellan)
            # determine if we have a bordering domain that can absorb this
        else:
            ruler = self.domain.ruler
            if ruler:
                bordering = Domain.objects.filter(land_id=target.land.id).filter(
                    ruler_id=ruler.id)
        # we have a bordering domain. We will annex/absorb the domain into it
        if bordering:
            if self.domain in bordering:
                conqueror = self.domain
            else:
                conqueror = bordering[0]
            conqueror.annex(target, week, self)
        else:  # no bordering domain. So domain intact, but changing owner
            # set the domain's ruler
            target.ruler = ruler       
            target.lawlessness += 50
            target.save()
            # set army as occupying the domain
            self.domain = target
            self.save()

    def do_weekly_adjustment(self, week, report=None):
        """
        Weekly maintenance for the army. Consume food.
        """
        self.consume_food(report)
                   
    def _get_costs(self):
        """
        Costs for the army.
        """
        cost = 0
        for unit in self.units.all():
            cost += unit.costs
        return cost
    costs = property(_get_costs)

    def _get_size(self):
        """
        Total size of our army
        """
        size = 0
        for unit in self.units.all():
            size += unit.quantity
        return size
    size = property(_get_size)

    def __unicode__(self):
        return "%s (#%s)" % (self.name or "Unnamed army", self.id)

    def __repr__(self):
        return "<Army (#%s): %s>" % (self.id, self.name)

    def save(self, *args, **kwargs):
        super(Army, self).save(*args, **kwargs)
        try:
            self.owner.clear_cache()
        except (AttributeError, ValueError, TypeError):
            pass


class Orders(models.Model):
    """
    Orders for an army that will be executed during weekly maintenance. These
    are macro-scale orders for the entire army. Tactical commands during battle
    will not be handled in the model level, but in a separate combat simulator.
    Orders cannot be given to individual units. For separate units to be given
    orders, they must be separated into different armies. This will be handled
    by player commands for Dominion.
    """
    TRAIN = 1
    EXPLORE = 2
    RAID = 3
    CONQUER = 4
    ENFORCE_ORDER = 5
    BESIEGE = 6
    MARCH = 7
       
    ORDER_CHOICES = (
        (TRAIN, 'Troop Training'),
        (EXPLORE, 'Explore territory'),
        (RAID, 'Raid Domain'),
        (CONQUER, 'Conquer Domain'),
        (ENFORCE_ORDER, 'Enforce Order'),
        (BESIEGE, 'Besiege Castle'),
        (MARCH, 'March'),)
    army = models.ForeignKey("Army", related_name="orders", null=True, blank=True)
    target_domain = models.ForeignKey("Domain", related_name="incoming_attacks", null=True, blank=True)
    target_land = models.ForeignKey("Land", related_name="incoming_army", null=True, blank=True)
    type = models.PositiveSmallIntegerField(choices=ORDER_CHOICES, default=TRAIN)
    coin_cost = models.PositiveIntegerField(default=0, blank=0)
    food_cost = models.PositiveIntegerField(default=0, blank=0)
    # the week this order was given, so we can keep it as a history
    week = models.PositiveSmallIntegerField(default=0, blank=0)
    complete = models.BooleanField(default=False, blank=False)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Army Orders"
    

class MilitaryUnit(models.Model):
    """
    An individual unit belonging to an army for a domain. Each unit can have its own
    commander, while the overall army has its own commander. It is assumed that every
    unit in an army is in the same space, and will all respond to the same orders.

    Most combat stats for a unit will be generated at runtime based on its 'type'. We'll
    only need to store modifiers for a unit that are specific to it, modifiers it has
    accured.
    """
    commander = models.ForeignKey("Member", on_delete=models.SET_NULL, related_name="units", blank=True, null=True)
    army = models.ForeignKey("Army", related_name="units", blank=True, null=True)
    # type will be used to derive units and their stats elsewhere 
    unit_type = models.PositiveSmallIntegerField(default=0, blank=0)
    quantity = models.PositiveSmallIntegerField(default=1, blank=1)
    level = models.PositiveSmallIntegerField(default=0, blank=0)
    equipment = models.PositiveSmallIntegerField(default=0, blank=0)
    # can go negative, such as when adding new recruits to a unit
    xp = models.SmallIntegerField(default=0, blank=0)
    # if a hostile area has bandits or whatever, we're not part of an army, just that
    hostile_area = models.ForeignKey("HostileArea", on_delete=models.SET_NULL, related_name="units", blank=True,
                                     null=True)

    def display(self):
        """
        Returns a string representation of this unit's stats.
        """
        msg = "{wType{n: %-16s {wAmount{n: %-7s" % (self.type.capitalize(), self.quantity)
        msg += " {wLevel{n: %s {wEquipment{n: %s {wXP{n: %s" % (self.level, self.equipment, self.xp)
        return msg
    
    def decimate(self, amount=0.10):
        """
        Losing a percentage of our troops. Generally this is due to death
        from starvation or desertion. In this case, we don't care which.
        """
        # Ten percent of our troops
        losses = self.quantity * amount
        # lose it, rounded up
        self.do_losses(int(round(losses)))

    def do_losses(self, losses):
        """
        Lose troops. If we have 0 left, this unit is gone.
        """
        self.quantity -= losses
        if self.quantity <= 0:
            self.delete()
    
    def train(self, val=1):
        """
        Getting xp, and increasing our level if we have enough. The default
        value is for weekly troop training as a command. Battles will generally
        give much more than normal training.
        """
        self.xp += val
        cost = (self.level + 1) * 5
        if self.xp >= cost:
            self.level += 1
            self.xp -= cost
        self.save()

    def adjust_readiness(self, troops, training=0, equip=0):
        """
        Degrades the existing training and equipment level of our troops
        when we merge into others. This does not perform the merger, only
        changes our readiness by the given number of troops, training level,
        and equipment level.
        """
        pass
    
    def _get_costs(self):
        """
        Costs for the unit.
        """
        try:
            cost = unit_types.upkeep[self.unit_type]
        except KeyError:
            print "Type %s is not a recognized MilitaryUnit type!" % self.unit_type
            print "Warning. No cost assigned to <MilitaryUnit- ID: %s>" % self.id
            cost = 0
        cost *= self.quantity
        return cost
    
    def _get_food_consumption(self):
        """
        Food for the unit
        """
        try:
            hunger = unit_types.food[self.unit_type]
        except KeyError:
            print "Type %s is not a recognized Military type!" % self.unit_type
            print "Warning. No food upkeep assigned to <MilitaryUnit - ID: %s>" % self.id
            hunger = 0
        hunger *= self.quantity
        return hunger
    
    food_consumption = property(_get_food_consumption)
    costs = property(_get_costs)

    def _get_type_name(self):
        return unit_types.get_type_str(self.unit_type)
    type = property(_get_type_name)

    def __unicode__(self):
        return "%s %s" % (self.quantity, self.type)

    def __repr__(self):
        return "<Unit (#%s): %s %s>" % (self.id, self.quantity, self.type)

    def save(self, *args, **kwargs):
        super(MilitaryUnit, self).save(*args, **kwargs)
        try:
            self.army.owner.clear_cache()
        except (AttributeError, TypeError, ValueError):
            pass
    

class Member(models.Model):
    """
    Membership information for a character in an organization. This may or
    may not be an actual in-game object. If pc_exists is true, we expect a
    character object to be defined. If not, then this is just an off-screen
    npc who fills some purpose in the structure of the organization, but should
    generally not appear in game - more active npcs are probably Agents under
    control of a player character. Agents should also not be defined here,
    since they're usually more of a class of npc rather than individuals.
    Although they might be employed by an organization, we track them separately.
    This does mean they don't have any formal 'rank', but if the situation
    arises, you could always create a duplicate NPC Member who is one of your
    agents, just as a separation of their off-screen and on-screen duties.

    As far as salary goes, anyone in the Member model can have a WeeklyTransaction
    set up with their Organization.
    """  
    
    player = models.ForeignKey('PlayerOrNpc', related_name='memberships', blank=True, null=True)
    commanding_officer = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='subordinates', blank=True,
                                           null=True)
    organization = models.ForeignKey('Organization', related_name='members', blank=True, null=True)
    
    work_this_week = models.PositiveSmallIntegerField(default=0, blank=0)
    work_total = models.PositiveSmallIntegerField(default=0, blank=0)
    secret = models.BooleanField(blank=False, default=False)
    deguilded = models.BooleanField(blank=False, default=False)

    # a rare case of us not using a player object, since we may designate any type of object as belonging
    # to an organization - character objects without players (npcs), rooms, exits, items, etc.
    object = models.ForeignKey('objects.ObjectDB', related_name='memberships', blank=True, null=True)
    
    rank = models.PositiveSmallIntegerField(blank=10, default=10)
    
    pc_exists = models.BooleanField(blank=True, default=True,
                                    help_text="Whether this member is a player character in the database")
    # stuff that players may set for their members:
    desc = models.TextField(blank=True, default=True)
    public_notes = models.TextField(blank=True, default=True)
    officer_notes = models.TextField(blank=True, default=True)

    class Meta:
        ordering = ['rank']

    def msg(self, *args, **kwargs):
        if self.player:
            self.player.msg(*args, **kwargs)

    def _get_char(self):
        if self.player and self.player.player and self.player.player.db.char_ob:
            return self.player.player.db.char_ob
    char = property(_get_char)

    def set_salary(self, val):
        if not hasattr(self, 'salary'):
            if not self.player.assets:
                assets = AssetOwner(player=self.player)
                assets.save()
                self.player.assets = assets
            salary = AccountTransaction(recever=self.player.assets, sender=self.organization.assets,
                                        category="Salary", member=self, weekly_amount=val)
            salary.save()
            self.salary = salary
        else:
            self.salary.weekly_amount = val
            self.salary.save()
        self.save()

    def __str__(self):
        return str(self.player)

    def __unicode__(self):
        return unicode(self.player)

    def __repr__(self):
        return "<Member %s (#%s)>" % (self.player, self.id)
    
    def fake_delete(self):
        """
        Alternative to deleting this object. That way we can just readd them if they
        rejoin and conserve their rank/description.
        """
        self.deguilded = True
        self.save()

    def work(self, worktype):
        """
        Perform work in a week for our Organization.
        """
        worktypes = ("military", "economic", "social")
        if worktype not in worktypes:
            raise ValueError("Type must be in: %s." % ", ".join(worktypes))
        self.work_this_week += 1
        self.work_total += 1
        self.save()
        # self.player.assets.vault += 20
        # self.organization.assets.vault += 20
        if worktype == "military":
            self.player.assets.military += 1
            self.organization.assets.military += 1
        if worktype == "economic":
            self.player.assets.economic += 1
            self.organization.assets.economic += 1
        if worktype == "social":
            self.player.assets.social += 1
            self.organization.assets.social += 1
        self.player.assets.save()
        self.organization.assets.save()

    @property
    def pool_share(self):
        def calc_share(rank):
            """
            These are not percentages. These are the number of shares they
            get based on rank, so they are only relative to each other.
            """
            if rank == 1:
                return 30
            if rank == 2:
                return 25
            if rank == 3:
                return 20
            if rank == 4:
                return 15
            if rank == 5:
                return 5
            if rank == 6:
                return 4
            if rank == 7:
                return 3
            if rank == 8:
                return 2
            if rank == 9:
                return 1
            return 0
        total = self.organization.support_pool
        shares = 0
        for member in self.organization.active_members:
            shares += calc_share(member.rank)
        myshare = calc_share(self.rank)
        myshare = (myshare*total)/shares
        if total % shares:
            myshare += 1
        return myshare

    def points_used(self, catname):
        week = get_week()
        try:
            sphere = self.organization.spheres.get(category__name__iexact=catname)
        except SphereOfInfluence.DoesNotExist:
            return 0
        return sum(sphere.usage.filter(Q(supporter__player=self.player) &
                                       Q(supporter__fake=False) &
                                       Q(week=week)).values_list('rating', flat=True))

    @property
    def total_points_used(self):
        week = get_week()
        total = 0
        for sphere in self.organization.spheres.all():
            total += sum(sphere.usage.filter(Q(supporter__player=self.player) &
                                             Q(supporter__fake=False) &
                                             Q(week=week)).values_list('rating', flat=True))
        return total

    def display(self):
        poolshare = self.pool_share
        used = self.total_points_used
        tasks = self.tasks.filter(finished=True)
        try:
            rep = self.organization.reputations.get(player=self.player)
        except Reputation.DoesNotExist:
            rep = None
        msg = "\n{wRank{n: %s" % self.rank
        msg += "\n{wSupport Pool Share{n: %s/%s" % (poolshare - used, poolshare)
        msg += "\n{wTotal Work{n: %s" % self.work_total
        msg += "\n{wTasks Completed{n: %s, {wTotal Rating{n: %s" % (tasks.count(), sum(task.total for task in tasks))
        if rep:
            msg += "\n{wReputation{n: {wAffection{n: %s, {wRespect:{n %s" % (rep.affection, rep.respect)
        return msg

    @property
    def rank_title(self):
        try:
            male = self.player.player.db.char_ob.db.gender.lower().startswith('m')
        except (AttributeError, ValueError, TypeError):
            male = False
        if male:
            rankstr = "rank_%s_%s" % (self.rank, "male")
        else:
            rankstr = "rank_%s_%s" % (self.rank, "female")
        return getattr(self.organization, rankstr)
        

class Task(models.Model):
    """
    A task that a guild creates and then assigns to members to carry out,
    to earn them and the members income. Used to create RP.
    """
    name = models.CharField(blank=True, null=True, max_length=80)
    org = models.ManyToManyField('Organization', related_name='tasks', blank=True)
    category = models.CharField(null=True, blank=True, max_length=80)
    room_echo = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=0, default=0)
    desc = models.TextField(blank=True, null=True)
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    results = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    
    @property
    def reqs(self):
        return ", ".join(str(ob.category) for ob in self.requirements.all())


class AssignedTask(models.Model):
    """
    A task assigned to a player.
    """
    task = models.ForeignKey('Task', related_name='assigned_tasks', blank=True, null=True)
    member = models.ForeignKey('Member', related_name='tasks', blank=True, null=True)
    finished = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=0, default=0)
    notes = models.TextField(blank=True, null=True)
    observer_text = models.TextField(blank=True, null=True)
    alt_echo = models.TextField(blank=True, null=True)

    @property
    def current_alt_echo(self):
        """
        Alt-echoes are a series of ; seprated strings. We return
        the first if we have one. Every new alt_echo is added at
        the start.
        """
        if not self.alt_echo:
            return self.task.room_echo
        return self.alt_echo.split(";")[0]

    @property
    def member_amount(self):
        """Reward amount for a player"""
        base = 3 * self.task.difficulty
        oflow = self.overflow
        if oflow > 0:
            base += oflow
        return base

    def get_org_amount(self, category):
        """Reward amount for an org"""
        try:
            mod = getattr(self.org, category+"_modifier") + 1
        except (TypeError, ValueError, AttributeError):
            mod = 1
        base = self.task.difficulty * mod
        oflow = self.overflow
        if oflow > 0:
            base += (mod * oflow)/2
        return base
    
    @property
    def overflow(self):
        return self.total - self.task.difficulty

    @property
    def org(self):
        return self.member.organization

    @property
    def dompc(self):
        return self.member.player

    @property
    def player(self):
        return self.dompc.player

    def cleanup_request_list(self):
        """Cleans the Attribute that lists who we requested support from"""
        char = self.player.db.char_ob
        try:
            del char.db.asked_supporters[self.id]
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
           
    def payout_check(self, week):
        total = self.total
        category_list = self.task.category.split(",")
        if total < self.task.difficulty:
            # we failed
            return
        org = self.org
        total_rep = 0
        # set week to the week we finished
        self.week = week
        self.cleanup_request_list()
        msg = "You have completed the task: %s\n" % self.task.name
        for category in category_list:
            category = category.strip().lower()
            div = len(category_list)
            self.finished = True
            # calculate rewards. Mod for org is based on our modifier
            amt = self.member_amount
            rep = amt
            amt /= div
            # calculate resources for org. We compare multiplier for org to player mod, calc through that
            orgres = self.get_org_amount(category)/div
            memassets = self.dompc.assets
            orgassets = org.assets
            current = getattr(memassets, category)
            setattr(memassets, category, current + amt)
            current = getattr(orgassets, category)
            setattr(orgassets, category, current + orgres)
            self.dompc.gain_reputation(org, amt, amt)
            self.save()
            memassets.save()
            orgassets.save()
            total_rep += rep
            msg += "%s Resources earned: %s\n" % (category, amt)
        msg += "Reputation earned: %s\n" % total_rep
        for support in self.supporters.all():
            support.award_renown()
        self.player.inform(msg, category="task", week=week,
                                         append=True)

    @property
    def total(self):
        if self.finished:
            if hasattr(self, 'cached_total'):
                return self.cached_total
        try:
            val = 0
            for sup in self.supporters.filter(fake=False):
                val += sup.rating
        except (AttributeError, TypeError, ValueError):
            val = 0
        self.cached_total = val
        return val

    def display(self):
        msg = "{wName{n: %s\n" % self.task.name
        msg += "{wOrganization{n %s\n" % self.member.organization.name
        msg += "{wWeek Finished{n: %s\n" % self.week
        msg += "{wTotal support{n: %s\n" % self.total
        msg += "{wSupporters:{n %s\n" % ", ".join(str(ob) for ob in self.supporters.all())
        msg += "{wNotes:{n\n%s\n" % self.notes
        msg += "{wStory:{n\n%s\n" % self.story
        return msg

    @property
    def story(self):
        msg = self.observer_text or ""
        if not msg:
            return msg
        msg += "\n\n"
        msg += "\n\n".join(ob.observer_text for ob in self.supporters.all() if ob.observer_text)
        return msg

    def __str__(self):
        return "%s's %s" % (self.member, self.task)

    @property
    def elapsed_time(self):
        elapsed = get_week() - self.week
        if elapsed < 1:
            return "Recently"
        if elapsed == 1:
            return "Last week"
        return "%s weeks ago" % elapsed
        

class TaskSupporter(models.Model):
    """
    A player that has pledged support to someone doing a task
    """
    player = models.ForeignKey('PlayerOrNpc', related_name='supported_tasks', blank=True, null=True)
    task = models.ForeignKey('AssignedTask', related_name='supporters', blank=True, null=True)
    fake = models.BooleanField(default=False)
    spheres = models.ManyToManyField('SphereOfInfluence', related_name='supported_tasks', blank=True,
                                     through='SupportUsed')
    observer_text = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return "%s supporting %s" % (self.player, self.task) or "Unknown supporter"

    def award_renown(self):
        """Give renown to both players."""
        targ = self.task.member.player
        if not self.fake:
            for char in (targ, self.player):
                for inf in self.allocation.all():
                    category = inf.sphere.category
                    try:
                        ren = char.renown.get(category=category)
                    except Renown.DoesNotExist:
                        ren = char.renown.create(category=category)
                    ren.rating += inf.rating
                    ren.save()
        else:  # we're an unreliable flake. We suffer penalties
            for req in self.task.task.requirements.all():
                category = req.category
                char = self.player
                if not char:
                    continue
                try:
                    ren = char.renown.get(category=category)
                except Renown.DoesNotExist:
                    ren = char.renown.create(category=category)
                ren.rating -= 1
                ren.save()

    @property
    def rating(self):
        """
        Total up our support used from different spheres of influence of our
        organizations. Add in freebie bonuses
        """
        total = 0
        if self.fake:
            return 0
        # freebie point
        total += 1
        week = get_week()
        total += (week - self.first_week)
        if self.player.supported_tasks.filter(task__member=self.task.member).first() == self:
            total += 5
        for usage in self.allocation.all():
            total += usage.rating
        return total

    @property
    def week(self):
        try:
            return self.allocation.all().last().week
        except AttributeError:
            return get_week()

    @property
    def first_week(self):
        # week tracking was first entered, so we have 14 to replace null values
        try:
            return self.allocation.all().first().week or 14
        except AttributeError:
            return 14
        

# helper classes for crafting recipe to simplify API - allow for 'recipe.materials.all()'
class Mats(object):
    def __init__(self, mat, amount):
        self.mat = mat
        self.id = mat.id
        self.type = mat
        self.amount = amount


class MatList(object):
    def __init__(self):
        self.mats = []

    def all(self):
        return self.mats


class CraftingRecipe(models.Model):
    """
    For crafting, a recipe has a name, description, then materials. A lot of information
    is saved as a parsable text string in the 'result' text field. It'll
    take a form like: "baseval:0;scaling:1" and so on. baseval is a value
    the object has (for armor, say) for minimum quality level, while
    scaling is the increase per quality level to stats. "slot" and "slot limit"
    are used for wearable objects to denote the slot they're worn in and
    how many other objects may be worn in that slot, respectively.
    """
    name = models.CharField(blank=True, null=True, max_length=255)
    desc = models.TextField(blank=True, null=True)
    # organizations or players that know this recipe
    known_by = models.ManyToManyField('AssetOwner', blank=True, related_name='recipes')
    primary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_primary')
    secondary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_secondary')
    tertiary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_tertiary')
    primary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    secondary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    tertiary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    additional_cost = models.PositiveIntegerField(blank=0, default=0)
    # the ability/profession that is used in creating this
    ability = models.CharField(blank=True, null=True, max_length=80)
    skill = models.CharField(blank=True, null=True, max_length=80)
    # the type of object we're creating
    type = models.CharField(blank=True, null=True, max_length=80)
    # level in ability this recipe corresponds to. 1 through 6, usually
    level = models.PositiveSmallIntegerField(blank=1, default=1)
    # the result is a text field that we can later parse to determine what we create
    result = models.TextField(blank=True, null=True)
    allow_adorn = models.BooleanField(default=True, blank=True)
    # lockstring
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')

    def __init__(self, *args, **kwargs):
        super(CraftingRecipe, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)
        self.resultsdict = self.parse_result(self.result)
        self.materials = MatList()
        # create throws errors on __init__ for many to many fields
        if self.primary_amount:
            for mat in self.primary_materials.all():
                self.materials.mats.append(Mats(mat, self.primary_amount))
        if self.secondary_amount:
            for mat in self.secondary_materials.all():
                self.materials.mats.append(Mats(mat, self.secondary_amount))
        if self.tertiary_amount:
            for mat in self.tertiary_materials.all():
                self.materials.mats.append(Mats(mat, self.tertiary_amount))

    def access(self, accessing_obj, access_type='learn', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    @staticmethod
    def parse_result(results):
        """
        Given a string, return a dictionary of the different
        key:value pairs separated by semicolons
        """
        if not results:
            return {}
        rlist = results.split(";")
        keyvalpairs = [pair.split(":") for pair in rlist]
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict

    def display_reqs(self, dompc=None, full=False):
        msg = ""
        if full:
            msg += "{wName:{n %s\n" % self.name
            msg += "{wDescription:{n %s\n" % self.desc
        msg += "{wSilver:{n %s\n" % self.additional_cost
        tups = ((self.primary_amount, "{wPrimary Materials:{n\n", self.primary_materials),
                (self.secondary_amount, "\n{wSecondary Materials:{n\n", self.secondary_materials),
                (self.tertiary_amount, "\n{wTertiary Materials:{n\n", self.tertiary_materials),)
        for tup in tups:
            if tup[0]:
                msg += tup[1]
                if dompc:
                    msglist = []
                    for mat in tup[2].all():
                        try:
                            pcmat = dompc.assets.materials.get(type=mat)
                            amt = pcmat.amount
                        except CraftingMaterials.DoesNotExist:
                            amt = 0
                        msglist.append("%s: %s (%s/%s)" % (str(mat), tup[0], amt, tup[0]))
                    msg += ", ".join(msglist)
                else:
                    msg += ", ".join("%s: %s" % (str(ob), tup[0]) for ob in tup[2].all())
        return msg
    
    @property
    def value(self):
        if hasattr(self, 'cached_value'):
            return self.cached_value
        val = self.additional_cost
        for mat in self.primary_materials.all():
            val += mat.value * self.primary_amount
        for mat in self.secondary_materials.all():
            val += mat.value * self.secondary_amount
        for mat in self.tertiary_materials.all():
            val += mat.value * self.tertiary_amount
        self.cached_value = val
        return val

    def __unicode__(self):
        return self.name or "Unknown"


class CraftingMaterialType(models.Model):
    """
    Different types of crafting materials. We have a silver value per unit
    stored. Similar to results in CraftingRecipe, mods holds a dictionary
    of key,value pairs parsed from our acquisition_modifiers textfield. For
    CraftingMaterialTypes, this includes the category of material, and how
    difficult it is to fake it as another material of the same category
    """
    # the type of material we are
    name = models.CharField(max_length=80)
    desc = models.TextField(blank=True, null=True)
    # silver value per unit
    value = models.PositiveIntegerField(blank=0, default=0)
    category = models.CharField(blank=True, null=True, max_length=80)
    # Text we can parse for notes about cost modifiers for different orgs, locations to obtain, etc
    acquisition_modifiers = models.TextField(blank=True, null=True)
    
    def __init__(self, *args, **kwargs):
        super(CraftingMaterialType, self).__init__(*args, **kwargs)
        # uses same method from CraftingRecipe in order to create a dict of our mods
        self.mods = CraftingRecipe.parse_result(self.acquisition_modifiers)

    def __unicode__(self):
        return self.name or "Unknown"


class CraftingMaterials(models.Model):
    """
    Materials used for crafting. Can be stored by an AssetOwner as part of their
    collection, -or- used in a recipe to measure how much they need of a material.
    If it is used in a recipe, do NOT set it owned by any asset owner, or by changing
    the amount they'll change the amount required in a recipe!
    """
    type = models.ForeignKey('CraftingMaterialType', blank=True, null=True)
    amount = models.PositiveIntegerField(blank=0, default=0)
    owner = models.ForeignKey('AssetOwner', blank=True, null=True, related_name='materials')
    
    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Crafting Materials"

    def __unicode__(self):
        return "%s %s" % (self.amount, self.type)
    
    @property
    def value(self):
        return self.type.value * self.amount


class RPEvent(models.Model):
    """
    A model to store RP events created by either players or GMs. We use the PlayerOrNpc
    model instead of directly linking to players so that we can have npcs creating
    or participating in events in our history for in-character transformations of
    the event into stories. Events can be public or private, and run by a gm or not.
    Events can have money tossed at them in order to generate prestige, which
    is indicated by the celebration_tier.
    """
    NONE = 0
    COMMON = 1
    REFINED = 2
    GRAND = 3
    EXTRAVAGANT = 4
    LEGENDARY = 5
    
    LARGESSE_CHOICES = (
        (NONE, 'Small'),
        (COMMON, 'Average'),
        (REFINED, 'Refined'),
        (GRAND, 'Grand'),
        (EXTRAVAGANT, 'Extravagant'),
        (LEGENDARY, 'Legendary'),
        )
    hosts = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='events_hosted')
    name = models.CharField(max_length=255)
    desc = models.TextField(blank=True, null=True)
    location = models.ForeignKey('objects.ObjectDB', blank=True, null=True, related_name='events_held')
    date = models.DateTimeField(blank=True, null=True)
    participants = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='events_attended')
    gms = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='events_gmd')
    celebration_tier = models.PositiveSmallIntegerField(choices=LARGESSE_CHOICES, default=NONE)
    gm_event = models.BooleanField(default=False, blank=False)
    public_event = models.BooleanField(default=True, blank=True)
    finished = models.BooleanField(default=False, blank=False)
    results = models.TextField(blank=True, null=True)
    room_desc = models.TextField(blank=True, null=True)

    @property
    def prestige(self):
        cel_level = self.celebration_tier
        prestige = 0
        if cel_level == 1:
            prestige = 1000
        elif cel_level == 2:
            prestige = 5000
        elif cel_level == 3:
            prestige = 20000
        elif cel_level == 4:
            prestige = 100000
        elif cel_level == 5:
            prestige = 400000
        return prestige

    def display(self):
        msg = "{wName:{n %s\n" % self.name
        msg += "{wHosts:{n %s\n" % ", ".join(str(ob) for ob in self.hosts.all())
        msg += "{wLocation:{n %s\n" % self.location
        if not self.public_event:
            msg += "{w*This event has been marked as private. Ask the host about attending.*{n\n"
        msg += "{wEvent Scale:{n %s\n" % self.get_celebration_tier_display()
        msg += "{wDate:{n %s\n" % self.date.strftime("%x %X")
        msg += "{wDesc:{n\n%s\n" % self.desc
        webpage = PAGEROOT + self.get_absolute_url()
        msg += "{wEvent Page:{n %s\n" % webpage
        comments = self.comments.filter(db_header__icontains="white_journal").order_by('-db_date_created')
        if comments:
            from server.utils.prettytable import PrettyTable
            msg += "\n{wComments:{n"
            table = PrettyTable(["#", "{wName{n"])
            x = 1
            for comment in comments:
                sender = ", ".join(str(ob) for ob in comment.senders)
                table.add_row([x, sender])
                x += 1
            msg += "\n%s" % (str(table))
        return msg

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name

    @property
    def hostnames(self):
        return ", ".join(str(ob) for ob in self.hosts.all())
    
    @property
    def log(self):
        try:
            from typeclasses.scripts.event_manager import LOGPATH
            filename = LOGPATH + "event_log_%s.txt" % self.id
            return open(filename, 'r').read()
        except IOError:
            return ""

    @property
    def tagkey(self):
        """
        Tagkey MUST be unique. So we have to incorporate the ID of the event
        for the tagkey in case of duplicate event names.
        """
        return "%s_%s" % (self.name.lower(), self.id)

    @property
    def tagdata(self):
        return str(self.id)

    @property
    def comments(self):
        from evennia.comms.models import Msg
        return Msg.objects.filter(db_tags__db_data=self.tagdata,
                                  db_tags__db_category="event")

    @property
    def main_host(self):
        from typeclasses.players import Player
        try:
            return Player.objects.get(db_tags__db_key=self.tagkey)
        except (Player.DoesNotExist, Player.MultipleObjectsReturned):
            try:
                return self.hosts.first().player
            except (PlayerOrNpc.DoesNotExist, AttributeError):
                return None

    def tag_obj(self, obj):
        from evennia.typeclasses.tags import Tag
        try:
            tag = Tag.objects.get(db_key=self.tagkey)
        except Tag.DoesNotExist:
            tag = Tag.objects.create(db_key=self.tagkey, db_data=self.tagdata,
                                     db_category="event")
        obj.db_tags.add(tag)
        return obj

    @property
    def public_comments(self):
        return self.comments.filter(db_header__icontains="white_journal")

    def get_absolute_url(self):
        return reverse('dominion:display_event', kwargs={'pk': self.id})
    

class InfluenceCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    orgs = models.ManyToManyField("Organization", through="SphereOfInfluence")
    players = models.ManyToManyField("PlayerOrNpc", through="Renown")
    tasks = models.ManyToManyField("Task", through="TaskRequirement")

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Influence Categories"

    def __str__(self):
        return self.name


class Renown(models.Model):
    category = models.ForeignKey("InfluenceCategory")
    player = models.ForeignKey("PlayerOrNpc", related_name="renown")
    rating = models.IntegerField(blank=0, default=0)

    class Meta:
        verbose_name_plural = "Renown"

    def __str__(self):
        return "%s's rating in %s: %s" % (self.player, self.category, self.rating)

    # scaling for how our renown will be represented
    @property
    def level(self):
        if self.rating <= 0:
            return 0
        if self.rating <= 1000:
            return self.rating/200
        if self.rating <= 3000:
            return 5 + (self.rating-1000)/400
        if self.rating <= 6000:
            return 10 + (self.rating-2000)/800
        if self.rating <= 13000:
            return 15 + (self.rating-4000)/1600
        return 20


class SphereOfInfluence(models.Model):
    category = models.ForeignKey("InfluenceCategory")
    org = models.ForeignKey("Organization", related_name="spheres")
    rating = models.IntegerField(blank=0, default=0)

    class Meta:
        verbose_name_plural = "Spheres of Influence"

    def __str__(self):
        return "%s's rating in %s: %s" % (self.org, self.category, self.rating)

    # example idea for scaling
    @property
    def level(self):
        if self.rating <= 150:
            return self.rating/10
        if self.rating <= 350:
            return 15 + (self.rating-150)/20
        if self.rating <= 750:
            return 25 + (self.rating-350)/40
        if self.rating <= 1550:
            return 35 + (self.rating-750)/80
        return 45 + (self.rating-1550)/100


class TaskRequirement(models.Model):
    category = models.ForeignKey("InfluenceCategory")
    task = models.ForeignKey("Task", related_name="requirements")
    minimum_amount = models.PositiveSmallIntegerField(blank=0, default=0)

    def __str__(self):
        return "%s requirement: %s" % (self.task, self.category)


class SupportUsed(models.Model):
    week = models.PositiveSmallIntegerField(default=0, blank=0)
    supporter = models.ForeignKey("TaskSupporter", related_name="allocation")
    sphere = models.ForeignKey("SphereOfInfluence", related_name="usage")
    rating = models.PositiveSmallIntegerField(blank=0, default=0)

    def __str__(self):
        return "%s using %s of %s" % (self.supporter, self.rating, self.sphere)
