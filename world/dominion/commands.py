"""
Commands for dominion. This will be the interface through which
players interact with the system, as well as commands for staff
to make changes.
"""
from ast import literal_eval

from django.conf import settings
from django.db.models import Q

from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from evennia.objects.models import ObjectDB
from evennia.players.models import PlayerDB
from server.utils.arx_utils import get_week
from server.utils.prettytable import PrettyTable
from evennia.utils.evtable import EvTable
from . import setup_utils
from .models import (Region, Domain, Land, PlayerOrNpc, Army,
                     Castle, AssetOwner, Task,
                     Ruler, Organization, Member, Orders, SphereOfInfluence, SupportUsed, AssignedTask,
                     TaskSupporter, InfluenceCategory, Minister)
from .unit_types import type_from_str

# Constants for Dominion projects
BUILDING_COST = 1000
# cost will be base * 5^(new level)
BASE_CASTLE_COST = 4000


# ---------------------Admin commands-------------------------------------------------

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
            npcdomains = ", ".join((repr(dom) for dom in Domain.objects.filter(ruler__castellan__player__isnull=True)))
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
                    elif region.name == "Oathlands":
                        house = Organization.objects.get(name__iexact="Valardin")
                    elif region.name == "Mourning Isles":
                        house = Organization.objects.get(name__iexact="Thrax")
                    elif region.name == "Northlands":
                        house = Organization.objects.get(name__iexact="Redrain")
                    elif region.name == "Crownlands":
                        house = Organization.objects.get(name__iexact="Grayson")
                    else:
                        self.msg("House for that region not found.")
                        return
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
                d_id = int(self.rhslist[0])
                if len(self.rhslist) > 1:
                    num_vassals = int(self.rhslist[1])
                else:
                    num_vassals = 2
                dom = Domain.objects.get(id=d_id)
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
                family = player.db.char_ob.db.family
                try:
                    house = Organization.objects.get(name__iexact=family)
                    owner = house.assets
                    # if the organization's AssetOwner has no Ruler object
                    if hasattr(owner, 'estate'):
                        ruler = owner.estate
                    else:
                        ruler = Ruler.objects.create(house=owner, castellan=dompc)
                except Organization.DoesNotExist:
                    ruler = setup_utils.setup_ruler(family, dompc)
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
            x, y = None, None
            try:
                # ast.literal_eval will parse a string into a tuple
                x, y = literal_eval(self.lhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # literal_eval gets SyntaxError if it gets no argument, not ValueError
            except (SyntaxError, ValueError):
                caller.msg("Must provide 'x,y' values for a Land square.")
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            except Land.DoesNotExist:
                caller.msg("No land square matches (%s,%s)." % (x, y))
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            doms = ", ".join(str(dom) for dom in land.domains.all())
            caller.msg("Domains at (%s, %s): %s" % (x, y, doms))
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
                owned = ", ".join(str(ob) for ob in Domain.objects.filter(
                    ruler__house__organization_owner__name__iexact=family))
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
            x, y = None, None
            try:
                dom = Domain.objects.get(id=int(self.lhs))
                x, y = literal_eval(self.rhs)
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
                caller.msg("No land with coords (%s,%s)." % (x, y))
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
            d_id = int(self.lhs)
            dom = Domain.objects.get(id=d_id)
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
            caller.msg("All switches must be in the following: %s. You passed %s." % (str(attr_switches),
                                                                                      str(self.switches)))
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
        else:  # switch is 'name', 'desc', or 'title', so val will be a string
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
    aliases = ["@admarmy", "@adm_army"]

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
                caller.msg("Example usage: @admdomain/unit 5=infantry,300,1,1")
                return
            except (TypeError, ValueError):
                caller.msg("Amount of troops, training level, and equipment level must all be numbers.")
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
            x, y = None, None
            try:
                x, y = literal_eval(self.rhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # Syntax for no self.rhs, Type for no lhs, Value for not for lhs/rhs not being digits
            except (SyntaxError, TypeError, ValueError):
                caller.msg("Usage: @admarmy/move army_id=(x,y)")
                caller.msg("You entered: %s" % self.args)
                return
            except Land.DoesNotExist:
                caller.msg("No land with coords (%s,%s)." % (x, y))
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
    aliases = ["@admassets", "@admasset", "@adm_asset", "@adm_assets"]

    @staticmethod
    def get_owner(args):
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
            caller.msg("Dominion initialized for %s. No domain created." % player)
            return
        try:
            owner = self.get_owner(self.lhs)
        except (TypeError, ValueError, AssetOwner.DoesNotExist):
            caller.msg("No assetowner found for %s." % self.lhs)
            return
        if not self.rhs:
            caller.msg(owner.display(), options={'box': True})
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
            tar = None
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
                obj.msg("%s adjusted %s's prestige by %s for the following reason: %s" % (caller, owner,
                                                                                          value, message))
            # post to a board about it
            from typeclasses.bulletin_board.bboard import BBoard
            board = BBoard.objects.get(db_key="Prestige Changes")
            msg = "{wName:{n %s\n" % str(owner)
            msg += "{wAdjustment:{n %s\n" % value
            msg += "{wGM:{n %s\n" % caller.key.capitalize()
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
        @admin_org/setinfluence <org name or number>=<inf name>,<value>

    Allows you to change or control organizations. Orgs can be accessed either by
    their ID number or name.
    """
    key = "@admin_org"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admorg", "@adm_org"]

    def set_influence(self, org):
        try:
            name, value = self.rhslist[0], int(self.rhslist[1])
        except (TypeError, ValueError, IndexError):
            self.msg("Must provide an influence name and value.")
            return
        try:
            cat = InfluenceCategory.objects.get(name__iexact=name)
        except InfluenceCategory.DoesNotExist:
            self.msg("No InfluenceCategory by that name.")
            self.msg("Valid ones are: %s" % ", ".join(ob.name for ob in InfluenceCategory.objects.all()))
            return
        try:
            sphere = org.spheres.get(category=cat)
        except SphereOfInfluence.DoesNotExist:
            sphere = org.spheres.create(category=cat)
        sphere.rating = value
        sphere.save()
        self.msg("Set %s's rating in %s to be %s." % (org, cat, value))

    def func(self):
        caller = self.caller
        if not self.args:
            if 'all' in self.switches:
                orgs = ", ".join(repr(org) for org in Organization.objects.all())
            else:
                orgs = ", ".join(repr(org) for org in Organization.objects.all()
                                 if org.members.filter(player__player__isnull=False))
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
                secret = org.secret
                dompc.memberships.create(organization=org, rank=rank, secret=secret)
                caller.msg("%s added to %s at rank %s." % (dompc, org, rank))
                try:
                    org.org_channel.connect(player)
                except AttributeError:
                    pass
                return
            except (AttributeError, ValueError, TypeError):
                caller.msg("Could not add %s. May need to run @admin_assets/setup on them." % self.rhs)
                return
        if 'title' in self.switches or 'femaletitle' in self.switches:
            male = 'femaletitle' not in self.switches
            try:
                rank, name = int(self.rhslist[0]), self.rhslist[1]
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
                caller.msg("No member found by name of %s." % self.rhslist[0])
                return
            except (ValueError, TypeError, AttributeError, KeyError):
                caller.msg("Usage: @admorg/set_rank <org> = <player>, <1-10>")
                return
        if 'setinfluence' in self.switches:
            self.set_influence(org)
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
    aliases = ["@admfamily", "@adm_family"]
    
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
            char.parents.create(npc_name=self.rhs)
            caller.msg("Created a parent named %s for %s." % (self.rhs, char))
            return
        if "createchild" in self.switches:
            char.children.create(npc_name=self.rhs)
            caller.msg("Created a child named %s for %s." % (self.rhs, char))
            return
        if "createspouse" in self.switches:
            char.spouses.create(npc_name=self.rhs)
            caller.msg("Created a spouse named %s for %s." % (self.rhs, char))
            return
        if "replacenpc" in self.switches:
            player = caller.search(self.rhs)
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
        default_home = ObjectDB.objects.get(id=13)
        caller = self.caller
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
        if "home" in self.switches or "homeaddowner" in self.switches or "homermowner" in self.switches:
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
                        if not char.home or char.home == default_home:
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
                    except ObjectDB.DoesNotExist:
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
                caller.msg("Some of the entrances do not connect to this room: %s" % ", ".join(str(ob)
                                                                                               for ob in invalid))
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
        @domain/castellan <domain ID>=<player>
        @domain/minister <domain ID>=<player>,<category>
        @domain/resign <domain ID>
        @domain/strip <domain ID>=<player>

    Commands to view and control your domain.

    Unfinished
    """
    key = "@domain"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@domains"]
    valid_categories = ("farming", "income", "loyalty", "population", "productivity", "upkeep", "warfare")
    minister_dict = dict((key.lower(), value) for (value, key) in Minister.MINISTER_TYPES)

    @property
    def orgs(self):
        return [org for org in self.caller.Dominion.current_orgs if org.access(self.caller, "command")]

    @property
    def org_domains(self):
        return Domain.objects.filter(ruler__house__organization_owner__in=self.orgs)

    @property
    def ruled_domains(self):
        return Domain.objects.filter(ruler__castellan=self.caller.Dominion)

    @property
    def ministered_domains(self):
        return Domain.objects.filter(ruler__ministers__player=self.caller.Dominion)

    @property
    def domains(self):
        org_owned = self.org_domains
        ruled = self.ruled_domains
        minister = self.ministered_domains
        return (org_owned | ruled | minister).distinct()

    def list_domains(self):
        table = EvTable("ID", "Domain", "House", "Castellan", "Ministers", width=78)
        for domain in self.domains:
            table.add_row(domain.id, domain.name, domain.ruler.house, domain.ruler.castellan,
                          ", ".join(str(ob.player) for ob in domain.ruler.ministers.all()))
        self.msg(str(table))

    def check_member(self, domain, player):
        player.refresh_from_db()
        if domain.ruler.house.organization_owner not in player.current_orgs:
            self.msg("%s is not a member of %s." % (player, domain.ruler.house))
            self.msg("current orgs: %s" % ", ".join(ob.name for ob in player.current_orgs
                                                    if self.caller == player.player))
            return False
        return True

    def busy_check(self, dompc):
        if dompc.appointments.all() or getattr(dompc, 'ruler', None):
            self.msg("They are already holding an office, and cannot hold another.")
            return True
        return False

    def func(self):
        if not self.args and not self.switches:
            self.list_domains()
            return
        # for other switches, get our domain from lhs
        try:
            if self.lhs.isdigit():
                dom = self.domains.get(id=self.lhs)
            else:
                dom = self.domains.get(name__iexact=self.lhs)
        except Domain.DoesNotExist:
            self.list_domains()
            self.msg("No domain found by that name or ID.")
            return
        if not self.switches:
            self.msg(dom.display())
            return
        if "castellan" in self.switches:
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to set a ruler.")
                return
            targ = self.caller.search(self.rhs)
            if not targ:
                return
            dompc = targ.Dominion
            if not self.check_member(dom, dompc):
                return
            if self.busy_check(dompc):
                return
            dom.ruler.castellan = dompc
            dom.ruler.save()
            self.msg("Castellan set to %s." % dompc)
            return
        if "minister" in self.switches:
            if len(self.rhslist) != 2:
                self.msg("Specify both a player and a category.")
                self.msg("Valid categories: %s" % ", ".join(self.valid_categories))
                return
            targ = self.caller.search(self.rhslist[0])
            if not targ:
                return
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to set a minister.")
                return
            dompc = targ.Dominion
            try:
                category = self.minister_dict[self.rhslist[1]]
            except KeyError:
                self.msg("Valid categories: %s" % ", ".join(self.valid_categories))
                return
            # if not self.check_member(dom, dompc):
            #     return
            if self.busy_check(dompc):
                return
            try:
                minister = dom.ruler.ministers.get(category=category)
                minister.player = dompc
                minister.save()
            except Minister.DoesNotExist:
                dom.ruler.ministers.create(player=dompc, category=category)
            self.msg("%s's Minister of %s set to be %s." % (dom, self.rhslist[1], dompc))
            return
        if "resign" in self.switches:
            if dom in self.ruled_domains:
                dom.ruler.castellan = None
                dom.ruler.save()
                self.msg("You resign as ruler of %s." % dom)
                return
            if dom in self.ministered_domains:
                minister = dom.ruler.ministers.get(player=self.caller.Dominion)
                minister.delete()
                self.msg("You resign as minister of %s." % dom)
                return
            self.msg("You are not a ruler or minister of %s." % dom)
            return
        if "strip" in self.switches:
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to strip someone of their position.")
                return
            targ = self.caller.search(self.rhs)
            if not targ:
                return
            dompc = targ.Dominion
            if dom.ruler.castellan == dompc:
                self.msg("Removing %s as castellan.")
                dom.ruler.castellan = None
                dom.ruler.save()
                return
            try:
                minister = dom.ruler.ministers.get(player=dompc)
                minister.delete()
                self.msg("You have removed %s as a minister." % dompc)
            except Minister.DoesNotExist:
                self.msg("They are neither a minister nor castellan for that domain.")
            return
        self.msg("Invalid switch.")


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
        except (AttributeError, Army.DoesNotExist):
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
                caller.msg("An army under your command already has an exploration order." +
                           " Only one army can explore per week.")
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
        @org/secret <player>[=<org name>]

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

    @staticmethod
    def get_org_and_member(caller, myorgs, args):
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
        caller.msg(table, options={'box': True})

    def display_permtypes(self):
        self.msg("Type must be one of the following: %s" % ", ".join(self.org_locks))
    
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
                secret = org.secret
                caller.Dominion.memberships.create(organization=org, secret=secret)
            caller.msg("You have joined %s." % org.name)
            org.msg("%s has joined %s." % (caller, org.name))
            try:
                org.org_channel.connect(caller)
            except AttributeError:
                pass
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
                caller.msg(myorgs[0].display(member), options={'box': True})
                return
            caller.msg("Your organizations: %s" % ", ".join(org.name for org in myorgs))
            return
        if not self.switches:
            try:
                org, member = self.get_org_and_member(caller, myorgs, self.lhs)
                caller.msg(org.display(member), options={'box': True})
                return
            except Organization.DoesNotExist:
                caller.msg("You are not a member of any organization named %s." % self.lhs)
                return
        player = None
        if not ('perm' in self.switches or 'rankname' in self.switches):
            player = caller.search(self.lhs)
            if not player:
                return
        if 'setrank' in self.switches or 'perm' in self.switches or 'rankname' in self.switches:
            if not self.rhs:
                if 'perm' in self.switches:
                    self.display_permtypes()
                    return
                caller.msg("You must supply a rank number.")
                return
            if len(myorgs) < 2:
                # if they supplied the org even though they don't have to
                rhs = self.rhs
                if len(self.rhslist) > 1:
                    rhs = self.rhslist[0]
                if not self.rhs.isdigit():
                    caller.msg("Rank must be a number.")
                    return
                org = myorgs[0]
                member = caller.Dominion.memberships.get(organization=org)
                rank = int(rhs)
            else:
                if len(self.rhslist) < 2:
                    caller.msg("You belong to more than one organization, so must supply both rank number and" +
                               " the organization name.")
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
                ltype = self.lhs.lower() if self.lhs else ""
                if ltype not in self.org_locks:
                    self.display_permtypes()
                    return
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit permissions.")
                    return
                org.locks.add("%s:rank(%s)" % (ltype, rank))
                org.save()
                caller.msg("Permission %s set to require rank %s or higher." % (ltype, rank))
                return
            if 'rankname' in self.switches:
                rankname = self.lhs
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit rank names.")
                    return
                maleonly = femaleonly = False
                if len(self.rhslist) == 3:
                    if self.rhslist[2].lower() == "male":
                        maleonly = True
                    elif self.rhslist[2].lower() == "female":
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
            msg += "To accept, type {w@org/accept %s{n. To decline, type {worg/decline %s{n." % (org.name, org.name)
            player.inform(msg, category="Invitation")
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
        if 'secret' in self.switches:
            if not org.access(caller, 'setrank'):
                caller.msg("You do not have permission to change member status.")
                return
            member = caller.Dominion.memberships.get(organization=org)
            if member.rank > tarmember.rank:
                caller.msg("You cannot change someone who is higher ranked than you.")
                return
            tarmember.secret = not tarmember.secret
            tarmember.save()
            caller.msg("Their secret status is now %s" % tarmember.secret)
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
        self.msg("Invalid switch.")


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
                except Organization.DoesNotExist:
                    # display nothing
                    pass
            return
        except PlayerOrNpc.DoesNotExist:
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

    Displays and manages patronage.
    """
    key = "@patronage"
    locks = "cmd:all()"
    help_category = "Dominion"

    @staticmethod
    def display_patronage(dompc):
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
        except AttributeError:
            dompc = setup_utils.setup_dom_for_char(self.caller.db.char_ob)
        if not self.args and not self.switches:        
            caller.msg(self.display_patronage(dompc), options={'box': True})
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
            except AttributeError:
                tdompc = setup_utils.setup_dom_for_char(char)
            if not self.switches:
                caller.msg(self.display_patronage(tdompc), options={'box': True})
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
                max_p = max_proteges.get(psrank, 0)
                if num >= max_p:
                    caller.msg("You already have the maximum number of proteges for your social rank.")
                    return
                # 'greater' social rank is worse. 1 is best, 10 is worst
                if psrank >= tsrank:
                    caller.msg("They must be a worse social rank than you to be your protege.")
                    return
                player.ndb.pending_patron = caller
                msg = "{c%s {wwants to become your patron. " % caller.key.capitalize()
                msg += " Use @patronage/accept to accept {wthis offer, or @patronage/reject to reject it.{n"
                player.msg(msg)
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
                old.player.msg("{c%s {rhas abandoned your patronage, and is no longer your protege.{n" % dompc)
                caller.msg("{rYou have abandoned {c%s{r's patronage, and are no longer their protege.{n" % old)
            else:
                caller.msg("You don't have a patron.")
            return
        caller.msg("Unrecognized switch.")
        return


# Character/IC commands------------------------------
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
    creation through the /altecho switch. /supportme without specifying
    players will list who you have previously asked.

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

    @staticmethod
    def display_tasks(tasks, dompc):
        """
        Returns a table of tasks
        """
        table = PrettyTable(["{wActive{n", "{wTask#{n", "{wCategory{n",
                             "{wOrganization{n", "{wTask Name{n", "{wRating{n"])
        already_displayed = []
        for task in tasks:
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

    @staticmethod
    def display_finished(tasks, dompc):
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

    @staticmethod
    def match_char_spheres_for_task(assignment, character):
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
        except AttributeError:
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
            tasks = mytasks.filter(assigned_tasks__finished=False)
            # NB: combining tasks this way, rather than in queryset form, is 1000 times faster
            # possibly due to lack of index or something, but tasks | available is chock-full of
            # LEFT OUTER JOINs, and literally 1000 times slower than evaluating independently.
            tasks = list(tasks)
            available = list(available)
            tasks = list(set(tasks) | set(available))
            caller.msg(self.display_tasks(tasks, dompc))
            caller.msg("You can perform %s more tasks." % tasks_remaining)            
            return
        if not self.switches:
            # display info on task
            # NB: Same query as above, but it executed around 70 times faster. Why is the execution
            # so much worse above than here? No idea. But still, evaluating the queries independently
            # rather than combining them was still faster, just not as mind-bogglingly so.
            tasks = [ob.id for ob in (set(mytasks) | set(available))]
            try:
                task = Task.objects.get(id=int(self.args), id__in=tasks)         
            except ValueError:
                try:
                    org = Organization.objects.get(Q(name__iexact=self.args) &
                                                   Q(members__player=dompc) &
                                                   Q(members__deguilded=False))
                    caller.msg(self.display_tasks(org.tasks.filter(active=True), dompc))
                    return
                except Organization.DoesNotExist:
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
            asked_supporters = caller.db.asked_supporters or {}
            for assign in assignments:
                echo = assign.current_alt_echo
                caller.msg("{wCurrent echo:{n %s" % echo)
                caller.msg("{wCurrent rumors (both yours and supporters):{n %s" % assign.story)
                caller.msg("{wCurrent story:{n %s" % assign.notes)
                asklist = asked_supporters.get(assign.id, [])
                caller.msg("{wPlayers asked for support:{n %s" % ", ".join(str(ob) for ob in asklist))
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
                else:  # set finished rumors
                    if ass.observer_text and ass.finished:
                        caller.msg("Once the task is finished, only a GM can change an existing rumor.")
                        return
                    ass.observer_text = self.rhs
                    ass.save()
                    caller.msg("Rumors changed to %s." % self.rhs)
            except (Task.DoesNotExist, AssignedTask.DoesNotExist, ValueError):
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
                    id=int(self.lhslist[0]))
                assignment = task.assigned_tasks.filter(member__player=dompc, finished=False)
                if not assignment:
                    caller.msg("That task isn't active for you.")
                    return
                if len(assignment) == 1:
                    assignment = assignment[0]
                else:
                    try:
                        assignment = assignment.get(member__organization__name=self.lhslist[1])
                    except (IndexError, AssignedTask.DoesNotExist):
                        caller.msg("More than one task by that number active. You must specify the organization.")
                        return
            except Task.DoesNotExist:
                caller.msg("Could not find an active task by that number for that organization.")
                self.msg("You may need to choose/accept it first.")
                return
            except ValueError:
                caller.msg("Task must be a number.")
                return
            if "update" in self.switches or "supportme" in self.switches:
                asked_supporters = caller.db.asked_supporters or {}
                asklist = asked_supporters.get(assignment.id, [])
                if not self.rhslist:
                    self.msg("Players you've asked for this task already: %s" % ", ".join(str(ob) for ob in asklist))
                    return
                playerlist = [caller.player.search(val) for val in self.rhslist]
                playerlist = [ob for ob in playerlist if ob]
                if not playerlist:
                    return
                org = assignment.member.organization
                # if not assignment.notes or not assignment.notes.strip():
                #     caller.msg("You have written no notes for how you completed this task.")
                #     caller.msg("Please add them with task/story before asking for support.")
                #     return
                # if not assignment.observer_text:
                #     caller.msg("You haven't written a {w+task/rumors{n for what everyone else will see "+
                #                "when you finish this task. You can add it later with 'setfinishedrumors' "+
                #                " to make it fit what your supporters enter. Please write some description " +
                #                "that details "+
                #                "what people might notice happening in the city when your task is "+
                #                "finished - the details are up to you, as long as they can gain some "+
                #                "general indication of what the npcs you influenced have been up to.")
                success = []
                warnmsg = "As a reminder, it is considered in bad form and is against the rules to "
                warnmsg += "ask someone OOCly for support, such as trying to convince them to help "
                warnmsg += "in pages. No OOC pressure, please."
                for pc in playerlist:
                    reminder = False
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
                    week = get_week()
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
                            reminder = True

                    highest = char.db.player_ob.Dominion.memberships.filter(Q(secret=False) &
                                                                            Q(deguilded=False)).order_by('rank')
                    if highest:
                        highest = highest[0]
                    else:
                        highest = None
                    if highest in org.members.filter(Q(player=char.db.player_ob.Dominion) & Q(deguilded=False)):
                        caller.msg("You cannot gain support from a member whose highest " +
                                   "rank is in the same organization as the task.")
                        continue
                    if char not in asklist:
                        # The action point cost of requesting support for a task
                        if not caller.db.player_ob.pay_action_points(10):
                            caller.msg("You don't have enough action points to ask for support from %s." % char.name)
                            continue
                        asklist.append(char)
                    # make sure assignment is current
                    assignment.refresh_from_db()
                    matches = self.match_char_spheres_for_task(assignment, char)
                    requests[caller.id] = assignment.id
                    char.db.requested_support = requests
                    mailmsg = "%s has asked you to support them in their task:" % caller.name
                    mailmsg += "\n" + assignment.current_alt_echo
                    if reminder:
                        mailmsg += "\nYou already have a pending request for that task, and they are "
                        mailmsg += "sending a reminder."
                    else:
                        mailmsg += "\nWhat this means is that they're asking for your character to use "
                        mailmsg += "influence that they have with different npc groups in order to help "
                        mailmsg += "them achieve the goals they indicate. This is represented by using "
                        mailmsg += "the '+support' command, filling out a form that indicates which npcs "
                        mailmsg += "you influenced on their behalf, how you did it, and what happened."
                        mailmsg += "\n\nYou can ask npcs to support them from any of the following "
                        mailmsg += "areas you have influence in: %s" % ", ".join(str(ob) for ob in matches)
                        mailmsg += "\n\nThe support command has the usage of {wsupport %s{n, then " % caller
                        mailmsg += "adding fields that indicate how the npcs you influenced are helping them "
                        mailmsg += "out. '{w+support/notes{n' Lets you state OOCly to GMs what occurs, while "
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
                    pc.inform(mailmsg, category="Support Request from %s" % caller, append=False)
                    success.append(char)
                if not success:
                    return
                caller.msg("You ask for the support of %s." % ", ".join(char.name for char in success))
                caller.msg(warnmsg)
                # update asklist
                asked_supporters[assignment.id] = asklist
                caller.db.asked_supporters = asked_supporters
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

    def get_assign_from_char(self, char):
        requests = self.caller.db.requested_support or {}
        if char.id not in requests:
            self.msg("%s has not asked you for support in a task recently enough." % char)
            return
        try:
            assignment = AssignedTask.objects.get(id=requests[char.id], finished=False)
        except AssignedTask.DoesNotExist:
            self.msg("No task found. It was abandoned or finished already.")
            del requests[char.id]
            return
        return assignment

    def disp_supportform(self):
        caller = self.caller
        form = caller.db.supportform
        if form:
            try:
                caller.msg("Building support for a task for %s." % form[0])
                assign = self.get_assign_from_char(form[0])
                if not assign:
                    return
                self.msg("{wCurrent echo for task:{n %s" % assign.current_alt_echo)
                caller.msg("Fake: %s" % form[1])
                for s_id in form[2]:
                    sphere = SphereOfInfluence.objects.get(id=s_id)
                    msg = "Organization: %s, Category: %s, Amount: %s" % (sphere.org, sphere.category, form[2][s_id])
                    caller.msg(msg)            
                caller.msg("Notes:\n%s" % form[3])
                caller.msg("Rumors:\n%s" % form[4])       
                caller.msg("Once all fields are finished, use /finish to commit.")
            except (TypeError, KeyError, IndexError):
                caller.msg("{rEncountered a supportform with invalid structure. Resetting the attribute." +
                           " Please start over.{n")
                print("%s had an invalid supportform. Wiping the attribute." % caller)
                caller.attributes.remove("supportform")
                return

    def get_support_table(self):
        caller = self.caller
        dompc = self.caller.db.player_ob.Dominion
        # week = get_week()
        supports = dompc.supported_tasks.filter(Q(task__finished=False)
                                                # &  Q(allocation__week=week)
                                                ).distinct()
        if supports:
            caller.msg("Open tasks supported:")
            table = PrettyTable(["{wID{n",  # "{wTask Name{n",
                                 "PC", "{wAmt{n"])
            for sup in supports:
                table.add_row([sup.id,  # sup.task.task.name,
                               str(sup.task.member), sup.rating])
            caller.msg(str(table))
    
    def func(self):
        week = get_week()
        caller = self.caller
        requests = caller.db.requested_support or {}
        dompc = self.caller.db.player_ob.Dominion
        dompc.refresh_from_db()
        cooldowns = dompc.support_cooldowns
        remaining = dompc.remaining_points
        max_points = caller.max_support
        form = caller.db.supportform
        if not self.args and not self.switches:
            # display requests and cooldowns
            chars = [ObjectDB.objects.get(id=r_id) for r_id in requests.keys()]
            chars = [ob for ob in chars if ob]
            msg = "Pending requests: "
            for char in chars:
                if not char:
                    continue
                try:
                    atask = AssignedTask.objects.get(id=requests[char.id], finished=False)
                except AssignedTask.DoesNotExist:
                    # caller.msg("Error: Could not find a task for request from %s." % char)
                    # caller.msg("Removing them from this list. Please run +support again.")
                    del requests[char.id]
                    caller.db.requested_support = requests
                    continue
                msg += "%s (valid categories: %s)\n" % (char, atask.task.reqs)
            caller.msg(msg)
            table = PrettyTable(["{wName{n", "{wMax Points Allowed{n"])
            for c_id in cooldowns:
                try:
                    char = ObjectDB.objects.get(id=c_id)
                except ObjectDB.DoesNotExist:
                    continue
                table.add_row([char.key, cooldowns[c_id]])
            caller.msg(str(table))
            self.get_support_table()          
            caller.msg("{wSupport points remaining:{n %s" % remaining)
            for memb in dompc.memberships.filter(deguilded=False):
                def rem_pts(allocation):
                    rat = allocation.rating
                    return "%s(%s)" % (rat - memb.points_used(allocation.category.name), rat)
                poolshare = memb.pool_share
                used = memb.total_points_used
                msg = "{wPool share for %s:{n %s(%s)" % (memb.organization, poolshare - used, poolshare)
                msg += ", {wCategory ratings:{n %s" % ", ".join("%s: %s" % (ob.category, rem_pts(ob))
                                                                for ob in memb.organization.spheres.all())
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
                r_id = int(self.args)
                sup = dompc.supported_tasks.get(id=r_id)
            except (TypeError, ValueError, TaskSupporter.DoesNotExist):
                caller.msg("No support given by that ID.")
                self.get_support_table()
                return
            caller.msg("{wID{n: %s" % sup.id)
            caller.msg("{wCharacter{n: %s" % sup.task.member)
            alloclist = sup.allocation.all()
            for alloc in alloclist:
                caller.msg("{wOrganization{n: %s, Sphere: %s, Amount: %s" % (alloc.sphere.org, alloc.sphere.category,
                                                                             alloc.rating))
            return
        if "change" in self.switches:
            org, sphere, sup, targmember, val, member, category = None, None, None, None, None, None, None
            try:
                # I've been having sync errors so going to do a bunch of manual refresh_from_db calls
                # and hope this actually resolves it this time.
                r_id = self.lhslist[0]
                category = self.lhslist[1]
                sup = dompc.supported_tasks.filter(task__finished=False).get(id=r_id)
                sup.refresh_from_db()
                if len(self.lhslist) > 2:
                    org = dompc.current_orgs.get(name__iexact=self.lhslist[2])
                else:
                    org = dompc.current_orgs[0]
                org.refresh_from_db()
                sphere = org.spheres.get(category__name__iexact=category)
                sphere.refresh_from_db()
                val = int(self.rhs)
                targmember = sup.task.member
                member = org.members.get(player=dompc)
                if val <= 0:
                    raise ValueError
                supused = sup.allocation.get(week=week, sphere=sphere)
                supused.refresh_from_db()
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
            # target character we're supporting
            char = targmember.player.player.db.char_ob
            char.refresh_from_db()
            diff = val - sup.rating
            if diff > remaining:
                caller.msg("You want to spend %s but only have %s available." % (diff, remaining))
                return
            diff = val - supused.rating
            member.refresh_from_db()  # try to catch possible sync errors here
            poolshare = member.pool_share
            if (member.total_points_used + diff) > poolshare:
                caller.msg("You can only use a total of %s points in that organization." % poolshare)
                return
            if (member.points_used(category) + diff) > sphere.rating:
                caller.msg("You can only spend up to %s points in that category." % sphere.rating)
                return
            supused.rating = val
            supused.save()
            # update our support cooldowns for target character
            points_remaining_for_char = dompc.support_cooldowns.get(char.id, max_points)
            points_remaining_for_char -= diff
            dompc.support_cooldowns[char.id] = points_remaining_for_char
            if points_remaining_for_char >= max_points:
                del dompc.support_cooldowns[char.id]
            caller.msg("New rating is now %s and you have %s points remaining." % (val, dompc.remaining_points))
            # remove any pending request that matched this
            try:
                if requests[char.id] == self.lhslist[0]:
                    del requests[char.id]
            except KeyError:
                pass
            return
        if not requests:
            caller.msg("No one has requested you to support them on a task recently enough.")
            caller.attributes.remove('supportform')
            return
        if not self.switches:
            char = self.caller.player.search(self.lhs)
            if not char:
                return
            char = char.db.char_ob
            assignment = self.get_assign_from_char(char)
            if not assignment:
                return
            if assignment.supporters.filter(player=caller.player.Dominion):
                caller.msg("You have already pledged your support to this task.")
                self.msg("Use the /change switch to support them again if you have in previous weeks, " +
                         "or to change existing support if you already have this week.")
                return
            if not self.caller.player.pay_action_points(5):
                caller.msg("You don't have enough action points to support %s." % char.name)
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
            org = None
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
            member.refresh_from_db()  # extra call in case of stale data
            poolshare = member.pool_share
            points_in_org = points
            for sid in sdict:
                try:
                    org.spheres.get(id=sid)
                    if sphere.id != sid:  # if it's another sphere, we add it to the total
                        points_in_org += sdict[sid]
                except SphereOfInfluence.DoesNotExist:
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
            # if not fake and not announcement:
            #     caller.msg("You need to write some sort of short description of what takes place " +
            #                "as a result of supporting this task. Think of what you're asking npcs " +
            #                "to do, and try to describe what other characters may infer just by hearing " +
            #                "about happenings in the city.")
            #     return
            if not fake and not sdict:
                caller.msg("You must define categories your support is coming from with /value if you are " +
                           "not faking your support with /fake (which will cause them to receive no points " +
                           "whatsoever). Choose an organization and a sphere of influence for that organization " +
                           "with /value, even if that value is 0. Even a value of 0 will cause them to receive 1 " +
                           "free point, and an additional 5 if you have never supported them before.")
                return
            sup = assignment.supporters.create(fake=fake, player=caller.player.Dominion, notes=notes,
                                               observer_text=announcement)
            for sid in sdict:
                rating = sdict[sid]
                sphere = SphereOfInfluence.objects.get(id=sid)
                SupportUsed.objects.create(week=week, supporter=sup, sphere=sphere, rating=rating)
                points += rating
            charpoints = cooldowns.get(char.id, caller.max_support)
            charpoints -= points
            cooldowns[char.id] = charpoints
            if not form[1]:
                caller.msg("You have pledged your support to %s in their task." % char.name)
            else:
                caller.msg("You pretend to support %s in their task." % char.name)
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
        """Init the cmdset"""
        self.add(CmdAdmDomain())
        self.add(CmdAdmArmy())
        self.add(CmdAdmCastle())
        self.add(CmdAdmAssets())
        self.add(CmdAdmFamily())
        self.add(CmdAdmOrganization())
        # self.add(CmdTagBarracks())
        # player commands
        self.add(CmdDomain())
        self.add(CmdFamily())
        self.add(CmdOrganization())
        from dominion.agent_commands import CmdAgents
        self.add(CmdAgents())
        from dominion.agent_commands import CmdGuards
        self.add(CmdGuards())
