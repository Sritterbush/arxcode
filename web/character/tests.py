"""
Tests for the Character app. Mostly this will be investigations/clue stuff.
"""
from mock import Mock

from django.test import Client
from django.urls import reverse

from server.utils.test_utils import ArxCommandTest, ArxTest
from web.character import investigation, scene_commands
from web.character.models import Clue, Revelation


class InvestigationTests(ArxCommandTest):
    def setUp(self):
        super(InvestigationTests, self).setUp()
        self.clue = Clue.objects.create(name="test clue", rating=10, desc="test clue desc")
        self.clue2 = Clue.objects.create(name="test clue2", rating=50, desc="test clue2 desc")
        self.revelation = Revelation.objects.create(name="test revelation", desc="test rev desc",
                                                    required_clue_value=60)
        self.clue_disco = self.roster_entry.clues.create(clue=self.clue, roll=200, message="additional text test")
        self.clue_disco2 = self.roster_entry.clues.create(clue=self.clue2, roll=50, message="additional text test2")
        self.revelation.clues_used.create(clue=self.clue)
        self.revelation.clues_used.create(clue=self.clue2)

    def test_cmd_clues(self):
        from datetime import datetime
        self.setup_cmd(investigation.CmdListClues, self.account)
        self.call_cmd("1", "test clue\nRating: 10\ntest clue desc")
        self.call_cmd("/addnote 1=test note", "test clue\nRating: 10\ntest clue desc\n\nadditional text test"
                                              "\n[%s] TestAccount wrote: test note" % datetime.now().strftime("%x %X"))
        self.call_cmd("/share 1=Testaccount2", "Sharing the clue(s) with them would cost 101 action points.")
        self.roster_entry.action_points = 101
        self.call_cmd("/share 1=Testaccount2", "You have shared the clue(s) 'test clue' with Char2.")
        self.call_cmd("/share 2=Testaccount2", "No clue found by that ID.")
        self.clue_disco2.roll += 450
        self.clue_disco2.save()
        self.assertFalse(bool(self.roster_entry2.revelations.all()))
        self.call_cmd("/share 2=Testaccount2/Love Tehom", "You have shared the clue(s) 'test clue2' with Char2.\nYour note: Love Tehom")
        self.assertTrue(bool(self.roster_entry2.revelations.all()))
        self.caller = self.account2
        self.call_cmd("2", "test clue2\nRating: 10\ntest clue2 desc\nThis clue was shared with you by Char1, who noted: Love Tehom\n")


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
                                                " 'testing'.", category="Flashbacks")
        self.call_cmd("/post 1", "You must include a message.")                                            
        self.assertEqual(self.char1.messages.num_flashbacks, 0)
        self.call_cmd("/post 1=A new testpost", "You have posted a new message to testing: A new testpost")
        self.assertEqual(self.char1.messages.num_flashbacks, 1)
        self.account2.inform.assert_called_with("There is a new post on flashback #1 by Char.",
                                                category="Flashbacks")
        self.caller = self.account2
        self.call_cmd("/catchup 1", "New posts for #1\nChar wrote: A new testpost\n")
        self.call_cmd("/summary 1=test", "Only the flashback's owner may use that switch.")
        self.caller = self.account
        self.call_cmd("/uninvite 1=Testaccount2", "You have uninvited Testaccount2 from this flashback.")
        self.account2.inform.assert_called_with("You have been removed from flashback #1.", category="Flashbacks")
        self.call_cmd("/summary 1=test summary", "summary set to: test summary.")


class ViewTests(ArxTest):
    def setUp(self):
        super(ViewTests, self).setUp()
        self.client = Client()

    def test_sheet(self):
        response = self.client.get(self.char2.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['character'], self.char2)
        self.assertEqual(response.context['show_hidden'], False)
        self.assertEqual(self.client.login(username='TestAccount2', password='testpassword'), True)
        response = self.client.get(self.char2.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['show_hidden'], True)
        self.client.logout()

    def test_view_flashbacks(self):
        response = self.client.get(reverse('character:list_flashbacks', kwargs={'object_id': self.char2.id}))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.login(username='TestAccount2', password='testpassword'), True)
        response = self.client.get(reverse('character:list_flashbacks', kwargs={'object_id': self.char2.id}))
        self.assertEqual(response.status_code, 200)
