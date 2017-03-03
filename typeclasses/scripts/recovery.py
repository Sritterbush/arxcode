"""
Script for characters healing.
"""

from .scripts import Script


class Recovery(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Recovery"
        self.desc = "Healing over time"
        self.interval = 28800
        self.persistent = True
        self.start_delay = True

    def at_repeat(self):
        """
        Called every 8 hours until we're all better.
        """
        def stop_it():
            self.stop()
            self.dbobj.delete()
        if not self.obj:
            stop_it()
            return
        # RIP in pepperinos
        try:
            if self.obj.dead:
                stop_it()
                return
        except AttributeError:
            stop_it()
            return
        if self.obj.db.damage and self.obj.db.damage > 0:
            self.obj.recovery_test(diff_mod=15)
        else:
            stop_it()

    def is_valid(self):
        try:
            if self.obj and self.obj.db.damage > 0:
                return True
        except (AttributeError, TypeError, ValueError):
            return False
        return False

    



   
