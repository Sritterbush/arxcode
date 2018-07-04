"""
Tests for different general commands. Tests for other command sets or for different apps can be found elsewhere.
"""

from mock import Mock, patch
from datetime import datetime, timedelta

from server.utils.test_utils import ArxCommandTest
from world.dominion.models import CrisisAction, Crisis, Army, RPEvent
from . import story_actions, overrides, social, staff_commands, roster


class StoryActionTests(ArxCommandTest):

    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_action(self, mock_get_week, mock_inform_staff):
        mock_get_week.return_value = 1
        self.setup_cmd(story_actions.CmdAction, self.account)
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
        self.call_cmd("/roll 1=foo,bar", "You must provide a valid stat and skill.")
        self.call_cmd("/roll 1=Strength,athletics", "stat set to strength.|skill set to athletics.")
        self.call_cmd("/setsecret 1=sekrit", "Secret actions set to sekrit.")
        self.call_cmd("/invite 1=foo", "Could not find 'foo'.")
        self.call_cmd("/invite 1=TestAccount2", "You have invited Testaccount2 to join your action.")
        self.caller = self.account2
        self.caller.pay_action_points = Mock(return_value=False)
        self.call_cmd("/setaction 1=test assist", "You do not have enough action points.")
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd("/setaction 1=test assist",
                      "Action by Testaccount for Test Crisis now has your assistance: test assist")
        Army.objects.create(name="test army", owner=self.assetowner)
        self.call_cmd("/add 1=army,1", "You don't have access to that Army.|Failed to send orders to the army.")
        self.call_cmd("/readycheck 1", "Only the action leader can use that switch.")
        self.caller = self.account
        self.call_cmd("/add 1=foo,bar", "Invalid type of resource.")
        self.call_cmd("/add 1=ap,50", "50 ap added. Action #1 Resources: extra action points 50")
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
        mock_inform_staff.assert_called_with('Testaccount submitted action #1. {wSummary:{n summary')
        self.call_cmd("/makepublic 1", "The action must be finished before you can make details of it public.")
        action.status = CrisisAction.PUBLISHED
        self.call_cmd("/makepublic 1", "You have gained 2 xp for making your action public.")
        self.call_cmd("/makepublic 1", "That action has already been made public.")
        self.call_cmd("/question 1=test question", "You have submitted a question: test question")
        self.call_cmd("/newaction test crisis=testing",
                      "You have already submitted an action for this stage of the crisis.")
        action_2 = self.dompc.actions.create(actions="completed storyaction", status=CrisisAction.PUBLISHED,
                                             date_submitted=datetime.now())
        action_2.assisting_actions.create(dompc=self.dompc2)
        action_3 = self.dompc.actions.create(actions="another completed storyaction", status=CrisisAction.PUBLISHED,
                                             date_submitted=datetime.now())
        action_3.assisting_actions.create(dompc=self.dompc2)
        draft = self.dompc.actions.create(actions="storyaction draft", status=CrisisAction.DRAFT,
                                          category=CrisisAction.RESEARCH,
                                          topic="test summary", stat_used="stat", skill_used="skill")
        draft.questions.create(is_intent=True, text="intent")
        self.call_cmd("/invite 4=TestAccount2", "You have invited Testaccount2 to join your action.")
        self.call_cmd("/submit 4", "You are permitted 2 action requests every 30 days. Recent actions: 1, 2, 3")
        self.caller = self.account2
        # unused actions can be used as assists. Try with one slot free to be used as an assist
        self.dompc2.actions.create(actions="dompc completed storyaction", status=CrisisAction.PUBLISHED,
                                   date_submitted=datetime.now())
        self.call_cmd("/setaction 4=test assist", 'Action by Testaccount now has your assistance: test assist')
        self.dompc2.actions.create(actions="another dompc completed storyaction", status=CrisisAction.PUBLISHED,
                                   date_submitted=datetime.now())
        # now both slots used up
        self.call_cmd("/setaction 4=test assist", "You are assisting too many actions.")
        # test making an action free
        action_2.free_action = True
        action_2.save()
        self.call_cmd("/setaction 4=test assist", 'Action by Testaccount now has your assistance: test assist')
        # now test again when it's definitely not free
        action_2.free_action = False
        action_2.save()
        self.call_cmd("/setaction 4=test assist", "You are assisting too many actions.")
        # cancel an action to free a slot
        action_2.status = CrisisAction.CANCELLED
        action_2.save()
        self.call_cmd("/setaction 4=test assist", 'Action by Testaccount now has your assistance: test assist')
        action.status = CrisisAction.CANCELLED
        action.save()
        # now back to player 1 to see if they can submit after the other actions are gone
        self.caller = self.account
        self.call_cmd("/submit 4", "Before submitting this action, make certain that you have invited all players you "
                                   "wish to help with the action, and add any resources necessary. Any invited players "
                                   "who have incomplete actions will have their assists deleted.\nThe following "
                                   "assistants are not ready and will be deleted: Testaccount2\nWhen ready, /submit "
                                   "the action again.")
        # make sure they can't create a new one while they have a draft
        self.call_cmd("/newaction test crisis=testing",
                      "You have drafted an action which needs to be submitted or canceled: 4")
        action_4 = self.dompc.actions.last()
        action_4.status = CrisisAction.CANCELLED
        action_4.save()
        self.call_cmd("/newaction test crisis=testing", "You have drafted a new action (#7) to respond to Test Crisis: "
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
        self.setup_cmd(story_actions.CmdGMAction, self.account)
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
        self.call_cmd("/charge 1=economic,2000", "2000 economic added. Action #1 Resources: economic 2000, silver 50")
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
        self.call_cmd("/togglefree 1", 'You have made their action free and the player has been informed.')
        self.account2.inform.assert_called_with('Your action is now a free action and will '
                                                'not count towards your maximum.',
                                                append=False, category='Actions', week=1)
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
        self.call_cmd("1", "Action ID: #1 Category: Unknown  Date: %s  " % (now.strftime("%x %X")) +
                           "GM: Testaccount\nAction by Testaccount2\nSummary: test summary\nAction: test\n"
                           "[physically present] Perception (stat) + Investigation (skill) at difficulty 60\n"
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
                                             subject='Action 1 Published by Testaccount')
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
                                                      'Story{n sekritfoo', subject='Action 1 Published by Testaccount')
        RPEvent.objects.create(name="test event")
        self.call_cmd("/addevent 1=1", "Added event: test event")
        self.call_cmd("/rmevent 1=1", "Removed event: test event")


class OverridesTests(ArxCommandTest):
    def test_cmd_give(self):
        from typeclasses.wearable.wearable import Wearable
        from evennia.utils.create import create_object
        self.setup_cmd(overrides.CmdGive, self.char1)
        self.call_cmd("obj to char2", "You are not holding Obj.")
        self.obj1.move_to(self.char1)
        self.call_cmd("obj to char2", "You give Obj to Char2.")
        wearable = create_object(typeclass=Wearable, key="worn", location=self.char1)
        wearable.wear(self.char1)
        self.call_cmd("worn to char2", 'worn is currently worn and cannot be moved.')
        wearable.remove(self.char1)
        self.call_cmd("worn to char2", "You give worn to Char2.")
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
        self.setup_cmd(overrides.CmdArxSay, self.char1)
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

    def test_cmd_who(self):
        self.setup_cmd(overrides.CmdWho, self.account2)
        self.call_cmd("asdf", "Players:\n\nPlayer name Fealty Idle \n\nShowing 0 out of 1 unique account logged in.")


class RosterTests(ArxCommandTest):
    def setUp(self):
        """Adds rosters and an announcement board"""
        from web.character.models import Roster
        from typeclasses.bulletin_board.bboard import BBoard
        from evennia.utils.create import create_object
        super(RosterTests, self).setUp()
        self.available_roster = Roster.objects.create(name="Available")
        self.gone_roster = Roster.objects.create(name="Gone")
        self.bboard = create_object(typeclass=BBoard, key="Roster Changes")

    @patch.object(roster, "inform_staff")
    def test_cmd_admin_roster(self, mock_inform_staff):
        from world.dominion.models import Organization
        self.org = Organization.objects.create(name="testorg")
        self.member = self.org.members.create(player=self.dompc2, rank=2)
        self.setup_cmd(roster.CmdAdminRoster, self.account)
        self.bboard.bb_post = Mock()
        self.dompc2.patron = self.dompc
        self.dompc2.save()
        self.call_cmd("/retire char2", 'Random password generated for Testaccount2.')
        self.assertEqual(self.roster_entry2.roster, self.available_roster)
        entry = self.roster_entry2
        post = "%s no longer has an active player and is now available for applications." % entry.character
        url = "http://play.arxmush.org" + entry.character.get_absolute_url()
        post += "\nCharacter page: %s" % url
        subject = "%s now available" % entry.character
        self.bboard.bb_post.assert_called_with(self.caller, post, subject=subject, poster_name="Roster")
        mock_inform_staff.assert_called_with("Testaccount has returned char2 to the Available roster.")
        self.assertEqual(self.member.rank, 3)
        self.assertEqual(self.dompc2.patron, None)


# noinspection PyUnresolvedReferences
class SocialTests(ArxCommandTest):
    def test_cmd_where(self):
        self.setup_cmd(social.CmdWhere, self.account)
        self.call_cmd("/shops", "List of shops:")
        self.room1.tags.add("shop")
        self.room1.db.shopowner = self.char2
        self.call_cmd("/shops", "List of shops:\nRoom: Char2")
        from web.character.models import Roster
        self.roster_entry2.roster = Roster.objects.create(name="Bishis")
        self.call_cmd("/shops/all", "List of shops:\nRoom: Char2 (Inactive)")
        # TODO: create AccountHistory thingies, set a firstimpression for one of the Chars
        # TODO: test /firstimp, /rs, /watch
        self.call_cmd("", 'Locations of players:\nPlayers who are currently LRP have a + by their name, '
                          'and players who are on your watch list have a * by their name.\nRoom: Char, Char2')
        self.char2.fakename = "Kamda"
        self.call_cmd("", 'Locations of players:\nPlayers who are currently LRP have a + by their name, '
                          'and players who are on your watch list have a * by their name.\nRoom: Char')
        self.room1.tags.add("private")
        self.call_cmd("", "No visible characters found.")

    def test_cmd_watch(self):
        self.setup_cmd(social.CmdWatch, self.account)
        max_size = social.CmdWatch.max_watchlist_size
        self.call_cmd("testaccount2", "You start watching Char2.")
        self.assertTrue(self.char2 in self.caller.db.watching)
        self.call_cmd("testaccount2", "You are already watching Char2.")
        self.call_cmd("/hide", "Hiding set to True.")
        self.assertTrue(bool(self.caller.db.hide_from_watch))
        self.call_cmd("/hide", "Hiding set to False.")
        self.assertFalse(bool(self.caller.db.hide_from_watch))
        self.call_cmd("/stop testAccount2", "Stopped watching Char2.")
        self.assertTrue(self.char2 not in self.caller.db.watching)
        for _ in range(max_size):
            self.caller.db.watching.append(self.char2)
        self.call_cmd("testAccount2", "You may only have %s characters on your watchlist." % max_size)

    def test_cmd_rphooks(self):
        self.setup_cmd(social.CmdRPHooks, self.account)
        self.call_cmd("/add bad: name", "That category name contains invalid characters.")
        self.call_cmd("/add catname=desc", "Added rphook tag: catname: desc.")
        self.call_cmd("/remove foo", "No rphook by that category name.")
        self.call_cmd("/remove catname", "Removed.")

    def test_cmd_messenger(self):
        self.setup_cmd(social.CmdMessenger, self.char2)
        self.char1.tags.add("no_messengers")
        self.char2.tags.add("no_messengers")
        self.call_cmd("testaccount=hiya", 'Char cannot send or receive messengers at the moment.'
                                          '|No valid receivers found.')
        self.char2.tags.remove("no_messengers")
        self.call_cmd("testaccount=hiya", 'Char cannot send or receive messengers at the moment.'
                                          '|No valid receivers found.')
        self.char1.tags.remove("no_messengers")
        self.call_cmd("testaccount=hiya", "You dispatch a messenger to Char with the following message:\n\n'hiya'")

    @patch.object(social, "inform_staff")
    @patch.object(social, "datetime")
    def test_cmd_rpevent(self, mock_datetime, mock_inform_staff):
        from evennia.utils.create import create_script
        from typeclasses.scripts.event_manager import EventManager
        script = create_script(typeclass=EventManager, key="Event Manager")
        script.post_event = Mock()
        now = datetime.now()
        mock_datetime.strptime = datetime.strptime
        mock_datetime.now = Mock(return_value=now)
        self.setup_cmd(social.CmdCalendar, self.account1)
        self.call_cmd("/create test_event", 'Starting project. It will not be saved until you submit it. Does not '
                                            'persist through logout/server reload.|Event name: test_event\nGMs: \n'
                                            'Date: No date yet\nLocation: No location set.\n'
                                            'Desc: No description set yet\nPublic: Public\nHosts: Testaccount\n'
                                            'Largesse: 0\nRoom Desc:')
        self.call_cmd("/desc test description", 'Desc of event set to:\ntest description')
        self.call_cmd('/submit', 'Name, date, desc, and hosts must be defined before you submit.|'
                                 'Event name: test_event\nGMs: \nDate: No date yet\nLocation: No location set.\n'
                                 'Desc: test description\nPublic: Public\nHosts: Testaccount\nLargesse: 0\nRoom Desc:')
        self.call_cmd("/date 26:35 sdf", "Date did not match 'mm/dd/yy hh:mm' format.|You entered: 26:35 sdf")
        self.call_cmd("/date 1/1/01 12:35", "You cannot make an event for the past.")
        datestr = now.strftime("%x %X")
        self.call_cmd("/date 12/12/30 12:00", ('Date set to 12/12/30 12:00:00.|' +
                                               ('Current time is {} for comparison.|'.format(datestr)) +
                                               'Number of events within 2 hours of that date: 0'))
        self.call_cmd("/addgm testaccount", "Testaccount added to GMs.|GMs are: Testaccount|"
                                            "Reminder - please only add a GM for an event if it's an actual "
                                            "player-run plot. Tagging a social event as a PRP is strictly prohibited. "
                                            "If you tagged this as a PRP in error, use addgm with no arguments to "
                                            "remove GMs.")
        self.char1.db.currency = -1.0
        self.call_cmd("/largesse grand", 'That requires 10000 to buy. You have -1.0.')
        self.char1.db.currency = 10000
        self.call_cmd("/largesse grand", "Largesse level set to grand for 10000.")
        self.call_cmd('/submit', 'You pay 10000 coins for the event.|'
                                 'New event created: test_event at 12/12/30 12:00:00.')
        self.assertEqual(self.char1.db.currency, 0)
        event = RPEvent.objects.get(name="test_event")
        self.assertTrue(event.gm_event)
        script.post_event.assert_called_with(event, self.account,
                                             '{wEvent name:{n test_event\n{wGMs:{n Testaccount\n{wDate:{n 12/12/30 '
                                             '12:00:00\n{wLocation:{n No location set.\n{wDesc:{n test description\n'
                                             '{wPublic:{n Public\n{wHosts:{n Testaccount\n{wLargesse:{n grand\n'
                                             '{wRoom Desc:{n \n')
        mock_inform_staff.assert_called_with('New event created by Testaccount: test_event, '
                                             'scheduled for 12/12/30 12:00:00.')


# noinspection PyUnresolvedReferences
class SocialTestsPlus(ArxCommandTest):
    num_additional_characters = 1

    @patch.object(social, "inform_staff")
    def test_cmd_randomscene(self, mock_inform_staff):
        from web.character.models import PlayerAccount
        self.setup_cmd(social.CmdRandomScene, self.char1)
        self.char2.sessions.all = Mock(return_value="Meow")
        self.account2.db_is_connected = True
        self.account2.last_login = datetime.now()
        self.account2.save()
        self.roster_entry2.current_account = PlayerAccount.objects.create(email="foo")
        self.roster_entry2.save()
        self.call_cmd("", "@Randomscene Information: \nRandomly generated RP partners for this week: Char2"
                          "\nReminder: Please only /claim those you have interacted with significantly in a scene.")
        self.char1.player_ob.db.random_scenelist = [self.char2, self.char2, self.char3]
        self.call_cmd("/online", "@Randomscene Information: Only displaying online characters."
                                 "\nRandomly generated RP partners for this week: Char2 and Char2"
                                 "\nReminder: Please only /claim those you have interacted with significantly "
                                 "in a scene.")
        self.call_cmd("/claim Char2", 'You must include some summary of the scene. It may be quite short.')
        self.call_cmd("/claim Char2=test test test", 'You have sent Char2 a request to validate your scene: '
                                                     'test test test')
        mock_inform_staff.assert_called_with("Char has completed this random scene with Char2: test test test")
        self.call_cmd("/claim Char2=test test test", "You have already claimed a scene with Char2 this week.")
        self.char2.db.false_name = "asdf"
        self.char2.aliases.add("asdf")
        self.caller = self.char3  # mask test, not staff
        self.call_cmd("/claim Char2=meow", "Could not find 'Char2'.")
        self.call_cmd("/claim asdf=meow", "You cannot claim 'asdf'.")
        self.caller = self.char1
        self.call_cmd("/claim Char2=test test test", "You cannot claim 'Char2'.")
        self.call_cmd("", "@Randomscene Information: \nRandomly generated RP partners for this week: Char2 and Char3"
                          "\nReminder: Please only /claim those you have interacted with significantly in a scene."
                          "\nThose you have already RP'd with this week: Char2")
        self.caller = self.char2
        self.call_cmd("/viewrequests", '| Name                               | Summary                               '
                                       '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n'
                                       '| Char                               | test test test')
        self.call_cmd("/validate Tehom",
                      'No character by that name has sent you a request.|\n'
                      '| Name                               | Summary                               '
                      '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n'
                      '| Char                               | test test test')
        self.call_cmd("/validate Char", "Validating their scene. Both of you will receive xp for it later.")
        self.assertEqual(self.char2.player_ob.db.validated_list, [self.char1])


class StaffCommandTests(ArxCommandTest):
    def test_cmd_admin_break(self):
        from server.utils.arx_utils import check_break
        now = datetime.now()
        future = now + timedelta(days=1)
        self.setup_cmd(staff_commands.CmdAdminBreak, self.account)
        self.call_cmd("", "Current end date is: No time set.")
        self.assertFalse(check_break())
        self.call_cmd("asdf", "Date did not match 'mm/dd/yy hh:mm' format.|You entered: asdf|"
                              "Current end date is: No time set.")
        future_string = future.strftime("%m/%d/%y %H:%M")
        self.call_cmd(future_string, "Break date updated.|Current end date is: %s." % future_string)
        self.assertTrue(check_break())
        self.call_cmd("/toggle_allow_ocs", "Allowing character creation during break has been set to True.")
        self.assertFalse(check_break(checking_character_creation=True))
        self.call_cmd("/toggle_allow_ocs", "Allowing character creation during break has been set to False.")
        self.assertTrue(check_break(checking_character_creation=True))
        past = now - timedelta(days=1)
        past_string = past.strftime("%m/%d/%y %H:%M")
        self.call_cmd(past_string, "Break date updated.|Current end date is: %s." % past_string)
        self.assertFalse(check_break())
