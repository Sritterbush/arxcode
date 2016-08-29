"""

CmdSet for Guests - will be a limited version of player
commandset, with unique commands for the tutorial.
"""

from evennia.commands.cmdset import CmdSet
from evennia.commands.default import help, comms, admin, system
from evennia.commands.default import building, player
import sys, traceback


class GuestCmdSet(CmdSet):
    """
    Implements the guest command set.
    """

    key = "DefaultGuest"
    # priority = -5

    def at_cmdset_creation(self):
        "Populates the cmdset"

        # Player-specific commands
        try:
            self.add(player.CmdOOCLook())
            self.add(player.CmdWho())
            self.add(player.CmdEncoding())
            self.add(player.CmdQuit())
            self.add(player.CmdColorTest())       
            # Help command
            self.add(help.CmdHelp())
            # Comm commands
            self.add(comms.CmdAddCom())
            self.add(comms.CmdDelCom())
            self.add(comms.CmdAllCom())
            self.add(comms.CmdChannels())
            self.add(comms.CmdCWho())
            from commands import general
            self.add(general.CmdPage())
            from commands import roster
            self.add(roster.CmdRosterList())
            self.add(roster.CmdAdminRoster())
            self.add(roster.CmdSheet())
            self.add(roster.CmdRelationship())
            from commands import guest
            self.add(guest.CmdGuestLook())
            self.add(guest.CmdGuestCharCreate())
            self.add(guest.CmdGuestPrompt())
            self.add(guest.CmdGuestAddInput())
            from world.dominion import commands as domcommands
            self.add(domcommands.CmdFamily())
            from commands import bboards
            self.add(bboards.CmdBBReadOrPost())
            self.add(bboards.CmdBBSub())
            from commands import staff_commands
            self.add(staff_commands.CmdAskStaff())
            self.add(staff_commands.CmdListStaff())
            from commands import social
            self.add(social.CmdWhere())
            self.add(social.CmdFinger())
        except Exception as err:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_tb(exc_traceback, limit=5, file=sys.stdout)
            print("Error encountered in loading Guest commandset: %s" % err)


