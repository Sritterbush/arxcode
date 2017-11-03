from mock import Mock, patch

from server.utils.test_utils import ArxCommandTest
from world.dominion.models import CrisisAction
from . import story_actions


class StoryActionTests(ArxCommandTest):

    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_action(self, mock_get_week, mock_inform_staff):
        mock_get_week.return_value = 1
        self.cmd_class = story_actions.CmdAction
        self.caller = self.player
        self.call_cmd("/newaction", "You need to include a story.")
        self.caller.pay_action_points = Mock(return_value=False)
        self.call_cmd("/newaction testing", "You do not have enough action points.")
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd("/newaction testing", "You have drafted a new action: testing|Please note that you cannot invite "
                                            "players to an action once it is submitted.")
        self.call_cmd("/submit 1", "Incomplete fields: ooc intent, tldr, roll, category")
        self.call_cmd("/category 1=foo", "You need to include one of these categories: scouting, combat, diplomacy, "
                                         "unknown, support, research, sabotage.")
        self.call_cmd("/category 1=research", "category set to Research.")
        self.call_cmd("/ooc 1=testooc", "You have set your ooc intent to be: testooc")
        self.call_cmd("/tldr 1=summary", "topic set to summary.")
        self.call_cmd("/roll 1=strength,athletics", "stat set to strength.|skill set to athletics.")
        self.call_cmd("/invite 1=foo", "Could not find 'foo'.")
        self.call_cmd("/invite 1=TestPlayer2", "You have invited Testplayer2 to join your action.")
        self.call_cmd("/add 1=foo,bar", "Invalid type of resource.")
        self.call_cmd("/add 1=ap,50", "50 ap added. Action Resources: extra action points 50")
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: True")
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: False")
        self.call_cmd("/toggleattend 1", "You are marked as no longer attending the action.")
        self.call_cmd("/toggleattend 1", "You have marked yourself as physically being present for that action.")
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: True")
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: False")
        self.call_cmd("/submit 1", "Before submitting this action, make certain that you have invited all players you "
                                   "wish to help with the action, and add any resources necessary. Any invited players "
                                   "who have incomplete actions will have their assists deleted.\nThe following "
                                   "assistants are not ready and will be deleted: Testplayer2\nWhen ready, /submit "
                                   "the action again.")
        self.call_cmd("/submit 1", "You have new informs. Use @inform 1 to read them.|You have submitted your action.")
        mock_inform_staff.assert_called_with('Testplayer has submitted action #1.')
        action = self.dompc.actions.last()
        self.call_cmd("/makepublic 1", "The action must be finished before you can make details of it public.")
        action.status = CrisisAction.PUBLISHED
        self.call_cmd("/makepublic 1", "You have gained 2 xp for making your action public.")

    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_gm_action(self, mock_get_week, mock_inform_staff):
        from datetime import datetime
        mock_get_week.return_value = 1
        action = self.dompc2.actions.create(actions="test", status=CrisisAction.NEEDS_GM, editable=False, silver=50,
                                            date_submitted=datetime.now())
        action.set_ooc_intent("ooc intent test")
        self.cmd_class = story_actions.CmdGMAction
        self.caller = self.player
        self.call_cmd("/story 2=foo", "No action by that ID #.")
        self.call_cmd("/story 1=foo", "story set to foo.")
        self.call_cmd("/secretstory 1=sekritfoo", "secret_story set to sekritfoo.")
        self.call_cmd("/stat 1=charm", "stat set to charm.")
        self.call_cmd("/skill 1=seduction", "skill set to seduction.")
        self.call_cmd("/diff 1=25", "difficulty set to 25.")
        self.call_cmd("/diff 1=hard", "difficulty set to %s." % CrisisAction.HARD_DIFFICULTY)
        self.call_cmd("/assign 1=Testplayer", "gm set to Testplayer.|GM for the action set to Testplayer")
        self.player2.pay_resources = Mock()
        self.call_cmd("/charge 1=economic,2000", "2000 economic added. Action Resources: economic 2000")
        self.player2.pay_resources.assert_called_with("economic", 2000)
        self.caller.inform = Mock()
        self.player2.inform = Mock()
        action.ask_question("foo inform")
        self.caller.inform.assert_called_with('{cTestplayer2{n added a comment/question about Action #1:\nfoo inform',
                                              category='Action questions')
        self.call_cmd("/ooc/allowedit 1=Sure go nuts", "editable set to True.|Answer added.")
        self.player2.inform.assert_called_with('GM Testplayer has posted a followup to action 1: Sure go nuts',
                                               append=False, category='Actions', week=1)
        self.assertEquals(action.editable, True)
        self.player2.gain_resources = Mock()
        self.call_cmd("/cancel 1", "Action cancelled.")
        self.player2.gain_resources.assert_called_with("economic", 2000)
        self.assertEquals(self.assetowner2.vault, 50)
        self.assertEquals(action.status, CrisisAction.CANCELLED)
        self.call_cmd("/markpending 1", "status set to Pending Publish.")
        self.assertEquals(action.status, CrisisAction.PENDING_PUBLISH)
        self.call_cmd("/publish 1", "You have published the action and sent the players informs.")
        self.assertEquals(action.status, CrisisAction.PUBLISHED)
        self.player2.inform.assert_called_with('{wGM Response to story action of Testplayer2\n'
                                               '{wRolls:{n 0\n\n{wStory Result:{n foo\n\n',
                                               append=False, category='Actions', week=1)
        mock_inform_staff.assert_called_with('Action 1 has been published by Testplayer:\n{wGM Response to story action'
                                             ' of Testplayer2\n{wRolls:{n 0\n\n{wStory Result:{n foo\n\n', post=True,
                                             subject='Action Published')
        with patch('server.utils.arx_utils.broadcast_msg_and_post') as mock_msg_and_post:
            from web.character.models import Story, Chapter, Episode
            chapter = Chapter.objects.create(name="test chapter")
            Episode.objects.create(name="test episode", chapter=chapter)
            Story.objects.create(name="test story", current_chapter=chapter)
            self.call_cmd("/gemit 1=test gemit", "StoryEmit created.")
            mock_msg_and_post.assert_called_with("test gemit", self.caller, episode_name="test episode")
            mock_inform_staff.assert_called_with('Action 1 has been published by Testplayer:\n{wGM Response to story '
                                                 'action of Testplayer2\n{wRolls:{n 0\n\n{wStory Result:{n foo\n\n',
                                                 post=True, subject='Action Published')
