"""
Commands for dominion. This will be the interface through which
players interact with the system, as well as commands for staff
to make changes.
"""
from django.conf import settings
from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from ast import literal_eval
from . import setup_utils
from .models import (Region, Domain, Land, PlayerOrNpc, Army,
                        Castle, AssetOwner, DomainProject, Task,
                        Ruler, Organization, Member, Orders, Agent,
                        SphereOfInfluence, SupportUsed, AssignedTask,
                        TaskSupporter, InfluenceCategory)
from evennia.players.models import PlayerDB
from evennia.objects.models import ObjectDB
from evennia.objects.objects import _AT_SEARCH_RESULT
from .unit_types import type_from_str
from typeclasses.npcs.npc_types import get_npc_type, generate_default_name_and_desc
from server.utils.prettytable import PrettyTable
from server.utils.utils import get_week
from django.db.models import Q, Sum

# Constants for Dominion projects
BUILDING_COST = 1000
# cost will be base * 5^(new level)
BASE_CASTLE_COST = 4000


#-Admin commands-------------------------------------------------

class CmdAdmDomain(MuxPlayerCommand):
    """
    @admin_domain
    Usage:
      @admin_domain
      @admin_domain/create player=region[, social rank]
      @admin_domain/replacevassal receiver=domain_id, numvassals
      @admin_domain/createvassal receiver=liege_domain_id, numvassals
      @admin_domain/transferowner receiver=domain_id
      @admdin_domain/transferrule char=domain_id
      @admin_domain/liege domain_id=family
      @admin_domain/list <fealty, eg: 'Velenosa'>
      @admin_domain/list_char player
      @admin_domain/list_land (x,y)
      @admin_domain/view domain_id
      @admin_domain/delete domain_id
      @admin_domain/move domain_id=(x,y)
      @admin_domain/farms domain_id=#
    switches for information/creation/transfer/deletion:
      create - creates a new domain
      npc_create - creates a new domain for an npc
      replacevassal - replaces npc vassal, creates vassals of their own
      transferowner - make character and their family ruler of a domain
      transferrule - Just change who is castellan/acting ruler
      liege - sets the liege of a domain to be given family
      list - all domains for a particular fealty, like Velenosa
      list_land - lists all domains in a given x,y land square
      list_char - lists all domains for a given character name
      view - get stats on a domain
      move - moves domain to new land square if it has room
      delete - destroy a domain
    switches for changing values in a domain:
      name - Domain's name
      title - Title for holder of domain
      desc - description/history of domain
      area - total area of domain
      tax_rate
      slave_labor_percentage
      num_farms - changes the number of farms to value
      num_mines - like farms
      num_mills - like farms
      num_lumber_yards - same
      stored_food - stored food
      farming_serfs
      mine_serfs
      mill_serfs
      lumber_serfs
      unassigned_serfs - serfs not currently working in a building
      amount_plundered - amount stolen from them this week
      income_modifier - default 100 for normal production
    """
    key = "@admin_domain"
    locks = "cmd:perm(Wizards)"
    aliases = ["@admin_domains", "@admdomain", "@admdomains", "@adm_domain", "@adm_domains"]
    help_category = "Dominion"
    
    def func(self):
        caller = self.caller
        if not self.args:
            pcdomains = ", ".join((repr(dom) for dom in Domain.objects.filter(ruler__castellan__isnull=False)))
            caller.msg("{wPlayer domains:{n %s" % pcdomains)
            npcdomains =", ".join((repr(dom) for dom in Domain.objects.filter(ruler__castellan__player__isnull=True)))
            caller.msg("{wNPC domains:{n %s" % npcdomains)
            return
        if "create" in self.switches:
            # usage: @admin_domain/create player=region[, social rank]
            if not self.rhs:
                caller.msg("Invalid usage. Requires player=region.")
                return
            player = caller.search(self.lhs)
            if not player:
                caller.msg("No player found by name %s." % self.lhs)
                return
            char = player.db.char_ob
            if not char:
                caller.msg("No valid character object for %s." % self.lhs)
                return
            if len(self.rhslist) > 1:
                region = self.rhslist[0]
                srank = self.rhslist[1]
            else:
                region = self.rhs
                srank = char.db.social_rank
            # Get our social rank and region from rhs arguments
            try:
                srank = int(srank)
                region = Region.objects.get(name__iexact=region)
            except ValueError:
                caller.msg("Character's Social rank must be a number. It was %s." % srank)
                return
            except Region.DoesNotExist:
                caller.msg("No region found of name %s." % self.rhslist[0])
                caller.msg("List of regions: %s" % ", ".join(str(region) for region in Region.objects.all()))
                return
            # we will only create an npc liege if our social rank is 4 or higher
            create_liege = srank > 3
            # The player has no Dominion object, so we must create it.
            if not hasattr(player, 'Dominion'):
                caller.msg("Creating a new domain of rank %s for %s." % (srank, char))
                dom = setup_utils.setup_dom_for_char(char, create_dompc=True, create_assets=True,
                                                     region=region, srank=srank, create_liege=create_liege)
            # Has a dominion object, so just set up the domain
            else:
                needs_assets = not hasattr(player.Dominion, 'assets')
                caller.msg("Setting up Dominion for player %s, and creating a new domain of rank %s." % (char, srank))
                dom = setup_utils.setup_dom_for_char(char, create_dompc=False, create_assets=needs_assets,
                                                     region=region, srank=srank, create_liege=create_liege)
            if not dom:
                caller.msg("Dominion failed to create a new domain.")
                return
            if srank == 2:
                try:
                    house = Organization.objects.get(name__iexact="Grayson")
                    if dom.ruler != house.assets.estate:
                        dom.ruler.liege = house.assets.estate
                        dom.ruler.save()
                except Organization.DoesNotExist:
                    caller.msg("Dominion could not find a suitable liege.")
            if srank == 3:
                try:
                    if region.name == "Lyceum":
                        house = Organization.objects.get(name__iexact="Velenosa")
                    if region.name == "Oathlands":
                        house = Organization.objects.get(name__iexact="Valardin")
                    if region.name == "Mourning Isles":
                        house = Organization.objects.get(name__iexact="Thrax")
                    if region.name == "Northlands":
                        house = Organization.objects.get(name__iexact="Redrain")
                    if region.name == "Crownlands":
                        house = Organization.objects.get(name__iexact="Grayson")
                    # Make sure we're not the same house
                    if dom.ruler != house.assets.estate:
                        dom.ruler.liege = house.assets.estate
                        dom.ruler.save()
                except (Organization.DoesNotExist, AttributeError):
                    caller.msg("Dominion could not find a suitable liege.")
            caller.msg("New Domain #%s created: %s in land square: %s" % (dom.id, str(dom), str(dom.land)))
            return
        if ("transferowner" in self.switches or "transferrule" in self.switches
            or "replacevassal" in self.switches or "createvassal" in self.switches):
            # usage: @admin_domain/transfer receiver=domain_id
            if not self.rhs or not self.lhs:
                caller.msg("Usage: @admin_domain/transfer receiver=domain's id")
                return
            player = caller.search(self.lhs)
            if not player:
                caller.msg("No player by the name %s." % self.lhs)
            try:
                id = int(self.rhslist[0])
                if len(self.rhslist) > 1:
                    num_vassals = int(self.rhslist[1])
                else:
                    num_vassals = 2
                dom = Domain.objects.get(id=id)
            except ValueError:
                caller.msg("Domain's id must be a number.")
                return
            except Domain.DoesNotExist:
                caller.msg("No domain by that id number.")
                return
            if "createvassal" in self.switches:
                try:
                    region = dom.land.region
                    setup_utils.setup_dom_for_char(player.db.char_ob, liege_domain=dom, region=region)
                    caller.msg("Vassal created.")
                except Exception as err:
                    caller.msg(err)
                    import traceback
                    traceback.print_exc()
                return
            if "replacevassal" in self.switches:
                try:
                    setup_utils.replace_vassal(dom, player, num_vassals)
                    caller.msg("%s now ruled by %s." % (dom, player))
                except Exception as err:
                    caller.msg(err)
                    import traceback
                    traceback.print_exc()
                return
            if not hasattr(player, 'Dominion'):
                dompc = setup_utils.setup_dom_for_char(player.db.char_ob)
            else:
                dompc = player.Dominion
            if "transferowner" in self.switches:
                try:
                    family = player.db.char_ob.db.family
                    house = Organization.objects.get(name__iexact=family)
                    owner = house.assets
                    # if the organization's AssetOwner has no Ruler object
                    if hasattr(owner, 'estate'):
                        ruler = owner.estate
                    else:
                        ruler = Ruler.objects.create(house=owner, castellan=dompc)
                except (Organization.DoesNotExist):
                    ruler = setup_utils.setup_ruler(family, dompc)
                    owner = ruler.house
                    house = owner.organization_owner
                dom.ruler = ruler
                dom.save()
                caller.msg("%s set to rule %s." % (ruler, dom))
                return
            if not dom.ruler:
                dom.ruler.create(castellan=dompc)
            else:
                dom.ruler.castellan = dompc
                dom.ruler.save()
            dom.save()
            caller.msg("Ruler set to be %s." % str(dompc))
            return
        if "list_land" in self.switches:
            try:
            # ast.literal_eval will parse a string into a tuple
                x,y = literal_eval(self.lhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # literal_eval gets SyntaxError if it gets no argument, not ValueError
            except (SyntaxError, ValueError):
                caller.msg("Must provide 'x,y' values for a Land square.")
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            except Land.DoesNotExist:
                caller.msg("No land square matches (%s,%s)." % (x,y))
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            doms = ", ".join(str(dom) for dom in land.domains.all())
            caller.msg("Domains at (%s, %s): %s" % (x,y,doms))
            return
        if "list_char" in self.switches:
            player = caller.search(self.args)
            if not player:
                try:
                    dompc = PlayerOrNpc.objects.get(npc_name__iexact=self.args)
                except PlayerOrNpc.DoesNotExist:
                    dompc = None
                except PlayerOrNpc.MultipleObjectsReturned as err:
                    caller.msg("More than one match for %s: %s" % (self.args, err))
                    return
            else:
                if not hasattr(player, 'Dominion'):
                    caller.msg("%s has no Dominion object." % player)
                    return
                dompc = player.Dominion
            if not dompc:
                caller.msg("No character by name: %s" % self.args)
                return
            ruled = "None"
            owned = "None"
            family = None
            if player.db.char_ob and player.db.char_ob.db.family:
                family = player.db.char_ob.db.family
            if hasattr(dompc, 'ruler'):
                ruled = ", ".join(str(ob) for ob in Domain.objects.filter(ruler_id=dompc.ruler.id))
            if player.db.char_ob and player.db.char_ob.db.family:
                owned = ", ".join(str(ob) for ob in Domain.objects.filter(ruler__house__organization_owner__name__iexact=family))
            caller.msg("{wDomains ruled by {c%s{n: %s" % (dompc, ruled))
            caller.msg("{wDomains owned directly by {c%s {wfamily{n: %s" % (family, owned))
            return
        if "list" in self.switches:
            valid_fealty = ("Grayson", "Velenosa", "Redrain", "Valardin", "Thrax")
            fealty = self.args.capitalize()
            if fealty not in valid_fealty:
                caller.msg("Listing by fealty must be in %s, you provided %s." % (valid_fealty, fealty))
                return
            house = Ruler.objects.filter(house__organization_owner__name__iexact=fealty)
            if not house:
                caller.msg("No matches for %s." % fealty)
                return
            house = house[0]
            caller.msg("{wDomains of %s{n" % fealty)
            caller.msg("{wDirect holdings:{n %s" % ", ".join(str(ob) for ob in house.holdings.all()))
            if house.vassals.all():
                caller.msg("{wDirect vassals of %s:{n %s" % (fealty, ", ".join(str(ob) for ob in house.vassals.all())))
            pcdomlist = []
            for pc in PlayerDB.objects.filter(Dominion__ruler__isnull=False):
                if pc.db.char_ob and pc.db.char_ob.db.fealty == fealty:
                    if pc.db.char_ob.db.family != fealty:
                        for dom in pc.Dominion.ruler.holdings.all():
                            pcdomlist.append(dom)
            if pcdomlist:
                caller.msg("{wPlayer domains under %s:{n %s" % (fealty, ", ".join(str(ob) for ob in pcdomlist)))
                return
            return
        if "move" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.lhs))
                x,y = literal_eval(self.rhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # Syntax for no self.rhs, Type for no lhs, Value for not for lhs/rhs not being digits
            except (SyntaxError, TypeError, ValueError):
                caller.msg("Usage: @admdomain/move dom_id=(x,y)")
                caller.msg("You entered: %s" % self.args)
                return
            except Domain.DoesNotExist:
                caller.msg("No domain with that id.")
                return
            except Land.DoesNotExist:
                caller.msg("No land with coords (%s,%s)." % (x,y))
                return
            if land.free_area < dom.area:
                caller.msg("%s only has %s free area, need %s." % (str(land), land.free_area, dom.area))
                return
            old = dom.land
            dom.land = land
            dom.save()
            caller.msg("Domain %s moved from %s to %s." % (str(dom), str(old), str(land)))
            return
        # after this point, self.lhs must be the domain
        if not self.lhs:
            caller.msg("Must provide a domain number.")
            return
        try:
            id = int(self.lhs)
            dom = Domain.objects.get(id=id)
        except ValueError:
            caller.msg("Domain must be a number for the domain's ID.")
            return
        except Domain.DoesNotExist:
            caller.msg("No domain by that number.")
            return
        if "liege" in self.switches:
            try:
                house = Organization.objects.get(name__iexact=self.rhs)
                estate = house.assets.estate
            except (Organization.DoesNotExist, AttributeError):
                caller.msg("Family %s does not exist or has not been set up properly." % self.rhs)
                return
            dom.ruler.liege = estate
            dom.ruler.save()
            caller.msg("Liege of %s changed to %s." % (dom.ruler, estate))
            return
        if "view" in self.switches or not self.switches:
            mssg = dom.display()
            caller.msg(mssg)
            return
        if "delete" in self.switches:
            # this nullifies its values and removes it from play, doesn't fully delete it
            # keeps description/name intact for historical reasons
            dom.fake_delete()
            caller.msg("Domain %s has been removed." % dom.id)
            return
        # after this point, we're matching the switches to fields in the domain
        # to change them
        attr_switches = ("name", "desc", "title", "area", "stored_food", "tax_rate",
                         "num_mines", "num_lumber_yards", "num_mills", "num_housing",
                         "num_farms", "unassigned_serfs", "slave_labor_percentage",
                         "mining_serfs", "lumber_serfs", "farming_serfs", "mill_serfs",
                         "lawlessness", "amount_plundered", "income_modifier")
        switches = [switch for switch in self.switches if switch in attr_switches]
        if not switches:
            caller.msg("All switches must be in the following: %s. You passed %s." % (str(attr_switches), str(self.switches)))
            return
        if not self.rhs:
            caller.msg("You must pass a value to change the domain field to.")
            return
        # if switch isn't 'name', 'desc', or 'title', val will be a number
        if any(True for ob in switches if ob not in ("name", "desc", "title")):
            try:
                val = int(self.rhs)
            except ValueError:
                caller.msg("Right hand side value must be a number.")
                return
        else: # switch is 'name', 'desc', or 'title', so val will be a string
            val = self.rhs
        for switch in switches:
            # get the attribute with the name given by switch
            old = getattr(dom, switch)
            # set the attribute with the name given by switch
            setattr(dom, switch, val)
            caller.msg("Domain field %s changed from %s to %s." % (switch, old, val))
        dom.save()

class CmdAdmCastle(MuxPlayerCommand):
    """
    @admin_castle
    Usage:
        @admin_castle
        @admin_castle castle_id
        @admin_castle/view castle_id
        @admin_castle/desc castle_id=description
        @admin_castle/name castle_id=name
        @admin_castle/level castle_id=level
        @admin_castle/transfer castle_id=new domain_id
    """
    key = "@admin_castle"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admcastle", "@adm_castle"]
    def func(self):
        caller = self.caller
        if not self.args:
            castles = ", ".join(str(castle) for castle in Castle.objects.all())
            caller.msg("Castles: %s" % castles)
            return
        try:
            castle = Castle.objects.get(id=int(self.lhs))
        except (TypeError, ValueError, Castle.DoesNotExist):
            caller.msg("Could not find a castle for id %s." % self.lhs)
            return
        if not self.switches or "view" in self.switches:
            caller.msg(castle.display())
            return
        if not self.rhs:
            caller.msg("Must specify a right hand side argument for that switch.")
            return
        if "desc" in self.switches:
            old = castle.desc
            castle.desc = self.rhs
            castle.save()
            caller.msg("Desc changed from %s to %s." % (old, self.rhs))
            return
        if "name" in self.switches:
            old = castle.name
            castle.name = self.rhs
            castle.save()
            caller.msg("Name changed from %s to %s." % (old, self.rhs))
            return
        if "level" in self.switches:
            old = castle.level
            try:
                castle.level = int(self.rhs)
            except (TypeError, ValueError):
                caller.msg("Level must be a number.")
                return
            castle.save()
            caller.msg("Level changed from %s to %s." % (old, self.rhs))
            return
        if "transfer" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.rhs))
            except (TypeError, ValueError, Domain.DoesNotExist):
                caller.msg("Could not find a domain with id of %s" % self.rhs)
                return
            old = castle.domain
            castle.domain = dom
            castle.save()
            caller.msg("Castle's domain changed from %s to %s." % (str(old), str(dom)))
            return

class CmdAdmArmy(MuxPlayerCommand):
    """
    @admin_army
    Usage:
        @admin_army
        @admin_army army_id
        @admin_army/view army_id
        @admin_army/list domain_id
        @admin_army/name army_id=name
        @admin_army/desc army_id=desc
        @admin_army/unit army_id=type,amount,level,equipment
        @admin_army/setservice army_id=domain_id
        @admin_army/owner army_id=organization
        @admin_army/move army_id=(x,y)
    """
    key = "@admin_army"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases=["@admarmy", "@adm_army"]
    def func(self):
        caller = self.caller
        if not self.args:
            armies = ", ".join(str(army) for army in Army.objects.all())
            caller.msg("All armies: %s" % armies)
            return
        if "list" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.args))
                armies = ", ".join(str(army) for army in dom.armies.all())
                caller.msg("All armies for %s: %s" % (str(dom), armies))
                return
            except (Domain.DoesNotExist, TypeError, ValueError):
                caller.msg("@admin_army/list requires the number of a valid domain.")
                return
        # after this point, self.lhs will be our army_id
        try:
            army = Army.objects.get(id=int(self.lhs))
        except (Army.DoesNotExist, TypeError, ValueError):
            caller.msg("Invalid army id of %s." % self.lhs)
            return
        if "view" in self.switches or not self.switches:
            caller.msg(army.display())
            return
        # after this point, require a self.rhs
        if not self.rhs:
            caller.msg("Need an argument after = for 'army_id=<value>'.")
            return
        if "name" in self.switches:
            old = army.name
            army.name = self.rhs
            caller.msg("Name changed from %s to %s." % (old, self.rhs))
            army.save()
            return
        if "desc" in self.switches:
            old = army.desc
            army.desc = self.rhs
            caller.msg("Desc changed from %s to %s." % (old, self.rhs))
            army.save()
            return
        if "unit" in self.switches:
            u_types = ("infantry", "cavalry", "pike", "archers", "warships", "siege weapons")
            try:
                utype = self.rhslist[0].lower()
                quantity = int(self.rhslist[1])
                level = int(self.rhslist[2])
                equip = int(self.rhslist[3])
            except IndexError:
                caller.msg("Needs four arguments: type of unit, amount of troops, training level, equipment level.")
                return
            except (TypeError, ValueError):
                caller.msg("Amount of troops, training level, and equipment level must all be numbers.")
                return
            except:
                caller.msg("Example usage: @admdomain/unit 5=infantry,300,1,1")
                return
            if utype not in u_types:
                caller.msg("The first argument after = must be one of the following: %s" % str(u_types))
                return
            utype = type_from_str(utype)
            unit = army.find_unit(utype)
            if level < 0 or equip < 0:
                caller.msg("Negative numbers for level or equipment are not supported.")
                return
            if not unit:
                if quantity <= 0:
                    caller.msg("Cannot create a unit without troops.")
                    return
                unit = army.create(unit_type=utype, quantity=quantity, level=level, equipment=equip)
            else:
                if quantity <= 0:
                    unit.delete()
                    caller.msg("Quantity was 0. Unit deleted.")
                    return
                unit.unit_type = utype
                unit.quantity = quantity
                unit.level = level
                unit.equipment = equip
                unit.save()
            caller.msg("Unit created: %s" % unit.display())
            return
        if "owner" in self.switches:
            try:
                owner = AssetOwner.objects.get(organization_owner__name__iexact=self.rhs)
            except (AssetOwner.DoesNotExist, ValueError, TypeError):
                caller.msg("No org/family by name of %s." % self.rhs)
                return
            army.owner = owner
            army.save()
            caller.msg("Army's owner set to %s." % str(owner))
            return
        if "setservice" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.rhs))
            except (Domain.DoesNotExist, ValueError, TypeError):
                caller.msg("No domain found for id of %s." % self.rhs)
                return
            army.domain = dom
            army.save()
            caller.msg("Army's domain set to %s." % str(dom))
            return
        if "move" in self.switches:
            try:
                x,y = literal_eval(self.rhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # Syntax for no self.rhs, Type for no lhs, Value for not for lhs/rhs not being digits
            except (SyntaxError, TypeError, ValueError):
                caller.msg("Usage: @admarmy/move army_id=(x,y)")
                caller.msg("You entered: %s" % self.args)
                return
            except Land.DoesNotExist:
                caller.msg("No land with coords (%s,%s)." % (x,y))
                return
            army.land = land
            army.save()
            caller.msg("Army moved to (%s, %s)." % (x, y))
            return

class CmdAdmAssets(MuxPlayerCommand):
    """
    @admin_assets
    @admin_assets/player
    @admin_assets/org
    @admin_assets/setup player
    @admin_assets/money <owner id or name>=money
    @admin_assets/transfer <owner id or name>=<receiver id>, <value>
    @admin_assets/prestige <owner id or name>=<+/-value>/<reason>

    The /player and /org tags display AssetOwner lists
    that correspond to players and organizations, respectively.
    """
    key = "@admin_assets"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases=["@admassets", "@admasset", "@adm_asset", "@adm_assets"]
    def get_owner(self, args):
        if args.isdigit():
            owner = AssetOwner.objects.get(id=int(args))
        else:
            player_matches = AssetOwner.objects.filter(player__player__username__iexact=args)
            npc_matches = AssetOwner.objects.filter(player__npc_name__iexact=args)
            org_matches = AssetOwner.objects.filter(organization_owner__name__iexact=args)
            if player_matches:
                owner = player_matches[0]
            elif npc_matches:
                owner = npc_matches[0]
            elif org_matches:
                owner = org_matches[0]
            else:
                raise AssetOwner.DoesNotExist
        return owner
        
    def func(self):
        caller = self.caller
        if not self.switches and not self.args:
            assets = ", ".join(repr(owner) for owner in AssetOwner.objects.all())
            caller.msg(assets)
            return
        if 'player' in self.switches:
            assets = ", ".join(repr(owner) for owner in AssetOwner.objects.filter(player__player__isnull=False))
            caller.msg(assets)
            return
        if 'org' in self.switches:
            assets = ", ".join(repr(owner) for owner in AssetOwner.objects.filter(organization_owner__isnull=False))
            caller.msg(assets)
            return
        if "setup" in self.switches:
            player = caller.search(self.lhs)
            if not player:
                return
            nodom = not hasattr(player, 'Dominion')
            if not nodom:
                noassets = not hasattr(player.Dominion, 'assets')
            else:
                noassets = True
            setup_utils.setup_dom_for_char(player.db.char_ob, nodom, noassets)
            caller.msg("Dominion initialized for %s. No domain created." % (player))
            return
        try:
            owner = self.get_owner(self.lhs)
        except (TypeError, ValueError, AssetOwner.DoesNotExist):
            caller.msg("No assetowner found for %s." % self.lhs)
            return
        if not self.rhs:
            caller.msg(owner.display(), options={'box':True})
            return
        if "money" in self.switches or not self.switches:
            try:
                old = owner.vault
                owner.vault = int(self.rhs)
                owner.save()
                caller.msg("Money for %s changed from %s to %s." % (owner.owner, old, self.rhs))
                return
            except (AttributeError, ValueError, TypeError):
                caller.msg("Could not change account to %s." % self.rhs)
                return
        if "transfer" in self.switches:
            try:
                tar, amt = self.rhslist
                tar = self.get_owner(tar)
                amt = int(amt)
                old = owner.vault
                tarold = tar.vault
                owner.vault -= amt
                tar.vault += amt
                owner.save()
                tar.save()
                caller.msg("%s: %s, %s: %s before transfer." % (owner, old, tar, tarold))
                caller.msg("%s: %s, %s: %s after transfer of %s." % (owner, owner.vault, tar, tar.vault, amt))
                return
            except AssetOwner.DoesNotExist:
                caller.msg("Could not find an owner of id %s." % tar)
                return
            except (ValueError, TypeError, AttributeError):
                caller.msg("Invalid arguments of %s." % self.rhs)
                return
        if "prestige" in self.switches:
            rhslist = self.rhs.split("/")
            message = ""
            try:
                value = int(rhslist[0])
            except (ValueError, TypeError):
                caller.msg("Value must be a number.")
                return
            if len(rhslist) == 2:
                message = rhslist[1]
            affected = owner.adjust_prestige(value)
            caller.msg("You have adjusted %s's prestige by %s." % (owner, value))
            for obj in affected:
                obj.msg("%s adjusted %s's prestige by %s for the following reason: %s" % (caller, owner, value, message))
            # post to a board about it
            from game.gamesrc.commands.bboards import get_boards
            boards = get_boards(caller)
            boards = [ob for ob in boards if ob.key == "Prestige Changes"]
            board = boards[0]
            msg = "{wName:{n %s\n" % str(owner)
            msg += "{wAdjustment:{n %s\n" % value
            msg  += "{wGM:{n %s\n" % caller.key.capitalize()
            msg += "{wReason:{n %s\n" % message
            board.bb_post(poster_obj=caller, msg=msg, subject="Prestige Change for %s" % str(owner))
        

class CmdAdmOrganization(MuxPlayerCommand):
    """
    @admin_org
    Usage:
        @admin_org <org name or number>
        @admin_org/all
        @admin_org/members <org name or number>
        @admin_org/boot <org name or number>=<player>
        @admin_org/add <org name or number>=<player>,<rank>
        @admin_org/setrank <org name or number>=<player>,<rank>
        @admin_org/create <org name>
        @admin_org/desc <org name or number>=<desc>
        @admin_org/name <org name or number>=<new name>
        @admin_org/title <orgname or number>=<rank>,<name>
        @admin_org/femaletitle <orgname or number>=<rank>,<name>
    """
    key = "@admin_org"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases=["@admorg", "@adm_org"]
    def func(self):
        caller = self.caller
        if not self.args:
            if 'all' in self.switches:
                orgs = ", ".join(repr(org) for org in Organization.objects.all())
            else:
                orgs = ", ".join(repr(org) for org in Organization.objects.all() if org.members.filter(player__player__isnull=False))
            caller.msg("{wOrganizations:{n %s" % orgs)
            return
        try:
            if self.lhs.isdigit():
                org = Organization.objects.get(id=int(self.lhs))
            else:
                org = Organization.objects.get(name__iexact=self.lhs)
        except Organization.DoesNotExist:
            # if we had create switch and found no Org, create it
            if 'create' in self.switches:
                if self.lhs.isdigit():
                    caller.msg("Organization name must be a name, not a number.")
                    return
                org = Organization.objects.create(name=self.lhs)
                # create Org's asset owner also
                AssetOwner.objects.create(organization_owner=org)
                caller.msg("Created organization %s." % org)
                return
            caller.msg("No organization found for %s." % self.lhs)
            return
        if not self.switches:
            caller.msg(org.display())
            return
        # already found an existing org
        if 'create' in self.switches:
            caller.msg("Organization %s already exists." % org)
            return
        if 'members' in self.switches:
            caller.msg(org.display_members())
            return
        if 'boot' in self.switches:
            try:
                member = org.members.get(player__player__username__iexact=self.rhs)
                caller.msg("%s removed from %s." % (str(member), str(org)))
                member.fake_delete()
                return
            except Member.DoesNotExist:
                caller.msg("Could not remove member #%s." % self.rhs)
                return
        if 'desc' in self.switches:
            org.desc = self.rhs
            org.save()
            caller.msg("Description set to %s." % self.rhs)
            return
        if 'name' in self.switches:
            org.name = self.rhs
            org.save()
            caller.msg("Name set to %s." % self.rhs)
            return
        if 'add' in self.switches:
            try:
                if len(self.rhslist) > 1:
                    player = caller.search(self.rhslist[0])
                    rank = int(self.rhslist[1])
                else:
                    player = caller.search(self.rhs)
                    rank = 10
                dompc = player.Dominion
                matches = org.members.filter(player__player_id=player.id)
                if matches:
                    match = matches[0]
                    if match.deguilded:
                        match.deguilded = False
                        match.rank = rank
                        caller.msg("Readded %s to the org.")
                        match.save()
                        return
                    caller.msg("%s is already a member.")
                    return
                dompc.memberships.create(organization=org, rank=rank)
                caller.msg("%s added to %s at rank %s." % (dompc, org, rank))
                return
            except (AttributeError, ValueError, TypeError):
                caller.msg("Could not add %s. May need to run @admin_assets/setup on them." % self.rhs)
                return
        if 'title' in self.switches or 'femaletitle' in self.switches:
            male = not 'femaletitle' in self.switches
            try:
                rank,name = int(self.rhslist[0]),self.rhslist[1]
            except (ValueError, TypeError, IndexError):
                caller.msg("Invalid usage.")
                return
            if male:
                setattr(org, 'rank_%s_male' % rank, name)
                org.save()
            else:
                setattr(org, 'rank_%s_female' % rank, name)
                org.save()
            caller.msg("Rank %s title changed to %s." % (rank, name))
            return
            
        if 'setrank' in self.switches:
            try:
                member = Member.objects.get(organization_id=org.id,
                                            player__player__username__iexact=self.rhslist[0])
                member.rank = self.rhslist[1]
                member.save()
                caller.msg("%s set to rank %s." % (member, self.rhslist[1]))
            except Member.DoesNotExist:
                caller.msg("No member found by name of %s." % self.rhsl[0])
                return
            except (ValueError, TypeError, AttributeError, KeyError):
                caller.msg("Usage: @admorg/set_rank <org> = <player>, <1-10>")
                return

class CmdAdmFamily(MuxPlayerCommand):
    """
    @admin_family
    Usage:
        @admin_family <character>
        @admin_family/addparent <character>=<character parent>
        @admin_family/createparent <character>=<npc name>
        @admin_family/addchild <character>=<character child>
        @admin_family/createchild <character>=<npc name>
        @admin_family/addspouse <character>=<character spouse>
        @admin_family/createspouse <character>=<npc name>
        @admin_family/replacenpc <character>=<player>
        @admin_family/rmchild <character>=<character child>
        @admin_family/rmparent <character>=<character parent>
        @admin_family/rmspouse <character>=<character spouse>
        @admin_family/alive <character>=<True or False>

    Add switches are used if both characters already exist, either
    as players or a Dominion npc. create switches are if only one
    exists, creating a Dominion npc as the child or parent. The
    replacenpc switch allows you to replace a Dominion npc with
    a player.
    """
    key = "@admin_family"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases=["@admfamily", "@adm_family"]
    
    def match_player(self, args):
        pcs = PlayerOrNpc.objects.filter(player__username__iexact=args)
        npcs = PlayerOrNpc.objects.filter(npc_name__iexact=args)
        matches = list(set(list(pcs) + list(npcs)))
        if not matches:
            self.caller.msg("No matches found for %s. They may not be added to Dominion." % args)
            return
        if len(matches) > 1:
            self.caller.msg("Too many matches for %s: %s." % (args, ", ".join(str(ob) for ob in matches)))
            return
        return matches[0]
    
    def func(self):
        caller = self.caller
        if not self.args:
            pcs = ", ".join(str(ob) for ob in PlayerOrNpc.objects.all())
            caller.msg("{wPlayer/NPCs in Dominion{n: %s" % pcs)
            return
        char = self.match_player(self.lhs)
        if not char:
            return
        if not self.switches:
            caller.msg("Family of %s:" % char)
            caller.msg(char.display_immediate_family())
            return
        if "createparent" in self.switches or "createchild" in self.switches or "createspouse" in self.switches:
            if PlayerOrNpc.objects.filter(npc_name=self.rhs):
                caller.msg("An npc with that name already exists.")
                return
        if "createparent" in self.switches:
            char.parents.create(npc_name = self.rhs)
            caller.msg("Created a parent named %s for %s." % (self.rhs, char))
            return
        if "createchild" in self.switches:
            char.children.create(npc_name = self.rhs)
            caller.msg("Created a child named %s for %s." % (self.rhs, char))
            return
        if "createspouse" in self.switches:
            char.spouses.create(npc_name = self.rhs)
            caller.msg("Created a spouse named %s for %s." % (self.rhs, char))
            return
        if "replacenpc" in self.switches:
            player = self.search(self.rhs)
            if hasattr(player, "Dominion"):
                caller.msg("Error. The player %s has Dominion set up." % player)
                caller.msg("This means we'd have two PlayerOrNpc objects, and one of them has to be deleted.")
                caller.msg("Get the administrator to resolve this.")
                return
            if char.player:
                caller.msg("%s already has %s defined as their player. Aborting." % (char, char.player))
                return
            char.player = player
            char.npc_name = None
            char.save()
            caller.msg("Character has been replaced by %s." % player)
            return
        if "alive" in self.switches:
            rhs = self.rhs.lower()
            alive = rhs != 'false'
            char.alive = alive
            char.save()
            caller.msg("%s alive status has been set to %s." % (char, alive))
            return
        tarchar = self.match_player(self.rhs)
        if not tarchar:
            return
        if "addparent" in self.switches:
            char.parents.add(tarchar)
            caller.msg("%s is now a parent of %s." % (tarchar, char))
            return
        if "addchild" in self.switches:
            char.children.add(tarchar)
            caller.msg("%s is now a child of %s." % (tarchar, char))
            return
        if "addspouse" in self.switches:
            char.spouses.add(tarchar)
            caller.msg("%s is now married to %s." % (tarchar, char))
            return
        if "rmparent" in self.switches:
            char.parents.remove(tarchar)
            caller.msg("%s is no longer a parent of %s." % (tarchar, char))
            return
        if "rmchild" in self.switches:
            char.children.remove(tarchar)
            caller.msg("%s has disowned %s. BAM. GET LOST, KID." % (char, tarchar))
            return
        if "rmspouse" in self.switches:
            char.spouses.remove(tarchar)
            caller.msg("%s and %s are no longer married." % (char, tarchar))
            return

class CmdSetRoom(MuxCommand):
    """
    @setroom
    Usage:
        @setroom/barracks <owner name>
        @setroom/market
        @setroom/bank
        @setroom/rumormill
        @setroom/home owner1,owner2,etc=entrance_id,entrance_id2,etc
        @setroom/homeaddowner owner1,owner2,etc
        @setroom/homermowner owner1,owner2,etc
        @setroom/none

    Sets the space you're currently in as being the place where the owner
    can execute their agent commands if it's barracks, or use a number
    of other commandsets based on the switch.

    Setting a home requires you to specify the IDs of the exits that lead
    into that room for it to work properly. @ex each exit to get its id,
    and then use them like '@setroom/home bob=374,375,352'.
    """
    key = "@setroom"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    allowed_switches = ("barracks", "market", "bank", "rumormill", "home",
                        "homeaddowner", "homermowner", "none")
    MARKETCMD = "commands.cmdsets.market.MarketCmdSet"
    BANKCMD = "commands.cmdsets.bank.BankCmdSet"
    RUMORCMD = "commands.cmdsets.rumor.RumorCmdSet"
    HOMECMD = "commands.cmdsets.home.HomeCmdSet"
    def func(self):
        DEFAULT_HOME = ObjectDB.objects.get(id=13)
        caller=self.caller
        if not (set(self.switches) & set(self.allowed_switches)):
            caller.msg("Please select one of the following: %s" % str(self.allowed_switches))
            return
        loc = caller.location
        if not loc or loc.typeclass_path != settings.BASE_ROOM_TYPECLASS:
            caller.msg("You are not in a valid room.")
            return 
        if "barracks" in self.switches:
            if not self.args:
                caller.msg("Valid owners: %s" % ", ".join(str(owner.owner) for owner in AssetOwner.objects.all()))
                return           
            players = AssetOwner.objects.filter(player__player__username__iexact=self.args)
            npcs = AssetOwner.objects.filter(player__npc_name__iexact=self.args)
            orgs = AssetOwner.objects.filter(organization_owner__name__iexact=self.args)
            matches = players | npcs | orgs
            if len(matches) > 1:
                caller.msg("Too many matches: %s" % ", ".join(owner.owner for owner in matches))
                return
            if not matches:
                caller.msg("No matches found. If you entered a player's name, they may not be set up for Dominion.")
                return
            owner = matches[0]
            tagname = str(owner.owner) + "_barracks"
            loc.tags.add(tagname)
            loc.db.barracks_owner = owner.id
            caller.msg("Barracks for %s have been set up in %s." % (owner.owner, loc))
            return
        if "market" in self.switches:
            if "MarketCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a market.")
                return
            loc.cmdset.add(self.MARKETCMD, permanent=True)
            loc.tags.add("market")
            caller.msg("%s now has market commands." % loc)
            return
        if "rumormill" in self.switches:
            if "RumorCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a rumormill.")
                return
            loc.cmdset.add(self.RUMORCMD, permanent=True)
            loc.tags.add("rumormill")
            caller.msg("%s now has rumor commands." % loc)
            return
        if "none" in self.switches:
            loc.cmdset.delete(self.MARKETCMD)
            loc.cmdset.delete(self.RUMORCMD)
            loc.cmdset.delete(self.BANKCMD)
            loc.cmdset.delete(self.HOMECMD)
            btags = [tag for tag in loc.tags.all() if "barracks" in tag]
            btags.extend(("market", "rumormill", "home", "bank"))
            for tag in btags:
                loc.tags.remove(tag)
                caller.msg("Removed tag %s" % tag)
            loc.attributes.remove("owner")
            if loc.db.entrances:
                for ent in loc.db.entrances:
                    ent.attributes.remove("err_traverse")
                    ent.attributes.remove("success_traverse")
            if loc.db.keylist:
                for char in loc.db.keylist:
                    if char.db.keylist and loc in char.db.keylist:
                        char.db.keylist.remove(loc)
            loc.attributes.remove("keylist")
            caller.msg("Room commands removed.")
            return
        if "bank" in self.switches:
            if "BankCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a bank.")
                return
            loc.cmdset.add(self.BANKCMD, permanent=True)
            loc.tags.add("bank")
            caller.msg("%s now has bank commands." % loc)
            return
        if ("home" in self.switches or "homeaddowner" in self.switches or
            "homermowner" in self.switches):
            owners = loc.db.owners or []
            targs = []
            rmkeys = []
            for lhs in self.lhslist:
                player = caller.player.search(lhs)
                if not player:
                    continue
                char = player.db.char_ob
                if not char:
                    caller.msg("No character found.")
                    continue
                targs.append(char)
            if "home" in self.switches:
                # remove keys from all old owners since 'home' overwrites
                rmkeys = [char for char in owners if char not in targs]
            elif "homermowner" in self.switches:
                rmkeys = targs
            if "home" in self.switches or "homeaddowner" in self.switches:
                for char in targs:
                    keys = char.db.keylist or []
                    if loc not in keys:
                        keys.append(loc)
                    char.db.keylist = keys
                    if char not in owners:
                        owners.append(char)
                    if "home" in self.switches:
                        if not char.home or char.home == DEFAULT_HOME:
                            char.home = loc
                            char.save()
            for char in rmkeys:
                keys = char.db.keylist or []
                if loc in keys:
                    keys.remove(loc)
                char.db.keylist = keys
                if char in owners:
                    owners.remove(char)
                if char.home == loc:
                    try:
                        # set them to default home square if this was their home
                        home = ObjectDB.objects.get(id=13)
                        char.home = home
                        char.save()
                    except Exception:
                        pass
            loc.tags.add("home")
            loc.db.owners = owners
            caller.msg("Owners set to: %s." % ", ".join(str(char) for char in owners))
            if "homeaddowner" in self.switches or "homermowner" in self.switches:
                return
            try:
                id_list = [int(val) for val in self.rhslist]
            except (ValueError, TypeError):
                caller.msg("Some of the rhs failed to convert to numbers.")
                caller.msg("Aborting setup.")
                return
            
            entrances = list(ObjectDB.objects.filter(id__in=id_list))
            valid_entrances = list(ObjectDB.objects.filter(db_destination=loc))
            invalid = [ent for ent in entrances if ent not in valid_entrances]
            if invalid:
                caller.msg("Some of the entrances do not connect to this room: %s" % ", ".join(str(ob) for ob in invalid))
                caller.msg("Valid entrances are: %s" % ", ".join(str(ob.id) for ob in valid_entrances))
                return
            for ent in entrances:
                ent.locks.add("usekey: perm(builders) or roomkey(%s)" % loc.id)
            if entrances:
                caller.msg("Setup entrances: %s" % ", ".join(str(ent) for ent in entrances))
                old_entrances = loc.db.entrances or []
                old_entrances = [ob for ob in old_entrances if ob not in entrances]
                for ob in old_entrances:
                    ob.locks.add("usekey: perm(builders)")
                if old_entrances:
                    caller.msg("Removed these old exits: %s" % ", ".join(str(ent) for ent in old_entrances))
                loc.db.entrances = entrances
            else:
                if loc.db.entrances:
                    entrances = loc.db.entrances
                    caller.msg("Current entrances are: %s" % ", ".join(str(ob.id) for ob in entrances))
                    caller.msg("Valid entrances are: %s" % ", ".join(str(ob.id) for ob in valid_entrances))
                caller.msg("No entrances set. To change this, run the command again with valid entrances.")
                if not entrances:
                    caller.msg("This room will initialize itself to all entrances the first time +home is used.")
            if "HomeCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a home.")
                return
            loc.cmdset.add(self.HOMECMD, permanent=True)
            caller.msg("%s now has home commands." % loc)
        
            
                

# Player/OOC commands for dominion---------------------

class CmdDomain(MuxPlayerCommand):
    """
    @domain
    Usage:
        @domain

    Commands to view and control your domain.

    Unfinished
    """
    key = "@domain"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@domains"]
    def func(self):
        caller = self.caller
        commanded_orgs = []
        if not hasattr(caller, 'Dominion'):
            caller.msg("You don't have access to any domains.")
            return
        dompc = caller.Dominion
        if not hasattr(dompc.assets, 'estate'):
            owned = []
        else:
            owned = dompc.assets.estate.holdings.all()
        ruled = Domain.objects.filter(ruler__castellan=dompc)
        orgs = dompc.current_orgs
        for org in orgs:
            if org.access(caller, 'command'):
                if hasattr(org.assets, 'estate'):
                    commanded_orgs.extend(org.assets.estate.holdings.all())
        ruled = set(ruled) | set(commanded_orgs)
        doms = set(owned) | set(ruled)
        if not doms:
            caller.msg("No domains found.")
            return
        if not self.args:
            ruledlist = ", ".join(str(ob) for ob in ruled if ob not in owned)
            ownlist = ", ".join(str(ob) for ob in owned)
            caller.msg("Your domains:")
            if ownlist:
                caller.msg("Domains owned by you: %s" % ownlist)
            if ruledlist:
                caller.msg("Domains you can command: %s" % ruledlist)
            return
        try:
            doms = [ob.id for ob in doms]
            doms = Domain.objects.filter(id__in=doms)
            if self.lhs.startswith('#'):
                self.lhs.lstrip('#')
            if self.lhs.isdigit():
                dom = doms.get(id=int(self.lhs))
            else:
                dom = doms.get(name__iexact=self.lhs)
        except Domain.DoesNotExist:
            caller.msg("No domain found.")
            return
        if not self.switches:
            caller.msg(dom.display())
            return

class CmdArmy(MuxPlayerCommand):
    """
    @army

    Usage:
        @army
        @army <army name or number>
        @army/countermand <army name or number>
        @army/explore <army name or number>
        @army/train <army name or number>
        @army/quell <army name or number>
        @army/raid <army name or number>=<domain name or number>
        @army/invade <army name or number>=<domain name or number>
        @army/march <army name or number>=x,y
        
    """
    key = "@army"
    locks = "cmd:all()"
    help_category = "Dominion"
    def func(self):
        caller = self.caller
        if not hasattr(caller, 'Dominion'):
            caller.msg("You have no armies to command.")
            return
        owned = Army.objects.filter(owner__player__player=caller)
        ruled = Army.objects.filter(domain__ruler__castellan__player=caller)
        house_ruled = Army.objects.filter(owner__estate__castellan__player=caller)
        armies = owned | ruled | house_ruled
        if not self.args:
            caller.msg("Your armies:")
            caller.msg(", ".join(repr(army) for army in armies))
            return
        try:
            if self.lhs.startswith('#'):
                self.lhs.lstrip('#')
            if self.lhs.isdigit():
                army = armies.get(id=int(self.lhs))
            else:
                army = armies.get(name__iexact=self.lhs)
        except:
            caller.msg("No armies found by that name or number.")
            return
        if not self.switches:
            caller.msg(army.display())
            return
        if 'countermand' in self.switches:
            val = army.countermand()
            if val:
                caller.msg("You have countermanded their orders. %s has been refunded %s coins." % (army.domain, val))
            else:
                caller.msg("No orders were erased.")
            return
        # if we have active orders, we cannot issue the army new ones
        if army.orders.filter(complete=False):
            caller.msg("That army has active orders. You must countermand them before issuing new ones.")
            return
        if 'explore' in self.switches:
            if army.land != army.domain.land:
                caller.msg("%s must return to its home domain's square to explore.")
                return
            if armies.filter(orders__complete=False, orders__type=Orders.EXPLORE):
                caller.msg("An army under your command already has an exploration order. Only one army can explore per week.")
                return
            army.orders.create(type=Orders.EXPLORE)
        if 'march' in self.switches:
            pass
        if 'train' in self.switches:
            pass
        if 'quell' in self.switches:
            pass
        if 'raid' in self.switches:
            pass
        if 'invade' in self.switches:
            pass
        

class CmdOrganization(MuxPlayerCommand):
    """
    @org
    Usage:
        @org
        @org <name>
        @org/invite <player>[=<org name>]
        @org/setrank <player>=<rank>[, <org name>]
        @org/boot <player>[=<org name>]
        @org/setruler <player>[=<org name>]
        @org/perm <type>=<rank>[, <org name>]
        @org/rankname <name>=<rank>[, <org name>][,male or female]
        @org/accept
        @org/decline
        @org/memberview <player>[=<org name>]

    Lists the houses/organizations your character is a member
    of. Give the name of an organization for more detailed information.
    @org/accept will accept an invtation to join an organization, while
    @org/decline will decline the invitation.

    @org/perm sets permissions for the organization. Use @org/perm with
    no arguments to see the type of permissions you can set.
    """
    key = "@org"
    locks = "cmd:all()"
    help_category = "Dominion"
    org_locks = ("edit", "boot", "withdraw", "setrank", "invite",
                 "setruler", "view", "guards", "build")
    def get_org_and_member(self, caller, myorgs, args):
        org = myorgs.get(name__iexact=args)
        member = caller.Dominion.memberships.get(organization=org)
        return org, member
    
    def disp_org_locks(self, caller, org):
        table = PrettyTable(["{wPermission{n", "{wRank{n"])
        for lock in self.org_locks:
            olock = org.locks.get(lock).split(":")
            if len(olock) > 1:
                olock = olock[1]
            table.add_row([lock, olock])
        caller.msg(table, options={'box':True})
    
    def func(self):
        caller = self.caller
        myorgs = Organization.objects.filter(Q(members__player__player=caller)
                                             & Q(members__deguilded=False))       
        if 'accept' in self.switches:
            org = caller.ndb.orginvite
            if not org:
                caller.msg("You have no current invitations.")
                return
            if org in myorgs:
                caller.msg("You are already a member.")
                caller.ndb.orginvite = None
                return
            # check if they were previously booted out, then we just have them rejoin
            try:
                deguilded = caller.Dominion.memberships.get(Q(deguilded=True)
                                                            & Q(organization=org))
                deguilded.deguilded = False
                deguilded.rank = 10
                deguilded.save()
            except Member.DoesNotExist:
                caller.Dominion.memberships.create(organization=org)
            caller.msg("You have joined %s." % org.name)
            org.msg("%s has joined %s." % (caller, org.name))
            return
        if 'decline' in self.switches:
            org = caller.ndb.orginvite
            if not org:
                caller.msg("You have no current invitations.")
                return
            caller.msg("You have declined the invitation to join %s." % org.name)
            caller.ndb.orginvite = None
            return
        if not self.args:
            if not myorgs:
                caller.msg("You are not a member of any organizations.")
                return
            if len(myorgs) == 1:
                if "perm" in self.switches:
                    self.disp_org_locks(caller, myorgs[0])
                    return
                member = caller.Dominion.memberships.get(organization=myorgs[0])
                caller.msg(myorgs[0].display(member), options={'box':True})
                return
            caller.msg("Your organizations: %s" % ", ".join(org.name for org in myorgs))
            return
        if not self.switches:
            try:
                org, member = self.get_org_and_member(caller, myorgs, self.lhs)
                caller.msg(org.display(member), options={'box':True})
                return
            except Organization.DoesNotExist:
                caller.msg("You are not a member of any organization named %s." % self.lhs)
                return
        if 'perm' in self.switches:
            ltype = self.lhs.lower() if self.lhs else ""
            if ltype not in self.org_locks:
                caller.msg("Type must be one of the following: %s" % ", ".join(self.org_locks))
                return
        elif 'rankname' in self.switches:
            rankname = self.lhs
        else:
            player = caller.search(self.lhs)
            if not player:
                return
        if 'setrank' in self.switches or 'perm' in self.switches or 'rankname' in self.switches:
            if not self.rhs:
                caller.msg("You must supply a rank number.")
                return
            if len(myorgs) < 2:
                # if they supplied the org even though they don't have to
                if len(self.rhslist) > 1:
                    self.rhs = self.rhslist[0]
                if not self.rhs.isdigit():
                    caller.msg("Rank must be a number.")
                    return
                org = myorgs[0]
                member = caller.Dominion.memberships.get(organization=org)
                rank = int(self.rhs)
            else:
                if len(self.rhslist) < 2:
                    caller.msg("You belong to more than one organization, so must supply both rank number and the organization name.")
                    return
                try:
                    org, member = self.get_org_and_member(caller, myorgs, self.rhslist[1])
                    rank = int(self.rhslist[0])
                except Organization.DoesNotExist:
                    caller.msg("You are not a member of any organization named %s." % self.rhslist[1])
                    return
                except (ValueError, TypeError, AttributeError, KeyError):
                    caller.msg("Invalid syntax. @org/setrank player=rank,orgname")
                    return
            if rank < 1 or rank > 10:
                caller.msg("Rank must be between 1 and 10.")
                return
            # setting permissions
            if 'perm' in self.switches:
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit permissions.")
                    return
                org.locks.add("%s:rank(%s)" % (ltype, rank))
                caller.msg("Permission %s set to require rank %s or higher." % (ltype, rank))
                return
            if 'rankname' in self.switches:
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit rank names.")
                    return
                maleonly = femaleonly = False
                if len(self.rhslist) == 3:
                    if self.rhslist[2].lower() == "male":
                        maleonly = True
                    elif self.rhslist[2].lower () == "female":
                        femaleonly = True
                if not femaleonly:
                    setattr(org, "rank_%s_male" % rank, rankname)
                    caller.msg("Title for rank %s male characters set to: %s" % (rank, rankname))
                if not maleonly:
                    setattr(org, "rank_%s_female" % rank, rankname)
                    caller.msg("Title for rank %s female characters set to: %s" % (rank, rankname))
                org.save()
                return
            # 'setrank' now
            if not org.access(caller, 'setrank'):
                caller.msg("You do not have permission to change ranks.")
                return           
            if rank < member.rank:
                caller.msg("You cannot set someone to be higher rank than yourself.")
                return
            try:
                tarmember = player.Dominion.memberships.get(organization=org)
            except Member.DoesNotExist:
                caller.msg("%s is not a member of %s." % (player, org))
                return
            if tarmember.rank <= member.rank:
                caller.msg("You cannot change the rank of someone equal to you or higher.")
                return
            tarmember.rank = rank
            tarmember.save()
            caller.msg("You have set %s's rank to %s." % (player, rank))
            player.msg("Your rank has been set to %s by %s." % (rank, caller))
            return
        # other switches can omit the org name if we're only a member of one org   
        if not self.rhs:
            if len(myorgs) > 1:
                caller.msg("You belong to more than one organization and must give its name.")
                return
            if not myorgs:
                caller.msg("You are not in any organizations.")
                return
            org = myorgs[0]
            member = caller.Dominion.memberships.get(organization=org)
        else:
            try:
                org, member = self.get_org_and_member(caller, myorgs, self.rhs)
            except Organization.DoesNotExist:
                caller.msg("You are not a member of any organization named %s." % self.rhs)
                return
        if 'invite' in self.switches:
            if not org.access(caller, 'invite'):
                caller.msg("You do not have permission to invite new members.")
                return
            if Member.objects.filter(Q(deguilded=False)
                                     & Q(organization=org)
                                     & Q(player__player=player)).exists():
                caller.msg("They are already a member of your organization.")
                return
            char = player.db.char_ob
            if not hasattr(player, 'Dominion'):
                setup_utils.setup_dom_for_char(char)
            if not player.is_connected:
                caller.msg("%s must be logged in to be invited." % player)
                return
            if player.ndb.orginvite:
                caller.msg("Player already has an outstanding invite they must accept or decline.")
                return
            player.ndb.orginvite = org
            caller.msg("You have invited %s to %s." % (char, org.name))
            msg = "You have been invited by %s to join %s.\n" % (caller, org.name)
            msg = "To accept, type {w@org/accept %s{n. To decline, type {worg/decline %s{n." % (org.name, org.name)
            player.msg(msg)
            return
        try:
            tarmember = player.Dominion.memberships.get(organization=org)
        except Member.DoesNotExist:
            caller.msg("%s is not a member of %s." % (player, org))
            return
        if 'boot' in self.switches:
            if not org.access(caller, 'boot'):
                caller.msg("You do not have permission to boot players.")
                return
            if tarmember.rank <= member.rank:
                caller.msg("You cannot boot someone who is equal or higher rank.")
                return
            tarmember.fake_delete()
            caller.msg("Booted %s from %s." % (player, org))
            player.msg("You have been removed from %s by %s." % (org, caller))
            return
        if 'memberview' in self.switches:
            if org.secret and not org.access(caller, 'view'):
                caller.msg("You do not have permission to view players.")
                return
            caller.msg("{wMember info for {c%s{n" % tarmember)
            caller.msg(tarmember.display())
            return
        if 'setruler' in self.switches:
            if not org.access(caller, 'setruler'):
                caller.msg("You do not have permission to set who handles ruling of your organization's estates.")
                return
            house = org.assets
            try:
                ruler = Ruler.objects.get(house=house)
            except Ruler.DoesNotExist:
                ruler = Ruler.objects.create(house=house)
            old = ruler.castellan
            ruler.castellan = tarmember.player
            ruler.save()
            if old:
                caller.msg("Command of armies and holdings has passed from %s to %s." % (old, player))
                return
            caller.msg("%s has been placed in command of all of the armies and holdings of %s." % (player, org))
            return

class CmdAgents(MuxPlayerCommand):
    """
    @agents

    Usage:
        @agents
        @agents <org name>
        @agents/guard player,<id #>,<amt>
        @agents/recall player,<id #>,<amt>
        @agents/hire <type>,<level>,<amount>=<organization>
        @agents/desc <ID #>,<desc>
        @agents/name <ID #>=name

    Hires guards, assassins, spies, or any other form of NPC that has a
    presence in-game and can act on player orders. Agents can be owned
    either personally by a character, or on behalf of an organization. If
    the name of an organization is omitted, it is assumed you are ordering
    agents that are owned personally. To use any of the switches of this
    command, you must be in a space designated by GMs to be the barracks
    your agents report to.

    Switches:
    guard: The 'guard' switch assigns agents of the type and the
    amount to a given player, who can then use them via the +guard command.
    'name' should be what the type of guard is named - for example, name
    might be 'Thrax elite guards'.
    
    recall: Recalls guards of the given type listed by 'name' and the value
    given by the deployment number, and the amount listed. For example, you
    might have 10 Grayson House Guards deployed to player name A, and 15 to
    player B. To recall 10 of the guards assigned to player B, you would do
    @agents/recall grayson house guards,B,10=grayson.

    hire: enter the type, level, and quantity of the agents and the org you
    wish to buy them for. The type will generally be 'guard' for nobles,
    and 'thug' for crime families and the like. Cost = 25*(lvl+1)^3 in
    military resources for each agent.
        
    """
    key = "@agents"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@agent"]
    def find_barracks(self, owner):
        "find rooms that are tagged as being barracks for that owner"
        tagname = str(owner.owner) + "_barracks"
        rooms = ObjectDB.objects.filter(db_tags__db_key__iexact=tagname)
        return list(rooms)

    def get_cost(self, lvl, amt):
        cost = pow((lvl + 1),3) * 100
        return cost

    def get_guard_cap(self, gtype, char):
        if gtype == 0:
            srank = char.db.social_rank or 10
            return 17 - (2*srank)
        return 6

    def get_allowed_types_from_org(self, org):
        if ("noble" in org.category or "social" in org.category or
            "military" in org.category):
            return ["guards"]
        if "crime" in org.category:
            return ["thugs"]
    
    def func(self):
        caller = self.caller
        personal = Agent.objects.filter(owner__player__player=caller)
        orgs = [org.assets for org in Organization.objects.filter(members__player=caller.Dominion)
                    if org.access(caller, 'guards')]
        house = Agent.objects.filter(owner__organization_owner__members__player__player=caller,
                                         owner__organization_owner__in=[org.organization_owner for org in orgs])
        agents = personal | house
        if not self.args:
            caller.msg("{WYour agents:{n\n%s" % ", ".join(agent.display() for agent in agents), options={'box':True})
            barracks = self.find_barracks(caller.Dominion.assets)
            for org in orgs:
                barracks.extend(self.find_barracks(org))
            caller.msg("{wBarracks locations:{n %s" % ", ".join(ob.key for ob in barracks))
            return
        if not self.switches:
            try:
                org = Organization.objects.get(name__iexact=self.args,
                                               members__player=caller.Dominion)
            except Organization.DoesNotExist:
                caller.msg("You are not a member of an organization named %s." % self.args)
                return
            caller.msg(", ".join(agent.display() for agent in org.assets.agents.all()), options={'box':True})
            barracks = self.find_barracks(org.assets)
            caller.msg("{wBarracks locations:{n %s" % ", ".join(ob.key for ob in barracks))
            return       
        try:
            loc = caller.character.location
            owner = AssetOwner.objects.get(id=loc.db.barracks_owner)
            if owner != caller.Dominion.assets and not owner.organization_owner.access(caller, 'guards'):
                caller.msg("You do not have access to guards here.")
        except (AttributeError, AssetOwner.DoesNotExist, ValueError, TypeError):
            caller.msg("You do not have access to guards here.")
            return
        if not self.lhslist:
            caller.msg("Must provide arguments separated by commas.")
            return
        if 'guard' in self.switches:
            try:
                player,id,amt = self.lhslist
                amt = int(amt)
                id = int(id)
                targ = caller.search(player)
                if not targ:
                    caller.msg("Could not find player by name %s." % player)
                    return
                avail_agent = Agent.objects.get(id=id, owner=owner)
                if avail_agent.quantity < amt:
                    caller.msg("You tried to assign %s, but only have %s available." % (amt, avail_agent.quantity))
                    return
                try:
                    # assigning it to their character
                    targ = targ.db.char_ob
                    if not targ:
                        caller.msg("They have no character to assign to.")
                        return
                    cap = self.get_guard_cap(avail_agent.type, targ)
                    if targ.num_guards + amt > cap:
                        caller.msg("They can only have %s guards assigned to them." % cap)
                        return
                    avail_agent.assign(targ, amt)
                    caller.msg("Assigned %s %s to %s." % (amt, avail_agent.name, targ))
                    return
                except ValueError as err:
                    caller.msg(err)
                    return
            except Agent.DoesNotExist:
                caller.msg("%s owns no agents by that name." % owner.owner)
                agents = Agent.objects.filter(owner=owner)
                caller.msg("{wAgents:{n %s" % ", ".join("%s (#%s)" % (agent.name, agent.id) for agent in agents))
                return
            except ValueError:
                caller.msg("Invalid usage: provide player, ID, and amount, separated by commas.")
                return
        if 'recall' in self.switches:
            try:
                pname,id,amt = self.lhslist
                player = caller.search(pname)
                if not player:
                    caller.msg("No player found by %s." % pname)
                    return
                amt = int(amt)
                id = int(id)
                if amt < 1:
                    raise ValueError
                agent = Agent.objects.get(id=id, owner=owner)
                # look through our agent actives for a dbobj assigned to player
                agentob = agent.find_assigned(player)
                if not agentob:
                    caller.msg("No agents assigned to %s by %s." % (player, owner.owner))
                    return
                val = agentob.recall(amt)
                caller.msg("You have recalled %s from %s. They have %s left." % (val, player, agentob.quantity))
                return
            except Agent.DoesNotExist:
                caller.msg("No agents found for those arguments.")
                return
            except ValueError:
                caller.msg("Amount and ID must be positive numbers.")
                return
        if 'hire' in self.switches:
            try:
                org = caller.Dominion.active_orgs.get(name__iexact=self.rhs)
                owner = org.assets
            except Exception:
                caller.msg("You are not in an organization by that name.")
                return
            try:
                gtype,level,amt = self.lhslist[0], int(self.lhslist[1]), int(self.lhslist[2])
            except (IndexError, TypeError, ValueError):
                caller.msg("Please give the type, level, and amount of agents to buy.")
                return
            if not org.access(caller, 'agents'):
                caller.msg("You do not have permission to hire agents for %s." % org)
                return
            types = self.get_allowed_types_from_org(org)
            if gtype not in types:
                caller.msg("%s is not a type %s is allowed to hire." % (gtype, org))
                caller.msg("You can buy: %s" % ", ".join(types))
                return
            gtype_num = get_npc_type(gtype)
            cost = self.get_cost(level, amt)
            if owner.military < cost:
                caller.msg("Not enough military resources. Cost was %s." % cost)
                return
            owner.military -= cost
            owner.save()
            # get or create agents of the appropriate type
            try:
                agent = owner.agents.get(quality=level, type=gtype_num)
            except Agent.DoesNotExist:
                gname, gdesc = generate_default_name_and_desc(gtype_num, level, org)
                agent = owner.agents.create(quality=level, type=gtype_num, name=gname,
                                            desc = gdesc)
            agent.quantity += amt
            agent.save()
            caller.msg("You have bought %s %s." % (amt, agent))
            return
        if 'desc' in self.switches or 'name' in self.switches:
            try:
                agent = Agent.objects.get(id=int(self.lhslist[0]))
                if not agent.access(caller, 'agents'):
                    caller.msg("No access.")
                    return
                if 'desc' in self.switches:
                    agent.desc = self.lhslist[1]
                elif 'name' in self.switches:
                    agent.name = self.lhslist[1]
                agent.save()
                caller.msg("Changed.")
                return
            except (Agent.DoesNotExist, TypeError, ValueError, IndexError):
                caller.msg("User error.")
                return
            
        

class CmdFamily(MuxPlayerCommand):
    """
    @family

    Usage:
        @family
        @family <player>

    Displays family information about a given character, if
    available.
    """
    key = "@family"
    locks = "cmd:all()"
    help_category = "Dominion"
    def func(self):
        caller = self.caller
        if not self.args:
            player = caller
            show_private = True
        else:
            player = caller.search(self.args, quiet=True)
            show_private = False
        try:
            if not player:
                dompc = PlayerOrNpc.objects.get(npc_name__iexact=self.args)
            else:
                dompc = player.Dominion
            caller.msg("\n{c%s's{w family:{n" % dompc)
            famtree = dompc.display_immediate_family()
            if not famtree:
                famtree = "No relatives found for {c%s{n.\n" % dompc
            caller.msg(famtree)
            if player:
                try:
                    family = player.db.char_ob.db.family
                    fam_org = Organization.objects.get(name__iexact=family)
                    if not fam_org.members.filter(player=dompc, deguilded=False):
                        show_private = False
                    if show_private:
                        details = fam_org.display()
                    else:
                        details = fam_org.display_public()
                    caller.msg("%s family information:\n%s" % (family, details))
                    return
                except Exception:
                    # display nothing
                    pass
            return
        except Exception:
            caller.msg("No relatives found for {c%s{n." % self.args)
            return

max_proteges = {
    1: 7,
    2: 6,
    3: 5,
    4: 4,
    5: 3,
    6: 2,
    }

class CmdPatronage(MuxPlayerCommand):
    """
    @patron

    Usage:
        @patronage
        @patronage <player>
        @patronage/addprotege <player>
        @patronage/dismiss <player>
        @patronage/accept
        @patronage/reject
        @patronage/abandon

    Displays family information about a given character, if
    available.
    """
    key = "@patronage"
    locks = "cmd:all()"
    help_category = "Dominion"
    def display_patronage(self, dompc):
        patron = dompc.patron
        proteges = dompc.proteges.all()
        msg = "{wPatron and Proteges for {c%s{n:\n" % str(dompc)
        msg += "{wPatron:{n %s\n" % ("{c%s{n" % patron if patron else "None")
        msg += "{wProteges:{n %s" % ", ".join("{c%s{n" % str(ob) for ob in proteges)
        return msg
    def func(self):
        caller = self.caller
        try:
            dompc = self.caller.Dominion
        except Exception:
            dompc = setup_utils.setup_dom_for_char(self.caller.db.char_ob)
        if not self.args and not self.switches:        
            caller.msg(self.display_patronage(dompc), options={'box':True})
            return
        if self.args:
            player = caller.search(self.args)
            if not player:
                return
            char = player.db.char_ob
            if not char:
                caller.msg("No character found for %s." % player)
                return
            try:
                tdompc = player.Dominion
            except Exception:
                tdompc = setup_utils.setup_dom_for_char(char)
            if not self.switches:
                caller.msg(self.display_patronage(tdompc), options={'box':True})
                return
            if "addprotege" in self.switches:
                if not player.is_connected:
                    caller.msg("They must be online to add them as a protege.")
                    return
                if tdompc.patron:
                    caller.msg("They already have a patron.")
                    return
                num = dompc.proteges.all().count()
                psrank = caller.db.char_ob.db.social_rank
                tsrank = char.db.social_rank
                max = max_proteges.get(psrank, 0)
                if num >= max:
                    caller.msg("You already have the maximum number of proteges for your social rank.")
                    return
                # 'greater' social rank is worse. 1 is best, 10 is worst
                if psrank >= tsrank:
                    caller.msg("They must be a worse social rank than you to be your protege.")
                    return
##                # check if they're in any of the same organizations publicly
##                porgs = [member.organization for member in dompc.memberships.filter(secret=False)]
##                torgs = [member.organization for member in tdompc.memberships.filter(secret=False)]
##                for org in porgs:
##                    if org in torgs:
##                        caller.msg("You cannot be the patron for someone in the same organization as you.")
##                        return
                player.ndb.pending_patron = caller
                player.msg("{c%s {wwants to become your patron. Use @patronage/accept to accept" % caller.key.capitalize())
                player.msg("{wthis offer, or @patronage/reject to reject it.{n")
                caller.msg("{wYou have extended the offer of patronage to {c%s{n." % player.key.capitalize())
                return
            if "dismiss" in self.switches:
                if tdompc not in dompc.proteges.all():
                    caller.msg("They are not one of your proteges.")
                    return
                dompc.proteges.remove(tdompc)
                caller.msg("{c%s {wis no longer one of your proteges.{n" % char)
                player.msg("{c%s {wis no longer your patron.{n" % caller.key.capitalize())
                return
            caller.msg("Unrecognized switch.")
            return
        pending = caller.ndb.pending_patron
        if 'accept' in self.switches:
            if not pending:
                caller.msg("You have no pending invitation.")
                return
            dompc.patron = pending.Dominion
            dompc.save()
            caller.msg("{c%s {wis now your patron.{n" % pending.key.capitalize())
            pending.msg("{c%s {whas accepted your patronage, and is now your protege.{n" % caller.key.capitalize())
            caller.ndb.pending_patron = None
            return
        if 'reject' in self.switches:
            if not pending:
                caller.msg("You have no pending invitation.")
                return
            caller.msg("You decline %s's invitation." % pending.key.capitalize())
            pending.msg("%s has declined your patronage." % caller.key.capitalize())
            caller.ndb.pending_patron = None
            return
        if 'abandon' in self.switches:
            old = dompc.patron          
            if old:
                dompc.patron = None
                dompc.save()
                old.player.msg("{c%s {rhas abandoned your patronage, and is no longer your protege.{n" % caller.key.capitalize())
                caller.msg("{rYou have abandonded {c%s{r's patronage, and are no longer their protege.{n" % old)
            else:
                caller.msg("You don't have a patron.")
            return
        caller.msg("Unrecognized switch.")
        return

# Character/IC commands------------------------------

# command to summon/order guards we own
class CmdGuards(MuxCommand):
    """
    +guards

    Usage:
        +guards
        +guards/summon <name>
        +guards/dismiss <name>
        +guards/attack <guard>=<victim>
        +guards/kill <guard>=<victim>
        +guards/stop <guard>
        +guards/follow <guard>=<person to follow>
    """
    key = "+guards"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@guards", "guards", "+guard", "@guard", "guard"]
    def func(self):
        caller = self.caller
        guards = caller.db.assigned_guards or []
        if not guards:
            caller.msg("You have no guards assigned to you.")
            return
        if not self.args and not self.switches:
            for guard in guards:
                caller.msg(guard.display())
                return
        if self.args:
            guard = ObjectDB.objects.object_search(self.lhs, candidates=guards)
            if not guard:
                _AT_SEARCH_RESULT(guard, caller, self.lhs)
                return
        else:
            if len(guards) > 1:
                caller.msg("You must specify which guards.")
                for guard in guards:
                    caller.msg(guard.display())
                    return
            guard = guards
        # object_search returns a list
        guard = guard[0]
        if not self.switches:
            guard.display()
            return
        if 'summon' in self.switches:
            if guard.location == caller.location:
                caller.msg("They are already here.")
                return
            if caller.location.db.docked_guards and guard in caller.location.db.docked_guards:
                guard.summon()
                return
            tagname = str(guard.agentob.agent_class.owner.owner) + "_barracks"
            barracks = ObjectDB.objects.filter(db_tags__db_key__iexact=tagname)
            if caller.location in barracks:
                guard.summon()
                return
            # if they're only one square away
            loc = guard.location or guard.db.docked
            if loc and caller.location.locations_set.filter(db_destination_id=loc.id):
                guard.summon()
                return
            caller.msg("Your guards aren't close enough to summon. They are at %s." % loc)
            return
        # after this point, need guards to be with us.
        if guard.location != caller.location:
            caller.msg("Your guards are not here to receive commands. You must summon them to you first.")
            return
        if 'dismiss' in self.switches:
            guard.dismiss()
            caller.msg("You dismiss %s." % guard.name)
            return
        if 'stop' in self.switches:
            guard.stop()
            caller.msg("You order your guards to stop what they're doing.")
            return
        targ = caller.search(self.rhs)
        if not targ:
            return
        if 'attack' in self.switches: 
            guard.attack(targ)
            caller.msg("You order %s to attack %s." % (guard.name, targ.name))
            return
        if 'kill' in self.switches:
            guard.attack(targ, lethal=True)
            caller.msg("You order %s to kill %s." % (guard.name, targ.name))
            return
        if 'follow' in self.switches:
            guard.follow(targ)
            caller.msg("You order %s to follow %s." % (guard.name, targ.name))
            return



# command to generate money/resources for ourself/org
class CmdTask(MuxCommand):
    """
    +task

    Usage:
        +task
        +task <organization name>
        +task <task ID>
        +task/history [<ID #>]
        +task/setfinishedrumors <ID #>=<text>
        +task/work <organization>,<resource type>
        +task/choose <task ID>=organization
        +task/story <task ID>,organization=<text>
        +task/rumors <task ID>,organization=<text>
        +task/altecho <task ID>,organization=<text>
        +task/abandon <task ID>=organization    
        +task/supportme <task id>[,organization]=<player1>,<player2>,...

    For a more complete walkthrough of how tasks work and how to use
    them, please read 'help task guide'.
    
    Tasks are an abstraction of performing work or gaining advantages
    for your organizations through roleplay. Tasks will describe various
    activities, and you'll seek out other characters to attempt to gain
    these objectives through roleplay.

    To choose a task that you'll attempt to get other players to support
    after RPing with them, use task/choose.

    To accomplish this, you ask other players to confirm that you achieved
    what you set out to do with the /supportme switch, sending them either
    a message based on the task, or an alternate message of your own
    creation through the /altecho switch.

    Please make notes with the /story switch that record how you
    accomplished your task. The /rumors switch is used to tell the IC
    rumors that other players will hear when your task is completed. You
    don't need to mention your name, only what other players might notice
    happening in town. If you'd prefer to wait until after you see what
    your supporters write, you can use /setfinishedrumors later.

    You can perform 7 tasks per week. You cannot gain the support of
    someone in the same organization as the task you are attempting to
    complete if that is their primary organization.    
    
    For example, Grand Duchess Esera is attempting to complete a task for
    Velenosa. She cannot ask for the support of Duke Niccolo, because he
    is a member of only Velenosa. However, she can ask for the assistance
    of Duke Hadrian Malvici, a vassal of Velenosa, because while he is a
    member of Velenosa, his primary organization is house Malvici.

    The /work switch allows you to consume one of your tasks per week in
    order to do some small service for your chosen organization, generating
    a nominal amount of money and resources. The 'resource type' should
    be either 'economic', 'military', or 'social'.
    """
    key = "+task"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@task", "task", "+tasks", "@tasks", "tasks"]

    def display_tasks(self, tasks, dompc):
        """
        Returns a table of tasks
        """
        table = PrettyTable(["{wActive{n", "{wTask#{n", "{wCategory{n",
                             "{wOrganization{n", "{wTask Name{n", "{wRating{n"])
        already_displayed = []
        for task in tasks:
            active = ""
            for org in task.org.filter(members__player=dompc, members__deguilded=False):
                if task.assigned_tasks.filter(Q(member__organization=org)
                                              & Q(member__player=dompc)
                                              & Q(finished=False)):
                    active = "{wX{n"
                else:
                    active = ""
                combo = (task, org)
                if combo in already_displayed:
                    continue
                already_displayed.append(combo)
                table.add_row([active, task.id, task.category, org.name,
                              task.name, task.difficulty])
        return str(table)

    def display_finished(self, tasks, dompc):
        """
        Returns a table of finished assignments
        """
        table = PrettyTable(["{wID #{n", "{wCategory{n",
                             "{wOrganization{n", "{wTask Name{n", "{wSupport{n"])
        for task in tasks:
            for ass in task.assigned_tasks.filter(Q(member__player=dompc)
                                                 & Q(finished=True)).distinct():
                table.add_row([ass.id, ass.task.category, ass.member.organization.name,
                              ass.task.name, ass.total])
        return str(table)

    def match_char_spheres_for_task(self, assignment, character):
        """
        Returns the spheres that the character can use for a
        given task
        """
        orgs = character.db.player_ob.Dominion.current_orgs
        return InfluenceCategory.objects.filter(orgs__in=orgs, tasks=assignment.task).distinct()
    
    def func(self):
        caller = self.caller
        try:
            dompc = self.caller.player.Dominion
        except Exception:
            dompc = setup_utils.setup_dom_for_char(self.caller)
        mytasks = Task.objects.filter(assigned_tasks__member__player=dompc).distinct()
        available = Task.objects.filter(org__members__player=dompc,
                                        org__members__deguilded=False,
                                        active=True).distinct()
        tasks_remaining = 7
        for member in dompc.memberships.filter(deguilded=False):
            tasks_remaining -= (member.work_this_week + member.tasks.filter(finished=False).count())
        if not self.switches and not self.args:
            # list all our active and available tasks
            caller.msg("{wAvailable/Active Tasks:{n")
            tasks = mytasks.filter(assigned_tasks__finished=False) | available
            caller.msg(self.display_tasks(tasks, dompc))
            caller.msg("You can perform %s more tasks." % tasks_remaining)            
            return
        if not self.switches:
            # display info on task
            tasks = mytasks | available
            try:
                task = Task.objects.get(id=int(self.args), id__in=tasks)         
            except ValueError:
                try:
                    org = Organization.objects.get(Q(name__iexact=self.args) &
                                                   Q(members__player=dompc) &
                                                   Q(members__deguilded=False))
                    caller.msg(self.display_tasks(org.tasks.filter(active=True), dompc))
                    return
                except Exception:
                    pass
                caller.msg("Task ID must be a number.")
                return
            except Task.DoesNotExist:
                caller.msg("No task by that number.")
                return
            caller.msg(self.display_tasks([task], dompc))
            caller.msg("{wDescription:{n\n%s" % task.desc)
            caller.msg("{wValid spheres of influence{n: %s" % task.reqs)
            assignments = task.assigned_tasks.filter(member__player=dompc, finished=False)
            for assign in assignments:
                echo = assign.current_alt_echo
                caller.msg("Current echo: %s" % echo)
                caller.msg("Current rumors (both yours and supporters): %s" % assign.story)
                caller.msg("Current story: %s" % assign.notes)
                org = assign.member.organization
##                supporters = assign.supporters.all()
##                if supporters:
##                    caller.msg("{wSupport for %s:{n %s" % (org.name, ", ".join(str(sup) for sup in supporters)))
            return
        if "history" in self.switches or "setfinishedrumors" in self.switches:
            # display our completed tasks
            if "history" in self.switches:
                tasks = mytasks.filter(assigned_tasks__finished=True)
            else:
                tasks = mytasks
            if not self.args:
                caller.msg(self.display_finished(tasks, dompc))
                return
            try:
                task = tasks.get(assigned_tasks__id=self.args)
                if "history" in self.switches:
                    ass = task.assigned_tasks.get(Q(id=self.args) &
                                                  Q(member__player=dompc) &
                                                  Q(finished=True))
                else:
                    ass = task.assigned_tasks.get(Q(id=self.args) &
                                                  Q(member__player=dompc))
                if "history" in self.switches:
                    caller.msg(ass.display())
                else: # set finished rumors
                    if ass.observer_text and ass.finished:
                        caller.msg("Once the task is finished, only a GM can change an existing rumor.")
                        return
                    ass.observer_text = self.rhs
                    ass.save()
                    caller.msg("Rumors changed to %s." % self.rhs)
            except Exception:
                caller.msg("No task found by that ID number.")
            return
        if "work" in self.switches:
            # do simple work for the Organization
            try:
                worktype = self.lhslist[1].lower()
                member = dompc.memberships.get(organization__name__iexact=self.lhslist[0],
                                               deguilded=False)
            except Member.DoesNotExist:
                caller.msg("You aren't in an organization by that name.")
                return
            except (TypeError, IndexError):
                caller.msg("Usage example: +task/work Grayson,social")
                return
            if tasks_remaining <= 0:
                caller.msg("You can only work or do tasks 7 times in a week.")
                return
            try:
                member.work(worktype)
            except ValueError as err:
                caller.msg(err)
                return
            caller.msg("You have performed work for %s." % member.organization.name)
            caller.msg("You and your organization have earned 1 %s resource." % worktype)
            return
        if "accept" in self.switches or "choose" in self.switches:
            # accept a task
            try:
                task = Task.objects.get(id=int(self.lhs), id__in=available)
                org = task.org.get(name__iexact=self.rhs)
                member = dompc.memberships.get(organization=org, deguilded=False)
            except Task.DoesNotExist:
                caller.msg("No task available by that number.")
                return
            except ValueError:
                caller.msg("You must supply a task number.")
                return
            except Organization.DoesNotExist:
                caller.msg("No org by that name.")
                return
            except Member.DoesNotExist:
                caller.msg("You are not a member of that organization.")
                return
            # check to make sure we don't already have an AssignedTask of this kind
            if member.tasks.filter(task=task, finished=False):
                caller.msg("You already have that task active.")
                return
            if tasks_remaining <= 0:
                caller.msg("You don't have any tasks remaining.")
                return
            task.assigned_tasks.create(week=get_week(), member=member)
            caller.msg("You have chosen the task: %s" % task.name)
            caller.msg(task.desc)
            return
        if "abandon" in self.switches:
            # delete an active AssignedTask
            
            try:
                org = Organization.objects.get(name__iexact=self.rhs)
                member = dompc.memberships.get(organization=org, deguilded=False)
                assignment = mytasks.get(id=int(self.lhs)).assigned_tasks.get(
                    member=member, finished=False)
            except Task.DoesNotExist:
                caller.msg("No task by that number.")
                return
            except ValueError:
                caller.msg("Task must by a number.")
                return         
            except AssignedTask.DoesNotExist:
                caller.msg("You do not have that task active.")
                return
            except (Organization.DoesNotExist, Member.DoesNotExist):
                caller.msg("No organization by that name.")
                return
            assignment.delete()
            caller.msg("Task abandoned.")
            # refund support?
            return
        if ("update" in self.switches or "story" in self.switches
            or "altecho" in self.switches or "announcement" in self.switches
            or "supportme" in self.switches or "rumors" in self.switches):
            # prompt the characters here to support me
            try:
                task = Task.objects.filter(assigned_tasks__finished=False, id__in=mytasks).distinct().get(
                                        id=int(self.lhslist[0]) )
                assignment = task.assigned_tasks.filter(member__player=dompc, finished=False)
                if not assignment:
                    caller.msg("That task isn't active for you.")
                    return
                if len(assignment) == 1:
                    assignment = assignment[0]
                else:
                    try:
                        assignment = assignment.get(member__organization__name=self.lhslist[1])
                    except Exception:
                        caller.msg("More than one task by that number active. You must specify the organization.")
                        return
            except Task.DoesNotExist:
                caller.msg("No task by that number.")
                return
            except ValueError:
                caller.msg("Task must be a number.")
                return
            if "update" in self.switches or "supportme" in self.switches:
                if not self.rhslist:
                    caller.msg("Must give at least one character to ask to support you.")
                    return
                playerlist = [caller.player.search(val) for val in self.rhslist]
                playerlist = [ob for ob in playerlist if ob]
                if not playerlist:
                    return
                org = assignment.member.organization
                if not assignment.notes or not assignment.notes.strip():
                    caller.msg("You have written no notes for how you completed this task.")
                    caller.msg("Please add them with task/story before asking for support.")
                    return
                if not assignment.observer_text:
                    caller.msg("You haven't written a {w+task/rumors{n for what everyone else will see "+
                               "when you finish this task. You can add it later with 'setfinishedrumors' "+
                               " to make it fit what your supporters enter. Please write some description that details "+
                               "what people might notice happening in the city when your task is "+
                               "finished - the details are up to you, as long as they can gain some "+
                               "general indication of what the npcs you influenced have been up to.")
                success = []
                warnmsg = "As a reminder, it is considered in bad form and is against the rules to "
                warnmsg += "ask someone OOCly for support, such as trying to convince them to help in pages. No OOC pressure, please."
                for pc in playerlist:
                    char = pc.db.char_ob
                    if not char:
                        continue
                    try:
                        dompc = pc.Dominion
                    except AttributeError:
                        continue
                    try:
                        if char.roster.current_account == caller.roster.current_account:
                            caller.msg("Don't ask for support from your own characters.")
                            continue
                    except AttributeError:
                        continue
                    # check if they can support caller
                    cooldowns = char.db.support_cooldown or {}
                    week=get_week()
                    current = assignment.supporters.filter(allocation__week=week, player=dompc)
                    if current:
                        caller.msg("{c%s {ris already supporting you in this task.{n" % char.name)
                        continue             
                    requests = char.db.requested_support or {}
                    if caller.id in requests:
                        caller.msg("{c%s {ralready has a pending support request from you.{n" % char.name)
                        if requests[caller.id] != assignment.id:
                            caller.msg("Replacing their previous request.")
                        else:
                            caller.msg("Sending them a reminder.")
                    
                    highest = char.db.player_ob.Dominion.memberships.filter(Q(secret=False) &
                                                                            Q(deguilded=False)).order_by('rank')
                    if highest:
                        highest = highest[0]
                    else:
                        highest = None
                    if highest in org.members.filter(Q(player=char.db.player_ob.Dominion)
                                          & Q(deguilded=False)):
                        caller.msg("You cannot gain support from a member whose highest rank is in the same organization as the task.")
                        continue
                    matches = self.match_char_spheres_for_task(assignment, char)
                    requests[caller.id] = assignment.id
                    char.db.requested_support = requests
                    mailmsg = "%s has asked you to support them in their task:" % caller.name
                    mailmsg += "\n" + assignment.current_alt_echo
                    mailmsg += "\nWhat this means is that they're asking for your character to use "
                    mailmsg += "influence that they have with different npc groups in order to help "
                    mailmsg += "them achieve the goals they indicate. This is represented by using "
                    mailmsg += "the '+support' command, filling out a form that indicates which npcs "
                    mailmsg += "you influenced on their behalf, how you did it, and what happened."
                    mailmsg += "\n\nYou can ask npcs to support them from any of the following "
                    mailmsg += "areas you have influence in: %s" % ", ".join(str(ob) for ob in matches)              
                    mailmsg += "\n\nThe support command has the usage of {wsupport %s{n, then " % caller
                    mailmsg += "adding fields that indicate how the npcs you influenced are helping them "
                    mailmsg += "out. '{w+support/note{n' Lets you state OOCly to GMs what occurs, while "
                    mailmsg += "'{wsupport/rumors{n' lets you write a short blurb that is displayed as a "
                    mailmsg += "rumor that other characters might hear around the city, noting what's "
                    mailmsg += "going on. To show how much support you're throwing their way, you use "
                    mailmsg += "{wsupport/value <organization>,<category>=<amount>{n. For example, if "
                    mailmsg += "you wanted to have sailors loyal to House Thrax pitch in to help, you "
                    mailmsg += "would do {wsupport/value thrax,sailors=2{n to use 2 points from your "
                    mailmsg += "support pool, representing the work your character is doing behind the "
                    mailmsg += "scenes, talking to npcs on %s's behalf.\n" % caller
                    mailmsg += "Pledging a value of 0 will give them 1 free point, while additional points "
                    mailmsg += "are subtracted from your available pool. You can "
                    mailmsg += "also choose to fake your support with the /fake switch. Your current pool "
                    remaining = char.db.player_ob.Dominion.remaining_points
                    mailmsg += "at the time of this message is %s points remaining." % remaining
                    mailmsg += "\nIf you decide to give them support, you finalize your choices with "
                    mailmsg += "'{wsupport/finish{n' once you have finished the form."
                    mailmsg += "\n\n" + warnmsg
                    pc.inform(mailmsg, category="Support Request", append=False)
                    success.append(char)
                if not success:
                    return
                caller.msg("You ask for the support of %s." % ", ".join(char.name for char in success))
                caller.msg(warnmsg)
                return      
            if "story" in self.switches:
                if not self.rhs:
                    caller.msg("You must supply a message.")
                    return
                assignment.notes = self.rhs
                assignment.save()
                caller.msg("Story for this assignment now is:\n%s" % assignment.notes)
                return
            if "altecho" in self.switches:
                if self.rhs:
                    assignment.alt_echo = "%s;%s" % (self.rhs, assignment.alt_echo)
                    assignment.save()
                if assignment.current_alt_echo:
                    msg = assignment.current_alt_echo
                else:
                    msg = task.room_echo
                caller.msg("The message sent to the room when you ask for support " +
                           "is now: %s" % msg)
                return
            if "announcement" in self.switches or "rumors" in self.switches:
                if not self.rhs:
                    caller.msg("You must supply a message.")
                    return
                assignment.observer_text = self.rhs
                assignment.save()
                caller.msg("The text other characters will read about when you finish your task is now:\n%s" % self.rhs)
                return
        caller.msg("Unrecognized switch.")
        return

class CmdSupport(MuxCommand):
    """
    +support

    Usage:
        +support
        +support <character>
        +support/decline <character>
        +support/fake
        +support/value <organization>,<sphere of influence>=<amount>
        +support/notes <notes>
        +support/rumors <text>
        +support/finish
        +support/abandon
        +support/change <id>,<category>[,org]=<new amount>
        +support/view <id>

    Pledges your support to a character who has executed a task. Pledging a
    value of 0 will give a free point to the player you are supporting if
    you aren't supporting them in other tasks this week. If you wish to only
    pretend to support them, you may use the /fake flag.

    Support is an abstraction that represents your participation or approval
    of someone's RP efforts. For example, their character may be attempting
    to influence public opinion in some way through a task, and your support
    indicates that your character goes along with it in some way. Economic
    tasks may represent maneuvering of financial resources that you agree to,
    and military tasks may represent the pledging of military support, or
    that you agreed that their actions won them reknown in some way.

    To pledge support, first +support a character, then fill the required
    fields, then use /finish. Value is 0 if not specified. For your org,
    you must specify a name and a field of the organization's influence
    which matches a requirement of the task. Notes are your own notes about
    what you did in the task, which may be viewed later. An announcement
    is later added to the historical record of the task's effects if it
    is completed, describing what observers can see as a result of the task.
    For example, you might describe how npcs you influenced worked to help
    complete what was asked for. Use /rumors to set this.

    Example of how to pledge support to a request:
    
    +support esera
    +support/value redrain,nobles=3
    +support/value redrain,merchants=2
    +support/notes I spoke to my vassals, encouraging them to strengthen
      our alliance with Velenosa.
    +support/rumors Demand for imports of Velenosan silk has increased
      among House Redrain. Their merchants can't seem to get enough of it.
    +support/finish
    """
    key = "+support"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["support"]

    def disp_supportform(self):
        caller = self.caller
        form = caller.db.supportform
        if form:
            try:
                caller.msg("Building support for a task for %s." % form[0])
                caller.msg("Fake: %s" % form[1])
                for s_id in form[2]:
                    sphere = SphereOfInfluence.objects.get(id=s_id)
                    msg = "Organization: %s, Category: %s, Amount: %s" % (sphere.org, sphere.category, form[2][s_id])
                    caller.msg(msg)            
                caller.msg("Notes:\n%s" % form[3])
                caller.msg("Rumors:\n%s" % form[4])       
                caller.msg("Once all fields are finished, use /finish to commit.")
            except (TypeError, KeyError, IndexError):
                caller.msg("{rEncountered a supportform with invalid structure. Resetting the attribute. Please start over.{n")
                print "%s had an invalid supportform. Wiping the attribute." % caller
                caller.attributes.remove("supportform")
                return

    def get_support_table(self):
        caller = self.caller
        dompc = self.caller.db.player_ob.Dominion
        week = get_week()
        supports = dompc.supported_tasks.filter(Q(task__finished=False)
                                                #&  Q(allocation__week=week)
                                                ).distinct()
        if supports:
            caller.msg("Open tasks supported:")
            table = PrettyTable(["{wID{n", "{wTask Name{n", "PC", "{wAmt{n"])
            for sup in supports:
                table.add_row([sup.id, sup.task.task.name,
                               str(sup.task.member), sup.rating])
            caller.msg(str(table))
    
    def func(self):
        week = get_week()
        caller = self.caller
        requests = caller.db.requested_support or {}
        dompc = self.caller.db.player_ob.Dominion
        cooldowns = dompc.support_cooldowns
        remaining = dompc.remaining_points
        max_points = caller.max_support
        form = caller.db.supportform
        if not self.args and not self.switches:
            # display requests and cooldowns
            chars = [ObjectDB.objects.get(id=id) for id in requests.keys()]
            chars = [ob for ob in chars if ob]
            msg = "Pending requests: "
            for char in chars:
                if not char:
                    continue
                try:
                    atask = AssignedTask.objects.get(id=requests[char.id])
                except AssignedTask.DoesNotExist:
                    import traceback
                    traceback.print_exc()
                    caller.msg("Error: Could not find a task for request from %s." % char)
                    caller.msg("Removing them from this list. Please run +support again.")
                    del requests[char.id]
                    caller.db.requested_support = requests
                    return
                msg += "%s (valid categories: %s)\n" % (char, atask.task.reqs)
            caller.msg(msg)
            table = PrettyTable(["{wName{n", "{wMax Points Allowed{n"])
            for id in cooldowns:
                try:
                    char = ObjectDB.objects.get(id=id)
                except Exception:
                    continue
                table.add_row([char.key, cooldowns[id]])
            caller.msg(str(table))
            self.get_support_table()          
            caller.msg("{wSupport points remaining:{n %s" % remaining)
            for memb in dompc.memberships.filter(deguilded=False):
                msg = "{wPool share for %s:{n %s" % (memb.organization, memb.pool_share)
                msg += ", {wCategory ratings:{n %s" % ", ".join("%s: %s" % (ob.category, ob.rating) for ob in memb.organization.spheres.all())
                caller.msg(msg)
            self.disp_supportform()
            return
        if "decline" in self.switches:
            char = caller.player.search(self.args)
            if not char:
                return
            char = char.db.char_ob
            try:
                del requests[char.id]
            except KeyError:
                caller.msg("No request found for that player.")
            caller.msg("You have declined the support request by %s." % char)
            return
        if "view" in self.switches:
            try:
                id = int(self.args)
                sup = dompc.supported_tasks.get(id=id)
            except (TypeError, ValueError, TaskSupporter.DoesNotExist):
                caller.msg("No support given by that ID.")
                self.get_support_table()
                return
            caller.msg("{wID{n: %s" % sup.id)
            caller.msg("{wCharacter{n: %s" % sup.task.member)
            alloclist = sup.allocation.all()
            for alloc in alloclist:
                caller.msg("{wOrganization{n: %s, Sphere: %s, Amount: %s" % (alloc.sphere.org, alloc.sphere.category, alloc.rating))
            return
        if "change" in self.switches:
            try:
                id = self.lhslist[0]
                category = self.lhslist[1]
                sup = dompc.supported_tasks.filter(task__finished=False).get(id=id)
                if len(self.lhslist) > 2:
                    org = dompc.current_orgs.get(name__iexact=self.lhslist[2])
                else:
                    org = dompc.current_orgs[0]
                sphere = org.spheres.get(category__name__iexact=category)             
                val = int(self.rhs)
                targmember = sup.task.member
                member = org.members.get(player=dompc)
                if val <= 0:
                    raise ValueError
                supused = sup.allocation.get(week=week, sphere=sphere)
            except IndexError:
                caller.msg("Must specify both the ID and the category name.")
                self.get_support_table()
                return
            except (TypeError, ValueError):
                caller.msg("Value cannot be negative.")
                return
            except Organization.DoesNotExist:
                caller.msg("No organization by that name.")
                caller.msg("Your organizations are: %s" % ", ".join(str(ob) for ob in dompc.current_orgs))
                return
            except SphereOfInfluence.DoesNotExist:
                caller.msg("No category by that name for that organization.")
                caller.msg("Valid spheres for %s: %s" % (org, ", ".join(str(ob.category) for ob in org.spheres.all())))
                return
            except TaskSupporter.DoesNotExist:
                caller.msg("Could not find a task you're supporting by that number.")
                self.get_support_table()
                return
            except SupportUsed.DoesNotExist:
                # create the supused for them
                supused = SupportUsed(week=week, sphere=sphere, rating=0, supporter=sup)
            char = targmember.player.player.db.char_ob
            diff = val - sup.rating
            if diff > remaining:
                caller.msg("You want to spend %s but only have %s available." % (diff, remaining))
                return
            diff = val - supused.rating
            poolshare = member.pool_share
            if (member.total_points_used + diff) > poolshare:
                caller.msg("You can only use a total of %s points in that organization." % poolshare)
                return
            if (member.points_used(category) + diff) > sphere.rating:
                caller.msg("You can only spend up to %s points in that category." % sphere.rating)
                return
            supused.rating = val
            supused.save()
            points_remaining_for_char = (dompc.support_cooldowns).get(char.id, max_points)
            points_remaining_for_char -= diff
            dompc.support_cooldowns[char.id] = points_remaining_for_char
            if points_remaining_for_char >= max_points:
                del dompc.support_cooldowns[char.id]
            caller.msg("New rating is now %s and you have %s points remaining." % (val, dompc.remaining_points))
            return
        if not requests:
            caller.msg("No one has requested you to support them on a task recently enough.")
            caller.attributes.remove('supportform')
            return
        if not self.switches:
            char = self.player.search(self.lhs)
            if not char:
                return
            char = char.db.char_ob
            if char.id not in requests:
                caller.msg("%s has not asked you for support in a task recently enough.")
                return
            assignment = AssignedTask.objects.filter(id=requests[char.id])
            if not assignment:
                caller.msg("No task found. They must have abandoned it already.")
                return
            assignment = assignment[0]
            if assignment.supporters.filter(player=caller.player.Dominion):
                caller.msg("You have already pledged your support to this task.")
                return
            caller.msg("{wExisting rumor for task:{n\n%s" % assignment.observer_text)
            form = [char, False, {}, "", ""]
            caller.db.supportform = form
            self.disp_supportform()
            return
        if "abandon" in self.switches:
            caller.attributes.remove('supportform')
            caller.msg("Abandoned.")
            return
        # check if form has been defined
        if not form:
            caller.msg("Please define who you're supporting first with {wsupport <character>{n.")
            return
        if "fake" in self.switches:
            form[1] = not form[1]
            self.disp_supportform()
            return
        if "value" in self.switches:
            try:
                if not self.rhs:
                    """
                    If they only gave points, then we take their first org,
                    and take the sphere with the highest points in it for them.
                    """
                    points = int(self.args)
                    org = dompc.current_orgs[0]
                    caller.msg("Using %s as the organization." % org)
                    sphere = org.spheres.all().order_by('-rating')[0]
                    category = sphere.category.name
                    caller.msg("Using %s as the category." % category)
                else:
                    # if only give sphere rather than org,sphere, use org[0]
                    points = int(self.rhs or 0)
                    if len(self.lhslist) == 2:
                        org = dompc.current_orgs.get(name__iexact=self.lhslist[0])
                        category = self.lhslist[1]
                    else:
                        org = dompc.current_orgs[0]
                        caller.msg("Using %s as the organization." % org)
                        category = self.lhs
                    sphere = org.spheres.get(category__name__iexact=category)
                member = dompc.memberships.get(organization=org)
                if points < 0:
                    raise ValueError
            except (ValueError, TypeError):
                caller.msg("You must provide a positive number.")
                return
            except IndexError:
                caller.msg("You must have an organization and influence type defined first.")
                return
            except Organization.DoesNotExist:
                caller.msg("No organization by that name.")
                caller.msg("Your organizations are: %s" % ", ".join(str(ob) for ob in dompc.current_orgs))
                return
            except SphereOfInfluence.DoesNotExist:
                caller.msg("No sphere of influence for the organization found by that name.")
                caller.msg("Valid spheres for %s: %s" % (org, ", ".join(str(ob.category) for ob in org.spheres.all())))
                return
            char = form[0]
            sdict = form[2]
            # check if we already have points set for the sphere we're modifying
            diff = points - sdict.get(sphere.id, 0)
            # add the new points to the total
            total_points = sum(sdict.values()) + diff
            if total_points > remaining:
                caller.msg("You are trying to spend %s, bringing your total to %s, and only have %s." % (points,
                                                                                                         total_points,
                                                                                                         remaining))
                return
            if char.id in cooldowns:
                max_points = cooldowns[char.id]
            if total_points > max_points:
                caller.msg("Because of your cooldowns, you may only spend %s points." % max_points)
                return
            if points > sphere.rating:
                caller.msg("Your organization only can spend %s points for %s." % (sphere.rating, sphere.category))
                return
            poolshare = member.pool_share
            points_in_org = 0
            for sid in sdict:
                try:
                    org.spheres.get(sid)
                    points_in_org += sdict[sid]
                except Exception:
                    continue
            if (member.total_points_used + points_in_org) > poolshare:
                caller.msg("You can only use a total of %s points in that organization." % poolshare)
                return
            if (member.points_used(category) + points) > sphere.rating:
                caller.msg("You can only spend up to %s points in that category." % sphere.rating)
                return
            sdict[sphere.id] = points
            form[2] = sdict
            caller.db.supportform = form
            self.disp_supportform()
            return
        if "notes" in self.switches:
            form[3] = self.args
            caller.db.supportform = form
            self.disp_supportform()
            return
        if "announcement" in self.switches or "rumors" in self.switches:
            form[4] = self.args
            caller.db.supportform = form
            self.disp_supportform()
            return
        if "finish" in self.switches:
            points = 0
            char = form[0]
            fake = form[1]
            try:
                assignment = AssignedTask.objects.get(id=requests[char.id])
            except (AssignedTask.DoesNotExist, KeyError):
                caller.msg("No assignment found that you're trying to support. Please abandon.")
                return
            sdict = form[2]
            notes = form[3] or ""
            announcement = form[4] or ""
            if not fake and not announcement:
                caller.msg("You need to write some sort of short description of what takes place " +
                           "as a result of supporting this task. Think of what you're asking npcs " +
                           "to do, and try to describe what other characters may infer just by hearing " +
                           "about happenings in the city.")
                return
            if not fake and not sdict:
                caller.msg("You must define categories your support is coming from with /value if you are "+
                           "not faking your support with /fake (which will cause them to receive no points "+
                           "whatsoever). Choose an organization and a sphere of influence for that organization "+
                           "with /value, even if that value is 0. Even a value of 0 will cause them to receive 1 "+
                           "free point, and an additional 5 if you have never supported them before.")
                return
            sup = assignment.supporters.create(fake=fake, player=caller.player.Dominion, notes=notes, observer_text=announcement)
            for sid in sdict:
                rating = sdict[sid]
                sphere = SphereOfInfluence.objects.get(id=sid)
                sused = SupportUsed.objects.create(week=week, supporter=sup, sphere=sphere, rating=rating)
                points += rating
            charpoints = cooldowns.get(char.id, caller.max_support)
            charpoints -= points
            cooldowns[char.id] = charpoints
            if not form[1]:
                caller.msg("You have pledged your support to %s in their task." % char.name)
            else:
                caller.msg("You pretend to support %s in their task." % char.name)
##            char.msg("{w%s has pledged their support to you in the task: %s" % (caller.name,
##                                                                                assignment.task.name))
            caller.attributes.remove("supportform")
            del requests[char.id]
            return
        caller.msg("Invalid usage.")
        return

# cmdset for all Dominion commands

class DominionCmdSet(CmdSet):
    key = "DominionDefault"
    duplicates = False
    def at_cmdset_creation(self):
        "Init the cmdset"
        self.add(CmdAdmDomain())
        self.add(CmdAdmArmy())
        self.add(CmdAdmCastle())
        self.add(CmdAdmAssets())
        self.add(CmdAdmFamily())
        self.add(CmdAdmOrganization())
        self.add(CmdTagBarracks())
        # player commands
        self.add(CmdDomain())
        self.add(CmdFamily())
        self.add(CmdOrganization())
        self.add(CmdAgents())
        self.add(CmdGuards())


