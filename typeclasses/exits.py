"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""
from evennia import DefaultExit
from typeclasses.mixins import ObjectMixins
from evennia.commands import command, cmdset

class Exit(ObjectMixins, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property. It also does work in the
    following methods:

     basetype_setup() - sets default exit locks (to change, use `at_object_creation` instead).
     at_cmdset_get(**kwargs) - this is called when the cmdset is accessed and should
                              rebuild the Exit cmdset along with a command matching the name
                              of the Exit object. Conventionally, a kwarg `force_init`
                              should force a rebuild of the cmdset, this is triggered
                              by the `@alias` command when aliases are changed.
     at_failed_traverse() - gives a default error message ("You cannot
                            go there") if exit traversal fails and an
                            attribute `err_traverse` is not defined.

    Relevant hooks to overload (compared to other types of Objects):
        at_traverse(traveller, target_loc) - called to do the actual traversal and calling of the other hooks.
                                            If overloading this, consider using super() to use the default
                                            movement implementation (and hook-calling).
        at_after_traverse(traveller, source_loc) - called by at_traverse just after traversing.
        at_failed_traverse(traveller) - called by at_traverse if traversal failed for some reason. Will
                                        not be called if the attribute `err_traverse` is
                                        defined, in which case that will simply be echoed.
    """
    def create_exit_cmdset(self, exidbobj):
        """
        Helper function for creating an exit command set + command.

        The command of this cmdset has the same name as the Exit object
        and allows the exit to react when the player enter the exit's name,
        triggering the movement between rooms.

        Note that exitdbobj is an ObjectDB instance. This is necessary
        for handling reloads and avoid tracebacks if this is called while
        the typeclass system is rebooting.
        """
        exitkey = exidbobj.db_key.strip().lower()
        exitaliases = list(exidbobj.aliases.all())
        class ExitCommand(command.Command):
            """
            This is a command that simply cause the caller
            to traverse the object it is attached to.
            """
            obj = None

            def func(self):
                "Default exit traverse if no syscommand is defined."

                if self.obj.access(self.caller, 'traverse'):
                    # we may traverse the exit.
                    self.obj.at_traverse(self.caller, self.obj.destination)
                elif self.caller.db.bypass_locked_doors:
                    msg = self.caller.db.bypass_locked_doors or "You ignore the locked door."
                    self.obj.at_traverse(self.caller, self.obj.destination)
                else:
                    # exit is locked
                    if self.obj.db.err_traverse:
                        # if exit has a better error message, let's use it.
                        self.caller.msg(self.obj.db.err_traverse)
                    else:
                        # No shorthand error message. Call hook.
                        self.obj.at_failed_traverse(self.caller)

        class LockExit(command.Command):
            def func(self):
                if self.obj.db.locked:
                    self.caller.msg("It is already locked.")
                    return
                if not self.obj.access(self.caller, 'usekey'):
                    self.caller.msg("You don't have a key to this exit.")
                    return
                self.obj.lock()
 
        class UnlockExit(command.Command):
            def func(self):
                if not self.obj.db.locked:
                    self.caller.msg("It is already unlocked.")
                    return
                if not self.obj.access(self.caller, 'usekey'):
                    self.caller.msg("You don't have a key to this exit.")
                    return
                self.obj.unlock()

        class PassExit(command.Command):
            def func(self):
                if self.obj.db.locked and not self.obj.access(self.caller, 'usekey'):
                    self.caller.msg("You don't have a key to this exit.")
                    return
                self.obj.at_traverse(self.caller, self.obj.destination)
 

        # create an exit command. We give the properties here,
        # to always trigger metaclass preparations
        exitcmd = ExitCommand(key=exitkey,
                          aliases=exitaliases,
                          locks=str(exidbobj.locks),
                          auto_help=False,
                          destination=exidbobj.db_destination,
                          arg_regex=r"$",
                          is_exit=True,
                          obj=exidbobj)
        lockaliases = ["lock %s" % alias for alias in exitaliases]
        lockcmd = LockExit(key="lock %s" % exitkey, aliases=lockaliases, auto_help=False, obj=exidbobj)
        unlockaliases = ["unlock %s" % alias for alias in exitaliases]
        unlockcmd = UnlockExit(key="unlock %s" % exitkey, aliases=unlockaliases, auto_help=False, obj=exidbobj)
        passaliases = ["pass %s" % alias for alias in exitaliases]
        passcmd = PassExit(key="pass %s" % exitkey, aliases = passaliases, is_exit=True, auto_help=False, obj=exidbobj)
        # create a cmdset
        exit_cmdset = cmdset.CmdSet(None)
        exit_cmdset.key = '_exitset'
        exit_cmdset.priority = 5
        exit_cmdset.duplicates = True
        # add command to cmdset
        exit_cmdset.add(exitcmd)
        exit_cmdset.add(lockcmd)
        exit_cmdset.add(unlockcmd)
        exit_cmdset.add(passcmd)
        return exit_cmdset

    # this and other hooks are what usually can be modified safely.
    def lock(self):
        self.db.locked = True
        self.locks.add("traverse: perm(builders)")
        self.location.msg_contents("%s is now locked." % self.key)
        if self.destination.db.locked == False:
            entrances = [ob for ob in self.destination.db.entrances if ob.db.locked == False]
            if not entrances:
                self.destination.db.locked = True
        

    def unlock(self):
        self.db.locked = False
        self.locks.add("traverse: all()")
        self.location.msg_contents("%s is now unlocked." % self.key)
        self.destination.db.locked = False


    
    def at_init(self):
        """
        This is always called whenever this object is initiated --
        that is, whenever it its typeclass is cached from memory. This
        happens on-demand first time the object is used or activated
        in some way after being created but also after each server
        restart or reload.
        """
        self.is_room = False
        self.is_exit = True
        self.is_character = False

    def at_traverse(self, traversing_object, target_location, key_message=True, special_entrance=None):
        """
        This implements the actual traversal. The traverse lock has already been
        checked (in the Exit command) at this point.
        """
        source_location = traversing_object.location
        if traversing_object.move_to(target_location):
            # if the door was locked, send a message about it unless we were following
            if key_message and self.db.locked:
                msg = special_entrance or self.db.success_traverse or "You unlock the locked door, then close and lock it behind you."
                traversing_object.msg(msg)
            self.at_after_traverse(traversing_object, source_location)
            # move followers
            if traversing_object and traversing_object.ndb.followers:
                for follower in traversing_object.ndb.followers:
                    # only move followers who were in same square
                    if follower.location == source_location:
                        fname = follower.ndb.following
                        if fname:
                            follower.msg("You follow %s." % fname.name)
                        # followers won't see the message about the door being locked
                        self.at_traverse(follower, self.destination, key_message=False)
        else:
            if self.db.err_traverse:
                # if exit has a better error message, let's use it.
                self.caller.msg(self.db.err_traverse)
            else:
                # No shorthand error message. Call hook.
                self.at_failed_traverse(traversing_object)

    def at_failed_traverse(self, traversing_object):
        """
        This is called if an object fails to traverse this object for some
        reason. It will not be called if the attribute "err_traverse" is
        defined, that attribute will then be echoed back instead as a
        convenient shortcut.

        (See also hooks at_before_traverse and at_after_traverse).
        """
        traversing_object.msg("That way is locked.")
        
        
    def msg(self, text=None, from_obj=None, radius=0, echo_list=None, **kwargs):
        """
        This allows the exit to pass along a message to its destination.dbref
        The echo list must be called with 'echo_list=[]' for each new call,
        since it will be saved and passed on to all calls of msg in exits
        until it is initialized again. This is intentional to prevent longer
        radius calls from overlapping rooms with one another, which is entirely
        possible even with a radius of 3. Higher radius calls are discouraged
        due to the amount of traversals causing significant lag and possibly
        running out of memory.
        """
        echo_list = echo_list or []
        if self.location not in echo_list:
            echo_list.append(self.location)
        if radius and self.destination and self.destination not in echo_list:
            # we still have radius left to burn, and our destination for this
            # exit has not seen the message. So we send it along with a reduced
            # radius and this room in the echo list, so we don't get it back.
            radius -= 1
            self.destination.msg_contents(text, exclude=None, from_obj=from_obj, radius=radius, echo_list=echo_list, **kwargs)



