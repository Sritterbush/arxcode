import re

from mock import Mock

from evennia.commands.default.tests import CommandTest
from evennia.server.sessionhandler import SESSIONS
from evennia.utils import ansi, utils
from typeclasses.characters import Character
from typeclasses.accounts import Account
from typeclasses.objects import Object
from typeclasses.rooms import ArxRoom
from typeclasses.exits import Exit


# set up signal here since we are not starting the server

_RE = re.compile(r"^\+|-+\+|\+-+|--*|\|(?:\s|$)", re.MULTILINE)


class ArxCommandTest(CommandTest):
    """
    child of Evennia's CommandTest class specifically for Arx. We'll add some
    objects that our characters/players would be expected to have for any 
    particular test.
    """
    account_typeclass = Account
    object_typeclass = Object
    character_typeclass = Character
    exit_typeclass = Exit
    room_typeclass = ArxRoom
    cmd_class = None
    caller = None

    def setUp(self):
        super(ArxCommandTest, self).setUp()
        from world.dominion.setup_utils import setup_dom_for_player, setup_assets
        from web.character.models import Roster
        self.dompc = setup_dom_for_player(self.account)
        self.dompc2 = setup_dom_for_player(self.account2)
        self.assetowner = setup_assets(self.dompc, 0)
        self.assetowner2 = setup_assets(self.dompc2, 0)
        self.active_roster = Roster.objects.create(name="Active")
        self.roster_entry = self.active_roster.entries.create(player=self.account, character=self.char1)
        self.roster_entry2 = self.active_roster.entries.create(player=self.account2, character=self.char2)

    def call_cmd(self, args, msg):
        self.call(self.cmd_class(), args, msg, caller=self.caller)

    # noinspection PyBroadException
    def call(self, cmdobj, args, msg=None, cmdset=None, noansi=True, caller=None, receiver=None, cmdstring=None,
             obj=None):
        """
        Test a command by assigning all the needed
        properties to cmdobj and  running
            cmdobj.at_pre_cmd()
            cmdobj.parse()
            cmdobj.func()
            cmdobj.at_post_cmd()
        The msgreturn value is compared to eventual
        output sent to caller.msg in the game

        Returns:
            msg (str): The received message that was sent to the caller.

        """
        caller = caller if caller else self.char1
        receiver = receiver if receiver else caller
        cmdobj.caller = caller
        cmdobj.cmdstring = cmdstring if cmdstring else cmdobj.key
        cmdobj.args = args
        cmdobj.cmdset = cmdset
        cmdobj.session = SESSIONS.session_from_sessid(1)
        cmdobj.account = self.account
        cmdobj.raw_string = cmdobj.key + " " + args
        cmdobj.obj = obj or (caller if caller else self.char1)
        # test
        old_msg = receiver.msg
        try:
            receiver.msg = Mock()
            cmdobj.at_pre_cmd()
            cmdobj.parse()
            cmdobj.func()
            cmdobj.at_post_cmd()
        except Exception:
            import traceback
            receiver.msg(traceback.format_exc())
        finally:
            # clean out prettytable sugar. We only operate on text-type
            stored_msg = [args[0] if args and args[0] else kwargs.get("text", utils.to_str(kwargs, force_string=True))
                          for name, args, kwargs in receiver.msg.mock_calls]
            # Get the first element of a tuple if msg received a tuple instead of a string
            stored_msg = [smsg[0] if hasattr(smsg, '__iter__') else smsg for smsg in stored_msg]
            if msg is not None:
                returned_msg = "||".join(_RE.sub("", str(mess)) for mess in stored_msg)
                returned_msg = ansi.parse_ansi(returned_msg, strip_ansi=noansi).strip()
                if msg == "" and returned_msg or not returned_msg.startswith(msg.strip()):
                    sep1 = "\n" + "="*30 + "Wanted message" + "="*34 + "\n"
                    sep2 = "\n" + "="*30 + "Returned message" + "="*32 + "\n"
                    sep3 = "\n" + "="*78
                    retval = sep1 + msg.strip() + sep2 + returned_msg + sep3
                    raise AssertionError(retval)
            else:
                returned_msg = "\n".join(str(msg) for msg in stored_msg)
                returned_msg = ansi.parse_ansi(returned_msg, strip_ansi=noansi).strip()
            receiver.msg = old_msg

        return returned_msg
