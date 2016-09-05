"""
wieldable objects. Weapons.

is_wieldable boolean is the check to see if we're a wieldable
object. wielded_by returns the object wielding us. currently_wielded
is a boolean saying our wielded state - True if being wielded,
False if not wielded.
"""

from django.conf import settings
from typeclasses.objects import Object
from cmdset_wieldable import DefaultCmdSet



class Wieldable(Object):
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
        self.db.is_wieldable = True
        self.db.wielded_by = None
        self.db.currently_wielded = False
        self.db.desc = "A weapon of some kind."
        # phrase that is seen when we equip it
        self.db.ready_phrase = "wields %s" % self.name
        self.db.stealth = False # whether it can be seen in character desc
        self.db.sense_difficulty = 15 # default if stealth is set to true
        self.db.attack_skill = "medium wpn"
        self.db.attack_stat = "dexterity"
        self.db.damage_stat = "strength"
        self.db.damage_bonus = 1
        self.db.attack_type = "melee"
        self.db.can_be_parried = True
        self.db.can_be_blocked = True
        self.db.can_be_dodged = True
        self.db.can_be_countered = True
        self.db.can_parry = True 
        self.db.can_riposte = True
        self.db.sheathed_by = None
        self.db.difficulty_mod = 0
        self.cmdset.add_default(DefaultCmdSet, permanent=True)

    def ranged_mode(self):
        self.db.can_be_parried = False
        self.db.can_parry = False
        self.db.can_riposte = False

    def melee_mode(self):
        self.db.can_be_parried = True
        self.db.can_parry = True
        self.db.can_parry = True

    def sheathe(self, wielder):
        """
        Puts the weapon in a sheathe or otherwise worn on our person,
        rather than removed into inventory.
        """
        if not self.remove(wielder):
            return False
        self.db.sheathed_by = wielder
        return True

    def remove(self, wielder):
        """
        Takes off the weapon
        """
        if not self.at_pre_remove(wielder):
            return False
        self.db.sheathed_by = None # in case we're dropped, no longer sheathed
        self.db.wielded_by = None
        self.db.currently_wielded = False
        wielder.db.weapon = None
        return True

    def wield_by(self, wielder):
        """
        Puts item on the wielder
        """
        #Assume any fail messages are written in at_pre_wield
        if not self.at_pre_wield(wielder):
            return False
        self.db.wielded_by = wielder
        self.db.currently_wielded = True
        wielder.db.weapon = self
        self.db.sheathed_by = None
        if self.location != wielder:
            self.location = wielder
        self.calc_weapon()
        return True

    def at_after_move(self, source_location):
        "If new location is not our wielder, remove."
        location = self.location
        wielder = self.db.wielded_by
        if not location:
            self.remove(wielder)
            return
        if self.db.currently_wielded and wielder and location != wielder:
            self.remove(wielder)

    def at_pre_wield(self, wielder):
        "Hook called before wielding for any checks."
        return True

    def at_post_wield(self, wielder):
        "Hook called after wielding for any checks."
        cscript = wielder.location.ndb.combat_manager
        if cscript and wielder in cscript.ndb.combatants:
            cdat = cscript.get_fighter_data(wielder.id)
            cdat.setup_weapon(wielder.weapondata)     
        return True

    def at_pre_remove(self, wielder):
        "Hook called before removing."
        return True

    def at_post_remove(self, wielder):
        "Hook called after removing."
        cscript = wielder.location.ndb.combat_manager
        if cscript and wielder in cscript.ndb.combatants:
            cdat = cscript.get_fighter_data(wielder.id)
            cdat.setup_weapon(wielder.weapondata)
        return True
    
    def calc_weapon(self):
        """
        If we have crafted armor, return the value from the recipe and
        quality.
        """
        quality = self.db.quality_level or 0
        recipe_id = self.db.recipe
        diffmod = self.db.difficulty_mod or 0
        flat_damage_bonus = self.db.flat_damage_bonus or 0
        if self.db.attack_skill == "huge wpn":
            diffmod += 1
        elif self.db.attack_skill == "archery":
            self.ranged_mode()
            diffmod += 5
        elif self.db.attack_skill == "small wpn":
            diffmod -= 1
        from world.dominion.models import CraftingRecipe
        try:
            recipe = CraftingRecipe.objects.get(id=recipe_id)
        except CraftingRecipe.DoesNotExist:
            return (self.db.damage_bonus or 0, diffmod, flat_damage_bonus)
        base = float(recipe.resultsdict.get("baseval", 0))
        scaling = float(recipe.resultsdict.get("scaling", 0.2))
        if not base and not scaling:
            self.ndb.cached_damage_bonus = 0
            self.ndb.cached_difficulty_mod = diffmod
            self.ndb.cached_flat_damage_bonus = flat_damage_bonus
            return (self.ndb.cached_damage_bonus, self.ndb.cached_difficulty_mod,
                    self.ndb.cached_flat_damage_bonus)
        try:
            damage = int(round(base + (scaling * quality)))
            diffmod -= int(round(scaling * quality))
            flat_damage_bonus += (quality - 2) * 2
        except (TypeError, ValueError):
            print "Error setting up weapon ID: %s" % self.id
            damage = 0
        self.ndb.purported_value = damage
        if self.db.forgery_penalty:
            try:
                damage /= self.db.forgery_penalty
                diffmod += self.db.forgery_penalty
                flat_damage_bonus /= self.db.forgery_penalty
            except (ValueError, TypeError):
                damage = 0
        self.ndb.cached_damage_bonus = damage
        self.ndb.cached_difficulty_mod = diffmod
        self.ndb.cached_flat_damage_bonus = flat_damage_bonus
        return (damage, diffmod, flat_damage_bonus)
    
    def _get_damage_bonus(self):
        # if we have no recipe or we are set to ignore it, use armor_class
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.damage_bonus
        if self.ndb.cached_damage_bonus != None:
            return self.ndb.cached_damage_bonus
        return self.calc_weapon()[0]
    
    def _set_damage_bonus(self, value):
        """
        Manually sets the value of our weapon, ignoring any crafting recipe we have.
        """
        self.db.damage_bonus = value
        self.db.ignore_crafted = True
        self.ndb.cached_damage_bonus = value

    def _get_difficulty_mod(self):
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.difficulty_mod or 0
        if self.ndb.cached_difficulty_mod != None:
            return self.ndb.cached_difficulty_mod
        return self.calc_weapon()[1]

    def _get_flat_damage(self):
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.flat_damage_bonus or 0
        if self.ndb.cached_flat_damage_bonus != None:
            return self.ndb.cached_flat_damage_bonus
        return self.calc_weapon()[2]

    damage_bonus = property(_get_damage_bonus, _set_damage_bonus)
    difficulty_mod = property(_get_difficulty_mod)
    flat_damage = property(_get_flat_damage)


    
