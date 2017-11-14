from mock import Mock, patch
from datetime import datetime

from server.utils.test_utils import ArxCommandTest
from world.dominion.models import CrisisAction, Crisis, Army
from . import story_actions, overrides, social


class StoryActionTests(ArxCommandTest):

    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_action(self, mock_get_week, mock_inform_staff):
        mock_get_week.return_value = 1
        self.cmd_class = story_actions.CmdAction
        self.caller = self.account
        self.crisis = Crisis.objects.create(name="Test Crisis")
        self.call_cmd("/newaction", "You need to include a story.")
        self.caller.pay_action_points = Mock(return_value=False)
        self.call_cmd("/newaction testing", "You do not have enough action points.")
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd("/newaction test crisis=testing", "You have drafted a new action (#1) to respond to Test Crisis: "
                                                        "testing|Please note that you cannot invite players to an "
                                                        "action once it is submitted.")
        action = self.dompc.actions.last()
        self.call_cmd("/submit 1", "Incomplete fields: ooc intent, tldr, roll, category")
        self.call_cmd("/category 1=foo", "You need to include one of these categories: scouting, combat, diplomacy, "
                                         "unknown, support, research, sabotage.")
        self.call_cmd("/category 1=Research", "category set to Research.")
        self.call_cmd("/category 1=combat", "category set to Combat.")
        self.call_cmd("/ooc_intent 1=testooc", "You have set your ooc intent to be: testooc")
        self.assertEquals(action.questions.first().is_intent, True)
        self.call_cmd("/tldr 1=summary", "topic set to summary.")
        self.call_cmd("/roll 1=strength,athletics", "stat set to strength.|skill set to athletics.")
        self.call_cmd("/setsecret 1=sekrit", "Secret actions set to sekrit.")
        self.call_cmd("/invite 1=foo", "Could not find 'foo'.")
        self.call_cmd("/invite 1=TestAccount2", "You have invited Testaccount2 to join your action.")
        self.caller = self.account2
        self.call_cmd("/setaction 1=test assist", "You do not have enough action points.")
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd("/setaction 1=test assist",
                      "Action by Testaccount for Test Crisis now has your assistance: test assist")
        Army.objects.create(name="test army", owner=self.assetowner)
        self.call_cmd("/add 1=army,1", "You don't have access to that Army.|Failed to send orders to the army.")
        self.call_cmd("/readycheck 1", "Only the action leader can use that switch.")
        self.caller = self.account
        self.call_cmd("/add 1=foo,bar", "Invalid type of resource.")
        self.call_cmd("/add 1=ap,50", "50 ap added. Action Resources: extra action points 50")
        self.call_cmd("/add 1=army,1", "You have successfully relayed new orders to that army.")
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: True")
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: False")
        self.call_cmd("/toggleattend 1", "You are marked as no longer attending the action.")
        self.call_cmd("/toggleattend 1", "You have marked yourself as physically being present for that action.")
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: True")
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: False")
        self.call_cmd("/readycheck 1", "The following assistants aren't ready: Testaccount2")
        self.call_cmd("/submit 1", "Before submitting this action, make certain that you have invited all players you "
                                   "wish to help with the action, and add any resources necessary. Any invited players "
                                   "who have incomplete actions will have their assists deleted.\nThe following "
                                   "assistants are not ready and will be deleted: Testaccount2\nWhen ready, /submit "
                                   "the action again.")
        self.call_cmd("/submit 1", "You have new informs. Use @inform 1 to read them.|You have submitted your action.")
        mock_inform_staff.assert_called_with('Testaccount has submitted action #1.')
        self.call_cmd("/makepublic 1", "The action must be finished before you can make details of it public.")
        action.status = CrisisAction.PUBLISHED
        self.call_cmd("/makepublic 1", "You have gained 2 xp for making your action public.")
        self.call_cmd("/makepublic 1", "That action has already been made public.")
        self.call_cmd("/question 1=test question", "You have submitted a question: test question")
        self.call_cmd("/newaction test crisis=testing",
                      "You have already submitted an action for this stage of the crisis.")
        action_2 = self.dompc.actions.create(actions="completed storyaction", status=CrisisAction.PUBLISHED,
                                             date_submitted=datetime.now())
        self.dompc.actions.create(actions="another completed storyaction", status=CrisisAction.PUBLISHED,
                                  date_submitted=datetime.now())
        draft = self.dompc.actions.create(actions="storyaction draft", status=CrisisAction.DRAFT,
                                          category=CrisisAction.RESEARCH,
                                          topic="test summary", stat_used="stat", skill_used="skill")
        draft.questions.create(is_intent=True, text="intent")
        self.call_cmd("/submit 4", "You are permitted 2 action requests every 30 days. Recent actions: 2, 3")
        action_2.status = CrisisAction.CANCELLED
        action_2.save()
        self.call_cmd("/submit 4", "Before submitting this action, make certain that you have invited all players you "
                                   "wish to help with the action, and add any resources necessary. Any invited players "
                                   "who have incomplete actions will have their assists deleted.\nWhen ready, /submit "
                                   "the action again.")
        action.status = CrisisAction.CANCELLED
        action.save()
        self.call_cmd("/newaction test crisis=testing",
                      "You have drafted an action which needs to be submitted or canceled: 4")
        action_4 = self.dompc.actions.last()
        action_4.status = CrisisAction.CANCELLED
        action_4.save()
        self.call_cmd("/newaction test crisis=testing", "You have drafted a new action (#5) to respond to Test Crisis: "
                                                        "testing|Please note that you cannot invite players to an "
                                                        "action once it is submitted.")

    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_gm_action(self, mock_get_week, mock_inform_staff):
        from datetime import datetime
        now = datetime.now()
        mock_get_week.return_value = 1
        action = self.dompc2.actions.create(actions="test", status=CrisisAction.NEEDS_GM, editable=False, silver=50,
                                            date_submitted=now, topic="test summary")
        action.set_ooc_intent("ooc intent test")
        self.cmd_class = story_actions.CmdGMAction
        self.caller = self.account
        self.call_cmd("/story 2=foo", "No action by that ID #.")
        self.call_cmd("/story 1=foo", "story set to foo.")
        self.call_cmd("/tldr 1", "Summary of action 1\nAction by Testaccount2: Summary: test summary")
        self.call_cmd("/secretstory 1=sekritfoo", "secret_story set to sekritfoo.")
        self.call_cmd("/stat 1=charm", "stat set to charm.")
        self.call_cmd("/skill 1=seduction", "skill set to seduction.")
        self.call_cmd("/diff 1=25", "difficulty set to 25.")
        self.call_cmd("/diff 1=hard", "difficulty set to %s." % CrisisAction.HARD_DIFFICULTY)
        self.call_cmd("/assign 1=Testaccount", "gm set to Testaccount.|GM for the action set to Testaccount")
        self.call_cmd("/invite 1=TestAccount2", "The owner of an action cannot be an assistant.")
        self.call_cmd("/invite 1=TestAccount", "You have new informs. Use @inform 1 to read them."
                                               "|You have invited Testaccount to join your action.")
        self.account2.pay_resources = Mock()
        self.call_cmd("/charge 1=economic,2000", "2000 economic added. Action Resources: economic 2000")
        self.account2.pay_resources.assert_called_with("economic", 2000)
        self.caller.inform = Mock()
        self.account2.inform = Mock()
        action.ask_question("foo inform")
        self.caller.inform.assert_called_with('{cTestaccount2{n added a comment/question about Action #1:\nfoo inform',
                                              category='Action questions')
        self.call_cmd("/ooc/allowedit 1=Sure go nuts", "editable set to True.|Answer added.")
        self.account2.inform.assert_called_with('GM Testaccount has posted a followup to action 1: Sure go nuts',
                                                append=False, category='Actions', week=1)
        self.assertEquals(action.editable, True)
        self.account2.gain_resources = Mock()
        self.call_cmd("/cancel 1", "Action cancelled.")
        self.account2.gain_resources.assert_called_with("economic", 2000)
        self.assertEquals(self.assetowner2.vault, 50)
        self.assertEquals(action.status, CrisisAction.CANCELLED)
        self.call_cmd("/markpending 1", "status set to Pending Resolution.")
        self.assertEquals(action.status, CrisisAction.PENDING_PUBLISH)
        self.call_cmd("/publish 1=story test", "That story already has an action written. " 
                      "To prevent accidental overwrites, please change "
                      "it manually and then /publish without additional arguments.")
        action.story = ""
        action.ask_question("another test question")
        self.call_cmd("/markanswered 1", "You have marked the questions as answered.")
        self.assertEqual(action.questions.last().mark_answered, True)
        self.call_cmd("1", "Action ID: #1  Date Submitted: %s\n" % (now.strftime("%x %X")) +
                           "Action by Testaccount2\nSummary: test summary\nAction: test\n"
                           "[physically present] Dice check: Stat: perception, Skill: investigation  Diff: 60\n"
                           "Testaccount2 OOC intentions: ooc intent test\n\nOOC Notes and GM responses\n"
                           "Testaccount2 OOC Question: foo inform\nReply by Testaccount: Sure go nuts\n"
                           "Testaccount2 OOC Question: another test question\nOutcome Value: 0\nStory Result: \n"
                           "Secret Story sekritfoo\nResources: economic 2000, silver 50\n[STATUS: Pending Resolution]")
        self.call_cmd("/publish 1=story test", "You have published the action and sent the players informs.")
        self.assertEquals(action.status, CrisisAction.PUBLISHED)
        self.account2.inform.assert_called_with('{wGM Response to story action of Testaccount2\n'
                                                '{wRolls:{n 0\n\n{wStory Result:{n story test\n\n',
                                                append=False, category='Actions', week=1)
        mock_inform_staff.assert_called_with('Action 1 has been published by Testaccount:\n'
                                             '{wGM Response to story action'
                                             ' of Testaccount2\n{wRolls:{n 0\n\n{wStory Result:{n story test\n\n',
                                             post='{wSummary of action 1{n\nAction by {cTestaccount2{n: {wSummary:{n '
                                                  'test summary\n\n{wStory Result:{n story test\n'
                                                  '{wSecret Story{n sekritfoo',
                                             subject='Action 1 Published')
        with patch('server.utils.arx_utils.broadcast_msg_and_post') as mock_msg_and_post:
            from web.character.models import Story, Chapter, Episode
            chapter = Chapter.objects.create(name="test chapter")
            Episode.objects.create(name="test episode", chapter=chapter)
            Story.objects.create(name="test story", current_chapter=chapter)
            self.call_cmd("/gemit 1=test gemit", "StoryEmit created.")
            mock_msg_and_post.assert_called_with("test gemit", self.caller, episode_name="test episode")
            mock_inform_staff.assert_called_with('Action 1 has been published by Testaccount:\n{wGM Response to story '
                                                 'action of Testaccount2\n{wRolls:{n 0\n\n'
                                                 '{wStory Result:{n story test\n\n',
                                                 post='{wSummary of action 1{n\nAction by {cTestaccount2{n: '
                                                      '{wSummary:{n test summary\n\n'
                                                      '{wStory Result:{n story test\n{wSecret '
                                                      'Story{n sekritfoo', subject='Action 1 Published')


class OverridesTests(ArxCommandTest):
    def test_cmd_give(self):
        self.cmd_class = overrides.CmdGive
        self.caller = self.char1
        self.call_cmd("obj to char2", "You are not holding Obj.")
        self.obj1.move_to(self.char1)
        self.call_cmd("obj to char2", "You give Obj to Char2")
        self.char1.currency = 50
        self.call_cmd("-10 silver to char2", "Amount must be positive.")
        self.call_cmd("75 silver to char2", "You do not have that much money to give.")
        self.call_cmd("25 silver to char2", "You give coins worth 25.0 silver pieces to Char2.")
        self.assetowner.economic = 50
        self.call_cmd("/resource economic,60 to TestAccount2", "You do not have enough economic resources.")
        self.account2.inform = Mock()
        self.call_cmd("/resource economic,50 to TestAccount2", "You give 50 economic resources to Char2.")
        self.assertEqual(self.assetowner2.economic, 50)
        self.account2.inform.assert_called_with("Char has given 50 economic resources to you.", category="Resources")

    def test_cmd_say(self):
        self.cmd_class = overrides.CmdArxSay
        self.caller = self.char1
        self.char2.msg = Mock()
        self.call_cmd("testing", 'You say, "testing"')
        self.char2.msg.assert_called_with(from_obj=self.char1, text=('Char says, "testing{n"', {}),
                                          options={'is_pose': True})
        self.caller.db.currently_speaking = "foobar"
        self.call_cmd("testing lang", 'You say in Foobar, "testing lang"')
        self.char2.msg.assert_called_with(from_obj=self.char1, text=('Char says in Foobar, "testing lang{n"', {}),
                                          options={'language': 'foobar', 'msg_content': "testing lang",
                                                   'is_pose': True})
        self.char1.fakename = "Bob the Faker"
        self.caller.db.currently_speaking = None
        self.call_cmd("test", 'You say, "test"')
        self.char2.msg.assert_called_with(from_obj=self.char1, text=('Bob the Faker says, "test{n"', {}),
                                          options={'is_pose': True})
        self.char2.tags.add("story_npc")
        self.call_cmd("test", 'You say, "test"')
        self.char2.msg.assert_called_with('Bob the Faker {c(Char){n says, "test{n"', options={'is_pose': True},
                                          from_obj=self.char1)


class SocialTests(ArxCommandTest):
    def test_cmd_watch(self):
        self.cmd_class = social.CmdWatch
        self.caller = self.account
        max_size = social.CmdWatch.max_watchlist_size
        self.call_cmd("testaccount2", "You start watching Char2.")
        self.assertTrue(self.char2 in self.caller.db.watching)
        self.call_cmd("testaccount2", "You are already watching Char2.")
        self.call_cmd("/hide", "Hiding set to True.")
        self.call_cmd("/hide", "Hiding set to False.")
        self.call_cmd("/stop testAccount2", "Stopped watching Char2.")
        self.assertTrue(self.char2 not in self.caller.db.watching)
        for _ in range(max_size):
            self.caller.db.watching.append(self.char2)
        self.call_cmd("testAccount2", "You may only have %s characters on your watchlist." % max_size)
