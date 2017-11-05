from mock import Mock, patch, PropertyMock

from server.utils.test_utils import ArxCommandTest
from . import combat


class CombatCommandsTests(ArxCommandTest):

    @patch.object(combat, 'do_dice_check')
    def test_cmd_heal(self, mock_dice_check):
        mock_dice_check.return_value = 10
        self.cmd_class = combat.CmdHeal
        self.caller = self.char1
        self.call_cmd("char2", "Char2 does not require any medical attention.")
        self.char2.dmg = 20
        self.call_cmd("char2", "Char2 has not granted you permission to heal them. Have them use +heal/permit.")
        self.call(self.cmd_class(), "/permit char", "You permit Char to heal you.", caller=self.char2)
        event = Mock()
        gms = Mock()
        event.gms = gms
        event.room_desc = "room desc test"
        type(self.room1).event = PropertyMock(return_value=event)
        gms.all = Mock(return_value=[])
        self.caller = self.char2
        self.call_cmd("/gmallow char=10", "This may only be used by the GM of an event.")
        self.call_cmd("char2", "There is an event here and you have not been granted GM permission to use +heal.")
        gms.all.return_value = [self.dompc2]
        self.call_cmd("/gmallow char=10", "You have allowed Char to use +heal, with a bonus to their roll of 10.")
        self.assertEqual(self.char1.ndb.healing_gm_allow, 10)
        self.caller = self.char1
        self.call_cmd("char2", "You rolled a 10 on your heal roll.")
