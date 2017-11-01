from server.utils.test_utils import ArxCommandTest
from . import story_actions


class StoryActionTests(ArxCommandTest):
        
    def test_cmdaction(self):
        self.cmd_class = story_actions.CmdAction
        self.caller = self.player
        self.call_cmd("/newaction", "You need to include a story.")
        self.call_cmd("/newaction testing", "You do not have enough action points.")
    
    def test_gmaction(self):
        pass