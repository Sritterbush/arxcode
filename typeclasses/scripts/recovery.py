"""
Script for characters healing.
"""

from .scripts import Script


class Recovery(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Recovery"
        self.desc = "Healing over time"
        self.interval = 28800
        self.persistent = True
        self.start_delay = True
        self.db.highest_heal = 0

    def at_repeat(self):
        """
        Called every 8 hours until we're all better.
        """
        # slowly reduce the impact of the highest heal we've gotten
        self.db.highest_heal = (self.db.highest_heal or 0)/2
        if not self.obj:
            self.stop()
            return
        # RIP in pepperinos
        try:
            if self.obj.dead:
                self.stop()
                return
        except AttributeError:
            self.stop()
            return
        if self.obj.db.damage and self.obj.db.damage > 0:
            self.obj.recovery_test(diff_mod=15 - self.db.highest_heal)
        else:
            self.stop()

    def is_valid(self):
        try:
            if self.obj and self.obj.db.damage > 0:
                return True
        except (AttributeError, TypeError, ValueError):
            return False
        return False
