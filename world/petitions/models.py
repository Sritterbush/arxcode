# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel

from server.utils.exceptions import PayError


class BrokeredSale(SharedMemoryModel):
    """A sale sitting on the broker, waiting for someone to buy it"""
    ACTION_POINTS = 0
    ECONOMIC = 1
    SOCIAL = 2
    MILITARY = 3
    CRAFTING_MATERIALS = 4
    OFFERING_TYPES = ((ACTION_POINTS, "Action Points"), (ECONOMIC, "Economic Resources"), (SOCIAL, "Social Resources"),
                      (MILITARY, "Military Resources"), (CRAFTING_MATERIALS, "Crafting Materials"))
    owner = models.ForeignKey("dominion.PlayerOrNpc", related_name="brokered_sales")
    offering_type = models.PositiveSmallIntegerField(default=ACTION_POINTS, choices=OFFERING_TYPES)
    amount = models.PositiveIntegerField(default=0)
    price = models.PositiveIntegerField(default=0)
    buyers = models.ManyToManyField("dominion.PlayerOrNpc", related_name="brokered_purchases",
                                    through="BrokeredPurchaseAmount")
    crafting_material_type = models.ForeignKey("dominion.CraftingMaterialType", null=True, on_delete=models.CASCADE)

    @property
    def material_name(self):
        """Returns the name of what we're offering"""
        if self.crafting_material_type:
            return self.crafting_material_type.name
        return self.get_offering_type_display()

    @property
    def owner_character(self):
        """Character object of our owner"""
        return self.owner.player.char_ob

    def display(self, caller):
        """
        Gets a string display of the sale based on caller's privileges
        Args:
            caller: Character object, determine if it's our owner to show buyer information

        Returns:
            string display of the sale
        """
        msg = "{wID{n: %s\n" % self.id
        msg += "{wMaterial{n: %s {wAmount{n: %s {wPrice{n: %s\n" % (self.material_name, self.amount, self.price)
        amounts = self.purchased_amounts.all()
        if caller == self.owner_character and amounts:
            msg += "{wPurchase History:{n\n"
            msg += ", ".join(ob.display() for ob in amounts)
        return msg

    def make_purchase(self, buyer, amount):
        """
        
        Args:
            buyer:
            amount:

        Returns:

        """


class PurchasedAmount(SharedMemoryModel):
    """Details of a purchase by a player"""
    deal = models.ForeignKey('BrokeredSale', related_name="purchased_amounts")
    buyer = models.ForeignKey('dominion.PlayerOrNpc', related_name="purchased_amounts")
    amount = models.PositiveIntegerField(default=0)

    def display(self):
        """Gets string display of the amount purchased and by whom"""
        return "{} bought {}".format(self.buyer, self.amount)
