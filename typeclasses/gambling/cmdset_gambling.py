"""
This defines the cmdset for the red_button. Here we have defined
the commands and the cmdset in the same module, but if you
have many different commands to merge it is often better
to define the cmdset separately, picking and choosing from
among the available commands as to what should be included in the
cmdset - this way you can often re-use the commands too.
"""

import random
from django.conf import settings
from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand



#------------------------------------------------------------
# Commands defined for wearable
#------------------------------------------------------------

class CmdRoll(MuxCommand):
    """
    rolls dice

    Usage:
        roll <number of dice>

    Rolls the dice.
    """
    key = "roll"
    locks = "cmd:all()"
    help_category = "Social"
    def func(self):
        "Implements command"
        caller = self.caller
        rolls = []
        for x in range(5):
            roll = random.randint(1, 6)
            rolls.append(str(roll))
        caller.msg("You have rolled: %s" % ", ".join(rolls))
        caller.location.msg_contents("%s has rolled five dice: %s" % (caller.name, ", ".join(rolls)),
                                     exclude=caller)
        return

        

class DiceCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "Dice"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"Dice": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        "Init the cmdset"
        self.add(CmdRoll())

        



  
