"""
Command sets

All commands in the game must be grouped in a cmdset.  A given command
can be part of any number of cmdsets and cmdsets can be added/removed
and merged onto entities at runtime.

To create new commands to populate the cmdset, see
`commands/command.py`.

This module wraps the default command sets of Evennia; overloads them
to add/remove commands from the default lineup. You can create your
own cmdsets by inheriting from them or directly from `evennia.CmdSet`.

"""

from evennia import default_cmds
from .cmdsets import standard

class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """
    The `CharacterCmdSet` contains general in-game commands like `look`,
    `get`, etc available on in-game Character objects. It is merged with
    the `PlayerCmdSet` when a Player puppets a Character.
    """
    key = "DefaultCharacter"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        super(CharacterCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
        try:
            self.add(standard.StateIndependentCmdSet)
            self.add(standard.MobileCmdSet)
            self.add(standard.OOCCmdSet)
            self.add(standard.StaffCmdSet)
        except Exception:
            import traceback
            traceback.print_exc()


class PlayerCmdSet(default_cmds.PlayerCmdSet):
    """
    This is the cmdset available to the Player at all times. It is
    combined with the `CharacterCmdSet` when the Player puppets a
    Character. It holds game-account-specific commands, channel
    commands, etc.
    """
    key = "DefaultPlayer"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        super(PlayerCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
        
        try:
            from .commands import general
            self.add(general.CmdPage())
            self.add(general.CmdMail())
            self.add(general.CmdGradient())
            self.add(general.CmdInform())
            self.add(general.CmdGameSettings())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading general cmdset in Player: %s" % err)
        try:
            from .commands import bboards
            self.add(bboards.CmdBBReadOrPost())
            self.add(bboards.CmdBBSub())
            self.add(bboards.CmdBBUnsub())
            self.add(bboards.CmdBBCreate())
            self.add(bboards.CmdBBNew())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading bboards cmdset in Player: %s" % err)
        try:
            from .commands import roster
            self.add(roster.CmdRosterList())
            self.add(roster.CmdAdminRoster())
            self.add(roster.CmdSheet())
            self.add(roster.CmdComment())
            self.add(roster.CmdRelationship())
            self.add(roster.CmdAddSecret())
            self.add(roster.CmdDelComment())
            self.add(roster.CmdAdmRelationship())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading roster cmdset in Player: %s" % err)
        try:
            from .commands import jobs
            self.add(jobs.CmdJob())
            self.add(jobs.CmdRequest())
            self.add(jobs.CmdApp())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading jobs cmdset in Player: %s" % err)
        try:
            from world.dominion import commands as domcommands
            self.add(domcommands.CmdAdmDomain())
            self.add(domcommands.CmdAdmArmy())
            self.add(domcommands.CmdAdmCastle())
            self.add(domcommands.CmdAdmAssets())
            self.add(domcommands.CmdAdmFamily())
            self.add(domcommands.CmdAdmOrganization())
            self.add(domcommands.CmdDomain())
            self.add(domcommands.CmdFamily())
            self.add(domcommands.CmdOrganization())
            self.add(domcommands.CmdAgents())
            self.add(domcommands.CmdPatronage())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading Dominion cmdset in Player: %s" % err)
        try:
            from .commands import social
            self.add(social.CmdFinger())
            self.add(social.CmdWatch())
            self.add(social.CmdCalendar())
            self.add(social.CmdAFK())
            self.add(social.CmdWhere())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading social cmdset in Player: %s" % err)
        try:
            from .commands import staff_commands
            # more recently implemented staff commands
            self.add(staff_commands.CmdRestore())
            self.add(staff_commands.CmdSendVision())
            self.add(staff_commands.CmdAskStaff())
            self.add(staff_commands.CmdListStaff())
            self.add(staff_commands.CmdPurgeJunk())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading staff_commands cmdset in Player: %s" % err)
        try:
            from .cmdsets import starting_gear
            self.add(starting_gear.CmdSetupGear())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading staff_commands cmdset in Player: %s" % err)
        try:
            from web.character import commands as investigation
            self.add(investigation.CmdAdminInvestigations())
            self.add(investigation.CmdListClues())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading investigation cmdset: %s" % err)


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """
    Command set available to the Session before being logged in.  This
    holds commands like creating a new account, logging in, etc.
    """
    key = "DefaultUnloggedin"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        #super(UnloggedinCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
        
        try:
            from evennia.commands.default import unloggedin as default_unloggedin
            self.add(default_unloggedin.CmdUnconnectedConnect())
            self.add(default_unloggedin.CmdUnconnectedQuit())
            self.add(default_unloggedin.CmdUnconnectedLook())
            self.add(default_unloggedin.CmdUnconnectedEncoding())
            self.add(default_unloggedin.CmdUnconnectedScreenreader())
            from .commands import unloggedin
            self.add(unloggedin.CmdGuestConnect())
            self.add(unloggedin.CmdUnconnectedHelp())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading Unlogged cmdset: %s" % err)

class SessionCmdSet(default_cmds.SessionCmdSet):
    """
    This cmdset is made available on Session level once logged in. It
    is empty by default.
    """
    key = "DefaultSession"

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        As and example we just add the empty base `Command` object.
        It prints some info.
        """
        super(SessionCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
