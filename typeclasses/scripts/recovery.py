"""
Script for characters healing.
"""

from django.conf import settings
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
        self.interval = 1800
        self.persistent = True
        self.start_delay = True

    def at_repeat(self):
        """
        Called every 30 minutes until we're all better.
        """
        if not self.obj:
            self.stop()
            self.dbobj.delete()
            return
        if self.obj.db.damage and self.obj.db.damage > 0:
            self.obj.recovery_test()
        else:
            self.stop()
            self.dbobj.delete()

    def is_valid(self):
        try:
            if self.obj and self.obj.db.damage > 0:
                return True
        except Exception:
            return False
        return False

    



   
