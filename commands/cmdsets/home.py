"""
Commands for home spaces/rooms.
"""

from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand
from django.conf import settings
from world.dominion.models import LIFESTYLES
from django.db.models import Q
from evennia.objects.models import ObjectDB
from world.dominion.models import AssetOwner, Organization, CraftingRecipe
from commands.commands.crafting import CmdCraft
from commands.commands.overrides import CmdDig
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import inform_staff
from evennia.utils import utils
import re
# error return function, needed by Extended Look command
AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

DESC_COST = 0


class HomeCmdSet(CmdSet):
    """CmdSet for a home spaces."""
    key = "HomeCmdSet"
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
        self.add(CmdManageHome())


class CmdManageHome(MuxCommand):
    """
    +home
    Usage:
        +home
        +home/lock
        +home/unlock
        +home/key <character>
        +home/passmsg <message people see when entering>
        +home/lockmsg <message those who can't enter see>
        +home/rmkey <character>
        +home/lifestyle <rating>

    Controls your home.
    """
    key = "+home"
    # aliases = ["@home"]
    locks = "cmd:all()"
    help_category = "Home"

    def display_lifestyles(self):
        caller = self.caller
        table = PrettyTable(["{wRating{n", "{wCost{n", "{wPrestige{n"])
        caller.msg("{wLifestyles:{n")
        for rating in LIFESTYLES:
            num = str(rating)
            if caller.db.player_ob.Dominion.lifestyle_rating == rating:
                num += '{w*{n'
            table.add_row([num, LIFESTYLES[rating][0], LIFESTYLES[rating][1]])
        caller.msg(str(table), options={'box': True})
    
    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        entrances = loc.db.entrances or []
        owners = loc.db.owners or []
        keylist = loc.db.keylist or []
        if caller not in owners and not caller.check_permstring("builders"):
            caller.msg("You are not the owner of this room.")
            return
        if not entrances:
            from evennia.objects.models import ObjectDB
            entrances = list(ObjectDB.objects.filter(db_destination=loc))
            loc.db.entrances = entrances
            for ent in entrances:
                ent.locks.add("usekey: perm(builders) or roomkey(%s)" % loc.id)
        if not self.args and not self.switches:
            locked = "{rlocked{n" if loc.db.locked else "{wunlocked{n"
            caller.msg("Your home is currently %s." % locked)
            caller.msg("{wOwners:{n %s" % ", ".join(str(ob) for ob in owners))
            caller.msg("{wCharacters who have keys:{n %s" % ", ".join(str(ob) for ob in keylist))
            entrance = entrances[0]
            entmsg = entrance.db.success_traverse or ""
            errmsg = entrance.db.err_traverse or ""
            caller.msg("{wMessage upon passing through locked door:{n %s" % entmsg)
            caller.msg("{wMessage upon being denied access:{n %s" % errmsg)
            return
        if "unlock" in self.switches:
            if not loc.db.locked:
                caller.msg("Your home is already unlocked.")
                return
            loc.db.locked = False
            caller.msg("Your house is now unlocked.")
            for ent in entrances:
                ent.unlock()
            return
        if "lock" in self.switches:
            if loc.db.locked:
                caller.msg("Your home is already locked.")
                return
            loc.db.locked = True
            caller.msg("Your house is now locked.")
            for ent in entrances:
                ent.lock()
            return
        if "lifestyle" in self.switches and not self.args:
            # list lifestyles
            self.display_lifestyles()
            return
        if not self.args:
            caller.msg("You must provide an argument to the command.")
            return
        if "lockmsg" in self.switches:
            for r_exit in entrances:
                r_exit.db.err_traverse = self.args
            caller.msg("{wThe message those who can't enter now see is{n: %s" % self.args)
            return
        if "passmsg" in self.switches:
            for r_exit in entrances:
                r_exit.db.success_traverse = self.args
            caller.msg("{wThe message those who enter will now see is{n: %s" % self.args)
            return
        if "lifestyle" in self.switches:
            if caller not in owners:
                caller.msg("You may only set the lifestyle rating for an owner.")
                return
            try:
                LIFESTYLES[int(self.args)]
            except (IndexError, TypeError, ValueError):
                caller.msg("%s is not a valid lifestyle." % self.args)
                self.display_lifestyles()
                return
            caller.db.player_ob.Dominion.lifestyle_rating = int(self.args)
            caller.db.player_ob.Dominion.save()
            caller.msg("Your lifestyle rating has been set to %s." % self.args)
            return
        player = caller.player.search(self.lhs)
        if not player:
            return
        char = player.db.char_ob
        if not char:
            caller.msg("No character found.")
            return
        keys = char.db.keylist or []
        if "key" in self.switches:          
            if loc in keys and char in keylist:
                caller.msg("They already have a key to here.")
                return
            if loc not in keys:
                keys.append(loc)
                char.db.keylist = keys
            if char not in keylist:
                keylist.append(char)
                loc.db.keylist = keylist
            char.msg("{c%s{w has granted you a key to %s." % (caller, loc))
            caller.msg("{wYou have granted {c%s{w a key.{n" % char)
            return
        if "rmkey" in self.switches:
            if loc not in keys and char not in keylist:
                caller.msg("They don't have a key to here.")
                return
            if loc in keys:
                keys.remove(loc)
                char.db.keylist = keys
            if char in keylist:
                keylist.remove(char)
                loc.db.keylist = keylist
            char.msg("{c%s{w has removed your access to %s." % (caller, loc))
            caller.msg("{wYou have removed {c%s{w's key.{n" % char)
            return


class CmdAllowBuilding(MuxCommand):
    """
    @allowbuilding

    Usage:
        @allowbuilding
        @allowbuilding all[=<cost>]
        @allowbuilding <name>[,<name2>,...][=<cost>]
        @allowbuilding/clear

    Flags your current room as permitting characters to build there.
    The name provided can either be a character or organization name.
    Cost is 100 economic resources unless specified otherwise. Max
    rooms that anyone can build off here is set by the 'expansion_cap'
    attribute, defaults to 1 if not defined. Tracked separately for
    each org/player, so any number of people could build 1 room off
    a room with expansion_cap of 1 in a room, as long as they are
    permitted to do so.
    """
    key = "@allowbuilding"
    locks = "cmd:perm(Builders)"
    help_category = "Building"

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        permits = loc.db.permitted_builders or {}
        if not self.args and not self.switches:
            table = PrettyTable(["Name", "Cost"])
            for permit_id in permits:
                if permit_id == "all":
                    owner = "all"
                else:
                    owner = AssetOwner.objects.get(id=permit_id)
                cost = permits[permit_id]
                table.add_row([str(owner), cost])
            caller.msg(str(table))
            return
        if "clear" in self.switches:
            loc.db.permitted_builders = {}
            caller.msg("Perms wiped.")
            return
        cost = self.rhs and int(self.rhs) or 100
        for name in self.lhslist:
            if name == "all":
                permits["all"] = cost
                continue
            try:
                owner = AssetOwner.objects.get(Q(organization_owner__name__iexact=name)
                                               | Q(player__player__username__iexact=name))
            except AssetOwner.DoesNotExist:
                caller.msg("No owner by name of %s." % name)
                continue
            permits[owner.id] = cost
        loc.db.permitted_builders = permits
        caller.msg("Perms set.")
        return


class CmdBuildRoom(CmdDig):
    """
    +buildroom - build and connect new rooms to the current one

    Usage:
      +buildroom roomname=exit_to_there[;alias], exit_to_here[;alias]

      +buildroom/org orgname/roomname=[exits]

    Examples:
       +buildroom kitchen = north;n, south;s
       +buildroom sheer cliff= climb up, climb down
       +buildroom/org velenosa/dungeon=door;d, out;o

    This command is a convenient way to build rooms quickly; it creates the
    new room and you can optionally set up exits back and forth between your
    current room and the new one. You can add as many aliases as you
    like to the name of the room and the exits in question; an example
    would be 'north;no;n'.
    """
    key = "+buildroom"
    locks = "cmd:all()"
    help_category = "Home"

    def func(self):
        """Do the digging. Inherits variables from ObjManipCommand.parse()"""

        caller = self.caller
        loc = caller.location

        # lots of checks and shit here
        permits = loc.db.permitted_builders or {}
        if not permits:
            caller.msg("No one is currently allowed to build a house from here.")
            return
        expansions = loc.db.expansions or {}
        max_expansions = loc.db.expansion_cap or 1
        assets = None
        # base cost = 1000
        dompc = caller.db.player_ob.Dominion
        if "org" in self.switches:
            max_rooms = 100
            try:
                largs = self.lhs.split("/")
                orgname = largs[0]
                roomname = largs[1]
            except IndexError:
                caller.msg("Please specify orgname/roomname.")
                return
            try:

                org = Organization.objects.get(Q(name__iexact=orgname) &
                                               Q(members__player=dompc) &
                                               Q(members__deguilded=False))
                if not org.access(caller, 'build'):
                    caller.msg("You are not permitted to build for this org.")
                    return    
                self.lhs = roomname
                self.lhslist = [roomname]
                # fix args for CmdDig
                self.parse()
                assets = org.assets
                cost = permits[assets.id]
            except KeyError:
                if "all" not in permits:
                    caller.msg("That org is not permitted to build here.")
                    return
                cost = permits["all"]
            except Organization.DoesNotExist:
                caller.msg("No org by that name: %s." % orgname)
                return
        else:
            max_rooms = 3
            assets = dompc.assets
            if assets.id in permits:
                cost = permits[assets.id]
            else:
                if "all" not in permits:
                    caller.msg("You are not allowed to build here.")
                    return
                cost = permits["all"]
        try:
            if expansions.get(assets.id, 0) >= max_expansions:
                caller.msg("You have built as many rooms from this space as you are allowed.")
                return
        except (AttributeError, TypeError, ValueError):
            caller.msg("{rError logged.{n")
            inform_staff("Room %s has an invalid expansions attribute." % loc.id)
            return
        if not self.lhs:
            caller.msg("The cost for you to build from this room is %s." % cost)
            return
        if cost > assets.economic:
            noun = "you" if dompc.assets == assets else str(assets)
            caller.msg("It would cost %s %s to build here, but only have %s." % (noun, cost, assets.economic))
            if noun != "you":
                caller.msg("Deposit resources into the account of %s." % noun)
            return
        tagname = "%s_owned_room" % str(assets)
        if tagname not in loc.tags.all() and (ObjectDB.objects.filter(Q(db_typeclass_path=settings.BASE_ROOM_TYPECLASS)
                                                                      & Q(db_tags__db_key__iexact=tagname)
                                                                      ).count() > max_rooms):
            caller.msg("You have as many rooms as you are allowed.")
            return
        if not self.rhs or len(self.rhslist) < 2:
            caller.msg("You must specify an exit and return exit for the new room.")
            return
        
        if not re.findall('^[\-\w\'{\[,%; ]+$', self.lhs) or not re.findall('^[\-\w\'{\[,%; ]+$', self.rhs):
            caller.msg("Invalid chraacters entered for names or exits.")
        new_room = CmdDig.func(self)
        if not new_room:
            return
        assets.economic -= cost
        assets.save()
        # do setup shit for new room here
        new_room.db.room_owner = assets.id
        new_room.tags.add("player_made_room")
        new_room.tags.add(tagname)
        new_room.tags.add("private")
        new_room.db.expansion_cap = 20
        new_room.db.expansions = {}
        new_room.db.cost_increase_per_expansion = 25
        cost_increase = loc.db.cost_increase_per_expansion or 0
        new_room.db.permitted_builders = {assets.id: cost + cost_increase}
        new_room.db.x_coord = loc.db.x_coord
        new_room.db.y_coord = loc.db.y_coord
        my_expansions = expansions.get(assets.id, 0) + 1
        expansions[assets.id] = my_expansions
        loc.db.expansions = expansions
        if cost_increase and assets.id in permits:
            permits[assets.id] += cost_increase
            loc.db.permitted_builders = permits


class CmdManageRoom(MuxCommand):
    """
    +manageroom

    Usage:
        +manageroom
        +manageroom/name <name>
        +manageroom/desc <description>
        +manageroom/exitname <exit>=<new name>
        +manageroom/addhome <owner>
        +manageroom/confirmhome <owner>
        +manageroom/rmhome <owner>
        +manageroom/addshop <owner>
        +manageroom/confirmshop <owner>
        +manageroom/rmshop <owner>
        +manageroom/toggleprivate
        +manageroom/setbarracks

    Flags your current room as permitting characters to build there.
    Cost is 100 economic resources unless specified otherwise.
    """
    key = "+manageroom"
    locks = "cmd:all()"
    help_category = "Home"

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        try:
            owner = AssetOwner.objects.get(id=loc.db.room_owner)
        except AssetOwner.DoesNotExist:
            caller.msg("No owner is defined here.")
            return
        org = owner.organization_owner
        if not org and not (owner == caller.db.player_ob.Dominion.assets
                            or ('confirmhome' in self.switches or
                                'confirmshop' in self.switches)):
            caller.msg("You are not the owner here.")
            return
        if org and not (org.access(caller, 'build') or ('confirmhome' in self.switches or
                                                        'confirmshop' in self.switches)):
            caller.msg("You do not have permission to build here.")
            return
        if not self.switches:
            # display who has a home here, who has a shop here
            owners = loc.db.owners or []
            caller.msg("{wHome Owners:{n %s" % ", ".join(str(ob) for ob in owners))
            shops = loc.db.shopowner
            caller.msg("{wShop Owners:{n %s" % shops)
            return
        if "name" in self.switches:
            loc.name = self.args or loc.key
            caller.msg("Room name changed to %s." % loc)
            return
        if "exitname" in self.switches:
            if not self.rhs:
                caller.msg("Invalid usage.")
                return
            rhslist = self.rhs.split(";")
            rhs = rhslist[0]
            aliases = rhslist[1:]
            exit_object = caller.search(self.lhs)
            if not exit_object:
                return
            old = str(exit_object)
            if exit_object.typeclass_path != settings.BASE_EXIT_TYPECLASS:
                caller.msg("That is not an exit.")
                return
            exit_object.name = rhs
            exit_object.save()
            exit_object.aliases.clear()
            for alias in aliases:
                exit_object.aliases.add(alias)
            if exit_object.destination:
                exit_object.flush_from_cache()
            caller.msg("%s changed to %s." % (old, exit_object))
            return
        if "desc" in self.switches:
            if loc.desc:
                cost = loc.db.desc_cost or DESC_COST
            else:
                cost = 0
            if loc.ndb.confirm_desc_change != self.args:
                caller.msg("Your room's current desc is:")
                caller.msg(loc.desc)
                caller.msg("{wCost of changing desc:{n %s economic resources" % cost)
                if self.args:
                    caller.msg("New desc:")
                    caller.msg(self.args)
                    caller.msg("{wTo confirm this, use the command again.{n")
                    caller.msg("{wChanging this desc will prompt you again for a confirmation.{n")
                    loc.ndb.confirm_desc_change = self.args
                return
            if cost:
                if cost > owner.economic:
                    caller.msg("It would cost %s to re-desc the room, and you have %s." % (cost, owner.economic))
                    return
                owner.economic -= cost
                owner.save()
            loc.desc = self.args
            loc.save()
            loc.ndb.confirm_desc_change = None
            caller.msg("Desc changed to:")
            caller.msg(loc.desc)
            return
        if "confirmhome" in self.switches:
            if caller.db.homeproposal != loc:
                caller.msg("You don't have an active invitation to accept here. Have them reissue it.")
                return
            caller.attributes.remove("homeproposal")
            loc.setup_home(caller)
            caller.msg("You have set up your home here.")
            return
        if "confirmshop" in self.switches:
            if caller.db.shopproposal != loc:
                caller.msg("You don't have an active invitation to accept here. Have them reissue it.")
                return
            caller.attributes.remove("shopproposal")
            loc.setup_shop(caller)
            caller.msg("You have set up a shop here.")
            return
        if "toggleprivate" in self.switches:
            if "private" in loc.tags.all():
                loc.tags.remove("private")
                caller.msg("Room no longer private.")
                return
            loc.tags.add("private")
            caller.msg("Room is now private.")
            return
        if "setbarracks" in self.switches:
            tagname = str(owner) + "_barracks"
            other_barracks = ObjectDB.objects.filter(db_tags__db_key=tagname)
            for obj in other_barracks:
                obj.tags.remove(tagname)
            loc.tags.add(tagname)
            self.msg("%s set to %s's barracks." % (loc, owner))
            return
        player = caller.player.search(self.args)
        if not player:
            return
        char = player.db.char_ob
        if not char:
            caller.msg("No char.")
            return
        if "addhome" in self.switches or "addshop" in self.switches:
            noun = "home" if "addhome" in self.switches else "shop" 
            if noun == "home":
                char.db.homeproposal = loc
            else:
                char.db.shopproposal = loc
                if loc.db.shopowner:
                    caller.msg("You must shut down the current shop here before adding another.")
                    return
            msg = "%s has offered you a %s. To accept it, go to %s" % (caller, noun, loc.key)
            msg += " and use {w+manageroom/confirm%s{n." % noun
            player.send_or_queue_msg(msg)
            caller.msg("You have offered %s this room as a %s." % (char, noun))
            return
        if "rmhome" in self.switches:
            loc.remove_homeowner(char)
            player.send_or_queue_msg("Your home at %s has been removed." % loc)
            return
        if "rmshop" in self.switches:
            loc.del_shop()
            player.send_or_queue_msg("Your shop at %s has been removed." % loc)
            return

        

class CmdManageShop(MuxCommand):
    """
    +manageshop

    Usage:
        +manageshop
        +manageshop/sellitem <object>=<price>
        +manageshop/rmitem <object id>
        +manageshop/all <markup percentage>
        +managehsop/refinecost <percentage>
        +manageshop/addrecipe <recipe name>=<markup percentage>
        +manageshop/rmrecipe <recipe name>
        +manageshop/addblacklist <player or org name>
        +manageshop/rmblacklist <player or org name>
        +manageshop/orgdiscount <org name>=<percentage>

    Sets prices for your shop. Note that if you use 'all', that will
    be used for any recipe you don't explicitly set a price for.
    """
    key = "+manageshop"
    locks = "cmd:all()"
    help_category = "Home"

    def list_prices(self):
        loc = self.caller.location
        prices = loc.db.crafting_prices or {}
        msg = "{wCrafting Prices{n\n"
        table = PrettyTable(["{wName{n", "{wPrice Markup Percentage{n"])
        for price in prices:
            if price == "removed":
                continue
            if price == "all" or price == "refine":
                name = price
            else:
                name = (CraftingRecipe.objects.get(id=price)).name
            table.add_row([name, "%s%%" % prices[price]])
        msg += str(table)
        msg += "\n{wItem Prices{n\n"
        table = PrettyTable(["{wID{n", "{wName{n", "{wPrice{n"])
        prices = loc.db.item_prices or {}
        for price in prices:
            obj = ObjectDB.objects.get(id=price)
            table.add_row([price, str(obj), prices[price]])
        msg += str(table)
        return msg
    
    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        if caller != loc.db.shopowner:
            caller.msg("You are not the shop's owner.")
            return
        if not self.args:
            caller.msg(self.list_prices())
            caller.msg("Discounts: %s" % str(loc.db.discounts))
            caller.msg("Blacklist: %s" % str(loc.db.blacklist))
            return
        if "sellitem" in self.switches:
            try:
                price = int(self.rhs)
                if price < 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Price must be a positive number.")
                return
            results = caller.search(self.lhs, location=caller, quiet=True)
            obj = AT_SEARCH_RESULT(results, caller, self.lhs, False,
                                   nofound_string="You don't carry %s." % self.lhs,
                                   multimatch_string="You carry more than one %s:" % self.lhs)
            if not obj:
                return
            obj.at_drop(caller)
            obj.location = None
            loc.db.item_prices[obj.id] = price
            caller.msg("You put %s for sale for %s silver." % (obj, price))
            return
        if "rmitem" in self.switches:
            try:
                num = int(self.args)
                if num not in loc.db.item_prices:
                    caller.msg("No item by that ID being sold.")
                    return
                obj = ObjectDB.objects.get(id=num)
            except ObjectDB.DoesNotExist:
                caller.msg("No object by that ID exists.")
                return
            except (ValueError, TypeError):
                caller.msg("You have to specify the ID # of an item you're trying to remove.")
                return
            obj.move_to(caller)
            del loc.db.item_prices[obj.id]
            caller.msg("You have removed %s from your sale list." % obj)
            return
        if "all" in self.switches or "refinecost" in self.switches:
            try:
                cost = int(self.args)
                if cost < 0:
                    raise ValueError
            except ValueError:
                caller.msg("Cost must be a non-negative number.")
                return
            if "all" in self.switches:
                loc.db.crafting_prices['all'] = cost
                caller.msg("Cost for non-specified recipes set to %s percent markup." % cost)
            else:
                loc.db.crafting_prices['refine'] = cost
                caller.msg("Cost for refining set to %s percent markup." % cost)
            return
        if "addrecipe" in self.switches:
            try:
                recipe = caller.db.player_ob.Dominion.assets.recipes.get(name__iexact=self.lhs)
                cost = int(self.rhs)
                if cost < 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Cost must be a positive number.")
                return
            except (CraftingRecipe.DoesNotExist, CraftingRecipe.MultipleObjectsReturned):
                caller.msg("Could not retrieve a recipe by that name.")
                return
            loc.db.crafting_prices[recipe.id] = cost
            caller.msg("Price for %s set to %s." % (recipe.name, cost))
            removedlist = loc.db.crafting_prices.get("removed", [])
            if recipe.id in removedlist:
                removedlist.remove(recipe.id)
            loc.db.crafting_prices['removed'] = removedlist
            return
        if "rmrecipe" in self.switches:
            arg = None
            try:
                recipe = None
                if self.lhs.lower() == "all":
                    arg = "all"
                elif self.lhs.lower() == "refining":
                    arg = "refining"
                else:
                    recipe = caller.db.player_ob.Dominion.assets.recipes.get(name__iexact=self.lhs)
                    arg = recipe.id
                del loc.db.crafting_prices[arg]
                caller.msg("Price for %s has been removed." % recipe.name if recipe else arg)
                return
            except KeyError:
                removedlist = loc.db.crafting_prices.get("removed", [])
                if arg in removedlist:
                    caller.msg("You had no price listed for that recipe.")
                else:
                    removedlist.append(arg)
                    loc.db.crafting_prices["removed"] = removedlist
                return
            except CraftingRecipe.DoesNotExist:
                caller.msg("No recipe found by that name.")
                return
        if "addblacklist" in self.switches or "rmblacklist" in self.switches:
            try:
                targ = caller.player.search(self.args)
                org = False
                if not targ:
                    org = True
                    targ = Organization.objects.get(name__iexact=self.args)
                else:
                    targ = targ.db.char_ob            
                if "addblacklist" in self.switches:
                    if org:
                        if targ.name in loc.db.blacklist:
                            caller.msg("They are already in the blacklist.")
                            return
                        loc.db.blacklist.append(targ.name)
                    else:
                        if targ in loc.db.blacklist:
                            caller.msg("They are already in the blacklist.")
                            return
                        loc.db.blacklist.append(targ)
                    caller.msg("%s added to blacklist." % targ)
                else:
                    if org:
                        if targ.name not in loc.db.blacklist:
                            caller.msg("They are not in the blacklist.")
                            return
                        loc.db.blacklist.remove(targ.name)
                    else:
                        if targ not in loc.db.blacklist:
                            caller.msg("They are not in the blacklist.")
                            return
                        loc.db.blacklist.remove(targ)
                    caller.msg("%s removed from blacklist." % targ)
            except Organization.DoesNotExist:
                caller.msg("No valid target found by that name.")
            return
        if "orgdiscount" in self.switches:
            try:
                org = Organization.objects.get(name__iexact=self.lhs)
                discount = int(self.rhs)
                if discount > 100:
                    raise ValueError
                loc.db.discounts[org.name] = discount
                caller.msg("%s given a discount of %s percent." % (org, discount))
                return
            except (TypeError, ValueError):
                caller.msg("Discount must be a number, max of 100.")
                return
            except Organization.DoesNotExist:
                caller.msg("No organization by that name found.")
                return
        caller.msg("Invalid switch.")


class CmdBuyFromShop(CmdCraft):
    """
    +shop

    Usage:
        +shop
        +shop/buy <item number>
        +shop/look <item number>
        +shop/refine <object>[=<additional silver to spend>]
        +shop/craft <recipe name>
        +shop/name <name>
        +shop/desc <description>
        +shop/adorn <material type>=<amount>
        +shop/finish [<additional silver to invest>]
        +shop/changename <object>=<new name>

    Flags your current room as permitting characters to build there.
    Cost is 50 economic resources unless specified otherwise.
    """
    key = "+shop"
    aliases = ["@shop", "shop"]
    locks = "cmd:all()"
    help_category = "Home"

    def get_discount(self):
        """Returns our percentage discount"""
        loc = self.caller.location
        discount = 0.0
        for org in self.caller.db.player_ob.Dominion.current_orgs:
            odiscount = loc.db.discounts.get(org.name, 0.0)
            if odiscount and not discount:
                discount = odiscount
            if odiscount and discount and odiscount > discount:
                discount = odiscount
        return discount

    def get_refine_price(self, base):
        """Price of refining"""
        loc = self.caller.location
        price = 0
        if "refine" in loc.db.crafting_prices:
            price = (base * loc.db.crafting_prices["refine"])/100.0
        if "all" in loc.db.crafting_prices:
            price = (base * loc.db.crafting_prices["all"])/100.0
        if price:
            price -= (price * self.get_discount()/100.0)
            if price < 0:
                raise ValueError("Negative price due to discount")
            return price
        raise ValueError
    
    def get_recipe_price(self, recipe):
        """Price for crafting a recipe"""
        loc = self.caller.location
        base = recipe.value
        price = 0
        if recipe.id in loc.db.crafting_prices:
            price = (base * loc.db.crafting_prices[recipe.id])/100.0
        elif "all" in loc.db.crafting_prices:
            price = (base * loc.db.crafting_prices["all"])/100.0
        if price:
            price -= (price * self.get_discount()/100.0)
            if price < 0:
                raise ValueError("Negative price due to discount")
            return price
        # no price defined
        raise ValueError         

    def list_prices(self):
        """List prices of everything"""
        loc = self.caller.location
        prices = loc.db.crafting_prices or {}
        msg = "{wCrafting Prices{n\n"
        table = PrettyTable(["{wName{n", "{wCraft Price{n", "{wRefine Price{n"])
        recipes = loc.db.shopowner.db.player_ob.Dominion.assets.recipes.all()
        removed = prices.get("removed", [])
        for recipe in recipes:
            if recipe.id in removed:
                continue
            try:
                try:
                    refineprice = str(self.get_refine_price(recipe.value))
                except ValueError:
                    refineprice = "--"
                table.add_row([recipe.name, str(recipe.additional_cost + self.get_recipe_price(recipe)),
                               refineprice])
            except (ValueError, TypeError):
                continue
        msg += str(table)
        msg += "\n{wItem Prices{n\n"
        table = PrettyTable(["{wID{n", "{wName{n", "{wPrice{n"])
        prices = loc.db.item_prices or {}
        for price in prices:
            obj = ObjectDB.objects.get(id=price)
            table.add_row([price, obj.name, prices[price]])
        msg += str(table)
        return msg
    
    def pay_owner(self, price, msg):
        """Pay money to the other and send an inform of the sale"""
        loc = self.caller.location
        loc.db.shopowner.pay_money(-price)
        loc.db.shopowner.db.player_ob.inform(msg, category="shop")

    def buy_item(self, item):
        """Buy an item from inventory - pay the owner and get the item"""
        loc = self.caller.location
        price = loc.db.item_prices[item.id]
        price -= price * (self.get_discount()/100.0)
        self.caller.pay_money(price)
        self.pay_owner(price, "%s has bought %s for %s." % (self.caller, item, price))
        item.move_to(self.caller)
        del loc.db.item_prices[item.id]

    def check_blacklist(self):
        """See if we're allowed to buy"""
        caller = self.caller
        loc = caller.location
        if caller in loc.db.blacklist:
            return True
        for org in caller.db.player_ob.Dominion.current_orgs:
            if org.name in loc.db.blacklist:
                return True
        return False

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        self.crafter = loc.db.shopowner
        if self.check_blacklist():
            caller.msg("You are not permitted to buy from this shop.")
            return
        if not self.switches and not self.args:
            caller.msg(self.list_prices())
            project = caller.db.crafting_project
            if project:
                caller.msg(self.display_project(project))
            return
        if "buy" in self.switches:
            try:
                num = int(self.args)
                price = loc.db.item_prices[num]
                obj = ObjectDB.objects.get(id=num)
            except (TypeError, ValueError, KeyError):
                caller.msg("You must supply the ID number of an item being sold.")
                return
            if price > caller.db.currency:
                caller.msg("You cannot afford it.")
                return
            self.buy_item(obj)
            return
        if "look" in self.switches:
            try:
                num = int(self.args)
                obj = ObjectDB.objects.get(id=num, id__in=loc.db.item_prices.keys())
            except (TypeError, ValueError):
                self.msg("Please provide a number of an item.")
                return
            except ObjectDB.DoesNotExist:
                caller.msg("No item found by that number.")
                return
            caller.msg(obj.return_appearance(caller))
            return
        if ("craft" in self.switches or "refine" in self.switches or
                "desc" in self.switches or "adorn" in self.switches or
                "finish" in self.switches or "name" in self.switches or
                "abandon" in self.switches or "changename" in self.switches):
            return CmdCraft.func(self)
        caller.msg("Invalid switch.")


class ShopCmdSet(CmdSet):
    """CmdSet for shop spaces."""
    key = "ShopCmdSet"
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
        self.add(CmdManageShop())
        self.add(CmdBuyFromShop())
