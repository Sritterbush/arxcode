"""
Usable object.
"""

from django.conf import settings
from ev import Object
from cmdset_usable import UsableCmdSet


class Usable(Object):
    """
    Usable object.
    """

    def at_object_creation(self):
        """
        Run at Usable creation.
        """
        self.desc = "It looks like someone could {use{n it."
        self.cmdset.add_default(UsableCmdSet, permanent=True)

     
    

    