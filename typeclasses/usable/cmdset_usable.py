"""
cmdset for usable object
"""
from django.conf import settings
from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand



#------------------------------------------------------------
# Commands defined for consumable object
#------------------------------------------------------------

class CmdUseObject(MuxCommand):
    """
    uses an object

    Usage:
        use <object>
        use <object> [on <target>]

    Uses an object.
    """
    key = "use"
    locks = "cmd:all()"
    help_category = "General"
    alises = ["eat", "drink", "apply"]
    def func(self):
        "Implements command"
        caller = self.caller
        cmdstr = self.cmdstring.lower()
        obj = caller.search(self.args, location=caller)
        if not obj:
            return
        if not obj.db.use_cmds or cmdstr not in obj.db.use_cmds:
            caller.msg("You cannot %s that." % cmdstr)
            return
        if not obj.access(caller, 'use'):
            errmsg = obj.db.err_use or "You are not allowed to use that."
            caller.msg(errmsg)
            return
        obj.on_use(caller, cmdstr)
        return

        

class UsableCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "UseObject"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"UseObject": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        "Init the cmdset"
        self.add(CmdUseObject())

        



  
