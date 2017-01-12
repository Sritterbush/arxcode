"""
General Character commands usually availabe to all characters
"""
from django.conf import settings
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from evennia.comms.models import TempMsg
from evennia.utils import utils, evtable
from server.utils import prettytable
from evennia.utils.utils import make_iter, variable_from_module
from world import stats_and_skills
from evennia.objects.models import ObjectDB
from evennia.utils.ansi import raw

AT_SEARCH_RESULT = variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))


class CmdBriefMode(MuxCommand):
    """
    brief

    Usage:
      brief

    Toggles whether to display long room descriptions
    when moving through rooms.
    """
    key = "brief"
    locks = "cmd:all()"
    help_category = "Settings"
    
    def func(self):
        """ Handles the toggle """
        caller = self.caller
        caller.db.briefmode = not caller.db.briefmode
        if not caller.db.briefmode:
            caller.msg("Brief mode is now off.")
        else:
            caller.msg("Brief mode is now on.")


class CmdGameSettings(MuxPlayerCommand):
    """
    @settings

    Usage:
        @settings
        @settings/brief
        @settings/posebreak
        @settings/stripansinames
        @settings/lrp
        @settings/afk <message>
        @settings/nomessengerpreview
        @settings/bbaltread
        @settings/ignore_messenger_notifications
        @settings/ignore_messenger_deliveries
        @settings/newline_on_messages
        @settings/private_mode
        @settings/ic_only

    Toggles different settings. Brief surpresses room descs when
    moving through rooms. Posebreak adds a newline between poses
    fro mcharacters. lrp flags your name in the who list
    as looking for scenes. afk sets that you are away from the
    keyboard, with an optional message. nomessengerpreview removes
    the echo of messengers that you send. bbaltread causes you to
    read @bb messages on your alts as well. ignore_messenger_notifications
    will suppress any notifications that you have unread messengers.
    ignore_messenger_deliveries will suppress messages of a messenger
    visiting someone else in a room. Private mode prevents logging any
    messages that are sent to you. ic_only prevents you from receiving
    pages.
    """
    key = "@settings"
    locks = "cmd:all()"
    help_category = "Settings"
    aliases = ["lrp"]

    def togglesetting(self, char, attr, tag=False):
        caller = self.caller
        if tag:
            if not char.tags.get(attr):
                self.msg("%s is now on." % attr)
                char.tags.add(attr)
            else:
                self.msg("%s is now off." % attr)
                char.tags.remove(attr)
                char.tags.all()  # update cache until there's a fix for that
            return
        char.attributes.add(attr, not char.attributes.get(attr))
        if not char.attributes.get(attr):
            caller.msg("%s is now off." % attr)
        else:
            caller.msg("%s is now on." % attr)
            
    def func(self):
        caller = self.caller
        char = caller.db.char_ob
        if not char:
            caller.msg("Settings have no effect without a character object.")
            return
        switches = self.switches
        if self.cmdstring == "lrp":
            switches = ["lrp"]
        if "brief" in switches:
            self.togglesetting(char, "briefmode")
            return
        if "posebreak" in switches:
            self.togglesetting(char, "posebreak")
            return
        if "stripansinames" in switches:
            self.togglesetting(char, "stripansinames")
            return
        if "lrp" in switches:
            self.togglesetting(caller, "lookingforrp")
            return
        if "nomessengerpreview" in switches:
            self.togglesetting(caller, "nomessengerpreview")
            return
        if "bbaltread" in switches:
            self.togglesetting(caller, "bbaltread")
            return
        if "afk" in switches:
            caller.execute_cmd("afk %s" % self.args)
            return
        if "ignore_messenger_notifications" in switches:
            self.togglesetting(caller, "ignore_messenger_notifications")
            return
        if "ignore_messenger_deliveries" in switches:
            self.togglesetting(char, "ignore_messenger_deliveries")
            return
        if "newline_on_messages" in switches:
            self.togglesetting(caller, "newline_on_messages", tag=True)
            return
        if "verbose_where" in switches:
            self.togglesetting(caller, "verbose_where", tag=True)
            return
        if "private_mode" in switches:
            self.togglesetting(caller, "private_mode", tag=True)
            return
        if "ic_only" in switches:
            self.togglesetting(caller, "IC_Only", tag=True)
            return
        caller.msg("Invalid switch.")


class CmdGlance(MuxCommand):
    """
    glance

    Usage:
        glance <character>

    Lets you see some information at a character in the same
    room as you.
    """
    key = "glance"
    locks = "cmd:all()"
    help_category = "Social"

    def send_glance_str(self, char):
        string = "\n{c%s{n\n%s\n%s" % (char.get_fancy_name(),
                                       char.return_extras(self.caller),
                                       char.get_health_appearance())
        self.msg(string)

    def func(self):
        caller = self.caller
        if not self.args:
            charlist = [ob for ob in caller.location.contents if ob != caller and hasattr(ob, 'return_extras')]
        else:
            char = caller.search(self.args)
            if not char:
                return
            charlist = [char]
        if not charlist:
            self.msg("No one to glance at.")
            return
        for ob in charlist:
            try:
                self.send_glance_str(ob)
            except AttributeError:
                caller.msg("You cannot glance at that.")
                continue


class CmdShout(MuxCommand):
    """
    shout

    Usage:
      shout <message>
      shout/loudly <MESSAGE>

    Sends a message to adjacent rooms. Shout sends a message
    to the rooms connected to your current one, while
    shout/loudly sends farther than that. Use with care!
    """
    key = "shout"
    locks = "cmd:all()"
    help_category = "Social"
    
    def func(self):
        """ Handles the toggle """
        caller = self.caller
        args = self.args
        switches = self.switches
        loudly = False
        if not args:
            caller.msg("Shout what?")
            return
        if switches and "loudly" in switches:
            loudly = True
        loudstr = "loudly " if loudly else ""
        from_dir = "from nearby"
        caller.msg('You shout, "%s"' % args)
        txt = '{c%s{n shouts %s%s, "%s"' % (caller.name, loudstr, from_dir, args)
        caller.location.msg_contents(txt, exclude=caller, options={'shout': True,
                                                                   'from_dir': from_dir})


class CmdFollow(MuxCommand):
    """
    follow

    Usage:
        follow

    Starts following the chosen object. Use follow without
    any arguments to stop following. While following a player,
    you can follow them through locked doors they can open.

    To stop someone from following you, use 'ditch'.
    """
    key = "follow"
    locks = "cmd:all()"
    help_category = "Travel"

    def func(self):
        """ Handles followin' """
        caller = self.caller
        args = self.args
        f_targ = caller.ndb.following
        if not args and f_targ:
            caller.stop_follow()
            return
        if not args:
            caller.msg("You are not following anyone.")
            return
        f_targ = caller.search(args)
        if not f_targ:
            caller.msg("No one to follow.")
            return
        caller.follow(f_targ)


class CmdDitch(MuxCommand):
    """
    ditch

    Usage:
        ditch
        ditch <list of followers>

    Shakes off someone following you. Players can follow you through
    any locked door you have access to.
    """
    key = "ditch"
    locks = "cmd:all()"
    aliases = ["lose"]
    help_category = "Travel"

    def func(self):
        """ Handles followin' """
        caller = self.caller
        args = self.args
        followers = caller.ndb.followers
        if not followers:
            caller.msg("No one is following you.")
            return
        if args:
            matches = []
            for arg in self.lhslist:
                obj = ObjectDB.objects.object_search(arg, candidates=caller.ndb.followers)
                if obj:
                    matches.append(obj[0])
                else:
                    AT_SEARCH_RESULT(obj, caller, arg)
            for match in matches:
                match.stop_follow()
            return
        # no args, so make everyone stop following
        if followers:
            for follower in followers:
                follower.stop_follow()
        caller.ndb.followers = []
        return
        

class CmdDiceString(MuxCommand):
    """
    @dicestring

    Usage:
      @dicestring <your very own dicestring here>

    Customizes a message you see whenever any character does a @check,
    in order to ensure that it is a real @check and not a pose.
    """
    key = "@dicestring"
    locks = "cmd:all()"
    
    def func(self):
        """ Handles the toggle """
        caller = self.caller
        args = self.args
        dicest = caller.db.dice_string
        if not dicest:
            dicest = "None."
        if not args:
            caller.msg("Your current dicestring is: {w%s" % dicest)
            caller.msg("To change your dicestring: {w@dicestring <word or phrase>")
            return
        caller.attributes.add("dice_string", args)
        caller.msg("Your dice string is now: %s" % args)
        return
      

# Note that if extended_room's Extended Look is defined, this is probably not used
class CmdLook(MuxCommand):
    """
    look

    Usage:
      look
      look <obj>
      look *<player>

    Observes your location or objects in your vicinity.
    """
    key = "look"
    aliases = ["l", "ls"]
    locks = "cmd:all()"
    arg_regex = r"\s.*?|$"

    def func(self):
        """
        Handle the looking.
        """
        caller = self.caller
        args = self.args
        if args:
            # Use search to handle duplicate/nonexistant results.
            looking_at_obj = caller.search(args, use_nicks=True)
            if not looking_at_obj:
                return
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
        caller.msg(looking_at_obj.return_appearance(caller))
        # the object's at_desc() method.
        looking_at_obj.at_desc(looker=caller)


# Whisper largely a modified page
# Turning it into a MuxCommand rather than MuxPlayerCommand
class CmdWhisper(MuxCommand):
    """
    whisper - send private IC message

    Usage:
      whisper[/switches] [<player>,<player>,... = <message>]
      whisper =<message> - sends whisper to last person you whispered
      whisper <name> <message>
      whisper/list <number> - Displays list of last <number> of recent whispers

    Switch:
      last - shows who you last messaged
      list - show your last <number> of messages (default)

    Send an IC message to a character in your room. A whisper of the format
    "whisper player=Hello" will send a message in the form of "You whisper
    <player>". A whisper of the format "whisper player=:does an emote" will appear
    in the form of "Discreetly, soandso does an emote" to <player>. It's generally
    expected that for whispers during public roleplay scenes that the players
    involved should pose to the room with some small mention that they're
    communicating discreetly. For ooc messages, please use the 'page'/'tell'
    command instead.

    If no argument is given, you will get a list of your whispers from this
    session.
    """

    key = "whisper"
    locks = "cmd:not pperm(page_banned)"
    help_category = "Social"

    def func(self):
        """Implement function using the Msg methods"""

        # this is a MuxCommand, which means caller will be a Character.
        caller = self.caller
        # get the messages we've sent (not to channels)
        if not caller.ndb.whispers_sent:
            caller.ndb.whispers_sent = []
        pages_we_sent = caller.ndb.whispers_sent
        # get last messages we've got
        if not caller.ndb.whispers_received:
            caller.ndb.whispers_received = []
        pages_we_got = caller.ndb.whispers_received

        if 'last' in self.switches:
            if pages_we_sent:
                recv = ",".join(obj.key for obj in pages_we_sent[-1].receivers)
                self.msg("You last whispered {c%s{n:%s" % (recv, pages_we_sent[-1].message))
                return
            else:
                self.msg("You haven't whispered anyone yet.")
                return

        if not self.args or 'list' in self.switches:
            pages = list(pages_we_sent) + list(pages_we_got)
            pages.sort(lambda x, y: cmp(x.date_created, y.date_created))

            number = 5
            if self.args:
                try:
                    number = int(self.args)
                except ValueError:
                    self.msg("Usage: whisper [<player> = msg]")
                    return

            if len(pages) > number:
                lastpages = pages[-number:]
            else:
                lastpages = pages
            template = "{w%s{n {c%s{n whispered to {c%s{n: %s"
            lastpages = "\n ".join(template %
                                   (utils.datetime_format(page.date_created),
                                    ",".join(obj.key for obj in page.senders),
                                    "{n,{c ".join([obj.name for obj in page.receivers]),
                                    page.message) for page in lastpages)

            if lastpages:
                string = "Your latest whispers:\n %s" % lastpages
            else:
                string = "You haven't whispered anyone yet."
            self.msg(string)
            return
        # We are sending. Build a list of targets
        lhs = self.lhs
        rhs = self.rhs
        lhslist = self.lhslist
        if not self.rhs:
            # MMO-type whisper. 'whisper <name> <target>'
            arglist = self.args.lstrip().split(' ', 1)
            if len(arglist) < 2:
                caller.msg("The MMO-style whisper format requires both a name and a message.")
                caller.msg("To send a message to your last whispered character, use {wwhisper =<message>")
                return
            lhs = arglist[0]
            rhs = arglist[1]
            lhslist = set(arglist[0].split(","))
            
        if not lhs and rhs:
            # If there are no targets, then set the targets
            # to the last person we paged.
            if pages_we_sent:
                receivers = pages_we_sent[-1].receivers
            else:
                self.msg("Who do you want to whisper?")
                return
        else:
            receivers = lhslist

        recobjs = []
        for receiver in set(receivers):
            if isinstance(receiver, basestring):
                pobj = caller.search(receiver, use_nicks=True)
            elif hasattr(receiver, 'character'):
                pobj = receiver.character
            elif hasattr(receiver, 'player'):
                pobj = receiver
            else:
                self.msg("Who do you want to whisper?")
                return
            if pobj:
                if hasattr(pobj, 'has_player') and not pobj.has_player:
                    self.msg("You may only send whispers to online characters.")                 
                elif not pobj.location or pobj.location != caller.location:
                    self.msg("You may only whisper characters in the same room as you.")
                else:
                    recobjs.append(pobj)                 
        if not recobjs:
            self.msg("No one found to whisper.")
            return
        header = "{c%s{n whispers," % caller.name
        message = rhs
        # if message begins with a :, we assume it is a 'whisper-pose'
        if message.startswith(":"):
            message = "%s %s %s" % ("Discreetly,", caller.name, message.strip(':').strip())
            is_a_whisper_pose = True
        elif message.startswith(";"):
            message = "%s %s%s" % ("Discreetly,", caller.name, message.lstrip(';').strip())
            is_a_whisper_pose = True
        else:
            is_a_whisper_pose = False
            message = "'" + message + "'"
        # create the temporary message object
        temp_message = TempMsg(senders=caller, receivers=recobjs, message=message)
                              
        caller.ndb.whispers_sent.append(temp_message)

        # tell the players they got a message.
        received = []
        rstrings = []
        for pobj in recobjs:
            otherobs = [ob for ob in recobjs if ob != pobj]
            if not pobj.access(caller, 'tell'):
                rstrings.append("You are not allowed to page %s." % pobj)
                continue
            if is_a_whisper_pose:
                omessage = message
                if otherobs:
                    omessage = "(Also sent to %s.) %s" % (", ".join(ob.name for ob in otherobs), message)
                pobj.msg(omessage, from_obj=caller, options={'is_pose': True})
            else:
                if otherobs:
                    myheader = header + " to {cyou{n and %s," % ", ".join("{c%s{n" % ob.name for ob in otherobs)
                else:
                    myheader = header
                pobj.msg("%s %s" % (myheader, message), from_obj=caller, options={'is_pose': True})
            if not pobj.ndb.whispers_received:
                pobj.ndb.whispers_received = []
            pobj.ndb.whispers_received.append(temp_message)
            if hasattr(pobj, 'has_player') and not pobj.has_player:
                received.append("{C%s{n" % pobj.name)
                rstrings.append("%s is offline. They will see your message if they list their pages later." %
                                received[-1])
            else:
                received.append("{c%s{n" % pobj.name)
            afk = pobj.db.player_ob and pobj.db.player_ob.db.afk
            if afk:
                pobj.msg("{wYou inform {c%s{w that you are AFK:{n %s" % (caller, afk))
                rstrings.append("{c%s{n is AFK: %s" % (pobj.name, afk))
        if rstrings:
            self.msg("\n".join(rstrings))
        if received:
            if is_a_whisper_pose:
                self.msg("You posed to %s: %s" % (", ".join(received), message))
            else:
                self.msg("You whispered to %s, %s" % (", ".join(received), message))


class CmdPage(MuxPlayerCommand):
    """
    page - send private message

    Usage:
      page[/switches] [<player>,<player2>,... = <message>]
      page[/switches] [<player> <player2> <player3>...= <message>]
      page [<message to last paged player>]
      tell  <player> <message>
      ttell [<message to last paged player>]
      page/list <number>
      page/noeval
      page/allow <name>
      page/unallow <name>

    Switch:
      last - shows who you last messaged
      list - show your last <number> of tells/pages (default)

    Send a message to target user (if online), or to the last person
    paged if no player is given. If no argument is given, you will
    get a list of your latest messages. Note that pages are only
    saved for your current session. Sending pages to multiple receivers
    accepts the names either separated by commas or whitespaces.

    /allow and /unallow sets who may page you when you use @settings/ic_only.
    """

    key = "page"
    aliases = ['tell', 'p', 'pa', 'pag', 'ttell']
    locks = "cmd:not pperm(page_banned)"
    help_category = "Comms"
    arg_regex = r'\/|\s|$'

    def disp_allow(self):
        self.msg("People on allow list: %s" % ", ".join(ob.key for ob in self.caller.allow_list))

    def func(self):
        """Implement function using the Msg methods"""

        # this is a MuxPlayerCommand, which means caller will be a Player.
        caller = self.caller
        if "allow" in self.switches or "unallow" in self.switches:
            if not self.args:
                self.disp_allow()
                return
            targ = caller.search(self.args)
            if not targ:
                return
            if "allow" in self.switches:
                if targ not in caller.allow_list:
                    caller.allow_list.append(targ)
            if "unallow" in self.switches:
                if targ in caller.allow_list:
                    caller.allow_list.remove(targ)
            self.disp_allow()
            return
        # get the messages we've sent (not to channels)
        if not caller.ndb.pages_sent:
            caller.ndb.pages_sent = []
        pages_we_sent = caller.ndb.pages_sent
        # get last messages we've got
        if not caller.ndb.pages_received:
            caller.ndb.pages_received = []
        pages_we_got = caller.ndb.pages_received

        if 'last' in self.switches:
            if pages_we_sent:
                recv = ",".join(obj.key for obj in pages_we_sent[-1].receivers)
                self.msg("You last paged {c%s{n:%s" % (recv, pages_we_sent[-1].message))
                return
            else:
                self.msg("You haven't paged anyone yet.")
                return
        if 'list' in self.switches or not self.args:
            pages = pages_we_sent + pages_we_got
            pages.sort(lambda x, y: cmp(x.date_created, y.date_created))

            number = 5
            if self.args:
                try:
                    number = int(self.args)
                except ValueError:
                    self.msg("Usage: tell [<player> = msg]")
                    return

            if len(pages) > number:
                lastpages = pages[-number:]
            else:
                lastpages = pages
            template = "{w%s{n {c%s{n paged to {c%s{n: %s"
            lastpages = "\n ".join(template %
                                   (utils.datetime_format(page.date_created),
                                    ",".join(obj.key for obj in page.senders),
                                    "{n,{c ".join([obj.name for obj in page.receivers]),
                                    page.message) for page in lastpages)

            if lastpages:
                string = "Your latest pages:\n %s" % lastpages
            else:
                string = "You haven't paged anyone yet."
            self.msg(string)
            return
        # if this is a 'tell' rather than a page, we use different syntax
        cmdstr = self.cmdstring.lower()
        lhs = self.lhs
        rhs = self.rhs
        lhslist = self.lhslist
        if cmdstr.startswith('tell'):
            arglist = self.args.lstrip().split(' ', 1)
            if len(arglist) < 2:
                caller.msg("The tell format requires both a name and a message.")
                return
            lhs = arglist[0]
            rhs = arglist[1]
            lhslist = set(arglist[0].split(","))
        # go through our comma separated list, also separate them by spaces
        elif lhs and rhs:
            tarlist = []
            for ob in lhslist:
                for word in ob.split():
                    tarlist.append(word)
            lhslist = tarlist

        # We are sending. Build a list of targets

        if (not lhs and rhs) or (self.args and not rhs) or cmdstr == 'ttell':
            # If there are no targets, then set the targets
            # to the last person we paged.
            # also take format of p <message> for last receiver
            if pages_we_sent:
                receivers = pages_we_sent[-1].receivers
                # if it's a 'tt' command, they can have '=' in a message body
                if not rhs or cmdstr == 'ttell':
                    rhs = self.args
            else:
                self.msg("Who do you want to page?")
                return
        else:
            receivers = lhslist

        if "noeval" in self.switches:
            rhs = raw(rhs)

        recobjs = []
        for receiver in set(receivers):
            # originally this section had this check, which always was true
            # Not entirely sure what he was trying to check for
            if isinstance(receiver, basestring):
                findpobj = caller.search(receiver)
            else:
                findpobj = receiver
            pobj = None
            if findpobj:
                # Make certain this is a player object, not a character
                if hasattr(findpobj, 'character'):
                    # players should always have is_connected, but just in case
                    if not hasattr(findpobj, 'is_connected'):
                        # only allow online tells
                        self.msg("%s is not online." % findpobj.key)
                        continue
                    elif findpobj.character:
                        if hasattr(findpobj.character, 'player') and not findpobj.character.player:
                            self.msg("%s is not online." % findpobj.key)
                        else:
                            pobj = findpobj.character
                    elif not findpobj.character:
                        # player is either OOC or offline. Find out which
                        if hasattr(findpobj, 'is_connected') and findpobj.is_connected:
                            pobj = findpobj
                        else:
                            self.msg("%s is not online." % findpobj.key.capitalize())
                else:
                    # Offline players do not have the character attribute
                    self.msg("%s is not online." % findpobj.key)
                    continue
                if findpobj.tags.get("ic_only") and not caller.check_permstring("builders"):
                    if caller not in findpobj.allow_list:
                        self.msg("%s is IC only and can not be sent pages." % findpobj)
                        continue
            else:
                continue
            if pobj:
                if hasattr(pobj, 'player') and pobj.player:
                    pobj = pobj.player
                recobjs.append(pobj)
                    
        if not recobjs:
            self.msg("No one found to page.")
            return
        if len(recobjs) > 1:
            rec_names = ", ".join("{c%s{n" % ob.key.capitalize() for ob in recobjs)
        else:
            rec_names = "{cyou{n"
        header = "{wPlayer{n {c%s{n {wpages %s:{n" % (caller.key.capitalize(), rec_names)
        message = rhs
        pagepose = False
        # if message begins with a :, we assume it is a 'page-pose'
        if message.startswith(":") or message.startswith(";"):
            pagepose = True
            header = "From afar,"
            if len(recobjs) > 1:
                header = "From afar to %s:" % rec_names
            if message.startswith(":"):
                message = "{c%s{n %s" % (caller.key.capitalize(), message.strip(':').strip())
            else:
                message = "{c%s{n%s" % (caller.key.capitalize(), message.strip(';').strip())

        # create the temporary message object
        temp_message = TempMsg(senders=caller, receivers=recobjs, message=message)
        caller.ndb.pages_sent.append(temp_message)

        # tell the players they got a message.
        received = []
        r_strings = []
        for pobj in recobjs:
            if not pobj.access(caller, 'msg'):
                r_strings.append("You are not allowed to page %s." % pobj)
                continue
            if "ic_only" in caller.tags.all() and pobj not in caller.allow_list:
                msg = "%s is not in your allow list, and you are IC Only. " % caller
                msg += "Allow them to send a page, or disable the IC Only @setting."
                self.msg(msg)
                continue
            pobj.msg("%s %s" % (header, message), from_obj=caller, options={'log_msg': True})
            if not pobj.ndb.pages_received:
                pobj.ndb.pages_received = []
            pobj.ndb.pages_received.append(temp_message)
            if hasattr(pobj, 'has_player') and not pobj.has_player:
                received.append("{C%s{n" % pobj.name)
                r_strings.append("%s is offline. They will see your message if they list their pages later." %
                                 received[-1])
            else:
                received.append("{c%s{n" % pobj.name.capitalize())
            afk = pobj.db.afk
            if afk:
                pobj.msg("{wYou inform {c%s{w that you are AFK:{n %s" % (caller, afk))
                r_strings.append("{c%s{n is AFK: %s" % (pobj.name, afk))
        if r_strings:
            self.msg("\n".join(r_strings))
        if received:
            if pagepose:          
                self.msg("Long distance to %s: %s" % (", ".join(received), message))
            else:
                self.msg("You paged %s with: '%s'." % (", ".join(received), message))


class CmdOOCSay(MuxCommand):
    """
    ooc

    Usage:
      ooc <message>

    Send an OOC message to your current location. For IC messages,
    use 'say' instead.
    """

    key = "ooc"
    locks = "cmd:all()"
    help_category = "Comms"

    def func(self):
        """Run the OOCsay command"""

        caller = self.caller

        if not self.args:
            caller.msg("No message specified. If you wish to stop being IC, use @ooc instead.")
            return

        speech = self.args
        oocpose = False
        nospace = False
        if speech.startswith(";") or speech.startswith(":"):
            oocpose = True
            if speech.startswith(";"):
                nospace = True
            speech = speech[1:]

        # calling the speech hook on the location
        speech = caller.location.at_say(caller, speech)
        options = {"ooc_note": True, "log_msg": True}

        # Feedback for the object doing the talking.
        if not oocpose:
            caller.msg('{y(OOC){n You say: %s{n' % speech)

            # Build the string to emit to neighbors.
            emit_string = '{y(OOC){n {c%s{n says: %s{n' % (caller.name, speech)
            caller.location.msg_contents(emit_string, from_obj=caller,
                                         exclude=caller, options=options)
        else:
            if nospace:
                emit_string = '{y(OOC){n {c%s{n%s' % (caller.name, speech)
            else:
                emit_string = '{y(OOC){n {c%s{n %s' % (caller.name, speech)
            caller.location.msg_contents(emit_string, exclude=None, options=options, from_obj=caller)


class CmdDiceCheck(MuxCommand):
    """
    @check

    Usage:
      @check <stat>[+<skill>][ at <difficulty number>][=receivers]

    Performs a stat/skill check for your character, generally to
    determine success in an attempted action. For example, if you
    tell a GM you want to climb up the wall of a castle, they might
    tell you to check your 'check dex + athletics, difficulty 30'.
    You would then '@check dexterity+athletics at 30'. You can also
    specify checks only to specific receivers. For example, if you
    are attempting to lie to someone in a whispered conversation,
    you might '@check charm+manipulation=Bob' for lying to Bob at
    the default difficulty of 15.

    The dice roll system has a stronger emphasis on skills than
    stats. A character attempting something that they have a skill
    of 0 in may find the task very difficult while someone with a
    skill of 2 may find it relatively easy.
    """

    key = "@check"
    aliases = ['+check', '+roll']
    locks = "cmd:all()"
    
    def func(self):
        """Run the OOCsay command"""

        caller = self.caller
        skill = None
        maximum_difference = 100

        if not self.args:
            caller.msg("Usage: @check <stat>[+<skill>][ at <difficulty number>][=receiver1,receiver2,etc]")
            return
        args = self.lhs if self.rhs else self.args
        args = args.lower()
        # if args contains ' at ', then we split into halves. otherwise, it's default of 6
        diff_list = args.split(' at ')
        difficulty = stats_and_skills.DIFF_DEFAULT
        if len(diff_list) > 1:
            if not diff_list[1].isdigit() or not 0 < int(diff_list[1]) < maximum_difference:
                caller.msg("Difficulty must be a number between 1 and %s." % maximum_difference)
                return
            difficulty = int(diff_list[1])
        args = diff_list[0]
        arg_list = args.split("+")
        if len(arg_list) > 1:
            skill = arg_list[1].strip()
        stat = arg_list[0].strip()
        matches = stats_and_skills.get_partial_match(stat, "stat")
        if not matches or len(matches) > 1:
            caller.msg("There must be one unique match for a character stat. Please check spelling and try again.")
            return
        # get unique string that matches stat
        stat = matches[0]
        
        if skill:
            matches = stats_and_skills.get_partial_match(skill, "skill")
            if not matches:
                # check for a skill not in the normal valid list
                if skill in caller.db.skills:
                    matches = [skill]
                else:
                    caller.msg("No matches for a skill by that name. Check spelling and try again.")
                    return
            if len(matches) > 1:
                caller.msg("There must be one unique match for a character skill. Please check spelling and try again.")
                return
            skill = matches[0]
        if not self.rhs:
            stats_and_skills.do_dice_check(caller, stat, skill, difficulty, quiet=False)
        else:
            result = stats_and_skills.do_dice_check(caller, stat, skill, difficulty)
            if result+difficulty >= difficulty:
                resultstr = "resulting in %s, %s {whigher{n than the difficulty" % (result+difficulty, result)
            else:
                resultstr = "resulting in %s, %s {rlower{n than the difficulty" % (result+difficulty, -result)

            if not skill:
                roll_msg = "checked %s against difficulty %s, %s{n." % (stat, difficulty, resultstr)
            else:
                roll_msg = "checked %s + %s against difficulty %s, %s{n." % (stat, skill, difficulty, resultstr)
            caller.msg("You " + roll_msg)
            roll_msg = caller.key.capitalize() + " " + roll_msg
            # if they have a recepient list, only tell those people (and GMs)
            if self.rhs:
                namelist = [name.strip() for name in self.rhs.split(",")]
                for name in namelist:
                    rec_ob = caller.search(name, use_nicks=True)
                    if rec_ob:
                        orig_msg = roll_msg
                        if rec_ob.attributes.has("dice_string"):
                            roll_msg = "{w<" + rec_ob.db.dice_string + "> {n" + roll_msg
                        rec_ob.msg(roll_msg)
                        roll_msg = orig_msg
                        rec_ob.msg("Private roll sent to: %s" % ", ".join(namelist))
                # GMs always get to see rolls.
                staff_list = [x for x in caller.location.contents if x.check_permstring("Builders")]
                for GM in staff_list:
                    GM.msg("{w(Private roll){n" + roll_msg)
                return
            # not a private roll, tell everyone who is here
            caller.location.msg_contents(roll_msg, exclude=caller, options={'roll': True})
        

# implement CmdMail. player.db.Mails is List of Mail
# each Mail is tuple of 3 strings - sender, subject, message        
class CmdMail(MuxPlayerCommand):
    """
    Send and check player mail

    Usage:
      @mail          - lists all mail in player's mailbox
      @mail #        - read mail by the given number
      @mail/quick [<player>[,<player2,...]/<subject>=<message>]
      @mail/delete # - deletes mail by given number

    Switches:
      delete - delete mail
      quick  - sends mail

    Examples:
      @mail/quick Tommy/Hello=Let's talk soon
      @mail/delete 5

    Accesses in-game mail. Players may send, receive,
    or delete messages.
    """
    key = "@mail"
    aliases = ["mail", "+mail"]
    locks = "cmd:all()"
    help_category = "Comms"

    def func(self):
        """Access mail"""

        caller = self.caller
        switches = self.switches

        # mailbox is combined from Player object and his characters
        mails = caller.db.mails
        
        # error message for invalid argument
        nomatch = "You must supply a number matching a mail message."

        if not switches:
            # if no argument and no switches, list all mail
            caller.db.newmail = False  # mark mail as read
            if not self.args or not self.lhs:
                table = prettytable.PrettyTable(["{wMail #",
                                                 "{wSender",
                                                 "{wSubject"])
                mail_number = 0
                for mail in mails:
                    # list the mail
                    # mail is a tuple of (sender,subject,message)
                    sender = mail[0]
                    subject = mail[1]
                    mail_number += 1
                    this_number = str(mail_number)
                    if mail not in (caller.db.readmails or set()):
                        col = "{w"
                    else:
                        col = "{n"
                    table.add_row([col + str(this_number), col + str(sender), col + str(subject)])
                string = "{wMailbox:{n\n%s" % table
                caller.msg(string)
                return
            else:
                # get mail number, then display the message
                try:
                    mail_number = int(self.args)
                except ValueError:
                    caller.msg(nomatch)
                    return
                if mail_number < 1 or mail_number > len(mails):
                    caller.msg(nomatch)
                    return
                mail = mails[mail_number - 1]
                sender = mail[0]
                subject = mail[1]
                message = mail[2]
                sentdate = mail[3]
                cclist = mail[4]
                string = "{wMessage:{n %s" % mail_number + "\n"
                string += "{wSent:{n %s" % str(sentdate) + "\n"
                string += "{wTo:{n %s" % cclist + "\n"
                string += "{wSender:{n %s" % sender + "\n"
                string += "{wSubject:{n %s" % subject + "\n"
                string += "{w"+20*"-"+"{n\n"
                
                string += raw(message)
                string += "\n{w"+20*"-"+"{n\n"
                caller.msg(string)
                read_mails = caller.db.readmails or set()
                if mail not in read_mails:
                    read_mails.add(mail)
                    caller.db.readmails = read_mails
                return
        if not self.args or not self.lhs:
            caller.msg("Usage: mail[/switches] # or mail/quick [<name>/<subject>=<message>]")
            return
        if 'delete' in switches:
            try:
                mail_number = int(self.args)
            except ValueError:
                caller.msg(nomatch)
                return
            if mail_number < 1 or mail_number > len(mails):
                caller.msg(nomatch)
                return
            mail = mails[mail_number - 1]
            caller.db.mails.remove(mail)
            caller.db.readmails.discard(mail)         
            caller.msg("Message deleted.")
            return
        if 'quick' in switches:
            if not self.rhs:
                caller.msg("You cannot mail a message with no body.")
                return
            recobjs = []
            message = self.rhs
            # separate it into receivers, subject. May not have a subject
            if not self.lhs:
                caller.msg("You must have a receiver set.")
                return
            arglist = self.lhs.split("/")
            if len(arglist) < 2:
                subject = "No Subject"
            else:
                subject = arglist[1]
            receivers_raw = arglist[0]
            receivers = receivers_raw.split(",")            
            sender = caller.key.capitalize()
            received_list = []
            for receiver in receivers:
                pobj = caller.search(receiver, global_search=True)
                # if we got a character instead of player, get their player
                if hasattr(pobj, 'player') and pobj.player:
                    pobj = pobj.player
                # if we found a match
                if pobj:
                    recobjs.append(pobj)
                    received_list.append(pobj.key.capitalize())
            if not recobjs:
                caller.msg("No players found.")
                return
            receivers = ", ".join(received_list)
            for pobj in recobjs:
                pobj.mail(message, subject, sender, receivers)
            caller.msg("Mail successfully sent to %s" % receivers)


class CmdDirections(MuxCommand):
    """
    @directions

    Usage:
      @directions <room name>
      @directions/off

    Gets directions to a room, or toggles it off. This will attempt to
    find a direct path between you and the room based on your current
    coordinates. If no such path exists, it will tell you the general
    heading. Please use @map to find a direct route otherwise. Your
    destination will be displayed as a red XX on the map.
    """
    key = "@directions"
    help_category = "Travel"
    locks = "cmd:all()"
    
    def func(self):
        """ Handles the toggle """
        caller = self.caller
        if "off" in self.switches or not self.args:
            if caller.ndb.waypoint:
                caller.ndb.waypoint = None
                caller.msg("Directions turned off.")
            else:
                caller.msg("You must give the name of a room.")
            return
        room = ObjectDB.objects.filter(db_typeclass_path=settings.BASE_ROOM_TYPECLASS, db_key__icontains=self.args)[:10]
        if len(room) > 1:
            exact = [ob for ob in room if self.args in ob.aliases.all()]
            if len(exact) == 1:
                room = exact[0]
            else:
                caller.msg("Multiple matches: %s" % ", ".join(str(ob.key) for ob in room))
                room = room[0]
                caller.msg("Showing directions to %s." % room.key)
        elif len(room) == 1:
            room = room[0]
        if not room:
            caller.msg("No matches for %s." % self.args)
            return
        caller.msg("Attempting to find where your destination is in relation to your position." +
                   " Please use {w@map{n if the directions don't have a direct exit there.")
        directions = caller.get_directions(room)
        if not directions:
            caller.msg("You can't figure out how to get there from here. "
                       "You may have to go someplace closer, like the City Center.")
            caller.ndb.waypoint = None
            return
        caller.msg("Your destination is through the %s." % directions)
        caller.ndb.waypoint = room
        return


class CmdPut(MuxCommand):
    """
    Puts an object inside a container
    Usage:
        put <object> in <object>

    Places an object you hold inside an unlocked
    container.
    """
    key = "put"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        args = self.args.split(" in ")
        if len(args) != 2:
            caller.msg("Usage: put <name> in <name>")
            return
        dest = caller.search(args[1], use_nicks=True, quiet=True)
        if not dest:
            return AT_SEARCH_RESULT(dest, caller, args[1])
        dest = make_iter(dest)[0]
        obj = caller.search(args[0], location=caller, use_nicks=True, quiet=True)
        if not obj:
            return AT_SEARCH_RESULT(obj, caller, args[0])
        obj = make_iter(obj)[0]
        if obj == dest:
            caller.msg("You can't put an object inside itself.")
            return
        if not dest.db.container:
            caller.msg("%s is not a container." % dest.name)
            return
        if dest.db.locked:
            caller.msg("%s is locked. Unlock it first." % dest.name)
            return
        if dest in obj.contents:
            caller.msg("You can't place an object in something it contains.")
            return
        max_volume = dest.db.max_volume or 0
        volume = obj.db.volume or 0
        if dest.volume + volume > max_volume:
            caller.msg("That won't fit in there.")
            return
        if not obj.access(caller, 'get'):
            caller.msg("You cannot move that.")
            return
        obj.move_to(dest)
        caller.msg("You put %s in %s." % (obj.name, dest.name))
        caller.location.msg_contents("%s puts %s in %s." % (caller.name, obj.name, dest.name), exclude=caller)
        from time import time
        obj.db.put_time = time()


class CmdGradient(MuxPlayerCommand):
    """
    @gradient - displays a string formatted with color codes
    Usage:
        @gradient <xxx>,<xxx>=<string to format>
        @gradient/reverse <xxx>,<xxx>=<string to format>

    @gradient takes two color code values and a string, then outputs the
    string with it changing colors through that range. If the reverse
    switch is specified, it will reverse colors halfway through the string.
    See @color xterm256 for a list of codes.
    """
    key = "@gradient"
    locks = "cmd: all()"

    @staticmethod
    def get_step(length, diff):
        if diff == 0:
            return 0
        return length/diff

    def color_string(self, start, end, text):
        
        current = start
        output = ""
        for x in range(len(text)):
            r, g, b = current[0], current[1], current[2]
            if x == 0:
                tag = "{{%s%s%s" % (str(r), str(g), str(b))
                output += "%s%s" % (tag, text[x])
                continue
            diff = (end[0]-current[0], end[1]-current[1], end[2]-current[2])
            previous = current        
            step = (self.get_step(len(text), diff[0]), self.get_step(len(text), diff[1]), self.get_step(len(text),
                                                                                                        diff[2]))
            if step[0] and x % step[0] == 0:
                if diff[0] > 1:
                    r += 1
                elif diff[0] < 1:
                    r -= 1
            if step[1] and x % step[1] == 0:
                if diff[1] > 1:
                    g += 1
                elif diff[1] < 1:
                    g -= 1
            if step[2] and x % step[2] == 0:
                if diff[2] > 1:
                    b += 1
                elif diff[2] < 1:
                    b -= 1
            current = (r, g, b)
            if current != previous:
                # we add a tag
                tag = "{{%s%s%s" % (str(r), str(g), str(b))
                output += "%s%s" % (tag, text[x])
            else:
                output += text[x]
        return output
    
    def func(self):
        caller = self.caller
        try:
            start, end = self.lhslist[0], self.lhslist[1]
            start = (int(start[0]), int(start[1]), int(start[2]))
            end = (int(end[0]), int(end[1]), int(end[2]))
            text = self.rhs or "Example Text"
        except IndexError:
            caller.msg("Must specify both a start and an end, ex: @gradient 050,132")
            return
        except ValueError:
            caller.msg("Please input numbers such as 050, 134, etc. No braces.")
            return
        reverse = "reverse" in self.switches
        if not reverse:
            caller.msg(self.color_string(start, end, text))
            return
        caller.msg(self.color_string(start, end, text[:len(text)/2]))
        caller.msg(self.color_string(end, start, text[len(text)/2:]))


class CmdInform(MuxPlayerCommand):
    """
    @inform - reads messages sent to you by the game
    Usage:
        @inform
        @inform <number>
        @inform/del <number>
        @inform/shopminimum <number>

    Displays your informs. /shopminimum sets a minimum amount that must be paid
    before you are informed of activity in your shops.
    """
    key = "@inform"
    aliases = ["@informs"]
    locks = "cmd: all()"

    @staticmethod
    def read_inform(caller, inform):
        msg = "\n{wCategory:{n %s\n" % inform.category
        msg += "{w" + "-"*70 + "{n\n\n%s\n" % inform.message
        caller.msg(msg, options={'box': True})
        if inform.is_unread:
            inform.is_unread = False
            inform.save()

    def func(self):
        caller = self.caller
        informs = list(caller.informs.all())
        if "shopminimum" in self.switches:
            if not self.args:
                self.msg("Removing minimum.")
                self.caller.db.char_ob.attributes.remove("min_shop_price_inform")
                return
            try:
                caller.db.char_ob.db.min_shop_price_inform = int(self.args)
                self.msg("Minimum price set to %s." % self.args)
            except (TypeError, ValueError):
                self.msg("Must specify a number.")
            except AttributeError:
                self.msg("Character object not found.")
            return
        if not informs:
            caller.msg("You have no messages from the game waiting for you.")
            return
        if not self.args:
            table = evtable.EvTable("{w#{n", "{wCategory{n", "{wDate{n", width=78, pad_width=0)
            x = 0
            for info in informs:
                x += 1

                def highlight(ob, add_star=False):
                    if not info.is_unread:
                        return ob
                    if add_star:
                        return "{w*%s{n" % ob
                    else:
                        return "{w%s{n" % ob
                num = highlight(x, add_star=True)
                cat = highlight(info.category)
                date = highlight(info.date_sent.strftime("%x %X"))
                table.add_row(num, cat, date)
            table.reformat_column(index=0, width=7)
            table.reformat_column(index=1, width=52)
            table.reformat_column(index=2, width=19)
            caller.msg(table)
            return
        try:
            val = int(self.args)
            if val <= 0:
                raise ValueError
            inform = informs[val - 1]
        except (ValueError, IndexError):
            caller.msg("You must specify a number between 1 and %s." % len(informs))
            return
        if not self.switches:
            self.read_inform(caller, inform)
            return
        if "del" in self.switches:
            inform.delete()
            caller.msg("Inform deleted.")
            return
        caller.msg("Invalid switch.")
        return


class CmdKeyring(MuxCommand):
    """
    Checks keys
    Usage:
        +keyring

    Checks your keys.
    """
    key = "+keyring"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        roomkeys = caller.db.keylist or []
        # remove any deleted objects
        if None in roomkeys:
            roomkeys = [ob for ob in roomkeys if ob is not None]
            caller.db.keylist = roomkeys
        chestkeys = caller.db.chestkeylist or []
        # remove any deleted objects
        if None in chestkeys:
            chestkeys = [ob for ob in chestkeys if ob is not None]
            caller.db.chestkeylist = chestkeys
        keylist = list(roomkeys) + list(chestkeys)
        caller.msg("Keys: %s" % ", ".join(ob.key for ob in keylist if ob))
        return


class CmdUndress(MuxCommand):
    """
    Completely remove all worn and wielded items on your person.
    Usage:
        undress

    Undress will completely remove all worn and wielded items on your person at once.
    """
    key = "undress"
    aliases = ["removeall"]
    locks = "cmd:all()"

    def func(self):
        caller = self.caller

        # Get the combat script if one is present
        cscript = caller.location.ndb.combat_manager

        # If there is a combat script present and the caller is one of the combatants we'll want to make some
        # additional checks about whether or not we can continue
        if cscript and caller in cscript.ndb.combatants:

            # If the current stage is not setup then we can't allow people to undress as we also unwield weapons
            if cscript.ndb.phase != 1:
                caller.msg("You cannot undress in combat outside of the setup phase.")
                return

        # Iterate over all the contents of the caller's inventory
        for obj in caller.contents:
            # Ensure the item is currently worn and that it's worn by the wearer - just in case
            if obj.db.currently_worn and obj.db.worn_by == caller:
                # Remove the wearable, setting the fact it is worn and who it is worn by to false/null
                obj.remove(caller)

                # Call the post-command hook explicitly - this might change to something internal to obj.remove later
                obj.at_post_remove(caller)

            # Ensure the item is currently wielded and that it's wielded by the wearer - just in case
            if obj.db.currently_wielded and obj.db.wielded_by == caller:
                # Remove the wieldable, setting the fact it is wielded and who it is wielded by to false/null
                obj.sheathe(caller)

                # Call the post-command hook explicitly - this might change to something internal to obj.sheathe later
                obj.at_post_remove(caller)

        # Throw a simple message to the caller only. We don't need to alert the room unless this design decision changes
        caller.msg("You undress.")
        return


class CmdLockObject(MuxCommand):
    """
    Locks or unlocks an exit or container

    Usage:
        lock <object>
        unlock <object>

    Locks or unlocks an object for which you have a key.
    """
    key = "+lock"
    aliases = ["lock", "unlock", "+unlock"]
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        verb = self.cmdstring.lstrip("+")
        obj = caller.search(self.args)
        if not obj:
            return
        try:
            lock_method = getattr(obj, verb)
            lock_method(caller)
        except AttributeError:
            self.msg("You cannot %s %s." % (verb, obj))
            return


class CmdTidyUp(MuxCommand):
    """
    Removes idle characters from the room

    Usage:
        +tidy

    This removes any character who has been idle for at least
    one hour in your current room, provided that the room is
    public.
    """
    key = "+tidy"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        loc = caller.location
        if "private" in loc.tags.all():
            self.msg("This is a private room.")
            return
        from typeclasses.characters import Character
        # can only boot Player Characters
        chars = Character.objects.filter(db_location=loc, roster__roster__name="Active")
        found = []
        for char in chars:
            time = char.idle_time
            player = char.player
            # no sessions connected, character that somehow became headless, such as server crash
            if not player:
                char.at_post_unpuppet(player)
                found.append(char)
                continue
            if time > 3600:
                player.execute_cmd("@ooc")
                found.append(char)
        if not found:
            self.msg("No characters were found to be idle.")
        else:
            self.msg("The following characters were removed: %s" % ", ".join(ob.name for ob in found))
