# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


class BrokeredDeal(SharedMemoryModel):
    """A deal sitting on the broker, waiting for someone to buy it"""
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


class BrokeredPurchaseAmount(SharedMemoryModel):
    """Details of a purchase by a player"""
    deal = models.ForeignKey('BrokeredDeal', related_name="purchase_amounts")
    buyer = models.ForeignKey('dominion.PlayerOrNpc', related_name="purchase_amounts")
    amount = models.PositiveIntegerField(default=0)
