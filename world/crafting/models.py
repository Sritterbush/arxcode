# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter
from django.db import models

# Create your models here.
from evennia.utils import create
from evennia.utils.idmapper.models import SharedMemoryModel
from server.utils.arx_utils import CachedProperty, CachedPropertiesMixin


class Mats(object):
    """helper classes for crafting recipe to simplify API - allow for 'recipe.materials.all()'"""
    def __init__(self, mat, amount):
        self.mat = mat
        self.id = mat.id
        self.type = mat
        self.amount = amount


class MatList(object):
    """Helper class for list of mats used"""
    def __init__(self):
        self.mats = []

    def all(self):
        """All method to simplify API"""
        return self.mats


class CraftingRecipe(CachedPropertiesMixin, SharedMemoryModel):
    """
    For crafting, a recipe has a name, description, then materials. A lot of information
    is saved as a parsable text string in the 'result' text field. It'll
    take a form like: "baseval:0;scaling:1" and so on. baseval is a value
    the object has (for armor, say) for minimum quality level, while
    scaling is the increase per quality level to stats. "slot" and "slot limit"
    are used for wearable objects to denote the slot they're worn in and
    how many other objects may be worn in that slot, respectively.
    """
    name = models.CharField(blank=True, max_length=255, unique=True)
    desc = models.TextField(blank=True)
    # organizations or players that know this recipe
    known_by = models.ManyToManyField('dominion.AssetOwner', blank=True, related_name='recipes')
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    additional_cost = models.PositiveIntegerField(blank=0, default=0)
    # the ability/profession that is used in creating this
    ability = models.CharField(blank=True, max_length=80, db_index=True)
    skill = models.CharField(blank=True, max_length=80, db_index=True)
    # the type of object we're creating
    type = models.CharField(blank=True, max_length=80)
    # level in ability this recipe corresponds to. 1 through 6, usually
    level = models.PositiveSmallIntegerField(default=1)
    allow_adorn = models.BooleanField(default=True)
    baseval = models.IntegerField("Value used for things like weapon damage, armor rating, etc.", default=0)

    def org_owners(self):
        return list(self.known_by.select_related('organization_owner').filter(organization_owner__isnull=False))

    org_owners = CachedProperty(org_owners, '_org_owners')  # type: list

    def can_be_learned_by(self, learner):
        """Returns True if learner can learn this recipe, False otherwise"""
        # insert new check for skill/stat/ability here
        pass
        # if we have no orgs that know this recipe, anyone can learn it normally
        if not self.org_owners:
            return True
        # check if they have granted access from any of the orgs that know it
        return any(ob.access(learner, access_type="recipe") for ob in self.org_owners)

    @CachedProperty
    def cached_required_materials(self):
        return list(self.required_materials.all())

    @property
    def materials_counter(self):
        counter = Counter()
        for req in self.cached_required_materials:
            counter.update({req.type: req.amount})
        return counter

    @property
    def primary_requirements(self):
        return [ob for ob in self.cached_required_materials if ob.priority == 1]

    @property
    def secondary_requirements(self):
        return [ob for ob in self.cached_required_materials if ob.priority == 2]

    @property
    def tertiary_requirements(self):
        return [ob for ob in self.cached_required_materials if ob.priority == 3]

    def display_reqs(self, dompc=None, full=False):
        """Returns string display for recipe"""
        msg = ""
        if full:
            msg += "{wName:{n %s\n" % self.name
            msg += "{wDescription:{n %s\n" % self.desc
        msg += "{wSilver:{n %s\n" % self.additional_cost
        if dompc:
            dompc_mats = dompc.assets.materials.all()
        else:
            dompc_mats = []
        mat_msgs = []
        for req in self.cached_required_materials:
            if req.amount:
                mat = req.type
                if dompc:
                    try:
                        pcmat = [ob for ob in dompc_mats if ob.type == mat][0]
                        amt = pcmat.amount
                    except IndexError:
                        amt = 0
                    mat_msgs.append("%s: %s (%s/%s)" % (mat, req.amount, amt, mat))
                else:
                    mat_msgs.append("%s: %s" % (mat, req.amount))
        if mat_msgs:
            msg += "Materials: %s" % ", ".join(mat_msgs)
        return msg

    @CachedProperty
    def value(self):
        """Returns total cost of all materials used"""
        val = self.additional_cost
        for req in self.cached_required_materials:
            val += req.material.value * req.amount
        return val

    def __str__(self):
        return self.name or "Unknown"

    def calculate_quality_from_roll(self, roll):
        diff = self.difficulty
        roll += diff
        if roll < diff / 4:
            return 0
        if roll < (diff * 3) / 4:
            return 1
        if roll < diff * 1.2:
            return 2
        if roll < diff * 1.6:
            return 3
        if roll < diff * 2:
            return 4
        if roll < diff * 2.5:
            return 5
        if roll < diff * 3.5:
            return 6
        if roll < diff * 5:
            return 7
        if roll < diff * 7:
            return 8
        if roll < diff * 10:
            return 9
        return 10

    def create_object(self, crafter, roll, adornment_map):
        """
        Crafts a new object for this recipe by the crafter. All costs are assumed to have
        already been paid at this point and success is guaranteed
        Args:
            crafter (Character): Character who created the object
            roll (int): The roll for crafting success
            adornment_map (dict): Dict of CraftingMaterialType and quantities

        Returns:
            The new object with the CraftingRecord and Adornments already applied.
        """
        obj = create.create_object(self.type)
        self.crafting_records.create(object=obj, crafter=crafter, base_quality=self.calculate_quality_from_roll(roll))
        for material, amount in adornment_map.items():
            obj.add_adornment(material, amount)
        return obj


class RecipeExtentions(models.Model):
    """Some of the recipes will have slightly different fields. For example, armor"""
    recipe = models.OneToOneField("crafting.CraftingRecipe", on_delete=models.CASCADE)

    class Meta:
        abstract = True


class WearableStats(RecipeExtentions):
    """
    Stats for wearable recipes, which is armor and pure fashion items. Slot will probably become a foreignkey
    eventually.
    """
    slot = models.CharField(max_length=80, blank=True)
    slot_volume = models.PositiveSmallIntegerField("How much space we take up. 100 is all of it.", default=0)
    fashion_mult = models.PositiveIntegerField("Percentage multiplier when used for fashion", default=0)
    penalty = models.SmallIntegerField("How much the armor impedes movement", default=0)
    resilience = models.SmallIntegerField("How easy the armor is to penetrate", default=0)


class WeaponStats(RecipeExtentions):
    """
    Stats for a Weapon Recipe. Currently just has the weapon skill, which will probably eventually become a
    foreignkey when skills/abilities are converted into a proper model. We'll probably add more stats here when
    we revamp combat.
    """
    MEDIUM_WPN = "medium wpn"
    SMALL_WPN = "small wpn"
    HUGE_WPN = "huge wpn"
    ARCHERY = "archery"
    WPN_SKILL_CHOICES = ((SMALL_WPN, "Small Weapons"), (MEDIUM_WPN, "Medium Weapons"), (HUGE_WPN, "Huge Weapons"),
                         (ARCHERY, "Archery"))
    weapon_skill = models.CharField(max_length=80, blank=True, choices=WPN_SKILL_CHOICES, default=MEDIUM_WPN)


class CraftingMaterialType(SharedMemoryModel):
    """
    Different types of crafting materials. We have a silver value per unit
    stored. Similar to results in CraftingRecipe, mods holds a dictionary
    of key,value pairs parsed from our acquisition_modifiers textfield. For
    CraftingMaterialTypes, this includes the category of material, and how
    difficult it is to fake it as another material of the same category
    """
    # the type of material we are
    name = models.CharField(max_length=80, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # silver value per unit
    value = models.PositiveIntegerField(blank=0, default=0)
    category = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    # Text we can parse for notes about cost modifiers for different orgs, locations to obtain, etc
    acquisition_modifiers = models.TextField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super(CraftingMaterialType, self).__init__(*args, **kwargs)
        # uses same method from CraftingRecipe in order to create a dict of our mods
        self.mods = CraftingRecipe.parse_result(self.acquisition_modifiers)

    def __unicode__(self):
        return self.name or "Unknown"

    def create_instance(self, quantity):
        name_string = self.name
        if quantity > 1:
            name_string = "{} {}".format(quantity, self.name)

        result = create.create_object(key=name_string,
                                      typeclass="world.dominion.dominion_typeclasses.CraftingMaterialObject")
        self.object_materials.create(object=result, amount=quantity)
        return result


class AbstractMaterialAmount(models.Model):
    type = models.ForeignKey("crafting.CraftingMaterialType", on_delete=models.CASCADE)
    amount = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True

    def __str__(self):
        return "%s %s" % (self.amount, self.type)

    @property
    def value(self):
        """Returns value of materials they have"""
        return self.type.value * self.amount


class RecipeRequirement(AbstractMaterialAmount):
    recipe = models.ForeignKey("crafting.CraftingRecipe", on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        default_related_name = "required_materials"
        verbose_name_plural = "Recipe Materials Requirements"


class Adornment(AbstractMaterialAmount):
    """Materials contained within an object, such as adornments, or when used as a loot object"""
    object = models.ForeignKey('objects.ObjectDB', on_delete=models.CASCADE, related_name="adornments")

    class Meta:
        default_related_name = "object_materials"
        verbose_name_plural = "Adornments"


class OwnedMaterial(AbstractMaterialAmount):
    """
    Crafting Materials owned by some AssetOwner
    """
    owner = models.ForeignKey('dominion.AssetOwner', on_delete=models.CASCADE)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Owned Materials"
        default_related_name = "materials"


class CraftingRecord(models.Model):
    """
    This is where stats for crafting an object are really recorded. We'll store data on who the crafter was,
    the current quality level, progress toward increasing the quality level, damage it has taken, etc.
    """
    object = models.OneToOneField('objects.ObjectDB', on_delete=models.CASCADE, related_name="crafting_record")
    recipe = models.ForeignKey('crafting.CraftingRecipe', on_delete=models.CASCADE, related_name="crafting_records")
    base_quality = models.SmallIntegerField("Quality without other modifiers", default=5)
    refining_progress = models.SmallIntegerField(default=0)
    damage = models.SmallIntegerField("Current damage, which affects quality", default=0)
