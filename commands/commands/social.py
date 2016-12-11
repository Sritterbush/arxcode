"""
Module for a number of social commands that we'll add for players. Most
will be character commands, since they'll deal with the grid.
"""
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from evennia.objects.models import ObjectDB
from django.conf import settings
from commands.commands.roster import format_header
from server.utils.prettytable import PrettyTable
from evennia.utils.evtable import EvTable
import time
from datetime import datetime, timedelta
from world.dominion import setup_utils
from world.dominion.models import RPEvent, Agent
from server.utils.arx_utils import inform_staff
from evennia.scripts.models import ScriptDB
from django.db.models import Q
from world.dominion.models import AssetOwner, Renown, Reputation
from typeclasses.characters import Character
import random


class CmdHangouts(MuxCommand):
    """
    +hangouts

    Usage:
        +hangouts

    Shows the public rooms marked as hangouts, displaying the players
    there. They are the rooms players gather in when they are seeking
    public scenes welcome to anyone.
    """
    key = "+hangouts"
    locks = "cmd:all()"
    aliases = ["@hangouts"]
    help_category = "Travel"

    def func(self):
        """Execute command."""
        caller = self.caller
        oblist = ObjectDB.objects.filter(Q(db_typeclass_path=settings.BASE_ROOM_TYPECLASS) &
                                         Q(locations_set__db_typeclass_path=settings.BASE_CHARACTER_TYPECLASS) &
                                         Q(db_tags__db_key="hangouts")).distinct()
        caller.msg(format_header("Hangouts"))
        if not oblist:
            caller.msg("No hangouts are currently occupied.")
            return
        for room in oblist:
            num_char = len(room.get_visible_characters(caller))
            if num_char > 0:
                name = room.name
                if room.db.x_coord is None and room.db.y_coord is None:
                    pos = (room.db.x_coord, room.db.y_coord)
                    name = "%s %s" % (name, str(pos))
                caller.msg("\n" + name)
                caller.msg("Number of characters: %s" % num_char)        


class CmdWhere(MuxPlayerCommand):
    """
    +where

    Usage:
        +where

    Displays a list of characters in public rooms.
    """
    key = "+where"
    locks = "cmd:all()"
    aliases = ["@where", "where"]
    help_category = "Travel"

    def func(self):
        """"Execute command."""
        caller = self.caller
        rooms = ObjectDB.objects.filter(Q(db_typeclass_path=settings.BASE_ROOM_TYPECLASS) &
                                        Q(locations_set__db_typeclass_path=settings.BASE_CHARACTER_TYPECLASS) &
                                        ~Q(db_tags__db_key__iexact="private")).distinct()
        if not rooms:
            caller.msg("No visible characters found.")
            return
        caller.msg("{wLocations of players:\n")
        verbose_where = False
        if caller.tags.get("verbose_where"):
            verbose_where = True
        self.msg("Players who are currently LRP have a |R+|n by their name.")
        for room in rooms:
            def char_name(ob):
                cname = ob.name
                if ob.db.player_ob and ob.db.player_ob.db.lookingforrp:
                    cname += "|R+|n"
                if not verbose_where:
                    return cname
                if ob.db.room_title:
                    cname += "{w(%s){n" % ob.db.room_title
                return cname
            charlist = sorted(room.get_visible_characters(caller), key=lambda x: x.name)
            char_names = ", ".join(char_name(char) for char in charlist if char.player
                                   and (not char.player.db.hide_from_watch or caller.check_permstring("builders")))
            if not char_names:
                continue
            name = room.name
            if room.db.x_coord is not None and room.db.y_coord is not None:
                pos = (room.db.x_coord, room.db.y_coord)
                name = "%s %s" % (name, str(pos))
            msg = "%s: %s" % (name, char_names)
            caller.msg(msg)


class CmdWatch(MuxPlayerCommand):
    """
    +watch

    Usage:
        +watch
        +watch <character>
        +watch/stop <character>
        +watch/hide

    Starts watching a player, letting you know when they
    go IC or stop being IC. If +watch/hide is set, you cannot
    be watched by anyone.
    """
    key = "+watch"
    locks = "cmd:all()"
    aliases = ["@watch", "watch"]
    help_category = "Social"

    @staticmethod
    def disp_watchlist(caller):
        watchlist = caller.db.watching or []
        if not watchlist:
            caller.msg("Not watching anyone.")
            return
        table = []
        for ob in sorted(watchlist, key=lambda x: x.key):
            name = ob.key.capitalize()
            if ob.db.player_ob.is_connected:
                name = "{c%s{n" % name
            table.append(name)
        caller.msg("Currently watching (online players are highlighted):\n%s" % ", ".join(table), options={'box': True})
        if caller.db.hide_from_watch:
            caller.msg("You are currently in hidden mode.")
        return
            
    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args and not self.switches:
            self.disp_watchlist(caller)
            return
        if 'hide' in self.switches:
            hide = caller.db.hide_from_watch or False
            hide = not hide
            caller.msg("Hiding set to %s." % str(hide))
            caller.db.hide_from_watch = hide
            return
        player = caller.search(self.args)
        if not player:
            return
        char = player.db.char_ob
        if not char:
            caller.msg("No character found.")
            return
        watchlist = caller.db.watching or []
        if 'stop' in self.switches:
            if char not in watchlist:
                caller.msg("You are not watching %s." % char)
                return
            # stop watching them
            watchlist.remove(char)
            caller.db.watching = watchlist
            watched = char.db.watched_by or []
            if caller in watched:
                watched.remove(caller)
                char.db.watched_by = watched
            caller.msg("Stopped watching %s." % char)
            return
        if char in watchlist:
            caller.msg("You are already watching %s." % char)
            return
        watched = char.db.watched_by or []
        if caller not in watched:
            watched.append(caller)
            char.db.watched_by = watched
        watchlist.append(char)
        caller.db.watching = watchlist
        caller.msg("You start watching %s." % char)


class CmdFinger(MuxPlayerCommand):
    """
    +finger

    Usage:
        +finger <character>

    Displays information about a given character.
    """
    key = "+finger"
    locks = "cmd:all()"
    aliases = ["@finger", "finger"]
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        show_hidden = caller.check_permstring("builders")
        if not self.args:
            caller.msg("You must supply a character name to +finger.")
            return
        player = caller.search(self.args)
        if not player:
            return
        char = player.db.char_ob
        if not char:
            caller.msg("No character found.")
            return
        name = char.db.longname or char.key
        msg = "\n{wName:{n %s\n" % name
        if show_hidden:
            msg += "{wCharID:{n %s, {wPlayerID:{n %s\n" % (char.id, player.id)
        session = player.get_all_sessions() and player.get_all_sessions()[0]
        if session and (not player.db.hide_from_watch or caller.check_permstring("builders")):
            idle_time = time.time() - session.cmd_last_visible
            idle = "Online and is idle" if idle_time > 1200 else "Online, not idle"
            msg += "{wStatus:{n %s\n" % idle
        else:
            last_online = player.last_login and player.last_login.strftime("%m-%d-%y") or "Never"
            msg += "{wStatus:{n Last logged in: %s\n" % last_online
        fealty = char.db.fealty or "None"
        msg += "{wFealty:{n %s\n" % fealty
        pageroot = "http://play.arxgame.org"
        quote = char.db.quote
        if quote:
            msg += "{wQuote:{n %s\n" % quote
        webpage = pageroot + char.get_absolute_url()
        msg += "{wCharacter page:{n %s\n" % webpage
        if show_hidden:
            orgs = player.current_orgs
        else:
            orgs = player.public_orgs
        if orgs:       
            org_str = ""
            apply_buffer = False
            for org in orgs:
                s_buffer = ""
                if apply_buffer:
                    s_buffer = " " * 15
                org_str += "%s%s: %s\n" % (s_buffer, org.name, pageroot + org.get_absolute_url())
                apply_buffer = True
            msg += "{wOrganizations:{n %s" % org_str
        caller.msg(msg, options={'box': True})
        

# for a character writing in their White Journal or Black Reflection
class CmdJournal(MuxCommand):
    """
    journal

    Usage:
        journal [<entry number>]
        journal <character>[=<entry number>]
        journal/search <character>=<text or tags to search for>
        journal/write <text>
        journal/event <event name>=<text>
        journal/black [<entry number>]
        journal/black <character>[=<entry number>]
        journal/addblack <text>
        journal/blackevent <event name>=<text>
        journal/index <character>[=<number of entries>]
        journal/blackindex <number of entries>
        journal/all
        journal/edit <entry number>=<text>
        journal/editblack <entry number>=<text>
        journal/markallread

    Allows a character to read the White Journals of characters,
    or add to their own White Journal or Black Reflections. White
    Journals are public notes that are recorded by the scribes of
    Velichor for all to see, while Black Reflections are sealed notes
    that are kept private until after the character is deceased and then
    only released if explicitly stated to do so in their will, along with
    the concurrence of their family and the Scholars of Vellichor.

    The edit function is only to fix typographical errors. ICly, the content
    of journals can never be altered once written. Only use it to fix
    formatting or typos.
    """
    key = "journal"
    locks = "cmd:all()"
    aliases = ["+journal"]
    help_category = "Social"

    def journal_index(self, character, jlist):
        num = 1
        table = PrettyTable(["{w#{n", "{wWritten About{n", "{wDate{n", "{wUnread?{n"])
        for entry in jlist:
            try:
                event = character.messages.get_event(entry)
                name = ", ".join(str(ob) for ob in entry.db_receivers_objects.all())       
                if event and not name:
                    name = event.name[:25]
                unread = "" if self.caller.db.player_ob in entry.receivers else "{wX{n"
                date = character.messages.get_date_from_header(entry)
                table.add_row([num, name, date, unread])
                num += 1
            except (AttributeError, RuntimeError, ValueError, TypeError):
                continue
        return str(table)

    def disp_unread_journals(self):
        
        caller = self.caller
        all_writers = ObjectDB.objects.filter(Q(sender_object_set__db_header__contains="white_journal") &
                                              ~Q(sender_object_set__db_receivers_players=caller.db.player_ob) &
                                              ~Q(roster__current_account=caller.roster.current_account)
                                              ).distinct().order_by('db_key')
        msglist = []
        for writer in all_writers:
            count = writer.sender_object_set.filter(Q(db_header__contains="white_journal") &
                                                    ~Q(db_receivers_players=caller.db.player_ob)).count()
            msglist.append("{C%s{c(%s){n" % (writer.key, count))
        caller.msg("Writers with journals you have not read: %s" % ", ".join(msglist))

    def mark_all_read(self):
        from evennia.comms.models import Msg
        caller = self.caller
        all_msgs = Msg.objects.filter(Q(db_header__contains="white_journal") &
                                      ~Q(db_receivers_players=caller.db.player_ob)
                                      # & ~Q(db_sender_objects__roster__current_account=caller.roster.current_account)
                                      ).distinct()
        for msg in all_msgs:
            msg.db_receivers_players.add(caller.db.player_ob)
            
    def func(self):
        """Execute command."""
        caller = self.caller
        num = 1
        # if no arguments, caller's journals
        if not self.args and not self.switches:
            char = caller
            white = "black" not in self.switches
            jname = "White Journal" if white else "Black Reflection"
            # display caller's latest white or black journal entry
            try:
                self.msg("Number of entries in your %s: %s" % (jname, char.messages.size(white))) 
                self.msg(char.messages.disp_entry_by_num(num=num, white=white, caller=caller.db.player_ob),
                         options={'box': True})
            except IndexError:
                caller.msg("No journal entries written yet.")
            self.disp_unread_journals()
            return
        if "markallread" in self.switches:
            self.mark_all_read()
            caller.msg("All messages marked read.")
            return
        # if no switches but have args, looking up journal of a character
        if not self.switches or 'black' in self.switches:
            white = "black" not in self.switches
            try:
                if not self.args:
                    char = caller
                    num = 1
                else:
                    if self.lhs.isdigit():
                        num = int(self.lhs)
                        char = caller
                    else:
                        # search as a player to make it global
                        char = caller.player.search(self.lhs)
                        # get character object from player we found
                        char = char.db.char_ob
                        if not char:
                            raise AttributeError
                        # display their latest white journal entry of the character
                        if not self.rhs:
                            num = 1
                        else:
                            num = int(self.rhs)
                    if num < 1:
                        caller.msg("Journal entry number must be at least 1.")
                        return
                journal = char.messages.white_journal if white else char.messages.black_journal
                msg = char.messages.disp_entry_by_num(num, white=white, caller=caller.db.player_ob)
                # if we fail access check, we have 'False' instead of a msg
                if msg is None:
                    caller.msg("Empty entry.")
                    return
                if not msg:
                    caller.msg("You do not have permission to read that.")
                    return
                caller.msg("Number of entries for {c%s{n's %s journal: %s" % (char, "white" if white else "black",
                                                                              len(journal)))
                caller.msg(msg, options={'box': True})
            except AttributeError:
                caller.msg("No player found for %s." % self.lhs)
                return
            except (ValueError, TypeError):
                caller.msg("You must provide a number for an entry.")
                return
            except IndexError:
                if num == 1:
                    caller.msg("No journal entries written yet.")
                    return
                caller.msg("You must provide a number that matches one of their entries.")
                return
            return
        # creating a new black or white journal
        if ("write" in self.switches or "addblack" in self.switches
                or "event" in self.switches or "blackevent" in self.switches):
            white = "addblack" not in self.switches and "blackevent" not in self.switches
            if not self.lhs:
                caller.msg("You cannot add a blank entry.")
                return
            if "event" in self.switches or "blackevent" in self.switches:
                if not self.rhs:
                    caller.msg("You must specify a comment for the event.")
                    return
                try:
                    event = RPEvent.objects.get(name__iexact=self.lhs)
                    entry = caller.messages.add_event_journal(event, self.rhs, white=white)
                except RPEvent.DoesNotExist:
                    caller.msg("Could not find an event by that name.")
                    return
            else:
                entry = caller.messages.add_journal(self.lhs, white=white)
            caller.msg("New %s added:" % ("white journal" if white else "black reflection"))
            caller.msg(caller.messages.disp_entry(entry), options={'box': True})
            if white:
                caller.msg_watchlist("A player you are watching, {c%s{n, has updated their white journal." % caller)
            return
        if "search" in self.switches:
            rhs = self.rhs
            if not rhs:
                char = caller
                rhs = self.args
            else:
                char = caller.player.search(self.lhs)
                if not char:
                    return
                char = char.db.char_ob
                if not char:
                    caller.msg("No character found.")
                    return
            entries = char.messages.search_journal(rhs)
            if not entries:
                caller.msg("No matches.")
                return
            journal = char.messages.white_journal
            white_matches = [journal.index(entry) + 1 for entry in entries if entry in journal]
            caller.msg("White journal matches: %s" % ", ".join("#%s" % str(num) for num in white_matches))
        if "index" in self.switches or "blackindex" in self.switches:
            num = 20
            if not self.lhs:
                char = caller
            elif self.lhs.isdigit():
                char = caller
                num = int(self.lhs)
            else:
                try:
                    char = caller.player.search(self.lhs).db.char_ob
                except AttributeError:
                    caller.msg("Character not found.")
                    return
            if self.rhs:
                try:
                    num = int(self.rhs)
                except ValueError:
                    caller.msg("Number of entries must be a number.")
                    return
            if "blackindex" in self.switches:
                if char != caller and not caller.check_permstring("builders"):
                    caller.msg("You can only see your own black journals.")
                    return
                journal = char.messages.black_journal
            else:
                journal = char.messages.white_journal
            caller.msg("{wJournal Entries for {c%s{n" % char)
            caller.msg(self.journal_index(char, journal[:num]))
            return
        if "all" in self.switches:
            self.disp_unread_journals()
            return
        if "edit" in self.switches or "editblack" in self.switches:
            journal = caller.messages.white_journal if "edit" in self.switches else caller.messages.black_journal
            try:
                num = int(self.lhs)
                text = self.rhs
                if num < 1 or not text:
                    raise ValueError
                entry = journal[num - 1]
            except (TypeError, ValueError):
                caller.msg("Must provide a journal entry number and replacement text.")
                return
            except IndexError:
                caller.msg("No entry by that number.")
                return
            now = datetime.now()
            if (now - entry.db_date_created).days > 2:
                caller.msg("It has been too long to edit that message.")
                return
            old = entry.db_message
            entry.db_message = self.rhs
            entry.save()
            logpath = settings.LOG_DIR + "/journal_changes.txt"
            try:
                log = open(logpath, 'a+')
                msg = "*" * 78
                msg += "\nJournal Change by %s\nOld:\n%s\nNew:\n%s\n" % (caller, old, self.rhs)
                msg += "*" * 78
                msg += "\n\n"
                log.write(msg)
            except IOError:
                import traceback
                traceback.print_exc()
            caller.msg("New journal entry body is:\n%s" % self.rhs)
            inform_staff("%s has editted their journal." % caller)
            return
                
        caller.msg("Invalid switch.")
        return


class CmdPosebreak(MuxCommand):
    """
    +posebreak

    Usage:
        +posebreak

    Toggles on or off a linebreak between poses.
    """
    key = "+posebreak"
    locks = "cmd:all()"
    aliases = ["@posebreak", "posebreak"]
    help_category = "Settings"

    def func(self):
        """Execute command."""
        caller = self.caller
        if caller.db.posebreak:
            caller.db.posebreak = False
        else:
            caller.db.posebreak = True
        caller.msg("Pose break set to %s." % caller.db.posebreak)
        return


class CmdMessenger(MuxCommand):
    """
    messenger

    Usage:
        messenger
        messenger <receiver>[,<receiver2>,...]=<message>
        messenger/receive
        messenger/deliver <receiver>,<object>,<money>=<message>
        messenger/money <receiver>,<amount>=<message>
        messenger/old <number>
        messenger/oldindex <amount to display>
        messenger/sent <number>
        messenger/sentindex <amount to display>
        messenger/delete <number>
        messenger/preserve <number>
        messenger/draft <receiver>=<message>
        messenger/proof
        messenger/send
        messenger/discreet <retainer ID>
        messenger/custom <retainer ID>

    Dispatches or receives in-game messengers. Messengers are an
    abstraction of any IC communication through distances - they
    can be people sent as messengers, courier ravens, whatever, as
    long as it's largely a letter being delivered personally to a
    receiving character. You can also deliver objects with the 'deliver'
    command.

    To draft a message before sending it, use the 'draft' switch, review
    your message with 'proof', and then finally send it with 'send'.
        
    """
    key = "messenger"
    locks = "cmd:all()"
    aliases = ["+messenger", "messengers", "+messengers", "receive messenger", "receive messengers",
               "receive messages", "message"]
    help_category = "Social"

    @staticmethod
    def send_messenger(caller, targ, msg, delivery=None, money=None):
        unread = targ.db.pending_messengers or []
        if type(unread) == 'unicode':
            # attribute was corrupted due to  database conversion, fix it
            unread = []
        m_name = caller.db.custom_messenger
        unread.insert(0, (msg, delivery, money, m_name))
        targ.db.pending_messengers = unread
        targ.messenger_notification(2)
        if caller.db.player_ob.db.nomessengerpreview:
            caller.msg("You dispatch %s to {c%s{n." % (m_name or "a messenger", targ))
        else:
            caller.msg("You dispatch %s to {c%s{n with the following message:\n\n'%s'\n" % (
                m_name or "a messenger", targ, msg.db_message))
        deliver_str = m_name or "Your messenger"
        if delivery:
            caller.msg("%s will also deliver %s." % (deliver_str, delivery))
        if money:
            caller.msg("%s will also deliver %s silver." % (deliver_str, money))
        caller.posecount += 1

    @staticmethod
    def disp_messenger(caller, msg):
        senders = msg.senders
        if senders:
            sender = senders[0]
            if sender:
                if sender.db.longname:
                    name = sender.db.longname
                else:
                    name = sender.key
            else:
 
                name = "Unknown Sender"
        else:
            name = "Unknown Sender"
        mssg = "{wSent by:{n %s\n" % name
        mssg += caller.messages.disp_entry(msg)
        caller.msg(mssg, options={'box': True})
            
    def func(self):
        """Execute command."""
        caller = self.caller
        # Display the number of old messages we have, and list whether
        # we have new messengers waiting
        cmdstr = getattr(self, 'cmdstring', "messenger")
        if cmdstr == "receive messenger" or cmdstr == "receive messengers" or cmdstr == "receive messages":
            self.switches.append("receive")
        if not self.args and not self.switches:
            unread = caller.db.pending_messengers or []
            read = caller.messages.messenger_history
            if not (read or unread):
                caller.msg("You have no messengers waiting for you, and have never received any messengers." +
                           " {wEver{n. At all. Not {rone{n.")
            if read:
                caller.msg("You have {w%s{n old messages you can re-read." % len(read))
            if unread:
                caller.msg("{mYou have {w%s{m new messengers waiting to be received." % len(unread))
            return
        if "discreet" in self.switches:
            if not self.args:
                if not caller.db.discreet_messenger:
                    self.msg("You are not using a retainer to receive messages discreetly.")
                    return
                caller.attributes.remove("discreet_messenger")
                self.msg("You will not receive messages discreetly.")
                return
            try:
                obj = caller.db.player_ob.retainers.get(id=self.args).dbobj
                if obj.db.abilities.get("discreet_messenger", 0):
                    caller.db.discreet_messenger = obj
                    self.msg("%s will now deliver messages to you discreetly if they are in the same room." % obj)
                else:
                    self.msg("%s does not have the ability to deliver messages discreetly." % obj)
            except (Agent.DoesNotExist, ValueError):
                self.msg("No retainer by that ID.")
            except AttributeError:
                self.msg("That agent cannot deliver messages.")
            return
        if "custom" in self.switches:
            if not self.args:
                ob = caller.db.custom_messenger
                if not ob:
                    self.msg("You are not using a custom messenger.")
                    return
                caller.attributes.remove("custom_messenger")
                self.msg("You will no longer send messages using %s." % ob)
                return
            try:
                obj = caller.db.player_ob.retainers.get(id=self.args).dbobj
                if obj.db.abilities.get("custom_messenger", 0):
                    caller.db.custom_messenger = obj
                    self.msg("%s will now deliver messages for you." % obj)
                else:
                    self.msg("%s does not have the ability to deliver messages for you." % obj)
            except (Agent.DoesNotExist, ValueError):
                self.msg("No retainer by that ID.")
            except AttributeError:
                self.msg("That agent cannot deliver messages.")
            return
        # get the first new messenger we have waiting
        if "receive" in self.switches:
            unread = caller.db.pending_messengers
            if type(unread) == 'unicode':
                caller.msg("Your pending_messengers attribute was corrupted " +
                           "in the database conversion. Sorry! Ask a GM to see "
                           "if they can find which messages were yours.")
                caller.db.pending_messengers = []
            if not unread:
                caller.msg("You have no messengers waiting to be received.")
                return
            # get msg object and any delivered obj
            msgtuple = unread.pop()
            messenger_name = "A messenger"
            msg = None
            obj = None
            money = None
            try:
                msg = msgtuple[0]
                obj = msgtuple[1]
                money = msgtuple[2]
                messenger_name = msgtuple[3] or "A messenger"
            except IndexError:
                pass
            except TypeError:
                self.msg("The message object was in the wrong format, possibly a result of a database error.")
                self.msg("It was just this: %s" % msgtuple)
                inform_staff("%s received a buggy messenger. They received: %s" % (caller, msgtuple))
                return
            caller.db.pending_messengers = unread
            # adds it to our list of old messages
            caller.messages.receive_messenger(msg)
            discreet = caller.db.discreet_messenger
            try:
                if discreet.location == caller.location:
                    self.msg("%s has discreetly informed you of a message delivered by %s." % (discreet,
                                                                                               messenger_name))
                else:
                    discreet = None
            except AttributeError:
                discreet = None
            self.disp_messenger(caller, msg)
            # handle a delivered object
            if obj:
                obj.move_to(caller, quiet=True)
                caller.msg("{gYou also have received a delivery!")
                caller.msg("{wYou receive{n %s." % obj)
            if money and money > 0:
                currency = caller.db.currency or 0.0
                currency += money
                caller.db.currency = currency
                caller.msg("{wYou receive %s silver coins.{n" % money)
            if not discreet:
                ignore = [ob for ob in caller.location.contents if ob.db.ignore_messenger_deliveries and ob != caller]
                caller.location.msg_contents("%s arrives, delivering a message to {c%s{n before departing." % (
                    messenger_name, caller.name), exclude=ignore)
            return
        # display an old message
        if ("old" in self.switches or 'delete' in self.switches or 'oldindex' in self.switches
                or "preserve" in self.switches):
            old = caller.messages.messenger_history
            if not old:
                caller.msg("You have never received a single messenger ever. Not a single one. " +
                           "Not even a death threat. {wNothing{n.")
                return
            if not self.args or 'oldindex' in self.switches:
                try:
                    num_disp = int(self.args)
                except (TypeError, ValueError):
                    num_disp = 30
                # display a prettytable of message number, sender, IC date
                msgtable = PrettyTable(["{wMsg #",
                                        "{wSender",
                                        "{wDate", "{wSave"])
                mess_num = 1
                old = old[:num_disp]
                for mess in old:
                    sender = mess.senders
                    if sender:
                        sender = sender[0]
                        name = sender.key
                    else:
                        name = "Unknown"
                    date = caller.messages.get_date_from_header(mess) or "Unknown"
                    saved = "{w*{n" if "preserve" in mess.db_header else ""
                    msgtable.add_row([mess_num, name, date, saved])
                    mess_num += 1
                caller.msg(msgtable)
                return
            try:
                num = int(self.lhs)
                if num < 1:
                    raise ValueError
                msg = old[num - 1]
                if "delete" in self.switches:
                    caller.messages.del_messenger(msg)
                    caller.msg("You destroy all evidence that you ever received that message.")
                    return
                if "preserve" in self.switches:
                    pres_count = caller.receiver_object_set.filter(db_header__icontains="preserve").count()
                    if pres_count >= 50:
                        caller.msg("You are preserving the maximum amount of messages allowed.")
                        return
                    if "preserve" in msg.db_header:
                        caller.msg("That message is already being preserved.")
                        return
                    msg.db_header = "%s;preserve" % msg.db_header
                    msg.save()
                    caller.msg("This message will no longer be automatically deleted.")
                self.disp_messenger(caller, msg)
                return
            except TypeError:
                caller.msg("You have %s old messages." % len(old))
                return
            except (ValueError, IndexError):
                caller.msg("You must supply a number between 1 and %s. You wrote '%s'." % (len(old), self.lhs))
                return
        if "sent" in self.switches or "sentindex" in self.switches or "oldsent" in self.switches:
            old = list(caller.sender_object_set.filter(db_header__icontains="messenger").order_by('-db_date_created'))
            if not old:
                caller.msg("There are no traces of old messages you sent. They may have all been destroyed.")
                return
            if not self.args or "sentindex" in self.switches:
                try:
                    num_disp = int(self.args)
                except (TypeError, ValueError):
                    num_disp = 20
                # display a prettytable of message number, sender, IC date
                msgtable = PrettyTable(["{wMsg #",
                                        "{wReceiver",
                                        "{wDate"])
                mess_num = 1
                old = old[:num_disp]
                for mess in old:
                    receiver = mess.receivers
                    if receiver:
                        receiver = receiver[0]
                        name = receiver.key
                    else:
                        name = "Unknown"
                    date = caller.messages.get_date_from_header(mess) or "Unknown"
                    msgtable.add_row([mess_num, name, date])
                    mess_num += 1
                caller.msg(msgtable)
                return
            try:
                num = int(self.lhs)
                if num < 1:
                    raise ValueError
                msg = old[num - 1]
                caller.msg("\n{wMessage to:{n %s" % ", ".join(str(ob) for ob in msg.receivers))
                self.disp_messenger(caller, msg)
                return
            except TypeError:
                caller.msg("You have %s old sent messages." % len(old))
                return
            except (ValueError, IndexError):
                caller.msg("You must supply a number between 1 and %s. You wrote '%s'." % (len(old), self.lhs))
                return
        if "proof" in self.switches:
            msg = caller.db.messenger_draft
            if not msg:
                caller.msg("You have no draft message stored.")
                return
            caller.msg("Message for: %s" % ", ".join(ob.key for ob in msg[0]))
            caller.msg(msg[1])
            return
        if "send" in self.switches:
            if not caller.db.messenger_draft:
                caller.msg("You have no draft message stored.")
                return
            targs, msg = caller.db.messenger_draft[0], caller.db.messenger_draft[1]
            msg = caller.messages.send_messenger(msg)
            for targ in targs:
                self.send_messenger(caller, targ, msg)
            caller.db.messenger_draft = None
            return
        if not self.lhs or not self.rhs:
            caller.msg("Invalid usage.")
            return
        # delivery messenger
        if "deliver" in self.switches or "money" in self.switches:
            money = 0.0
            try:
                targs = [caller.player.search(self.lhslist[0])]
                if "money" in self.switches:
                    money = float(self.lhslist[1])
                    delivery = None
                else:
                    delivery = caller.search(self.lhslist[1], location=caller)
                    if not delivery:
                        return
                    if len(self.lhslist) > 2:
                        money = self.lhslist[2]
                money = float(money)
                if money and money > caller.db.currency:
                    caller.msg("You cannot send that much money.")
                    return
            except IndexError:
                caller.msg("Must provide both a receiver and an object for a delivery.")
                caller.msg("Ex: messenger/deliver alaric,a bloody rose=Only for you.")
                return
            except (ValueError, TypeError):
                caller.msg("Money must be a number.")
                return
        # normal messenger
        elif "draft" in self.switches or not self.switches:
            money = 0
            targs = []
            for arg in self.lhslist:
                targ = caller.player.search(arg)
                if targ:
                    targs.append(targ)
            delivery = None
        else:  # invalid switch
            self.msg("Unrecognized switch.")
            return
        if not targs:
            return
        # get character objects of each match
        targs = [targ.db.char_ob for targ in targs if targ and targ.db.char_ob]
        if not targs:
            caller.msg("No character found.")
            return
        if "draft" in self.switches:
            caller.db.messenger_draft = (targs, self.rhs)
            caller.msg("Saved message. To see it, type 'message/proof'.")
            return
        if (delivery or money) and len(targs) > 1:
            caller.msg("You cannot send a delivery or money to more than one person.")
            return
        # format our messenger
        msg = caller.messages.send_messenger(self.rhs)
        # make delivery object unavailable while in transit, if we have one
        if delivery or money:
            if delivery:
                delivery.location = None
            if money:
                caller.pay_money(money)
            targ = targs[0]
            self.send_messenger(caller, targ, msg, delivery, money)
            return
        for targ in targs:
            self.send_messenger(caller, targ, msg, delivery)

largesse_types = ('none', 'common', 'refined', 'grand', 'extravagant', 'legendary')
costs = {
    'none': (0, 0),
    'common': (100, 1000),
    'refined': (1000, 5000),
    'grand': (10000, 20000),
    'extravagant': (100000, 100000),
    'legendary': (500000, 400000)
    }


class CmdCalendar(MuxPlayerCommand):
    """
    @cal

    Usage:
        @cal
        @cal/list
        @cal <event number>
        @cal/create <name>
        @cal/desc <description>
        @cal/date <date>
        @cal/largesse <level>
        @cal/location [<room name, otherwise room you're in>]
        @cal/private
        @cal/addhost <playername>
        @cal/roomdesc <description>
        @cal/submit
        @cal/starteventearly <event number>
        @cal/endevent <event number>
        @cal/reschedule <event number>=<new date>
        @cal/cancel <event number>
        @cal/changeroomdesc <event number>=<new desc>
        @cal/old
        @cal/comments <event number>=<comment number>

    Creates or displays information about events. date should be
    in the format of 'MM/DD/YY HR:MN'. /private toggles whether the
    event is public or private (defaults to public). To spend extravagant
    amounts of money in hosting an event for prestige, set the /largesse
    level. To see the valid largesse types with their costs and prestige
    values, do '@cal/largesse'. All times are in EST.
    """
    key = "@cal"
    locks = "cmd:all()"
    aliases = ["+event", "+events", "@calendar"]
    help_category = "Social"

    @staticmethod
    def display_events(events):
        table = PrettyTable(["{wID{n", "{wName{n", "{wDate{n", "{wHost{n", "{wPublic{n"])
        for event in events:
            host = event.main_host or "No host"
            host = str(host).capitalize()
            public = "Public" if event.public_event else "Not Public"
            table.add_row([event.id, event.name[:25], event.date.strftime("%x %X"), host, public])
        return table

    @staticmethod
    def display_project(proj):
        """proj is [name, date, location, desc, public, hosts, largesse]"""
        name = proj[0] or "None"
        date = proj[1].strftime("%x %X") if proj[1] else "No date yet"
        loc = proj[2].name if proj[2] else "No location set"
        desc = proj[3] or "No description set yet"
        pub = "Public" if proj[4] else "Not Public"
        hosts = proj[5] or []
        largesse = proj[6] or 0
        roomdesc = proj[7] or ""
        hosts = ", ".join(str(ob) for ob in hosts)
        mssg = "{wEvent name:{n %s\n" % name
        mssg += "{wDate:{n %s\n" % date
        mssg += "{wLocation:{n %s\n" % loc
        mssg += "{wDesc:{n %s\n" % desc
        mssg += "{wPublic:{n %s\n" % pub
        mssg += "{wHosts:{n %s\n" % hosts
        mssg += "{wLargesse:{n %s\n" % largesse
        mssg += "{wRoom Desc:{n %s\n" % roomdesc
        return mssg
                         
    def func(self):
        """Execute command."""
        caller = self.caller
        char = caller.db.char_ob
        if not char:
            caller.msg("You have no character object.")
            return
        if not hasattr(caller, 'Dominion') and char:
            setup_utils.setup_dom_for_char(char)
        dompc = caller.Dominion
        # check if we have a project
        proj = caller.ndb.event_creation
        if not self.args and not self.switches:
            if proj:
                caller.msg("{wEvent you're creating:\n%s" % self.display_project(proj), options={'box': True})
                return
            else:
                # if we don't have a project, just display upcoming events
                self.switches.append("list")            
        if not self.switches or "comments" in self.switches:
            lhslist = self.lhs.split("/")
            if len(lhslist) > 1:
                lhs = lhslist[0]
                rhs = lhslist[1]
            else:
                lhs = self.lhs
                rhs = self.rhs
            try:
                event = RPEvent.objects.get(id=int(lhs))
            except ValueError:
                caller.msg("Event must be a number.")
                return
            except RPEvent.DoesNotExist:
                caller.msg("No event found by that number.")
                return
            # display info on a given event
            if not rhs:
                caller.msg(event.display(), options={'box': True})
                return
            try:
                num = int(rhs)
                if num < 1:
                    raise ValueError
                comments = list(event.comments.filter(
                    db_header__icontains="white_journal").order_by('-db_date_created'))
                caller.msg(char.messages.disp_entry(comments[num - 1]))
                return
            except (ValueError, TypeError):
                caller.msg("Must leave a positive number for a comment.")
                return
            except IndexError:
                caller.msg("No entry by that number.")
                return
        if "list" in self.switches:
            # display upcoming events
            unfinished = RPEvent.objects.filter(finished=False).order_by('date')
            table = self.display_events(unfinished)
            caller.msg("{wUpcoming events:\n%s" % table, options={'box': True})
            return
        if "old" in self.switches:
            # display finished events
            finished = RPEvent.objects.filter(finished=True).order_by('date')
            table = self.display_events(finished)
            caller.msg("{wOld events:\n%s" % table, options={'box': True})
            return
        # at this point, we may be trying to update our project. Set defaults.
        proj = caller.ndb.event_creation or [None, None, None, None, True, [], None, None]
        if 'largesse' in self.switches:
            if not self.args:
                table = PrettyTable(['level', 'cost', 'prestige'])
                for key in largesse_types:
                    table.add_row([key, costs[key][0], costs[key][1]])
                caller.msg(table, options={'box': True})
                return
            args = self.args.lower()
            if args not in largesse_types:
                caller.msg("Argument needs to be in %s." % ", ".join(ob for ob in largesse_types))
                return
            cost = costs[args][0]
            currency = caller.db.char_ob.db.currency
            if currency < cost:
                caller.msg("That requires %s to buy. You have %s." % (cost, currency))
                return
            proj[6] = args
            caller.ndb.proj = proj
            caller.msg("Largesse level set to %s for %s." % (args, cost))
            return
        if "date" in self.switches:
            try:
                date = datetime.strptime(self.lhs, "%m/%d/%y %H:%M")
            except ValueError:
                caller.msg("Date did not match 'mm/dd/yy hh:mm' format.")
                caller.msg("You entered: %s" % self.lhs)
                return
            now = datetime.now()
            if date < now:
                caller.msg("You cannot make an event for the past.")
                return
            proj[1] = date
            caller.ndb.proj = proj
            caller.msg("Date set to %s." % date.strftime("%x %X"))
            return
        if "location" in self.switches:
            if self.lhs:
                try:
                    room = ObjectDB.objects.get(db_typeclass_path=settings.BASE_ROOM_TYPECLASS,
                                                db_key__icontains=self.lhs)
                except (ObjectDB.DoesNotExist, ObjectDB.MultipleObjectsReturned):
                    caller.msg("Could not find a unique match for %s." % self.lhs)
                    return
            else:
                if not caller.character:
                    caller.msg("You must be in a room to mark it as the event location.")
                    return
                room = caller.character.location
            if not room:
                caller.msg("No room found.")
                return
            proj[2] = room
            caller.ndb.event_creation = proj
            caller.msg("Room set to %s." % room.name)
            return
        if "desc" in self.switches:
            proj[3] = self.lhs
            caller.ndb.event_creation = proj
            caller.msg("Desc of event set to:\n%s" % self.lhs)
            return
        if "roomdesc" in self.switches:
            proj[7] = self.lhs
            caller.ndb.event_creation = proj
            caller.msg("Room desc of event set to:\n%s" % self.lhs)
            return
        if "private" in self.switches:
            proj[4] = not proj[4]
            caller.ndb.event_creation = proj
            caller.msg("Public is now set to: %s" % proj[4])
            return
        if "addhost" in self.switches:
            hosts = proj[5] or []
            host = caller.search(self.lhs)
            if not host:
                return
            if host in hosts:
                caller.msg("Host is already listed.")
                return
            try:
                host = host.Dominion
            except AttributeError:
                char = host.db.char_ob
                if not char:
                    caller.msg("Host does not have a character.")
                    return
                host = setup_utils.setup_dom_for_char(char)
            hosts.append(host)
            caller.msg("%s added to hosts." % host)
            caller.msg("Hosts are: %s" % ", ".join(str(host) for host in hosts))
            proj[5] = hosts
            caller.ndb.event_creation = proj
            return
        if "create" in self.switches:
            if RPEvent.objects.filter(name__iexact=self.lhs):
                caller.msg("There is already an event by that name. Choose a different name," +
                           " or add a number if it's a sequel event.")
                return
            proj = [self.lhs, proj[1], proj[2], proj[3], proj[4], [dompc] if dompc not in proj[5] else proj[5], proj[6],
                    proj[7]]
            caller.msg("{wStarting project. It will not be saved until you submit it. " +
                       "Does not persist through logout/server reload.{n")
            caller.msg(self.display_project(proj), options={'box': True})
            caller.ndb.event_creation = proj
            return
        if "submit" in self.switches:
            name, date, loc, desc, public, hosts, largesse, room_desc = proj
            if not (name and date and loc and desc and hosts):
                caller.msg("All fields must be defined before you submit.")
                caller.msg(self.display_project(proj), options={'box': True})
                return         
            if not largesse:
                cel_lvl = 0
            elif largesse.lower() == 'common':
                cel_lvl = 1
            elif largesse.lower() == 'refined':
                cel_lvl = 2
            elif largesse.lower() == 'grand':
                cel_lvl = 3
            elif largesse.lower() == 'extravagant':
                cel_lvl = 4
            elif largesse.lower() == 'legendary':
                cel_lvl = 5
            else:
                caller.msg("That is not a valid type of largesse.")
                caller.msg("It must be 'common', 'refined', 'grand', 'extravagant', or 'legendary.'")
                return
            cost = costs.get(largesse, (0, 0))[0]
            if cost > caller.db.char_ob.db.currency:
                caller.msg("The largesse level set requires %s, you have %s." % (cost, caller.db.currency))
                return
            else:
                caller.db.char_ob.pay_money(cost)
                caller.msg("You pay %s coins for the event." % cost)
            event = RPEvent.objects.create(name=name, date=date, desc=desc, location=loc,
                                           public_event=public, celebration_tier=cel_lvl,
                                           room_desc=room_desc)
            for host in hosts:
                event.hosts.add(host)
            post = self.display_project(proj)
            # mark as main host with a tag
            event.tag_obj(caller)
            caller.ndb.event_creation = None
            caller.msg("New event created: %s at %s." % (event.name, date.strftime("%x %X")))
            inform_staff("New event created by %s: %s, scheduled for %s." % (caller, event.name,
                                                                             date.strftime("%x %X")))
            event_manager = ScriptDB.objects.get(db_key="Event Manager")
            event_manager.post_event(event, caller, post)         
            return
        # both starting an event and ending one requires a Dominion object
        try:
            dompc = caller.Dominion
        except AttributeError:
            char = caller.db.char_ob
            if not char:
                caller.msg("You have no character, which is required to set up Dominion.")
                return
            dompc = setup_utils.setup_dom_for_char(char)
        # get the events they're hosting
        events = dompc.events_hosted.filter(finished=False)
        if not events:
            caller.msg("You are not hosting any events that are unfinished.")
            return
        # make sure caller input an integer
        try:
            eventid = int(self.lhs)
        except (ValueError, TypeError):
            caller.msg("You must supply a number for an event.")
            caller.msg(self.display_events(events), options={'box': True})
            return
        # get the script that manages events
        event_manager = ScriptDB.objects.get(db_key="Event Manager")
        # try to get event matching caller's input
        try:
            event = events.get(id=eventid)
        except RPEvent.DoesNotExist:
            caller.msg("You are not hosting any event by that number. Your events:")
            caller.msg(self.display_events(events), options={'box': True})
            return
        if "starteventearly" in self.switches:
            event_manager.start_event(event)
            caller.msg("You have started the event.")        
            return
        if "endevent" in self.switches:
            event_manager.finish_event(event)
            caller.msg("You have ended the event.")
            return
        if "reschedule" in self.switches:
            try:
                date = datetime.strptime(self.rhs, "%m/%d/%y %H:%M")
            except ValueError:
                caller.msg("Date did not match 'mm/dd/yy hh:mm' format.")
                caller.msg("You entered: %s" % self.rhs)
                return
            now = datetime.now()
            if date < now:
                caller.msg("You cannot schedule an event for the past.")
                return
            event.date = date
            event.save()
            caller.msg("Event now scheduled for %s." % date)
            event_manager.reschedule_event(event, date)
            return
        if "changeroomdesc" in self.switches:
            event.room_desc = self.rhs
            event.save()
            caller.msg("Event's room desc is now:\n%s" % self.rhs)
            return
        if "cancel" in self.switches:
            if event.id in event_manager.db.active_events:
                caller.msg("You must /end an active event.")
                return
            cel_tier = event.celebration_tier
            if cel_tier == 1:
                rating = 'common'
            elif cel_tier == 2:
                rating = 'refined'
            elif cel_tier == 3:
                rating = 'grand'
            elif cel_tier == 4:
                rating = 'extravagant'
            elif cel_tier == 5:
                rating = 'legendary'
            else:
                rating = 'none'
            cost = costs.get(rating, (0, 0))[0]
            caller.db.char_ob.pay_money(-cost)
            inform_staff("%s event has been cancelled." % str(event))
            event_manager.cancel_event(event)
            caller.msg("You have cancelled the event.")
            return
        
        caller.msg("Invalid switch.")


def get_max_praises(char):
    val = char.db.charm or 0
    val += char.db.command or 0
    val += char.db.skills.get('propaganda', 0)
    val += char.db.skills.get('diplomacy', 0)
    val *= 2
    srank = char.db.social_rank or 10
    if srank == 0:
        srank = 10
    val /= srank
    if val <= 0:
        val = 1
    return val
    

def display_praises(player):
    praises = player.db.praises or {}
    condemns = player.db.condemns or {}
    msg = "Praises:\n"
    table = EvTable("Name", "Praises", "Message", width=78)
    current = 0
    for pc in praises:
        table.add_row(pc.capitalize(), praises[pc][0], praises[pc][1])
        current += praises[pc][0]
    p_max = get_max_praises(player.db.char_ob)
    msg += str(table)
    msg += "\nPraises remaining: %s" % (p_max - current)
    msg += "\nCondemns:\n"
    current = 0
    table = EvTable("Name", "Condemns", "Message", width=78)
    for pc in condemns:
        table.add_row(pc.capitalize(), condemns[pc][0], condemns[pc][1])
        current += condemns[pc][0]
    msg += str(table)
    msg += "\nCondemns remaining: %s" % (p_max - current)
    return msg


class CmdPraise(MuxCommand):
    """
    praise

    Usage:
        praise <character>[=<message>]
        praise/all <character>[=<message>]

    Praises a character, increasing their prestige. Your number
    of praises per week are based on your social rank and skills.
    """
    key = "praise"
    locks = "cmd:all()"
    help_category = "Social"
    aliases = ["igotyoufam"]
    attr = "praises"
    verb = "praise"
    verbing = "praising"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args:
            caller.msg(display_praises(caller.player), options={'box': True})
            return
        targ = caller.player.search(self.lhs)
        if not targ or not targ.db.char_ob:
            caller.msg("No character object found.")
            return
        account = caller.roster.current_account
        if account == targ.roster.current_account:
            caller.msg("You cannot %s yourself." % self.verb)
            return
        if targ.roster.roster.name != "Active":
            caller.msg("You can only %s active characters." % self.verb)
            return
        if targ.is_staff:
            caller.msg("Staff don't need your %s." % self.attr)
            return
        char = caller
        caller = caller.player       
        p_max = get_max_praises(char)
        current = 0
        praises = caller.attributes.get(self.attr) or {}
        for key in praises:
            current += praises[key][0]
        if current >= p_max:
            caller.msg("You have already used all your %s for the week." % self.attr)
            return
        to_use = 1 if "all" not in self.switches else p_max - current
        current += to_use
        key = self.lhs.lower()
        value = praises.get(key, [0, ""])
        value[0] += to_use
        value[1] = self.rhs
        praises[key] = value
        caller.attributes.add(self.attr, praises)
        caller.msg("You %s the actions of %s. You have %s %s remaining." %
                   (self.verb, self.lhs.capitalize(), (p_max-current), self.attr)
                   )
        if self.rhs:
            char.location.msg_contents("%s is overheard %s %s for: %s" % (char.name, self.verbing,
                                                                          targ.key.capitalize(), self.rhs),
                                       exclude=char)
        else:
            char.location.msg_contents("%s is overheard %s %s." % (char.name, self.verbing,
                                                                   targ.key.capitalize()),
                                       exclude=char)


class CmdCondemn(CmdPraise):
    """
    condemn

    Usage:
        condemn <character>[=<message>]
        condemn/all <character>[=<message>]

    Condemns a character, decreasing their prestige. Your number
    of condemns per week are based on your social rank and skills.
    """
    key = "condemn"
    attr = "condemns"
    verb = "condemn"
    verbing = "condemning"
    aliases = ["throw shade"]


class CmdAFK(MuxPlayerCommand):
    """
    afk

    Usage:
        afk
        afk <message>

    Toggles on or off AFK(away from keyboard). If you provide a message,
    it will be sent to people who send you pages.
    """
    key = "afk"
    locks = "cmd:all()"
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        if caller.db.afk:
            caller.db.afk = ""
            caller.msg("You are no longer AFK.")
            return
        caller.db.afk = self.args or "Sorry, I am AFK(away from keyboard) right now."
        caller.msg("{wYou are now AFK with the following message{n: %s" % caller.db.afk)
        return


class CmdRoomHistory(MuxCommand):
    """
    Adds a historical note to a room

    Usage:
        +roomhistory <message>
        
    Tags a note into a room to indicate that something significant happened
    here in-character. This is primarily intended to allow for magically
    sensitive characters to have a mechanism for detecting a past event, far
    in the future.
    """
    key = "+roomhistory"
    locks = "cmd:all()"
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args:
            caller.msg("Please enter a description for the event.")
            return
        history = caller.location.db.roomhistory or []
        history.append((caller, self.args))
        caller.location.db.roomhistory = history
        caller.location.tags.add('roomhistory')
        caller.msg("Added the historical note {w'%s'{n to this room. Thank you." % self.args)
        inform_staff("%s added the note {w'%s'{n to room %s." % (caller, self.args, caller.location))
        return


class CmdSocialScore(MuxCommand):
    """
    The who's-who of Arx

    Usage:
        +score
        +score/orgs
        +score/personal
        +score/renown [<category>]
        +score/reputation [<organization>]
        
    Checks the organizations and players who have the highest prestige. Renown measures the influence
    a character has built with different npc groups, while reputation is how a character is thought of
    by the npcs within an organization.
    """
    key = "+score"
    locks = "cmd:all()"
    help_category = "Information"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.switches:
            pcs = sorted(AssetOwner.objects.select_related('player__patron').filter(
                player__player__isnull=False).prefetch_related('player__memberships'),
                         key=lambda x: x.total_prestige, reverse=True)[:20]
            table = PrettyTable(["{wName{n", "{wPrestige{n"])
            for pc in pcs:
                table.add_row([str(pc), pc.total_prestige])
            caller.msg(str(table))
            return
        if "renown" in self.switches:
            renowned = Renown.objects.filter(player__player__isnull=False,
                                             player__player__roster__roster__name="Active").exclude(
                                             category__name__icontains="mystery").order_by('-rating')
            if self.args:
                renowned = renowned.filter(category__name__iexact=self.args)
            renowned = renowned[:20]
            table = PrettyTable(["{wName{n", "{wCategory{n", "{wLevel{n", "{wRating{n"])
            for ob in renowned:
                table.add_row([str(ob.player), ob.category, ob.level, ob.rating])
            self.msg(str(table))
            return
        if "reputation" in self.switches:
            rep = Reputation.objects.filter(player__player__isnull=False, organization__secret=False,
                                            player__player__roster__roster__name="Active").order_by('-respect')
            if self.args:
                rep = rep.filter(organization__name__iexact=self.args)
            rep = rep[:20]
            table = PrettyTable(["{wName{n", "{wOrganization{n", "{wAffection{n", "{wRespect{n"])
            for ob in rep:
                table.add_row([str(ob.player), str(ob.organization), ob.affection, ob.respect])
            self.msg(str(table))
            return
        if "personal" in self.switches:
            assets = AssetOwner.objects.filter(player__player__isnull=False).order_by('-prestige')[:20]
        elif "orgs" in self.switches:
            assets = AssetOwner.objects.filter(organization_owner__isnull=False).order_by('-prestige')[:20]
        else:
            caller.msg("Invalid switch.")
            return
        table = PrettyTable(["{wName{n", "{wPrestige{n"])
        for asset in assets:
            table.add_row([str(asset), asset.prestige])
        caller.msg(str(table))


class CmdThink(MuxCommand):
    """
    Think to yourself

    Usage:
        +think <message>
        
    Sends a message to yourself about your thoughts. At present, this
    is really mostly for your own use in logs and the like. Eventually,
    characters with mind-reading powers may be able to see these.
    """
    key = "+think"
    aliases = ["think"]
    locks = "cmd:all()"
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        caller.msg("You think: %s" % self.args)


class CmdFeel(MuxCommand):
    """
    State what your character is feeling

    Usage:
        +feel
        
    Sends a message to yourself about your feelings. Can possibly
    be seen by very sensitive people.
    """
    key = "+feel"
    aliases = ["feel"]
    locks = "cmd:all()"
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        caller.msg("You feel: %s" % self.args)


class CmdDonate(MuxCommand):
    """
    Donates money to some group

    Usage:
        +donate <group name>=<amount>
        
    Donates money to some group of npcs in exchange for prestige.
    """
    key = "+donate"
    locks = "cmd:all()"
    help_category = "Social"
            
    def func(self):
        """Execute command."""
        caller = self.caller
        dompc = caller.db.player_ob.Dominion
        donations = caller.db.donations or {}
        if not self.lhs:
            caller.msg("{wDonations:{n")
            table = PrettyTable(["{wGroup{n", "{wTotal{n"])
            for group in sorted(donations.keys()):
                table.add_row([group, donations[group]])
            caller.msg(str(table))
            return
        group = self.lhs
        old = donations.get(group, 0)
        try:
            val = int(self.rhs)
            if val > caller.db.currency:
                caller.msg("Not enough money.")
                return
            caller.pay_money(val)
            old += val
            donations[group] = old
            caller.db.donations = donations
            prest = int(val * 0.5)
            dompc.assets.adjust_prestige(prest)
            caller.msg("You donate %s to %s and gain %s prestige." % (val, group, prest))
        except (TypeError, ValueError):
            caller.msg("Must give a number.")
            return


class CmdRandomScene(MuxCommand):
    """
    @randomscene

    Usage:
        @randomscene
        @randomscene/claim <player>=<summary of the scene>
        @randomscene/validate <player>
        @randomscene/viewrequests

    Generates three characters who you can receive bonus xp for this week
    by having an RP scene with them. Executing the command generates the
    names, and then once you meet with the player and have a scene with
    them, using @randomscene/claim will send a request to that player to
    validate the scene you both had. If they agree, during the weekly script
    you'll both receive xp. Requests that aren't answered are wiped in
    weekly maintenance. /claim requires that both of you be in the same room.
    """
    key = "@randomscene"
    locks = "cmd:all()"
    help_category = "Social"
    NUM_SCENES = 3
    NUM_DAYS = 3
    DAYS_FOR_NEWBIE_CHECK = 14

    @property
    def scenelist(self):
        return self.caller.db.player_ob.db.random_scenelist or []

    @property
    def claimlist(self):
        return self.caller.db.player_ob.db.claimed_scenelist or []

    @property
    def newbies(self):
        """
        A list of new players we want to encourage people to RP with
        """
        newness = datetime.now() - timedelta(days=self.DAYS_FOR_NEWBIE_CHECK)
        return self.valid_choices.filter(Q(roster__accounthistory__start_date__gte=newness) &
                                         Q(roster__accounthistory__end_date__isnull=True))

    @property
    def valid_choices(self):
        last_week = datetime.now() - timedelta(days=self.NUM_DAYS)
        return Character.objects.filter(Q(roster__roster__name="Active") &
                                        ~Q(roster__current_account=self.caller.roster.current_account) &
                                        Q(roster__player__last_login__isnull=False) &
                                        Q(roster__player__last_login__gte=last_week) &
                                        Q(roster__player__is_staff=False) &
                                        ~Q(roster__player__db_tags__db_key="staff_npc"))

    def display_lists(self):
        if len(self.scenelist) + len(self.claimlist) < self.NUM_SCENES:
            self.generate_lists()
        scenelist = self.scenelist
        claimlist = self.claimlist
        self.msg("{wRandomly generated RP partners for this week:{n %s" % ", ".join(str(ob) for ob in scenelist))
        self.msg("{wNew players who can be also RP'd with for credit:{n %s" % ", ".join(str(ob) for ob in self.newbies))
        if claimlist:
            self.msg("{wThose you have already RP'd with this week:{n %s" % ", ".join(str(ob) for ob in claimlist))

    def generate_lists(self):
        scenelist = self.scenelist
        claimlist = self.claimlist
        newbies = [ob.id for ob in self.newbies]
        choices = self.valid_choices
        if newbies:
            choices = choices.exclude(id__in=newbies)
        choices = list(choices)
        max_iter = 0
        while len(scenelist) < (self.NUM_SCENES - len(claimlist)):
            max_iter += 1
            if max_iter > 10000:
                raise RuntimeError("Max Recursion Depth Exceeded.")
            choice = random.choice(choices)
            if choice not in scenelist:
                scenelist.append(choice)
        scenelist = sorted(scenelist, key=lambda x: x.key.capitalize())
        self.caller.db.player_ob.db.random_scenelist = scenelist

    def claim_scene(self):
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        if targ not in self.scenelist and targ not in self.newbies:
            self.msg("%s is not in your list of random scene partners this week: %s" % (targ, ", ".join(
                str(ob) for ob in self.scenelist)))
            self.msg("New players who can be RP'd with for credit: %s" % ", ".join(str(ob) for ob in self.newbies))
            return
        if targ in self.claimlist:
            self.msg("You have already claimed a scene with %s this week." % targ)
            return
        if not self.rhs:
            self.msg("You must include some summary of the scene. It may be quite short.")
            return
        requests = targ.db.scene_requests or {}
        tup = (self.caller, self.rhs)
        name = self.caller.name
        requests[name.lower()] = tup
        targ.db.scene_requests = requests
        msg = "%s has requested that you validate their RP scene with you, which will grant you both xp." % name
        msg += "\n\nTheir summary of the scene was the following: %s\n" % self.rhs
        msg += "If you ignore this request, it will be wiped in weekly maintenance."
        msg += "\nTo validate, use {w@randomscene/validate %s{n" % name
        targ.db.player_ob.inform(msg, category="Validate")
        inform_staff("%s has completed a random scene with %s. Summary: %s" % (self.caller, targ, self.rhs))
        self.msg("You have sent a request to %s to validate your scene." % targ)

    def validate_scene(self):
        targ = self.caller.db.scene_requests.pop(self.args.lower(), (None, ""))[0]
        if not targ:
            self.msg("No character by that name has sent you a request.")
            self.view_requests()
            return
        claimed = targ.db.player_ob.db.claimed_scenelist or []
        claimed.append(self.caller)
        targ_scenelist = targ.db.player_ob.db.random_scenelist or []
        if self.caller in targ_scenelist:
            targ_scenelist.remove(self.caller)
            targ.db.player_ob.db.random_scenelist = targ_scenelist
        targ.db.player_ob.db.claimed_scenelist = claimed
        self.msg("Validating their scene. Both of you will receive xp for it later.")

    def view_requests(self):
        requests = self.caller.db.scene_requests or {}
        table = EvTable("{wName{n", "{wSummary{n", width=78, border="cells")
        for tup in requests.values():
            table.add_row(tup[0], tup[1])
        self.msg(str(table))

    def func(self):
        if not self.switches and not self.args:
            self.display_lists()
            return
        if "claim" in self.switches or (not self.switches and self.args):
            self.claim_scene()
            return
        if "validate" in self.switches:
            self.validate_scene()
            return
        if "viewrequests" in self.switches:
            self.view_requests()
            return
        self.msg("Invalid switch.")


class CmdCensus(MuxPlayerCommand):
    """
    Displays population of active players by fealty

    Usage:
        +census

    Lists the number of active characters in each fealty. New characters
    created receive an xp bonus for being in a less populated fealty.
    """
    key = "+census"
    locks = "cmd:all()"
    category = "Information"

    def func(self):
        from .guest import census_of_fealty
        fealties = census_of_fealty()
        table = PrettyTable(["{wFealty{n", "{w#{n"])
        for fealty in fealties:
            table.add_row([fealty, fealties[fealty]])
        self.msg(table)


class CmdRoomTitle(MuxCommand):
    """
    Displays what your character is currently doing in the room

    Usage:
        +roomtitle <description>

    Appends a short blurb to your character's name when they are displayed
    to the room in parentheses.
    """
    key = "+roomtitle"
    locks = "cmd:all()"
    category = "Social"

    def func(self):
        if not self.args:
            self.msg("Roomtitle cleared.")
            self.caller.attributes.remove("room_title")
            return
        self.caller.db.room_title = self.args
        self.msg("Your roomtitle set to %s {w({n%s{w){n" % (self.caller, self.args))
        return
