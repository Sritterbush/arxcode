"""
This cmdset is to try to define the state of being dead.
It will replace the mobile command set, and then specific
other commands.

This is for a character who is dead. Not undead, such as
a sexy vampire or a shambling zombie. Not braindead, such
as someone who approaches RP as a competition. No, this is
for dead-dead. Stone dead. Super dead. The deadest.

Not that they will necessarily STAY that way. But while
this is on them, they are dead.

"""

from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand



class DeathCmdSet(CmdSet):
    "CmdSet for players who are currently dead."    
    key = "DeathCmdSet"
    key_mergetype = {"DefaultCharacter" :"Replace"}
    priority = 20
    duplicates = False
    no_exits = True
    no_objs = True
    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        from game.gamesrc.commands.cmdsets.standard import OOCCmdSet
        self.add(OOCCmdSet)
        from game.gamesrc.commands.cmdsets.standard import StateIndependentCmdSet
        self.add(StateIndependentCmdSet)
        from game.gamesrc.commands.cmdsets.standard import StaffCmdSet
        self.add(StaffCmdSet)
        self.add(CmdGet())
        self.add(CmdDrop())
        self.add(CmdGive())
        self.add(CmdSay())
        self.add(CmdWhisper())
        self.add(CmdFollow())
        self.add(CmdDitch())
        self.add(CmdShout())
        self.add(CmdMoveOverride())
        

class DeathCommand(MuxCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "dead"
    locks = "cmd:all()"
    def func(self):
        "Let the player know they can't do anything."
        self.caller.msg("You are dead. You cannot do that.")
        return

class CmdMoveOverride(DeathCommand):
    key = "movement"
    aliases = ["n", "s", "w", "e"]

class CmdGet(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "get"

class CmdDrop(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """    
    key = "drop"

class CmdGive(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """    
    key = "give"

class CmdSay(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """   
    key = "say"

class CmdWhisper(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "whisper"

class CmdFollow(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "follow"

class CmdDitch(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "ditch"

class CmdShout(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """
    key = "shout"
 
