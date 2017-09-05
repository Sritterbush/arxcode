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
from commands.command import ArxCommand
import time

# one hour between recovery tests
MIN_TIME = 3600 


class SleepCmdSet(CmdSet):
    """CmdSet for players who are currently sleeping. Lower priority than death cmdset, so it's overriden."""
    key = "SleepCmdSet"
    key_mergetype = {"DefaultCharacter": "Replace"}
    priority = 120
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
        from commands.cmdsets.standard import OOCCmdSet
        self.add(OOCCmdSet)
        from commands.cmdsets.standard import StateIndependentCmdSet
        self.add(StateIndependentCmdSet)
        from commands.cmdsets.standard import StaffCmdSet
        self.add(StaffCmdSet)
        self.add(CmdGet())
        self.add(CmdDrop())
        self.add(CmdGive())
        self.add(CmdSay())
        self.add(CmdWhisper())
        self.add(CmdFollow())
        self.add(CmdDitch())
        self.add(CmdShout())
        self.add(CmdWake())
        self.add(CmdMoveOverride())
        

class SleepCommand(ArxCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "sleep"
    
    locks = "cmd:all()"

    def func(self):
        """Let the player know they can't do anything."""
        self.caller.msg("You can't do that while sleeping. To wake up, use the {wwake{n command.")
        return


class CmdMoveOverride(SleepCommand):
    key = "north"
    aliases = ["n", "s", "w", "e"]


class CmdWake(ArxCommand):
    """
    Attempt to wake up from sleep. Automatic if uninjured.
    """
    key = "wake"
    locks = "cmd:all()"

    def func(self):
        """Try to wake."""
        caller = self.caller
        if not hasattr(caller, 'wake_up'):
            caller.cmdset.delete(SleepCmdSet)
            caller.msg("Deleting SleepCmdSet from non-character object.")
            return
        if not hasattr(caller, 'dmg') or not hasattr(caller, 'max_hp') or caller.dmg <= caller.max_hp:
            caller.wake_up()
            return
        # determine if we're healthy enough to wake up automatically
        if caller.dmg <= caller.max_hp:
            caller.wake_up()
            return
        # we're not, so we need to make a recovery test
        recov = caller.db.last_recovery_test or 0
        time_passed = int(time.time()) - int(recov)
        if time_passed < MIN_TIME:
            caller.msg("It has been too recent since your last recovery test.")
            caller.msg("You must wait %s seconds." % (MIN_TIME - time_passed))
        else:
            caller.recovery_test()
        if caller.dmg <= caller.max_hp:
            caller.wake_up()
            return
        caller.msg("You are still too injured to wake up.")
        return
            

class CmdGet(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "get"


class CmdDrop(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """    
    key = "drop"


class CmdGive(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """    
    key = "give"


class CmdSay(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """   
    key = "say"


class CmdWhisper(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "whisper"


class CmdFollow(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "follow"


class CmdDitch(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "ditch"


class CmdShout(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """
    key = "shout"
