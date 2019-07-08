# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

# Create your models here.
from evennia.locks.lockhandler import LockHandler
from evennia.utils import create
from evennia.utils.idmapper.models import SharedMemoryModel
from server.utils.arx_utils import CachedProperty


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
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # organizations or players that know this recipe
    known_by = models.ManyToManyField('dominion.AssetOwner', blank=True, related_name='recipes', db_index=True)
    primary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_primary')
    secondary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_secondary')
    tertiary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_tertiary')
    primary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    secondary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    tertiary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    additional_cost = models.PositiveIntegerField(blank=0, default=0)
    # the ability/profession that is used in creating this
    ability = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    skill = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    # the type of object we're creating
    type = models.CharField(blank=True, null=True, max_length=80)
    # level in ability this recipe corresponds to. 1 through 6, usually
    level = models.PositiveSmallIntegerField(blank=1, default=1)
    # the result is a text field that we can later parse to determine what we create
    result = models.TextField(blank=True, null=True)
    allow_adorn = models.BooleanField(default=True, blank=True)
    # lockstring
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')

    def __init__(self, *args, **kwargs):
        super(CraftingRecipe, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)
        self.resultsdict = self.parse_result(self.result)
        self.materials = MatList()
        # create throws errors on __init__ for many to many fields
        if self.pk:
            if self.primary_amount:
                for mat in self.primary_materials.all():
                    self.materials.mats.append(Mats(mat, self.primary_amount))
            if self.secondary_amount:
                for mat in self.secondary_materials.all():
                    self.materials.mats.append(Mats(mat, self.secondary_amount))
            if self.tertiary_amount:
                for mat in self.tertiary_materials.all():
                    self.materials.mats.append(Mats(mat, self.tertiary_amount))

    def access(self, accessing_obj, access_type='learn', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def org_owners(self):
        return self.known_by.select_related('organization_owner').filter(organization_owner__isnull=False)

    org_owners = CachedProperty(org_owners, '_org_owners')

    def can_be_learned_by(self, learner):
        """Returns True if learner can learn this recipe, False otherwise"""
        if not self.access(learner):
            return False
        # if we have no orgs that know this recipe, anyone can learn it normally
        if not self.org_owners:
            return True
        # check if they have granted access from any of the orgs that know it
        return any(ob.access(learner, access_type="recipe") for ob in self.org_owners)

    @staticmethod
    def parse_result(results):
        """
        Given a string, return a dictionary of the different
        key:value pairs separated by semicolons
        """
        if not results:
            return {}
        rlist = results.split(";")
        keyvalpairs = [pair.split(":") for pair in rlist]
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict

    def display_reqs(self, dompc=None, full=False):
        """Returns string display for recipe"""
        msg = ""
        if full:
            msg += "{wName:{n %s\n" % self.name
            msg += "{wDescription:{n %s\n" % self.desc
        msg += "{wSilver:{n %s\n" % self.additional_cost
        tups = ((self.primary_amount, "{wPrimary Materials:{n\n", self.primary_materials),
                (self.secondary_amount, "\n{wSecondary Materials:{n\n", self.secondary_materials),
                (self.tertiary_amount, "\n{wTertiary Materials:{n\n", self.tertiary_materials),)
        for tup in tups:
            if tup[0]:
                msg += tup[1]
                if dompc:
                    msglist = []
                    for mat in tup[2].all():
                        try:
                            pcmat = dompc.assets.materials.get(type=mat)
                            amt = pcmat.amount
                        except CraftingMaterials.DoesNotExist:
                            amt = 0
                        msglist.append("%s: %s (%s/%s)" % (str(mat), tup[0], amt, tup[0]))
                    msg += ", ".join(msglist)
                else:
                    msg += ", ".join("%s: %s" % (str(ob), tup[0]) for ob in tup[2].all())
        return msg

    @CachedProperty
    def value(self):
        """Returns total cost of all materials used"""
        val = self.additional_cost
        for mat in self.primary_materials.all():
            val += mat.value * self.primary_amount
        for mat in self.secondary_materials.all():
            val += mat.value * self.secondary_amount
        for mat in self.tertiary_materials.all():
            val += mat.value * self.tertiary_amount
        return val

    def __unicode__(self):
        return self.name or "Unknown"

    @property
    def baseval(self):
        """Returns baseval used in recipes"""
        return float(self.resultsdict.get("baseval", 0.0))


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
        result.db.desc = self.desc
        result.db.material_type = self.id
        result.db.quantity = quantity
        return result


class CraftingMaterials(SharedMemoryModel):
    """
    Materials used for crafting. Can be stored by an AssetOwner as part of their
    collection, -or- used in a recipe to measure how much they need of a material.
    If it is used in a recipe, do NOT set it owned by any asset owner, or by changing
    the amount they'll change the amount required in a recipe!
    """
    type = models.ForeignKey('CraftingMaterialType', blank=True, null=True, db_index=True)
    amount = models.PositiveIntegerField(blank=0, default=0)
    owner = models.ForeignKey('dominion.AssetOwner', blank=True, null=True, related_name='materials', db_index=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Crafting Materials"

    def __unicode__(self):
        return "%s %s" % (self.amount, self.type)

    @property
    def value(self):
        """Returns value of materials they have"""
        return self.type.value * self.amount