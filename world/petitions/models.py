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
    sale_type = models.PositiveSmallIntegerField(default=ACTION_POINTS, choices=OFFERING_TYPES)
    amount = models.PositiveIntegerField(default=0)
    price = models.PositiveIntegerField(default=0)
    buyers = models.ManyToManyField("dominion.PlayerOrNpc", related_name="brokered_purchases",
                                    through="PurchasedAmount")
    crafting_material_type = models.ForeignKey("dominion.CraftingMaterialType", null=True, on_delete=models.CASCADE)

    @property
    def material_name(self):
        """Returns the name of what we're offering"""
        if self.crafting_material_type:
            return self.crafting_material_type.name
        return self.get_sale_type_display()

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
        Khajit has wares, if you have coin.
        Args:
            buyer (PlayerOrNpc): the buyer
            amount (int): How much they're buying

        Returns:
            the amount they paid

        Raises:
            PayError if they can't afford stuff
        """
        if amount > self.amount:
            raise PayError("You want to buy %s, but there is only %s for sale." % (amount, self.amount))
        cost = self.price * amount
        character = buyer.player.char_ob
        if cost > character.currency:
            raise PayError("You cannot afford to pay %s when you only have %s silver." % (cost, character.currency))
        character.pay_money(cost)
        self.amount -= amount
        self.save()
        self.record_sale(buyer, amount)
        self.send_goods(buyer, amount)
        self.pay_owner(buyer, amount, cost)
        return cost

    def send_goods(self, buyer, amount):
        """
        Sends the results of a sale to buyer and records the purchase
        Args:
            buyer (PlayerOrNpc): person we send the goods to
            amount (int): How much we're sending
        """
        if self.sale_type == self.ACTION_POINTS:
            buyer.player.pay_action_points(-amount)
        elif self.sale_type == self.CRAFTING_MATERIALS:
            buyer.player.gain_materials(self.crafting_material_type, amount)
        else:  # resources
            resource_types = {self.ECONOMIC: "economic", self.MILITARY: "military", self.SOCIAL: "social"}
            resource = resource_types[self.sale_type]
            buyer.player.gain_resources(resource, amount)

    def record_sale(self, buyer, amount):
        """Records a sale"""
        record, _ = self.purchased_amounts.get_or_create(buyer=buyer)
        record.amount += amount
        record.save()

    def pay_owner(self, buyer, quantity, cost):
        """Pays our owner"""
        self.owner_character.pay_money(-cost)
        self.owner.player.inform("%s has bought %s %s for %s silver." % (buyer, quantity, self.material_name, cost),
                                 category="Broker Sale", append=True)


class PurchasedAmount(SharedMemoryModel):
    """Details of a purchase by a player"""
    deal = models.ForeignKey('BrokeredSale', related_name="purchased_amounts")
    buyer = models.ForeignKey('dominion.PlayerOrNpc', related_name="purchased_amounts")
    amount = models.PositiveIntegerField(default=0)

    def display(self):
        """Gets string display of the amount purchased and by whom"""
        return "{} bought {}".format(self.buyer, self.amount)
