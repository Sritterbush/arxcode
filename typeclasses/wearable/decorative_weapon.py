"""
wearable weapons
"""
from wieldable import Wieldable
from wearable import Wearable


class DecorativeWieldable(Wieldable, Wearable):
    """
    Class for wieldable objects
    API: Properties are all a series of database attributes,
    for easy customization by builders using @set.
    'ready_phrase' allows a builder to set the string added to character name when
    the object is wielded. ex: @set sword/ready_phrase = "wields a large sword"
    'stealth' determines if the weapon will give an echo to the room when it is
    wielded. Poisons, magic, stealthy daggers, etc, fall into this category.
    """             
    def at_object_creation(self):
        """
        Run at wieldable creation. The defaults are for a generic melee
        weapon.
        """
        Wearable.at_object_creation(self)
        Wieldable.at_object_creation(self)
        self.db.is_wieldable = True

    def remove(self, wielder):
        """
        Takes off the weapon
        """
        return Wearable.remove(self, wielder) and Wieldable.remove(self, wielder)

    def at_after_move(self, source_location, **kwargs):
        "If new location is not our wielder, remove."
        Wearable.at_after_move(self, source_location)
        Wieldable.at_after_move(self, source_location)

    def wield_by(self, wielder):
        self.remove(wielder)
        return Wieldable.wield_by(self, wielder)

    def wear(self, wearer):
        self.remove(wearer)
        return Wearable.wear(self, wearer)

    def _get_armor(self):
        return 0

    # noinspection PyMethodMayBeStatic
    def _calc_armor(self):
        return
    armor = property(_get_armor)
