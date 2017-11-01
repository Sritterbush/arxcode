from mock import Mock, patch

from server.utils.test_utils import ArxCommandTest
from . import crisis_commands


class TestCrisisCommands(ArxCommandTest):
    def setUp(self):
        super(TestCrisisCommands, self).setUp()
        from .models import Crisis, CrisisAction
        self.crisis = Crisis.objects.create(name="test crisis", escalation_points=100)
        self.action = self.crisis.actions.create(dompc=self.dompc2, actions="test action", outcome_value=50, 
                                                 status=CrisisAction.PENDING_PUBLISH)
        
    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_gm_crisis(self, mock_get_week, mock_inform_staff):
        self.cmd_class = crisis_commands.CmdGMCrisis
        self.caller = self.player
        mock_get_week.return_value = 1
        self.call_cmd("/create test crisis2/ermagerd headline=test desc", 
                      "Crisis created. Make gemits or whatever for it.")
        with patch('server.utils.arx_utils.broadcast_msg_and_post') as mock_msg_and_post:
            from web.character.models import Story, Chapter, Episode
            chapter = Chapter.objects.create(name="test chapter")
            Episode.objects.create(name="test episode", chapter=chapter)
            Story.objects.create(name="test story", current_chapter=chapter)
            self.call_cmd("/update 1=test gemit/test note", "You have updated the crisis.")
            mock_msg_and_post.assert_called_with("test gemit", self.caller, episode_name="test episode")
            mock_inform_staff.assert_called_with('Crisis update posted by TestPlayer for test crisis:\n'
                                                 'Gemit:\ntest gemit\nGM Notes: test note',
                                                 post=True, subject='Action Published')
        self.call_cmd("1", self.crisis.display())
        
    def test_cmd_view_crisis(self):
        self.cmd_class = crisis_commands.CmdViewCrisis
        self.caller = self.player
        self.call_cmd("1", self.crisis.display())
