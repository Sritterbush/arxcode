"""
Extended Room

Evennia Contribution - Griatch 2012

This is an extended Room typeclass for Evennia. It is supported
by an extended Look command and an extended @desc command, also
in this module.


Features:

1) Time-changing description slots

This allows to change the full description text the room shows
depending on larger time variations. Four seasons - spring, summer,
autumn and winter are used by default). The season is calculated
on-demand (no Script or timer needed) and updates the full text block.

There is also a general description which is used as fallback if
one or more of the seasonal descriptions are not set when their
time comes.

An updated @desc command allows for setting seasonal descriptions.

The room uses the src.utils.gametime.GameTime global script. This is
started by default, but if you have deactivated it, you need to
supply your own time keeping mechanism.


2) In-description changing tags

Within each seasonal (or general) description text, you can also embed
time-of-day dependent sections. Text inside such a tag will only show
during that particular time of day. The tags looks like <timeslot> ...
</timeslot>. By default there are four timeslots per day - morning,
afternoon, evening and night.


3) Details

The Extended Room can be "detailed" with special keywords. This makes
use of a special Look command. Details are "virtual" targets to look
at, without there having to be a database object created for it. The
Details are simply stored in a dictionary on the room and if the look
command cannot find an object match for a "look <target>" command it
will also look through the available details at the current location
if applicable. An extended @desc command is used to set details.


4) Extra commands

  CmdExtendedLook - look command supporting room details
  CmdExtendedDesc - @desc command allowing to add seasonal descs and details,
                    as well as listing them
  CmdGameTime     - A simple "time" command, displaying the current
                    time and season.


Installation/testing:

1) Add CmdExtendedLook, CmdExtendedDesc and CmdGameTime to the default cmdset
   (see wiki how to do this).
2) @dig a room of type contrib.extended_room.ExtendedRoom (or make it the
   default room type)
3) Use @desc and @detail to customize the room, then play around!

"""

import re
from django.conf import settings
from evennia.contrib.extended_room import ExtendedRoom
from evennia import gametime
from evennia import default_cmds
from evennia import utils
from evennia.objects.models import ObjectDB
from typeclasses.mixins import DescMixins, AppearanceMixins, NameMixins
from world.msgs.messagehandler import MessageHandler

# error return function, needed by Extended Look command
_AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

# room cmdsets
MARKETCMD = "cmdsets.market.MarketCmdSet"
BANKCMD = "cmdsets.bank.BankCmdSet"
RUMORCMD = "cmdsets.rumor.RumorCmdSet"
HOMECMD = "cmdsets.home.HomeCmdSet"
SHOPCMD = "cmdsets.home.ShopCmdSet"


# implements the Extended Room

class ArxRoom(DescMixins, NameMixins, ExtendedRoom, AppearanceMixins):
    """
    This room implements a more advanced look functionality depending on
    time. It also allows for "details", together with a slightly modified
    look command.
    """
    

    def at_init(self):
        """
        This is always called whenever this object is initiated --
        that is, whenever it its typeclass is cached from memory. This
        happens on-demand first time the object is used or activated
        in some way after being created but also after each server
        restart or reload.
        """
        self.is_room = True
        self.is_exit = False
        self.is_character = False
        self.messages = MessageHandler(self)
        
    def get_visible_characters(self, pobject):
        "Returns a list of visible characters in a room."
        char_list = [ob for ob in self.contents if ob.is_character]
        return [char for char in char_list if char.access(pobject, "view")]

    

    def return_appearance(self, looker, detailed=False, format_desc=True):
        "This is called when e.g. the look command wants to retrieve the description of this object."
        # update desc
        super(ArxRoom, self).return_appearance(looker)
        # return updated desc plus other stuff
        return AppearanceMixins.return_appearance(self, looker, detailed, format_desc) + self.command_string() + self.event_string()
    
    def _current_event(self):
        if not self.db.current_event:
            return None
        try:
            from game.dominion.models import RPEvent
            return RPEvent.objects.get(id=self.db.current_event)
        except Exception:
            return None
    event = property(_current_event)

    def _entrances(self):
        return ObjectDB.objects.filter(db_destination=self)
    entrances = property(_entrances)
    
    def event_string(self):
        event = self.event
        if not event:
            return ""
        msg = "\n{wCurrent Event{n: %s (for more - {w@cal %s{n)" % (event.name, event.id)
        if event.celebration_tier == 0:
            largesse = "poor"
        elif event.celebration_tier == 1:
            largesse = "common"
        elif event.celebration_tier == 2:
            largesse = "refined"
        elif event.celebration_tier == 3:
            largesse = "grand"
        elif event.celebration_tier == 4:
            largesse = "extravagant"
        elif event.celebration_tier == 5:
            largesse = "legendary"
        msg += "\n{wScale of the Event:{n %s" % largesse
        msg += "\n{rEvent logging is currently turned on in this room.{n\n"
        desc = event.room_desc
        if desc:
            msg += "\n" + desc + "\n"
        return msg

    def command_string(self):
        msg = ""
        if "shop" in self.tags.all():
            msg += "\n    {wYou can {c+shop{w here.{n"
        if "bank" in self.tags.all():
            msg += "\n    {wYou can {c+bank{w here.{n"
        return msg

    def _homeowners(self):
        return self.db.owners or []
    homeowners = property(_homeowners)
    def give_key(self, char):
        keylist = char.db.keylist or []
        if self not in keylist:
            keylist.append(self)
        char.db.keylist = keylist
    def remove_key(self, char):
        keylist = char.db.keylist or []
        if self in keylist:
            keylist.remove(self)
        char.db.keylist = keylist
    def add_homeowner(self, char, sethomespace=True):
        owners = self.db.owners or []
        if char not in owners:
            owners.append(char)
            self.give_key(char)
        self.db.owners = owners
        if sethomespace:
            char.home = self
            char.save()
    def remove_homeowner(self, char):
        owners = self.db.owners or []
        if char in owners:
            owners.remove(char)
            self.remove_key(char)
            if char.home == self:
                char.home = ObjectDB.objects.get(id=13)
                char.save()
            self.db.owners = owners
            if not owners:
                self.del_home()
        
    def setup_home(self, owners=None, sethomespace=True):
        owners = utils.make_iter(owners)
        for owner in owners:
            self.add_homeowner(owner, sethomespace)
        self.tags.add("home")
        for ent in self.entrances:
            ent.locks.add("usekey: perm(builders) or roomkey(%s)" % self.id)
        if "HomeCmdSet" not in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.add(HOMECMD, permanent=True)
        try:
            # add our room owner as a homeowner if they're a player
            from game.dominion.models import AssetOwner
            aowner = AssetOwner.objects.get(id=self.db.room_owner)
            char = aowner.player.player.db.char_ob
            if char not in owners:
                self.add_homeowner(char, False)
        except Exception:
            pass

    def del_home(self):
        if self.db.owners:
            self.db.owners = []
        self.tags.remove("home")
        for ent in self.entrances:
            ent.locks.add("usekey: perm(builders)")
            ent.db.locked = False
        if "HomeCmdSet" in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.delete(HOMECMD)

    def setup_shop(self, owner):
        self.db.shopowner = owner
        self.tags.add("shop")
        if "ShopCmdSet" not in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.add(SHOPCMD, permanent=True)
        self.db.discounts = {}
        self.db.crafting_prices = {}
        self.db.blacklist = []
        self.db.item_prices = {}

    def return_inventory(self):
        for id in self.db.item_prices or {}:
            obj = ObjectDB.objects.get(id=id)
            obj.move_to(self.db.shopowner)

    def del_shop(self):
        self.return_inventory()
        self.tags.remove("shop")
        if "ShopCmdSet" in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.delete(SHOPCMD)
        self.attributes.remove("discounts")
        self.attributes.remove("crafting_prices")
        self.attributes.remove("blacklist")
        self.attributes.remove("shopowner")

    def msg_contents(self, text=None, exclude=None, from_obj=None, **kwargs):
        """
        Emits something to all objects inside an object.

        exclude is a list of objects not to send to. See self.msg() for
                more info.
        """
        eventid = self.db.current_event
        gm_only = kwargs.get('gm_msg', False)
        if gm_only:
            exclude = exclude or []
            exclude = exclude + [ob for ob in self.contents if not ob.check_permstring("builders")]
        # if we have an event at this location, log messages
        if eventid:
            from evennia.scripts.models import ScriptDB
            try:
                event_script = ScriptDB.objects.get(db_key="Event Manager")
                if gm_only:
                    event_script.add_gmnote(eventid, text)
                else:
                    event_script.add_msg(eventid, text, from_obj)
            except ScriptDB.DoesNotExist:
                if from_obj:
                    from_obj.msg("Error: Event Manager not found.")
        super(Room, self).msg_contents(text, exclude=exclude,
                                from_obj=from_obj, **kwargs)

        

class CmdExtendedLook(default_cmds.CmdLook):
    """
    look

    Usage:
      look
      look <obj>
      look <room detail>
      look *<player>

    Observes your location, details at your location or objects in your vicinity.
    """
    arg_regex = r'\/|\s|$'
    def func(self):
        """
        Handle the looking - add fallback to details.
        """
        caller = self.caller
        args = self.args
        looking_at_obj = None
        if args:
            alist = args.split("'s ")
            if len(alist) == 2:               
                obj = caller.search(alist[0], use_nicks=True, quiet=True)
                if obj:
                    obj = utils.make_iter(obj)
                    looking_at_obj = caller.search(alist[1], location=obj[0], use_nicks=True, quiet=True)
            else:
                looking_at_obj = caller.search(args, use_nicks=True, quiet=True)
            # originally called search with invalid arg of no_error or something instead of quiet
            if not looking_at_obj:
                # no object found. Check if there is a matching
                # detail at location.
                location = caller.location
                if location and hasattr(location, "return_detail") and callable(location.return_detail):
                    detail = location.return_detail(args)
                    if detail:
                        # we found a detail instead. Show that.
                        caller.msg(detail)
                        return
                # no detail found. Trigger delayed error messages
                _AT_SEARCH_RESULT(looking_at_obj, caller, args, False)
                return
            else:
                # we need to extract the match manually.
                if len(utils.make_iter(looking_at_obj)) > 1:
                    _AT_SEARCH_RESULT(looking_at_obj, caller, args, False)
                    return
                looking_at_obj = utils.make_iter(looking_at_obj)[0]
        else:
            looking_at_obj = caller.location
            if not looking_at_obj:
                caller.msg("You have no location to look at!")
                return

        if not hasattr(looking_at_obj, 'return_appearance'):
            # this is likely due to us having a player instead
            looking_at_obj = looking_at_obj.character
        if not looking_at_obj.access(caller, "view"):
            caller.msg("Could not find '%s'." % args)
            return
        # get object's appearance
        caller.msg(looking_at_obj.return_appearance(caller, detailed=False), formatted=True)
        # the object's at_desc() method.
        looking_at_obj.at_desc(looker=caller)

class CmdStudyRawAnsi(default_cmds.MuxCommand):
    """
    prints raw ansi codes for a name
    Usage:
        @study <obj>

    Prints raw ansi.
    """
    key = "@study"
    locks = "cmd:all()"
    def func(self):
        caller = self.caller
        ob = caller.search(self.lhs)
        if not ob:
            return
        from evennia.utils.ansi import raw
        caller.msg("Escaped name: %s" % raw(ob.name))
        caller.msg("Escaped desc: %s" % raw(ob.return_appearance(caller, detailed=False)))


# Custom build commands for setting seasonal descriptions
# and detailing extended rooms.

class CmdExtendedDesc(default_cmds.CmdDesc):
    """
    @desc - describe an object or room

    Usage:
      @desc [<obj> = <description>]
      @desc/char <character>=<description>
      @desc[/switch] <description>
      @detail[/del] [<key> = <description>]
      @detail/fix <key>=<string to replace>,<new string to replace it>


    Switches for @desc:
      spring  - set description for <season> in current room
      summer
      autumn
      winter

    Switch for @detail:
      del   - delete a named detail

    Sets the "desc" attribute on an object. If an object is not given,
    describe the current room.

    The alias @detail allows to assign a "detail" (a non-object
    target for the look command) to the current room (only).

    You can also embed special time markers in your room description, like this:
      <night>In the darkness, the forest looks foreboding.</night>. Text
    marked this way will only display when the server is truly at the given
    time slot. The available times
    are night, morning, afternoon and evening.

    Note that @detail, seasons and time-of-day slots only works on rooms in this
    version of the @desc command.

    """
    aliases = ["@describe", "@detail"]

    def reset_times(self, obj):
        "By deleteting the caches we force a re-load."
        obj.ndb.last_season = None
        obj.ndb.last_timeslot = None

    def func(self):
        "Define extended command"
        caller = self.caller
        location = caller.location
        if self.cmdstring == '@detail':
            # switch to detailing mode. This operates only on current location
            if not location:
                caller.msg("No location to detail!")
                return
            if not location.access(caller, 'edit'):
                caller.msg("You do not have permission to use @desc here.")
                return
            
            if not self.args:
                # No args given. Return all details on location
                string = "{wDetails on %s{n:\n" % location
                string += "\n".join(" {w%s{n: %s" % (key, utils.crop(text)) for key, text in location.db.details.items())
                caller.msg(string)
                return
            if self.switches and self.switches[0] in 'del':
                # removing a detail.
                if self.lhs in location.db.details:
                    del location.db.details[self.lhs]
                    caller.msg("Detail %s deleted, if it existed." % self.lhs)
                self.reset_times(location)
                return
            if self.switches and self.switches[0] in 'fix':
                if not self.lhs or not self.rhs:
                    caller.msg("Syntax: @detail/fix key=old,new")
                fixlist = self.rhs.split(",")
                if len(fixlist) != 2:
                    caller.msg("Syntax: @detail/fix key=old,new")
                    return
                key = self.lhs
                try:
                    location.db.details[key] = location.db.details[key].replace(fixlist[0], fixlist[1])
                except (KeyError, AttributeError):
                    caller.msg("No such detail found.")
                    return
                caller.msg("Detail %s has had text changed to: %s" % (key, location.db.details[key]))
                return
            if not self.rhs:
                # no '=' used - list content of given detail
                if self.args in location.db.details:
                    string = "{wDetail '%s' on %s:\n{n" % (self.args, location)
                    string += location.db.details[self.args]
                    caller.msg(string)
                    return
            # setting a detail
            location.db.details[self.lhs] = self.rhs
            caller.msg("{wSet Detail %s to {n'%s'." % (self.lhs, self.rhs))
            self.reset_times(location)
            return
        else:
            # we are doing a @desc call
            if not self.args:
                if location:
                    string = "{wDescriptions on %s{n:\n" % location.key
                    string += " {wspring:{n %s\n" % location.db.spring_desc
                    string += " {wsummer:{n %s\n" % location.db.summer_desc
                    string += " {wautumn:{n %s\n" % location.db.autumn_desc
                    string += " {wwinter:{n %s\n" % location.db.winter_desc
                    string += " {wgeneral:{n %s" % location.db.general_desc
                    caller.msg(string)
                    return
            if self.switches and self.switches[0] in ("spring",
                                                      "summer",
                                                      "autumn",
                                                      "winter"):
                # a seasonal switch was given
                if self.rhs:
                    caller.msg("Seasonal descs only works with rooms, not objects.")
                    return
                switch = self.switches[0]
                if not location:
                    caller.msg("No location was found!")
                    return
                if not location.access(caller, 'edit'):
                    caller.msg("You do not have permission to @desc here.")
                    return
                if switch == 'spring':
                    location.db.spring_desc = self.args
                elif switch == 'summer':
                    location.db.summer_desc = self.args
                elif switch == 'autumn':
                    location.db.autumn_desc = self.args
                elif switch == 'winter':
                    location.db.winter_desc = self.args
                # clear flag to force an update
                self.reset_times(location)
                caller.msg("Seasonal description was set on %s." % location.key)
            else:
                # Not seasonal desc set, maybe this is not an extended room
                if self.rhs:
                    text = self.rhs
                    if "char" in self.switches:
                        # if we're looking for a character, find them by player
                        # so we can @desc someone not in the room
                        caller = caller.player
                    obj = caller.search(self.lhs)
                    # if we did a search as a player, get the character object
                    if obj and obj.db.char_ob:
                        obj = obj.db.char_ob
                    if not obj:
                        return
                else:
                    caller.msg("You must have both an object to describe and the description.")
                    caller.msg("Format: @desc <object>=<description>")
                    return
                if not obj.access(caller, 'edit'):
                    caller.msg("You do not have permission to change the @desc of %s." % obj.name)
                    return
                obj.desc = self.rhs # a compatability fallback
                if utils.inherits_from(obj, ExtendedRoom):
                    # this is an extendedroom, we need to reset
                    # times and set general_desc
                    obj.db.general_desc = text
                    self.reset_times(obj)
                    caller.msg("General description was set on %s." % obj.key)
                else:
                    caller.msg("The description was set on %s." % obj.key)



# Simple command to view the current time and season

class CmdGameTime(default_cmds.MuxCommand):
    """
    Check the game time

    Usage:
      time

    Shows the current in-game time and season.
    """
    key = "time"
    locks = "cmd:all()"
    help_category = "General"

    def func(self):
        "Reads time info from current room"
        location = self.caller.location
        if not location or not hasattr(location, "get_time_and_season"):
            self.caller.msg("No location available - you are outside time.")
        else:
            season, timeslot = location.get_time_and_season()
            prep = "a"
            if season == "autumn":
                prep = "an"
            self.caller.msg("It's %s %s day, in the %s." % (prep, season.capitalize(), timeslot))
            time = gametime.gametime(format=True)
            hour, minute = time[4], time[5]
            from server.utils.utils import get_date
            self.caller.msg("Today's date: %s. Current time: %s:%02d" % (get_date(), hour, minute))
