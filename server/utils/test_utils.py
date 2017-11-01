from evennia.commands.default.tests import CommandTest


class ArxCommandTest(CommandTest):
    """
    child of Evennia's CommandTest class specifically for Arx. We'll add some
    objects that our characters/players would be expected to have for any 
    particular test.
    """
    def setUp(self):
        super(ArxCommandTest, self).setUp()
        from world.dominion.setup_utils import setup_dom_for_player, setup_assets
        from web.character.models import Roster, RosterEntry
        self.dompc = setup_dom_for_player(self.player)
        self.dompc2 = setup_dom_for_player(self.player2)
        self.assetowner = setup_assets(self.dompc, 0)
        self.assetowner2 = setup_assets(self.dompc2, 0)
        self.active_roster = Roster.objects.create(name="Active")
        self.roster_entry = self.active_roster.entries.create(player=self.player, character=self.char1)
        self.roster_entry2 = self.active_roster.entries.create(player=self.player2, character=self.char2)
