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
from evennia import utils
from evennia.commands.default.muxcommand import MuxCommand

# error return function, needed by wear/remove command
AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

#------------------------------------------------------------
# Commands defined for wearable
#------------------------------------------------------------
class CmdWear(MuxCommand):
    """
    Put on an item of clothing or armor.
    
    Usage:
        wear <item>

    Wears the given item on your character. The object must be in
    your inventory to wear it.
    """
    key = "wear"
    locks = "cmd:all()"
    def func(self):
        "Look for object in inventory that matches args to wear"
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Wear what?")
            return
        # Because the wear command by definition looks for items
        # in inventory, call the search function using location = caller
        results = caller.search(args, location=caller, quiet=True)
        # now we send it into the error handler (this will output consistent
        # error messages if there are problems).
        obj = AT_SEARCH_RESULT(caller, args, results, False,
                               nofound_string="You don't carry %s." % args,
                               multimatch_string="You carry more than one %s:" % args)
        if not obj:
            return

        if not obj.db.is_wearable:
            caller.msg("You can't wear that.")
            return
        if obj.db.currently_worn:
            caller.msg("You're already wearing %s." % obj.name)
            return
        if obj.db.slot_limit and obj.db.slot:
            worn = [ob for ob in caller.contents if ob.db.currently_worn and ob.db.slot == obj.db.slot]
            if len(worn) >= obj.db.slot_limit:
                caller.msg("You are wearing too many things on your %s for it to fit." % obj.db.slot)
                return
        if obj.wear(caller):
            caller.msg("You put on %s." % obj.name)
            obj.at_post_wear(caller)
            return
            
        
        pass

class CmdRemove(MuxCommand):
    """
    Remove an item of clothing or armor.
    Usage:
        remove <item>
        
    Takes off the given item from your character. The object must
    be in your inventory and currently worn to remove it.
    """
    key = "remove"
    locks = "cmd:all()"
    def func(self):
        "Look for object in inventory that matches args to wear"
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Remove what?")
            return
        # Because the wear command by definition looks for items
        # in inventory, call the search function using location = caller
        results = caller.search(args, location=caller, quiet=True)

        # now we send it into the error handler (this will output consistent
        # error messages if there are problems).
        obj = AT_SEARCH_RESULT(caller, args, results, False,
                                nofound_string="You don't carry %s." % args,
                                multimatch_string="You carry more than one %s:" % args)
        if not obj:
            return
        if not obj.db.currently_worn or obj.db.worn_by != caller:
            caller.msg("You're not wearing %s." % obj.name)
            return
        if obj.remove(caller):
            caller.msg("You take off %s." % obj.name)
            obj.at_post_remove(caller)
            return
        pass
        

class DefaultCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "WearableDefault"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"WearableDefault": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        "Init the cmdset"
        self.add(CmdWear())
        self.add(CmdRemove())
