"""
Consumable object.
"""

from typeclasses.objects import Object


class Consumable(Object):
    """
    Consumable object. We will use the quality level in order to determine
    the number of uses we have remaining.
    """

    def at_object_creation(self):
        """
        Run at Usable creation.
        """
        self.desc = "A consumable object"

    def consume(self):
        """
        Use a charge if it has any remaining. Return True if successful
        :return:
        """
        if not self.charges:
            return False
        self.charges -= 1
        return True

    @property
    def charges(self):
        if self.db.quality_level is None:
            self.db.quality_level = 0
        return self.db.quality_level

    @charges.setter
    def charges(self, val):
        self.db.quality_level = val

    def get_quality_appearance(self):
        return "\nIt has %s charges remaining." % self.charges
