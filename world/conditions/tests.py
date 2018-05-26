"""
Tests for Conditions app
"""
# -*- coding: utf-8 -*-
from server.utils.test_utils import ArxCommandTest
from . import condition_commands


class ConditionsCommandsTests(ArxCommandTest):
    def test_modifiers_cmd(self):
        self.setup_cmd(condition_commands.CmdModifiers, self.char1)
        self.call_cmd("char2", "Modifiers on Char2: ")
        self.call_cmd("/targetmod char2=10,abyssal,any combat",
                      "You have added a modifier to Char2: "
                      "Modifier on Char2 of +10 against abyssal for Any Combat checks.")
        self.call_cmd("char2", "Modifiers on Char2: Modifier on Char2 of +10 against abyssal for Any Combat checks")
        self.call_cmd("/usermod here=10,divine,defense",
                      "You have added a modifier to Room: Modifier on Room of +10 for divine for Defense checks.")
        self.call_cmd("/search asdf", "Modifiers for/against asdf: ")
        self.call_cmd("/search divine", "Modifiers for/against divine: "
                                        "Modifier on Room of +10 for divine for Defense checks")
