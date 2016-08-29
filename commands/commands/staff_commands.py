"""

Admin commands

"""

import time
import re
from django.conf import settings
from django.contrib.auth.models import User
from evennia.server.sessionhandler import SESSIONS
from evennia.server.models import ServerConfig
from evennia.utils import utils, search, evtable, create
from server.utils import prettytable
from server.utils.utils import inform_staff
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from evennia.players.models import PlayerDB
from evennia.objects.models import ObjectDB

PERMISSION_HIERARCHY = [p.lower() for p in settings.PERMISSION_HIERARCHY]

# limit members for API inclusion
__all__ = ("CmdBoot", "CmdBan", "CmdUnban", "CmdDelPlayer",
           "CmdEmit", "CmdNewPassword", "CmdPerm", "CmdWall", "CmdGemit",
           "CmdHome")

class CmdHome(MuxCommand):
    """
    home

    Usage:
      home

    Teleports you to your home location.
    """

    key = "home"
    locks = "cmd:all()"
    help_category = "Travel"

    def func(self):
        "Implement the command"
        caller = self.caller
        home = caller.home
        room = caller.location
        cscript = room.ndb.combat_manager
        guards = caller.db.assigned_guards or []
        if not caller.check_permstring("builders"):
            if cscript:
                caller.msg("You cannot use home to leave a room where a combat is occurring.")
                return
            if 'private' in room.tags.all():
                caller.msg("You cannot use home to leave a private room.")
                return
        if not home:
            caller.msg("You have no home!")
        elif home == caller.location:
            caller.msg("You are already home!")
        else:
            caller.move_to(home)
            caller.msg("There's no place like home ...")
            for guard in guards:
                guard.summon()

class CmdGemit(MuxPlayerCommand):
    """
    @gemit

    Usage:
      @gemit/norecord <message>
      @gemit/startepisode <name>=<message>
      @gemit <message>

    Announces a message to all connected players.
    Unlike @wall, this command will only send the text,
    without "soandso shouts:" attached.
    """
    key = "@gemit"
    locks = "cmd:perm(gemit) or perm(Wizards)"
    help_category = "Admin"

    def func(self):
        "Implements command"
        caller = self.caller
        if not self.args:
            self.caller.msg("Usage: @gemit <message>")
            return
        if "norecord" in self.switches:
            self.msg("Announcing to all connected players ...")
            SESSIONS.announce_all(self.args)
            return
        from src.web.character.models import Story,Episode,Chapter,StoryEmit
        # current story
        story = Story.objects.latest('start_date')
        chapter = story.current_chapter
        episode = None
        msg = self.lhs
        if "startepisode" in self.switches:
            if not self.lhs:
                caller.msg("You must give a name for the new episode.")
                return
            if not self.rhs:
                caller.msg("You must give a message for the emit.")
                return
            from datetime import datetime
            date = datetime.now()
            episode = Episode.objects.create(name=self.lhs, date=date, chapter=chapter)
            msg = self.rhs
        elif "noepisode" not in self.switches:
            episode = Episode.objects.latest('date')
        StoryEmit.objects.create(episode=episode, chapter=chapter, text=msg,
                                 sender=caller.dbobj)
        self.msg("Announcing to all connected players ...")
        SESSIONS.announce_all(msg)
        # get board and post
        BOARDS = "game.gamesrc.objects.bulletin_board.bboard.BBoard"
        bboard = ObjectDB.objects.get(db_typeclass_path=BOARDS,
                                      db_key="story updates")
        subject = "Story Update"
        if episode:
            subject = "Episode: %s" % episode.name
        elif chapter:
            subject = "Chapter: %s" % chapter.name
        bboard.bb_post(poster_obj=caller, msg=msg, subject=subject, poster_name="Story")
        
            


class CmdWall(MuxCommand):
    """
    @wall

    Usage:
      @wall <message>

    Shouts a message to all connected players.
    This command should be used to send OOC broadcasts,
    while @gemit is used for IC global messages.
    """
    key = "@wall"
    locks = "cmd:perm(wall) or perm(Wizards)"
    help_category = "Admin"

    def func(self):
        "Implements command"
        if not self.args:
            self.caller.msg("Usage: @wall <message>")
            return
        message = "%s shouts \"%s\"" % (self.caller.name, self.args)
        self.msg("Announcing to all connected players ...")
        SESSIONS.announce_all(message)

class CmdResurrect(MuxCommand):
    """
    @resurrect

    Usage:
        @resurrect <character>

    Resurrects a dead character. It will target either a character
    in your own location, or with an * before the name, it will
    resurrect the primary character of a player of the given name.
    """
    key = "@resurrect"
    locks = "cmd:perm(resurrect) or perm(Wizards)"
    help_category = "Building"

    def func(self):
        "Implements command"
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("Rez who?")
            return
        obj = caller.search(args, location=caller.location)
        if args.startswith("*"):
            # We're looking for a player
            args = args[1:]
            obj = caller.player.search(args)
            # found a player, get the character
            if obj:
                obj = obj.db.char_ob
        if not obj or not hasattr(obj, 'resurrect'):
            caller.msg("No character found by that name.")
            return
        obj.resurrect()
        caller.msg("%s resurrected." % obj.key)


class CmdKill(MuxCommand):
    """
    @kill

    Usage:
        @kill <character>

    Kills a character. It will target either a character
    in your own location, or with an * before the name, it will
    resurrect the primary character of a player of the given name.
    """
    key = "@kill"
    locks = "cmd:perm(kill) or perm(Wizards)"
    help_category = "Building"

    def func(self):
        "Implements command"
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("Kill who?")
            return
        obj = caller.search(args, location=caller.location)
        if args.startswith("*"):
            # We're looking for a player
            args = args[1:]
            obj = caller.player.search(args)
            # found a player, get the character
            if obj:
                obj = obj.db.char_ob
        if not obj:
            caller.msg("No character found by that name.")
        obj.death_process()
        caller.msg("%s has been murdered." % obj.key)

class CmdForce(MuxCommand):
    """
    @force

    Usage:
      @force <character>=<command>
      @force/char <player>=command

    Forces a given character to execute a command. Without the char switch,
    this will search for character objects in your room, which may be npcs
    that have no player object. With the /char switch, this searches for
    the character of a given player name, who may be anywhere.
    """
    key = "@force"
    locks = "cmd:perm(force) or perm(Immortals)"
    help_category = "Admin"

    def func(self):
        "Implements command"
        caller = self.caller
        if not self.lhs or not self.rhs:
            self.caller.msg("Usage: @force <character>=<command>")
            return
        if "char" in self.switches:
            player = self.caller.player.search(self.lhs)
            if not player:
                return
            char = player.db.char_ob
        else:
            char = caller.search(self.lhs)
        if not char:
            caller.msg("No character found.")
            return
        if not char.access(caller, 'edit'):
            caller.msg("You don't have 'edit' permission for %s." % char)
            return
        char.execute_cmd(self.rhs)
        caller.msg("Forced %s to execute the command '%s'." % (char, self.rhs))
        if char.db.player_ob:
            inform_staff("%s forced %s to execute the command '%s'." % (caller, char, self.rhs))


class CmdRestore(MuxPlayerCommand):
    """
    @restore

    Usage:
      @restore
      @restore/player <playername>
      @restore <object ID>

    Undeletes an object or player
    """
    key = "@restore"
    locks = "cmd:perm(restore) or perm(Immortals)"
    help_category = "Admin"

    def func(self):
        "Implements command"
        caller = self.caller
        if not self.args:
            dplayers = [str(ob) for ob in PlayerDB.objects.filter(is_active=False) if not ob.is_guest()]
            dobjs = ["%s (ID:%s)" % (ob.key, ob.id) for ob in ObjectDB.objects.filter(db_tags__db_key__iexact="deleted")]
            caller.msg("Deleted players: %s" % ", ".join(dplayers))
            caller.msg("Deleted objects: %s" % ", ".join(dobjs))
            return
        if "player" in self.switches:
            try:
                targ = PlayerDB.objects.get(username__iexact=self.args)
                targ.undelete()
                caller.msg("%s restored." % targ)
                inform_staff("%s restored player: %s" % (caller, targ))
                return
            except PlayerDB.DoesNotExist:
                caller.msg("No player found for %s." % self.args)
                return
        try:
            targ = ObjectDB.objects.get(id=self.args)
            if "deleted" not in str(targ.tags).split(","):
                caller.msg("%s does not appear to be deleted." % targ)
                return
            targ.tags.remove("deleted")
            char = caller.db.char_ob
            inform_staff("%s restored item: %s" % (caller, targ))
            caller.msg("Restored %s." % targ)
            if char:
                if char.location:
                    targ.move_to(char.location)
                    caller.msg("%s moved to your location" % targ)
                    return
                targ.move_to(char)
                caller.msg("%s moved to your character object." % targ)
                return
            caller.msg("You do not have a character object to move %s to. Use @tel to return it to the game." % targ)
            return
        except ObjectDB.DoesNotExist:
            caller.msg("No object found for ID %s." % self.args)
            return

class CmdPurgeJunk(MuxPlayerCommand):
    """
    @purgejunk

    Usage:
      @purgejunk
      @purgejunk <object ID>

    Permanently removes a deleted item from the database
    """
    key = "@purgejunk"
    locks = "cmd:perm(restore) or perm(Immortals)"
    help_category = "Admin"

    def func(self):
        "Implements command"
        caller = self.caller
        if not self.args:
            dplayers = [str(ob) for ob in PlayerDB.objects.filter(is_active=False) if not ob.is_guest()]
            dobjs = ["%s (ID:%s)" % (ob.key, ob.id) for ob in ObjectDB.objects.filter(db_tags__db_key__iexact="deleted")]
            caller.msg("Deleted players: %s" % ", ".join(dplayers))
            caller.msg("Deleted objects: %s" % ", ".join(dobjs))
            return
        try:
            targ = ObjectDB.objects.get(id=self.args)
            if "deleted" not in str(targ.tags).split(","):
                caller.msg("%s does not appear to be deleted." % targ)
                return
            if (targ.typeclass_path == settings.BASE_CHARACTER_TYPECLASS or
                targ.typeclass_path == settings.BASE_ROOM_TYPECLASS):
                caller.msg("Rooms or characters cannot be deleted with this command. Must be removed via shell script for safety.")
                return
            targ.delete(true_delete=True)
            inform_staff("%s purged item ID %s from the database" % (caller, self.args))
            return
        except ObjectDB.DoesNotExist:
            caller.msg("No object found for ID %s." % self.args)
            return


class CmdSendVision(MuxPlayerCommand):
    """
    @sendvision

    Usage:
        @sendvision
        @sendvision <character>
        @sendvision <character>=<What they see>

    With no args, list characters who have have the visions tag, or display
    all visions for a given character. Otherwise, send a vision with the
    appropriate text to a given character.
    """
    key = "@sendvision"
    aliases = ["@sendvisions"]
    locks = "cmd:perm(sendvision) or perm(Wizards)"
    help_category = "Building"

    def func(self):
        "Implements command"
        args = self.args
        caller = self.caller
        if not args:
            visionaries = ObjectDB.objects.filter(db_tags__db_key__iexact="visions")
            table = prettytable.PrettyTable(["{wName{n", "{wNumber of Visions{n"])
            for char in visionaries:
                table.add_row([char.key, len(char.messages.visions)])
            caller.msg("{wCharacters who have the 'visions' @tag:{n")
            caller.msg(str(table))
            return
        targ = caller.search(self.lhs)
        if not targ:
            return
        char = targ.db.char_ob
        if not char:
            caller.msg("No valid character.")
            return
        visions = char.messages.visions
        if not self.rhs: 
            table = evtable.EvTable("{wVisions{n", width=78)
            for vision in visions:
                table.add_row(char.messages.disp_entry(vision))
            caller.msg(str(table))
            return
        char.messages.add_vision(self.rhs, caller)
        caller.msg("Vision added to %s: %s" % (char, self.rhs))
        msg = "{rYou have experienced a vision!{n\n%s" % self.rhs
        targ.send_or_queue_msg(msg)
        targ.inform("Your character has experienced a vision. Use @sheet/visions to view it.")
        return

class CmdAskStaff(MuxPlayerCommand):
    """
    @askstaff

    Usage:
        @askstaff <message>

    Submits a question to staff channels. Unlike +request, there's no
    record of this, so it's just a heads-up to any currently active
    staff who are paying attention. If you want to submit a question
    that will get a response later, use +request.
    """
    key = "@askstaff"

    locks = "cmd:all()"
    help_category = "Admin"

    def func(self):
        "Implements command"
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("You must ask a question.")
            return
        caller.msg("Asking: %s" % args)
        inform_staff("{c%s {wasking a question:{n %s" % (caller, args))

class CmdListStaff(MuxPlayerCommand):
    """
    +staff

    Usage:
        +staff

    Lists staff that are currently online.
    """
    key = "+staff"

    locks = "cmd:all()"
    help_category = "Admin"

    def func(self):
        "Implements command"
        args = self.args
        caller = self.caller
        staff = PlayerDB.objects.filter(db_is_connected=True, is_staff=True)
        caller.msg("{wOnline staff:{n %s" % ", ".join(ob.key.capitalize() for ob in staff))
            
            


        
        
