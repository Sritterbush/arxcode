"""
Container objects. Bags, chests, etc.


"""
from typeclasses.objects import Object as DefaultObject
from evennia.commands.default.muxcommand import MuxCommand
from evennia.commands import command, cmdset


class Container(DefaultObject):
    """
    Containers - bags, chests, etc. Players can have keys and can
    lock/unlock containers.
    """
    def create_container_cmdset(self, contdbobj):
        """
        Helper function for creating an container command set + command.

        The command of this cmdset has the same name as the container object
        and allows the container to react when the player enter the container's name,
        triggering the movement between rooms.

        Note that containerdbobj is an ObjectDB instance. This is necessary
        for handling reloads and avoid tracebacks if this is called while
        the typeclass system is rebooting.
        """
        containerkey = contdbobj.db_key.strip().lower()
        containeraliases = list(contdbobj.aliases.all())

        class CmdLockContainer(command.Command):
            def func(self):
                if self.obj.db.locked:
                    self.caller.msg("It is already locked.")
                    return
                if not self.obj.access(self.caller, 'usekey'):
                    self.caller.msg("You don't have a key to this container.")
                    return
                self.obj.db.locked = True
                self.caller.msg("You lock %s." % self.obj.name)
 
        class CmdUnlockContainer(command.Command):
            def func(self):
                if not self.obj.db.locked:
                    self.caller.msg("It is already unlocked.")
                    return
                if not self.obj.access(self.caller, 'usekey'):
                    self.caller.msg("You don't have a key to this container.")
                    return
                self.obj.db.locked = False
                self.caller.msg("You unlock %s." % self.obj.name)

        class CmdChestKey(MuxCommand):
            """
            Grants a key to this chest to a player

            Usage:
                @chestkey <player>
            """
            key = "@chestkey"
            locks = "cmd:all()"
            help_category = "containers"
            def func(self):
                caller = self.caller
                chestkeys = caller.db.chestkeylist or []
                if (caller != self.obj.db.crafted_by and not caller.check_permstring("builders")
                    and self.obj not in chestkeys):
                    caller.msg("You cannot grant keys to %s." % self)
                    return
                if not self.args:
                    caller.msg("Grant a key to whom?")
                    return
                player = caller.player.search(self.args)
                if not player:
                    return
                char = player.db.char_ob
                if not char:
                    return
                if not self.switches:
                    if not self.obj.grantkey(char):
                        caller.msg("They already have a key.")
                        return
                    caller.msg("%s has been granted a key to %s." % (char, self.obj))
                    return
                if "rmkey" in self.switches:
                    if not self.obj.rmkey(char):
                        caller.msg("They don't have a key.")
                        return
                    caller.msg("%s has had their key to %s removed." % (char, self.obj))
                    return
                caller.msg("Invalid switch.")
                return

        lockaliases = ["lock %s" % alias for alias in containeraliases]
        lockcmd = CmdLockContainer(key="lock %s" % containerkey, aliases=lockaliases, auto_help=False, obj=contdbobj)
        unlockaliases = ["unlock %s" % alias for alias in containeraliases]
        unlockcmd = CmdUnlockContainer(key="unlock %s" % containerkey, aliases=unlockaliases, auto_help=False, obj=contdbobj)
        # create a cmdset
        container_cmdset = cmdset.CmdSet(None)
        container_cmdset.key = '_containerset'
        container_cmdset.priority = 9
        container_cmdset.duplicates = True
        # add command to cmdset
        container_cmdset.add(lockcmd)
        container_cmdset.add(unlockcmd)
        container_cmdset.add(CmdChestKey(obj=contdbobj))
        return container_cmdset
    
    def at_cmdset_get(self):
        """
        Called when the cmdset is requested from this object, just before the
        cmdset is actually extracted. If no container-cmdset is cached, create
        it now.
        """
        if self.ndb.container_reset or not self.cmdset.has_cmdset("_containerset", must_be_default=True):
            # we are resetting, or no container-cmdset was set. Create one dynamically.
            self.cmdset.add_default(self.create_container_cmdset(self.dbobj), permanent=False)
            self.ndb.container_reset = False

    def at_object_creation(self):
        "Called once, when object is first created (after basetype_setup)."
        self.locks.add("usekey: chestkey(%s)" % self.id)
        self.db.container = True
        self.db.max_volume = 1

    def grantkey(self, char):
        "Grants a key to this chest for char."
        chestkeys = char.db.chestkeylist or []
        if self in chestkeys:
            return False
        chestkeys.append(self)
        char.db.chestkeylist = chestkeys
        return True

    def rmkey(self, char):
        "Removes a key to this chest from char."
        chestkeys = char.db.chestkeylist or []
        if self not in chestkeys:
            return
        chestkeys.remove(self)
        char.db.chestkeylist = chestkeys
        return True

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        show_contents = not self.db.locked
        string = DefaultObject.return_appearance(self, pobject, detailed, format_desc,
                                                 show_contents)
        if self.db.locked:
            string += "\nIt is locked."
        else:
            string += "\nIt is unlocked."
        return string
    
