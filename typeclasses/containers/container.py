"""
Container objects. Bags, chests, etc.


"""
from typeclasses.objects import Object as DefaultObject
from evennia.commands.default.muxcommand import MuxCommand
from evennia.commands import cmdset
from typeclasses.mixins import LockMixins


# noinspection PyTypeChecker
class Container(LockMixins, DefaultObject):
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
        # noinspection PyUnresolvedReferences
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
                """
                self.obj  #  type: Container
                :return:
                """
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
        # create a cmdset
        container_cmdset = cmdset.CmdSet(None)
        container_cmdset.key = '_containerset'
        container_cmdset.priority = 9
        container_cmdset.duplicates = True
        # add command to cmdset
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
            self.cmdset.add_default(self.create_container_cmdset(self), permanent=False)
            self.ndb.container_reset = False

    def at_object_creation(self):
        """Called once, when object is first created (after basetype_setup)."""
        self.locks.add("usekey: chestkey(%s)" % self.id)
        self.db.container = True
        self.db.max_volume = 1
        self.at_init()

    def grantkey(self, char):
        """Grants a key to this chest for char."""
        chestkeys = char.db.chestkeylist or []
        if self in chestkeys:
            return False
        chestkeys.append(self)
        char.db.chestkeylist = chestkeys
        return True

    def rmkey(self, char):
        """Removes a key to this chest from char."""
        chestkeys = char.db.chestkeylist or []
        if self not in chestkeys:
            return
        chestkeys.remove(self)
        char.db.chestkeylist = chestkeys
        return True
