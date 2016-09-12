"""
General Character commands usually availabe to all characters
"""
from django.conf import settings
from server.utils import utils, prettytable
from evennia.utils.utils import make_iter, crop, time_format, variable_from_module
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from evennia.server.sessionhandler import SESSIONS
import time

# limit symbol import for API
__all__ = ("CmdHome", "CmdLook", "CmdNick",
           "CmdInventory", "CmdGet", "CmdDrop", "CmdGive",
           "CmdSay", "CmdPose", "CmdAccess")

AT_SEARCH_RESULT = variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.',1))

def args_are_currency(args):
    """
    Check if args to a given command match the expression of coins. Must be a number
    followed by 'silver' and/or 'coins', then nothing after.
    """
    units = ("pieces", "coins", "coin", "piece")
    if not args: return False
    if args in units or args in "silver":
        return True
    arglist = args.split()
    if len(arglist) < 2:
        return False
    try:
        float(arglist[0])
    except ValueError:
        return False
    if len(arglist) == 2 and not (arglist[1] == "silver" or arglist[1] in units):
        return False
    if len(arglist) == 3 and (arglist[1] != "silver" or arglist[2] not in units):
        return False
    if len(arglist) > 3:
        return False
    return True

def check_volume(obj, char, quiet=False):
    vol = obj.db.volume or 1
    max = char.db.max_volume or 100
    if char.volume + vol > max:
        if not quiet:
            char.msg("You can't carry %s." % obj)
        return False
    return True



class CmdInventory(MuxCommand):
    """
    inventory

    Usage:
      inventory
      inv
      i

    Shows your inventory.
    """
    key = "inventory"
    aliases = ["inv", "i"]
    locks = "cmd:all()"
    perm_for_switches = "Builders"

    def dynamic_help(self, caller):
        if not caller.check_permstring(self.perm_for_switches):
            return self.__doc__
        help_string = """
        inventory

        Usage :
            inventory
            inv
            inv/view <character>

        Shows character's inventory.
        """
        return help_string

    def func(self):
        "check inventory"
        show_other = self.caller.check_permstring(self.perm_for_switches) and 'view' in self.switches
        if not show_other:
            basemsg = "You are"
            char = self.caller
            player = char.player
        else:
            player = self.caller.player.search(self.args)
            if not player:
                return
            char = player.db.char_ob
            if not char:
                self.caller.msg("No character found.")
                return
            basemsg = "%s is" % char.key
        items = char.return_contents(self.caller, detailed=True, show_ids=show_other)
        if not items:
            string = "%s not carrying anything." % basemsg
        else:        
            string = "{w%s carrying:%s" % (basemsg, items)
        string += "\n{wVolume:{n %s/%s" % (char.volume,
                                           char.db.max_volume or 100)
        xp = char.db.xp or 0
        self.caller.msg("\n{w%s currently %s {c%s {wxp." % ("You" if not show_other else char.key,
                                                            "have" if not show_other else 'has',
                                                            xp))
        self.caller.msg(string)
        if hasattr(player, 'Dominion') and hasattr(player.Dominion, 'assets'):
            vault = player.Dominion.assets.vault
            self.caller.msg("{wBank Account:{n %s silver coins" % vault)
            total_prestige = player.Dominion.assets.total_prestige
            personal_prestige = player.Dominion.assets.prestige
            self.caller.msg("{wPrestige:{n %s personal, %s total" % (personal_prestige, total_prestige))
            econ = player.Dominion.assets.economic
            soc = player.Dominion.assets.social
            mil = player.Dominion.assets.military
            self.caller.msg("{wEconomic Resources:{n %s" % econ)
            self.caller.msg("{wSocial Resources:{n %s" % soc)
            self.caller.msg("{wMilitary Resources:{n %s" % mil)
            mats = player.Dominion.assets.materials.filter(amount__gte=1)
            self.caller.msg("{wMaterials:{n %s" % ", ".join(str(ob) for ob in mats))


class CmdGet(MuxCommand):
    """
    get

    Usage:
      get <obj>
      get <obj> from <obj>

    Picks up an object from your location and puts it in
    your inventory.
    """
    key = "get"
    aliases = ["grab", "take"]
    locks = "cmd:all()"

    def get_money(self, args, caller, fromobj):
        allcoins = ("coins", "coin", "silver", "money", "pieces", "all")
        currency = fromobj.db.currency or 0
        currency = float(currency)
        currency = round(currency, 2)
        if args in allcoins:
            val = currency
        else:
            arglist = args.split()
            val = float(arglist[0])
            val = round(val, 2)
        if val > currency:
            caller.msg("There isn't enough money here. You tried to get %s, and there is only %s here." % (val, currency))
            return
        fromobj.pay_money(val, caller)
        if fromobj == caller.location:
            caller.msg("You pick up %s." % args)
            caller.location.msg_contents("%s picks up %s." % (caller.name, args), exclude=caller)
        else:
            caller.msg("You get %s from %s." % (args, fromobj.name))
            caller.location.msg_contents("%s picks up %s from %s." % (caller.name, args, fromobj.name), exclude=caller)      

    def func(self):
        "implements the command."

        caller = self.caller

        if not self.args:
            caller.msg("Get what?")
            return
        # check if we're trying to get some coins
        if args_are_currency(self.args) or self.args == "all":
            self.get_money(self.args, caller, caller.location)
            return
        args = self.args.split(" from ")
        if len(args) == 2:
            fromobj = caller.search(args[1])
            self.args = args[0]
            if not fromobj:
                return
            loc = fromobj
            if not fromobj.db.container:
                caller.msg("That is not a container.")
                return
            if fromobj.db.locked and not caller.check_permstring("builders"):
                caller.msg("%s is locked. Unlock it first." % fromobj)
                return
            if args_are_currency(self.args):
                self.get_money(self.args, caller, fromobj)
                return     
        else:
            fromobj = None
            loc = caller.location           
        #print "general/get:", caller, caller.location, self.args, caller.location.contents
        obj = caller.search(self.args, location=loc, use_nicks=True, quiet=True)
        if not obj:
            AT_SEARCH_RESULT(obj, caller, self.args, False)
            return
        else:
            if len(make_iter(obj)) > 1:
                AT_SEARCH_RESULT(obj, caller, self.args, False)
                return
            obj = make_iter(obj)[0]
        if caller == obj:
            caller.msg("You can't get yourself.")
            return
        #print obj, obj.location, caller, caller==obj.location
        if caller == obj.location:
            caller.msg("You already hold that.")
            return
        if not obj.access(caller, 'get'):
            if obj.db.get_err_msg:
                caller.msg(obj.db.get_err_msg)
            else:
                caller.msg("You can't get that.")
            return
        if not check_volume(obj, caller):
            return
        if fromobj:
            getmsg = "You get %s from %s." % (obj.name, fromobj.name)
            gotmsg = "%s gets %s from %s." % (caller.name, obj.name, fromobj.name)
        else:
            getmsg = "You pick up %s." % obj.name
            gotmsg = "%s picks up %s." % (caller.name, obj.name)
        caller.msg(getmsg)
        obj.move_to(caller, quiet=True)
        caller.location.msg_contents(gotmsg, exclude=caller)
        # calling hook method
        obj.at_get(caller)


class CmdDrop(MuxCommand):
    """
    drop

    Usage:
      drop <obj>

    Lets you drop an object from your inventory into the
    location you are currently in.
    """

    key = "drop"
    locks = "cmd:all()"

    def func(self):
        "Implement command"

        caller = self.caller
        obj = None
        oblist = []
        if not self.args:
            caller.msg("Drop what?")
            return
        if self.args.lower() == "all":
            oblist = [ob for ob in caller.contents if ob not in caller.worn]
            if not oblist:
                caller.msg("You have nothing to drop.")
                return
        if args_are_currency(self.args):
            arglist = self.args.split()
            try:
                val = round(float(arglist[0]), 2)
            except ValueError:
                val = round(float(caller.db.currency or 0), 2)
            currency = round(float(caller.db.currency or 0), 2)
            if val > currency:
                caller.msg("You don't have enough money.")
                return
            caller.pay_money(val, caller.location)
            caller.msg("You drop %s coins." % val)
            caller.location.msg_contents("%s drops coins worth %s silver." % (caller, val), exclude=caller)
            return
        if not obj and not oblist:
            # Because the DROP command by definition looks for items
            # in inventory, call the search function using location = caller
            results = caller.search(self.args, location=caller, quiet=True)

            # now we send it into the error handler (this will output consistent
            # error messages if there are problems).
            obj = AT_SEARCH_RESULT(results, caller, self.args, False,
                                  nofound_string="You don't carry %s." % self.args,
                                  multimatch_string="You carry more than one %s:" % self.args)
            if not obj:
                return
            else:
                oblist = [obj]

        obnames = ", ".join(ob.name for ob in oblist)
        caller.msg("You drop %s." % (obnames))
        caller.location.msg_contents("%s drops %s." %
                                         (caller.name, obnames),
                                         exclude=caller)
        for obj in oblist:
            obj.move_to(caller.location, quiet=True)
            # Call the object script's at_drop() method.
            obj.at_drop(caller)


class CmdGive(MuxCommand):
    """
    give away things

    Usage:
      give <inventory obj> = <target>
      give <inventory obj> to <target>
      give <amount> silver to <target>
      give/mats <type>,<amount> to <target>
      give/resource <type>,<amount> to <target>

    Gives an items from your inventory to another character,
    placing it in their inventory.
    """
    key = "give"
    locks = "cmd:all()"

    def func(self):
        "Implement give"

        caller = self.caller
        to_give = None
        if not self.args:
            caller.msg("Usage: give <inventory object> = <target>")
            return
        if not self.rhs:
            arglist = self.args.split(" to ")
            if len(arglist) < 2:
                caller.msg("Usage: give <inventory object> to <target>")
                return
            self.lhs, self.rhs = arglist[0], arglist[1]
        target = caller.search(self.rhs)
        if not target:
            return
        if target == caller:
            caller.msg("You cannot give things to yourself.")
            return
        if "mats" in self.switches:
            lhslist = self.lhs.split(",")
            try:
                from game.dominion.models import CraftingMaterials
                mat = caller.db.player_ob.Dominion.assets.materials.get(type__name__iexact=lhslist[0])
                amount = int(lhslist[1])
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            except CraftingMaterials.DoesNotExist:
                caller.msg("No materials by that name.")
                return
            if mat.amount < amount:
                caller.msg("Not enough materials.")
                return
            try:
                tmat = target.db.player_ob.Dominion.assets.materials.get(type=mat.type)
            except CraftingMaterials.DoesNotExist:
                tmat = target.db.player_ob.Dominion.assets.materials.create(type=mat.type)
            mat.amount -= amount
            tmat.amount += amount
            mat.save()
            tmat.save()
            caller.msg("You give %s %s to %s." % (amount, mat.type, target))
            target.msg("%s gives %s %s to you." % (caller, amount, mat.type))
            return
        if "resource" in self.switches:
            rtypes = ("economic", "social", "military")
            lhslist = self.lhs.split(",")
            try:
                rtype = lhslist[0].lower()
                amount = int(lhslist[1])
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            if rtype not in rtypes:
                caller.msg("Type must be in %s." % rtypes)
                return
            cres = getattr(caller.db.player_ob.Dominion.assets, rtype)
            if cres < amount:
                caller.msg("You do not have enough %s resources." % rtype)
                return
            tres = getattr(target.db.player_ob.Dominion.assets, rtype)
            cres -= amount
            tres += amount
            setattr(target.db.player_ob.Dominion.assets, rtype, tres)
            setattr(caller.db.player_ob.Dominion.assets, rtype, cres)
            target.db.player_ob.Dominion.assets.save()
            caller.db.player_ob.Dominion.assets.save()
            caller.msg("You give %s %s resources to %s." % (amount, rtype, target))
            target.msg("%s gives %s %s resources to you." % (caller, amount, rtype))
            return
        if args_are_currency(self.lhs):
            arglist = self.lhs.split()
            val = round(float(arglist[0]),2)
            currency = round(float(caller.db.currency or 0),2)
            if val > currency:
                caller.msg("You do not have that much money to give.")
                return
            caller.pay_money(val, target)
            caller.msg("You give coins worth %s silver pieces to %s." % (val, target.name))
            target.msg("%s has given you coins worth %s silver pieces." % (caller.name, val))
            return
        # if we didn't find a match in currency that we're giving
        if not to_give:
            to_give = caller.search(self.lhs)
        if not (to_give and target):
            return
        if target == caller:
            caller.msg("You keep %s to yourself." % to_give.key)
            to_give.at_get(caller)
            return
        if not to_give.location == caller:
            caller.msg("You are not holding %s." % to_give.key)
            return
        if not check_volume(to_give, target, quiet=True):
            caller.msg("%s can't hold %s." % (target.name, to_give.name))
            return
        # give object
        to_give.move_to(target, quiet=True)
        caller.msg("You give %s to %s." % (to_give.key, target.key))
        target.msg("%s gives you %s." % (caller.key, to_give.key))
        to_give.at_get(target)


class CmdEmit(MuxCommand):
    """
    @emit

    Usage:
      @emit[/switches] [<obj>, <obj>, ... =] <message>
      @remit           [<obj>, <obj>, ... =] <message>
      @pemit           [<obj>, <obj>, ... =] <message>

    Switches:
      room : limit emits to rooms only (default)
      players : limit emits to players only
      contents : send to the contents of matched objects too

    Emits a message to the selected objects or to
    your immediate surroundings. If the object is a room,
    send to its contents. @remit and @pemit are just
    limited forms of @emit, for sending to rooms and
    to players respectively.
    """
    key = "@emit"
    aliases = ["@pemit", "@remit", "\\\\"]
    locks = "cmd:all()"
    help_category = "Social"
    perm_for_switches = "Builders"

    def dynamic_help(self, caller):
        if caller.check_permstring(self.perm_for_switches):
            return self.__doc__
        help_string = """
        @emit

        Usage :
            @emit <message>

        Emits a message to your immediate surroundings. This command is
        used to provide more flexibility than the structure of poses, but
        please remember to indicate your character's name.
        """
        return help_string

    def func(self):
        "Implement the command"

        caller = self.caller
        args = self.args

        if not args:
            string = "Usage: "
            string += "\n@emit[/switches] [<obj>, <obj>, ... =] <message>"
            string += "\n@remit           [<obj>, <obj>, ... =] <message>"
            string += "\n@pemit           [<obj>, <obj>, ... =] <message>"
            caller.msg(string)
            return

        rooms_only = 'rooms' in self.switches
        players_only = 'players' in self.switches
        send_to_contents = 'contents' in self.switches
        perm = self.perm_for_switches
        normal_emit = False

        # we check which command was used to force the switches
        if (self.cmdstring == '@remit' or self.cmdstring == '@pemit') and not caller.check_permstring(perm):
            caller.msg("Those options are restricted to GMs only.")
            return
        if self.cmdstring == '@remit':
            rooms_only = True
            send_to_contents = True
        elif self.cmdstring == '@pemit':
            players_only = True

        if not caller.check_permstring(perm):
            rooms_only = False
            players_only = False

        if not self.rhs or not caller.check_permstring(perm):
            message = self.args
            normal_emit = True
            objnames = []
            do_global = False
        else:
            do_global = True
            message = self.rhs
            if caller.check_permstring(perm):
                objnames = self.lhslist
            else:
                objnames = [x.key for x in caller.location.contents if x.player]
        if do_global:
            do_global = caller.check_permstring(perm)
        # normal emits by players are just sent to the room
        if normal_emit:
            gms = [ob for ob in caller.location.contents if ob.check_permstring('builders')]
            caller.location.msg_contents("{w[Emit by: {c%s{w]{n %s" % (caller.name, message), gm_msg=True)
            caller.location.msg_contents(message, exclude=gms, from_obj=caller, is_pose=True)
            return
        # send to all objects
        for objname in objnames:
            if players_only:
                obj = caller.player.search(objname)
                if obj:
                    obj = obj.character
            else:
                obj = caller.search(objname, global_search=do_global)
            if not obj:
                caller.msg("Could not find %s." % objname)
                continue
            if rooms_only and not obj.location is None:
                caller.msg("%s is not a room. Ignored." % objname)
                continue
            if players_only and not obj.player:
                caller.msg("%s has no active player. Ignored." % objname)
                continue
            if obj.access(caller, 'tell'):
                if obj.check_permstring(perm):
                    bmessage = "{w[Emit by: {c%s{w]{n %s" % (caller.name, message)
                    obj.msg(bmessage, is_pose=True)
                else:
                    obj.msg(message, is_pose=True)
                if send_to_contents and hasattr(obj, "msg_contents"):
                    obj.msg_contents(message, from_obj=caller, is_pose=True)
                    caller.msg("Emitted to %s and contents:\n%s" % (objname, message))
                elif caller.check_permstring(perm):
                    caller.msg("Emitted to %s:\n%s" % (objname, message))
            else:
                caller.msg("You are not allowed to emit to %s." % objname)

#Changed to display room dbref number rather than room name
class CmdWho(MuxPlayerCommand):
    """
    who

    Usage:
      who
      doing

    Shows who is currently online. Doing is an alias that limits info
    also for those with all permissions.
    """

    key = "who"
    aliases = ["doing", "+who"]
    locks = "cmd:all()"

    def func(self):
        """
        Get all connected players by polling session.
        """

        player = self.caller
        session_list = SESSIONS.get_sessions()

        session_list = sorted(session_list, key=lambda o: o.player.key.lower())

        if self.cmdstring == "doing":
            show_session_data = False
        else:
            show_session_data = player.check_permstring("Immortals") or player.check_permstring("Wizards")

        nplayers = (SESSIONS.player_count())
        if show_session_data:
            table = prettytable.PrettyTable(["{wPlayer Name",
                                             "{wOn for",
                                             "{wIdle",
                                             "{wRoom",
                                             #"{wCmds",
                                             "{wProtocol",
                                             "{wHost"])
            for session in session_list:
                if not session.logged_in: continue
                delta_cmd = time.time() - session.cmd_last_visible
                delta_conn = time.time() - session.conn_time
                plr_pobject = session.get_puppet()
                plr_pobject = plr_pobject or session.get_player()
                table.add_row([crop(plr_pobject.name, width=25),
                               time_format(delta_conn, 0),
                               time_format(delta_cmd, 1),
                               # hasattr(plr_pobject, "location") and plr_pobject.location.key or "None",
                               hasattr(plr_pobject, "location") and plr_pobject.location and plr_pobject.location.dbref or "None",
                               #session.cmd_total,
                               session.protocol_key,
                               isinstance(session.address, tuple) and session.address[0] or session.address])
        else:
            table = prettytable.PrettyTable(["{wPlayer name", "{wOn for", "{wIdle"])
            for session in session_list:
                if not session.logged_in:
                    continue
                delta_cmd = time.time() - session.cmd_last_visible
                delta_conn = time.time() - session.conn_time
                plr_pobject = session.get_puppet()
                plr_pobject = plr_pobject or session.get_player()
                if not session.get_player().db.hide_from_watch:
                    table.add_row([crop(plr_pobject.name, width=25),
                                   time_format(delta_conn, 0),
                                   time_format(delta_cmd, 1)])
                else:
                    nplayers -= 1

        isone = nplayers == 1
        string = "{wPlayers:{n\n%s\n%s unique account%s logged in." % (table, "One" if isone else nplayers, "" if isone else "s")
        self.msg(string)

from evennia.commands.default.building import _LITERAL_EVAL, ObjManipCommand
from evennia.utils.utils import to_str
class CmdSetAttribute(ObjManipCommand):
    """
    @set - set attributes

    Usage:
      @set <obj>/<attr> = <value>
      @set <obj>/<attr> =
      @set <obj>/<attr>
      
      @set *<player>/attr = <value>
      @set/char <obj>/<attr>
      @set/primitive <obj><attr>

    Sets attributes on objects. The second form clears a previously set
    attribute while the last form inspects the current value of the
    attribute (if any). * forces it to find the player matching that name,
    while the /char switches forces a match to any character object with
    the given name. The /primitive switch is designed to stop you from
    changing any attribute that is not a string or number.

    The most common data to save with this command are strings and
    numbers. You can however also set Python primities such as lists,
    dictionaries and tuples on objects (this might be important for
    the functionality of certain custom objects).  This is indicated
    by you starting your value with one of {c'{n, {c"{n, {c({n, {c[{n
    or {c{ {n.
    Note that you should leave a space after starting a dictionary ('{ ')
    so as to not confuse the dictionary start with a colour code like \{g.
    Remember that if you use Python primitives like this, you must
    write proper Python syntax too - notably you must include quotes
    around your strings or you will get an error.

    """

    key = "@set"
    locks = "cmd:perm(set) or perm(Wizards)"
    help_category = "Building"

    def convert_from_string(self, strobj):
        """
        Converts a single object in *string form* to its equivalent python
        type.

         Python earlier than 2.6:
        Handles floats, ints, and limited nested lists and dicts
        (can't handle lists in a dict, for example, this is mainly due to
        the complexity of parsing this rather than any technical difficulty -
        if there is a need for @set-ing such complex structures on the
        command line we might consider adding it).
         Python 2.6 and later:
        Supports all Python structures through literal_eval as long as they
        are valid Python syntax. If they are not (such as [test, test2], ie
        withtout the quotes around the strings), the entire structure will
        be converted to a string and a warning will be given.

        We need to convert like this since all data being sent over the
        telnet connection by the Player is text - but we will want to
        store it as the "real" python type so we can do convenient
        comparisons later (e.g.  obj.db.value = 2, if value is stored as a
        string this will always fail).
        """

        def rec_convert(obj):
            """
            Helper function of recursive conversion calls. This is only
            used for Python <=2.5. After that literal_eval is available.
            """
            # simple types
            try:
                return int(obj)
            except ValueError:
                pass
            try:
                return float(obj)
            except ValueError:
                pass
            # iterables
            if obj.startswith('[') and obj.endswith(']'):
                "A list. Traverse recursively."
                return [rec_convert(val) for val in obj[1:-1].split(',')]
            if obj.startswith('(') and obj.endswith(')'):
                "A tuple. Traverse recursively."
                return tuple([rec_convert(val) for val in obj[1:-1].split(',')])
            if obj.startswith('{') and obj.endswith('}') and ':' in obj:
                "A dict. Traverse recursively."
                return dict([(rec_convert(pair.split(":", 1)[0]),
                              rec_convert(pair.split(":", 1)[1]))
                             for pair in obj[1:-1].split(',') if ":" in pair])
            # if nothing matches, return as-is
            return obj

        if _LITERAL_EVAL:
            # Use literal_eval to parse python structure exactly.
            try:
                return _LITERAL_EVAL(strobj)
            except (SyntaxError, ValueError):
                # treat as string
                string = "{RNote: Value was converted to string. If you don't want this, "
                string += "use proper Python syntax, like enclosing strings in quotes.{n"
                self.caller.msg(string)
                return to_str(strobj)
        else:
            # fall back to old recursive solution (does not support
            # nested lists/dicts)
            return rec_convert(strobj.strip())

    def func(self):
        "Implement the set attribute - a limited form of @py."

        caller = self.caller
        if not self.args:
            caller.msg("Usage: @set obj/attr = value. Use empty value to clear.")
            return

        # get values prepared by the parser
        value = self.rhs
        objname = self.lhs_objattr[0]['name']
        attrs = self.lhs_objattr[0]['attrs']

        if objname.startswith('*') or 'char' in self.switches:
            obj = caller.search(objname.lstrip('*'))
            if 'char' in self.switches and obj:
                obj = obj.db.char_ob
        else:
            obj = caller.search(objname)
        if not obj:
            return

        string = ""
        if not value:
            if self.rhs is None:
                # no = means we inspect the attribute(s)
                if not attrs:
                    attrs = [attr.key for attr in obj.get_all_attributes()]
                for attr in attrs:
                    if obj.attributes.has(attr):
                        string += "\nAttribute %s/%s = %s" % (obj.name, attr,
                                                      obj.attributes.get(attr))
                    else:
                        string += "\n%s has no attribute '%s'." % (obj.name, attr)
                    # we view it without parsing markup.
                self.caller.msg(string.strip(), data={"raw": True})
                return
            else:
                # deleting the attribute(s)
                for attr in attrs:
                    if obj.attributes.has(attr):
                        val = obj.attributes.has(attr)
                        obj.attributes.remove(attr)
                        string += "\nDeleted attribute '%s' (= %s) from %s." % (attr, val, obj.name)
                    else:
                        string += "\n%s has no attribute '%s'." % (obj.name, attr)
        else:
            primitive = "primitive" in self.switches
            # setting attribute(s). Make sure to convert to real Python type before saving.
            for attr in attrs:
                current = obj.attributes.get(attr)
                if current and not primitive and not (isinstance(current, basestring) or
                                                       isinstance(current, float) or
                                                       isinstance(current, int)):
                    caller.msg("That attribute is a python object. To change it, use the primitive switch.")
                    return
                try:
                    obj.attributes.add(attr, self.convert_from_string(value))
                    string += "\nCreated attribute %s/%s = %s" % (obj.name, attr, value)
                except SyntaxError:
                    # this means literal_eval tried to parse a faulty string
                    string = "{RCritical Python syntax error in your value. "
                    string += "Only primitive Python structures are allowed. "
                    string += "\nYou also need to use correct Python syntax. "
                    string += "Remember especially to put quotes around all "
                    string += "strings inside lists and dicts.{n"
        # send feedback
        caller.msg(string.strip('\n'))
        if obj != caller and not caller.check_permstring("immortals"):
            utils.inform_staff("Building command by %s: %s" % (caller, string))


