"""
Wearable objects. Clothing and armor. No distinction between
clothing and armor except armor will have an armor value
defined as an attribute.

is_wearable boolean is the check to see if we're a wearable
object. worn_by returns the object wearing us. currently_worn
is a boolean saying our worn state - True if being worn,
False if not worn.
"""

from django.conf import settings
from typeclasses.objects import Object
from time import time



class Wearable(Object):
    """
    Class for wearable objects
    """          
    def at_object_creation(self):
        """
        Run at Wearable creation.
        """
        self.db.is_wearable = True
        self.db.worn_by = None
        self.db.currently_worn = False
        self.db.desc = "A piece of clothing or armor."
        self.db.armor_class = 0
        self.db.slot = None
        self.db.slot_limit = 1
        self.at_init()

    def remove(self, wearer):
        """
        Takes off the armor
        """
        if not self.at_pre_remove(wearer):
            return False
        self.db.worn_by = None
        self.db.currently_worn = False
        # TODO it could be worth moving self.at_post_remove to this point rather than have separate calls
        # outside the function. Be sure to search for all instances of the usage of at_post_remove.
        return True

    def wear(self, wearer):
        """
        Puts item on the wearer
        """
        #Assume any fail messages are written in at_pre_wear
        if not self.at_pre_wear(wearer):
            return False
        self.db.worn_by = wearer
        self.db.currently_worn = True
        if self.location != wearer:
            self.location = wearer
        self.db.worn_time = time()
        self.calc_armor()
        return True

    def at_after_move(self, source_location):
        "If new location is not our wearer, remove."
        location = self.location
        wearer = self.db.worn_by
        if not location:
            self.remove(wearer)
            return
        if self.db.currently_worn and wearer and location != wearer:
            self.remove(wearer)

    def at_pre_wear(self, wearer):
        "Hook called before wearing for any checks."
        return True

    def at_post_wear(self, wearer):
        "Hook called after wearing for any checks."
        return True

    def at_pre_remove(self, wearer):
        "Hook called before removing."
        return True

    def at_post_remove(self, wearer):
        "Hook called after removing."
        return True
    
    def calc_armor(self):
        """
        If we have crafted armor, return the value from the recipe and
        quality.
        """
        quality = self.db.quality_level or 0
        recipe_id = self.db.recipe
        penalty = 0
        from world.dominion.models import CraftingRecipe
        try:
            recipe = CraftingRecipe.objects.get(id=recipe_id)
        except CraftingRecipe.DoesNotExist:
            return (self.db.armor_class or 0, self.db.penalty or 0)
        base = int(recipe.resultsdict.get("baseval", 0))
        scaling = float(recipe.resultsdict.get("scaling", 0.2))
        penalty = float(recipe.resultsdict.get("penalty", 0.0))
        if not base and not scaling:
            self.ndb.cached_armor_value = 0
            self.ndb.cached_penalty_value = penalty
            return (self.ndb.cached_armor_value, self.ndb.cached_penalty_value)
        try:
            armor = base + int(round(scaling * quality))
        except (TypeError, ValueError):
            armor = 0
        self.ndb.purported_value = armor
        if self.db.forgery_penalty:
            try:
                armor /= self.db.forgery_penalty
            except (ValueError, TypeError):
                armor = 0
        self.ndb.cached_armor_value = armor
        self.ndb.cached_penalty_value = penalty
        return (armor, penalty)
    
    def _get_armor(self):
        # if we have no recipe or we are set to ignore it, use armor_class
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.armor_class
        if self.ndb.cached_armor_value != None:
            return self.ndb.cached_armor_value
        return self.calc_armor()[0]
    
    def _set_armor(self, value):
        """
        Manually sets the value of our armor, ignoring any crafting recipe we have.
        """
        self.db.armor_class = value
        self.db.ignore_crafted = True
        self.ndb.cached_armor_value = value

    armor = property(_get_armor, _set_armor)

    def _get_penalty(self):
        # if we have no recipe or we are set to ignore it, use penalty
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.penalty or 0
        if self.ndb.cached_penalty_value != None:
            return self.ndb.cached_penalty_value
        return self.calc_armor()[1]
    penalty = property(_get_penalty)

from typeclasses.containers.container import Container

class WearableContainer(Wearable, Container):
    def at_object_creation(self):
        Wearable.at_object_creation(self)
        Container.at_object_creation(self)
    
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

    def _get_armor(self):
        return 0

    def _calc_armor(self):
        return
    armor = property(_get_armor)


    
