"""
This commandset attempts to define the combat state.
Combat in Arx isn't designed to mimic the real-time
nature of MMOs, or even a lot of MUDs. Our model is
closer to tabletop RPGs - a turn based system that
can only proceed when everyone is ready. The reason
for this is that having 'forced' events based on a
time limit, while perfectly appropriate for a video
game, is unacceptable when attempting to have a game
that is largely an exercise in collaborative story-
telling. It's simply too disruptive, and often creates
situations that are damaging to immersion and the
creative process.
"""

from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand
from server.utils import prettytable
from evennia.utils.create import create_object
from django.conf import settings
from world.dominion.models import (CraftingMaterialType, PlayerOrNpc, CraftingMaterials)
from world.dominion import setup_utils



RESOURCE_VAL = 250
BOOK_PRICE = 1
other_items = {"book": [BOOK_PRICE, "parchment",
                        "game.gamesrc.objects.readable.readable.Readable",
                        "A book that you can write in and others can read."],
               }

class OtherMaterial(object):
    def __init__(self, otype):
        self.name = "book"       
        self.value = other_items[otype][0]
        self.category = other_items[otype][1]
        self.path = other_items[otype][2]
        self.desc = other_items[otype][3]
    def __str__(self):
        return self.name
    def create(self, caller):
        stacking = [ob for ob in caller.contents if ob.typeclass_path == self.path and ob.db.can_stack]
        if stacking:
            obj = stacking[0]
            obj.set_num(obj.db.num_instances + 1)
        else:
            obj = create_object(typeclass=self.path, key=self.name,
                            location=caller, home=caller)
        return obj

class MarketCmdSet(CmdSet):
    "CmdSet for a market."    
    key = "MarketCmdSet"
    priority = 20
    duplicates = False
    no_exits = False
    no_objs = False
    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdMarket())



class CmdMarket(MuxCommand):
    """
    market
    Usage:
        market
        market/buy <material>=<amount>
        market/sell <material>=<amount>
        market/info <material>
        market/import <material>=<amount>
        market/economic <amount>
        market/social <amount>
        market/military <amount>

    Used to buy and sell materials at the market. Materials can be
    sold to the market for half price. Economic resources are worth
    250 silver for buying materials, and cost 500 silver to purchase.
    """
    key = "market"
    aliases = ["buy", "sell"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        "Execute command."
        caller = self.caller
        usemats = True
        if self.cmdstring == "buy" and not ('economic' in self.switches or
                                            'social' in self.switches or
                                            'military' in self.switches):
            # allow for buy/economic, etc. buy switch precludes that, so we
            # only add it if we don't have the above switches
            self.switches.append("buy")
        if self.cmdstring == "sell":
            # having other switches is misleading. They could think they can sell
            # other things.
            if self.switches:
                caller.msg("Use market/sell or just 'sell' as the command.")
                return
            self.switches.append("sell")
        materials = CraftingMaterialType.objects.filter(value__gte=0).order_by("value")
        if not caller.check_permstring("builders"):
            materials = materials.exclude(acquisition_modifiers__icontains="nosell")
        if not self.args:
            mtable = prettytable.PrettyTable(["{wMaterial",
                                       "{wCategory",
                                       "{wCost"])
            for mat in materials:
                mtable.add_row([mat.name, mat.category, str(mat.value) ])
            # add other items by hand
            for mat in other_items:
                mtable.add_row([mat, other_items[mat][1], other_items[mat][0]])
            caller.msg("\n{w" + "="*60 + "{n\n%s"% mtable)
            pmats = CraftingMaterials.objects.filter(owner__player__player=caller.player)
            if pmats:
                caller.msg("\n{wYour materials:{n %s" % ", ".join(str(ob) for ob in pmats))
            return
        if not ("economic" in self.switches or "buyeconomic" in self.switches or "social" in self.switches or
                "military" in self.switches):
            try:
                material = materials.get(name__icontains=self.lhs)
            except CraftingMaterialType.DoesNotExist:
                if self.lhs not in other_items:
                    caller.msg("No material found for name %s." % self.lhs)
                    return
                material = OtherMaterial(self.lhs)
                usemats = False
            except CraftingMaterialType.MultipleObjectsReturned:
                try:
                    material = materials.get(name__iexact=self.lhs)
                except Exception:
                    caller.msg("Unable to get a unique match for that.")
                    return           
        if 'buy' in self.switches or 'import' in self.switches:
            if not usemats:
                amt = 1
            else:
                try:
                    amt = int(self.rhs)
                except (ValueError, TypeError):
                    caller.msg("Amount must be a number.")
                    return
                if amt < 1:
                    caller.msg("Amount must be a positive number")
                    return    
            cost = material.value * amt
            try:
                dompc = caller.db.player_ob.Dominion
            except AttributeError:
                dompc = setup_utils.setup_dom_for_char(caller)
            if "buy" in self.switches:
                # use silver
                if cost > caller.db.currency:
                    caller.msg("That would cost %s silver coins, and you only have %s." % (cost, caller.db.currency))
                    return
                caller.pay_money(cost)
                paystr = "%s silver" % cost
            else:
                # use economic resources
                eamt = cost/RESOURCE_VAL
                # round up if not exact
                if cost % RESOURCE_VAL:
                    eamt += 1
                assets = dompc.assets
                if assets.economic < eamt:
                    caller.msg("That costs %s economic resources, and you have %s." % (eamt, assets.economic))
                    return
                assets.economic -= eamt         
                assets.save()
                paystr = "%s economic resources" % eamt
                # check if they could have bought more than the amount they specified
                optimal_amt = (eamt * RESOURCE_VAL)/(material.value or 1)
                if amt < optimal_amt:
                    caller.msg("You could get %s for the same price, so doing that instead." % optimal_amt)
                    amt = optimal_amt
            if usemats:             
                try:
                    mat = dompc.assets.materials.get(type=material)
                    mat.amount += amt
                    mat.save()
                except CraftingMaterials.DoesNotExist:
                    mat = dompc.assets.materials.create(type=material, amount=amt)
            else:
                obj = material.create(caller)
            caller.msg("You buy %s %s for %s." % (amt, material, paystr))
            return
        if 'sell' in self.switches:
            try:
                amt = int(self.rhs)
            except (ValueError, TypeError):
                caller.msg("Amount must be a number.")
                return
            if amt < 1:
                caller.msg("Must be a positive number.")
                return
            if not usemats:
                caller.msg("The market will only buy raw materials.")
                return
            try:
                dompc = PlayerOrNpc.objects.get(player=caller.player)
            except PlayerOrNpc.DoesNotExist:
                dompc = setup_utils.setup_dom_for_char(caller)
            try:
                mat = dompc.assets.materials.get(type=material)
            except CraftingMaterials.DoesNotExist:
                caller.msg("You don't have any of %s." % material.name)
                return
            if mat.amount < amt:
                caller.msg("You want to sell %s %s, but only have %s." % (amt, material, mat.amount))
                return
            mat.amount -= amt
            mat.save()
            money = caller.db.currency or 0.0
            sale = amt * material.value/2
            money += sale
            caller.db.currency = money
            caller.msg("You have sold %s %s for %s silver coins." % (amt, material.name, sale))
            return
        if 'info' in self.switches:
            caller.msg("{wInformation on %s:{n" % material.name)
            caller.msg(material.desc)
            price = material.value
            caller.msg("{wPrice:{n %s" % price)
            cost = price/250
            if price % 250:
                cost += 1
            caller.msg("{wPrice in economic resources:{n %s" % cost)
            return
        if "economic" in self.switches or "military" in self.switches or "social" in self.switches:
            try:
                assets = caller.db.player_ob.Dominion.assets
                amt = int(self.args)
                if amt <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Must specify a positive number.")
                return
            cost = 500 * amt
            if cost > caller.db.currency:
                caller.msg("That would cost %s and you have %s." % (cost, caller.db.currency))
                return
            caller.pay_money(cost)
            if "economic" in self.switches:
                assets.economic += amt
            elif "social" in self.switches:
                assets.social += amt
            elif "military" in self.switches:
                assets.military += amt
            assets.save()
            caller.msg("You have bought %s resources for %s." % (amt, cost))
            return
        caller.msg("Invalid switch.")
        return
