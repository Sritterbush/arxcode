# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from server.utils.test_utils import ArxCommandTest
from world.petitions import petitions_commands


class TestPetitionCommands(ArxCommandTest):
    def test_cmd_broker(self):
        from world.petitions.models import BrokeredSale
        from world.dominion.models import CraftingMaterialType
        mat = CraftingMaterialType.objects.create(name="testium", value=5000)
        sale = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ACTION_POINTS, amount=50, price=5)
        self.setup_cmd(petitions_commands.CmdBroker, self.char1)
        self.call_cmd("", 'ID Seller       Type          Price Amount \n'
                          '1  Testaccount2 Action Points 5     50')
        self.call_cmd("/buy 2", "Could not find a sale on the broker by the ID 2.")
        self.call_cmd("/buy 1", "You must provide a positive number as the amount.")
        self.call_cmd("/buy 1=-5", "You must provide a positive number as the amount.")
        self.call_cmd("/buy 1=100", "You want to buy 100, but there is only 50 for sale.")
        self.call_cmd("/buy 1=25", "You cannot afford to pay 125 when you only have 0.0 silver.")
        self.char1.currency += 20000
        self.call_cmd("/buy 1=25", 'You have bought 25 Action Points from Testaccount2 for 125 silver.')
        self.assertEqual(self.roster_entry.action_points, 125)
        self.assertEqual(sale.amount, 25)
        self.call_cmd("/buy 1=10", "You have bought 10 Action Points from Testaccount2 for 50 silver.")
        self.assertEqual(self.roster_entry.action_points, 135)
        self.assertEqual(sale.amount, 15)
        sale2 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ECONOMIC, amount=50, price=5)
        sale3 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.CRAFTING_MATERIALS, amount=50,
                                            price=5, crafting_material_type=mat)
        self.call_cmd("/buy 2=5", "You have bought 5 Economic Resources from Testaccount2 for 25 silver.")
        self.call_cmd("/buy 3=10", "You have bought 10 testium from Testaccount2 for 50 silver.")
        self.assertEqual(self.char1.currency, 19750)
        self.assertEqual(self.char2.currency, 250)
        self.assertEqual(self.assetowner.economic, 5)
        self.assertEqual(self.assetowner.materials.get(type=mat).amount, 10)
