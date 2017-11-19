from mock import Mock

from server.utils.test_utils import ArxCommandTest
from web.character import investigation, scene_commands
from web.character.models import Clue


class InvestigationTests(ArxCommandTest):
    def setUp(self):
        super(InvestigationTests, self).setUp()
        self.clue = Clue.objects.create(name="test clue", rating=10, desc="test clue desc")
        self.roster_entry.clues.create(clue=self.clue, roll=200, message="additional text test")

    def test_cmd_clues(self):
        from datetime import datetime
        self.setup_cmd(investigation.CmdListClues, self.account)
        self.call_cmd("1", "test clue\nRating: 10\ntest clue desc")
        self.call_cmd("/addnote 1=test note", "test clue\nRating: 10\ntest clue desc\n\nadditional text test"
                                              "\n[%s] TestAccount wrote: test note" % datetime.now().strftime("%x %X"))
        self.call_cmd("/share 1=Testaccount2", "Sharing that many clues would cost 101 action points.")
        self.roster_entry.action_points = 101
        self.call_cmd("/share 1=Testaccount2", "You have shared the clues 'test clue' with Char2.")


class SceneCommandTests(ArxCommandTest):
    def test_cmd_flashback(self):
        self.setup_cmd(scene_commands.CmdFlashback, self.account)
        self.call_cmd("/create testing", "You have created a new flashback with the ID of #1.")
        self.call_cmd("/create testing", "There is already a flashback with that title. Please choose another.")
        self.call_cmd("1", "(#1) testing\nOwner: Char\nSummary: \nPosts: ")
        self.call_cmd("/catchup 1", "No new posts for #1.")
        self.account2.inform = Mock()
        self.call_cmd("/invite 1=Testaccount2", "You have invited Testaccount2 to participate in this flashback.")
        self.account2.inform.assert_called_with("You have been invited by Testaccount to participate in flashback #1:"
                                                " 'testing'", category="Flashbacks")
