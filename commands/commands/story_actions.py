from datetime import datetime

from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.utils.evtable import EvTable
from server.utils.arx_utils import inform_staff, get_week
from django.db.models import Q


class CmdAction(MuxPlayerCommand):
    """
    A character's story actions that a GM responds to.
    
    Usage:
        @action/newaction [<crisis #>=]<action you're taking>
        @action/stat <action #>=<stat>
        @action/skill <action #>=<skill>
        @action/ooc <action #>=<ooc description of your intent, or follow-up question>
        @action/cancel <action #>
        @action/submit <action #>
    Options:
        @action[/public] [<action #>]
        @action/invite <action #>=<character>
        @action/decline <action #>
        @action/setaction <action #>=<action text>
        @action/setsecret <action #>=<secret action>
        @action/setcrisis <action #>=<crisis #>
        @action/add <action #>,<resource or 'ap' or 'army'>=<amount or army ID#>
        @action/toggleview <action #>[=<assistant>]
        @action/togglepublic <action #>
        
    Creating a new action costs Action Points (ap). It requires that you set stat/skill
    and a clear out-of-character description of your action's single goal before
    submitting it for GM response. The GM may require additional ooc information or
    ask you to edit with /setaction and then /submit again.
    
    With /invite you ask others to assist your action. Join (or edit) with /setaction;
    /decline to reject the invitation. A covert action can be added with /setsecret.
    With /setcrisis this becomes your response to a Crisis. Allocate resources with 
    /add by specifying which type (ap, army, social, silver, etc.,) and an amount, 
    or the ID# of the army. The /toggleview switch lets an assistant see the owner's
    secret action or vice-versa. The /togglepublic switch allows everyone to see
    your action once a GM writes an outcome and publishes it.
    """
    key = "@action"
    locks = "cmd:all()"
    help_category = "Dominion"
    
    def func(self):
        if "newaction" in self.switches:
            return self.new_action()
        # action = self.get_action(self.lhs)
        # if not action:
        #     return
        # if "stat" in self.switches or "skill" in self.switches:
        #     return self.set_stat_or_skill(action)
        # elif "ooc" in self.switches:
        #     return self.write_ooc(action)
        # elif "cancel" in self.switches:
        #     return self.cancel_action(action)
        # elif "submit" in self.switches:
        #     return self.submit_action(action)
        # elif "invite" in self.switches:
        #     return self.invite_assistant(action)
        # elif "decline" in self.switches:
        #     return self.decline_action(action)
        # elif "setaction" in self.switches:
        #     return self.set_action(action)
        # elif "setcrisis" in self.switches:
        #     return self.set_crisis(action)
        # elif "add" in self.switches:
        #     return self.add_resource(action)
        # elif "toggleview" in self.switches:
        #     return self.toggle_view(action)
        # elif "togglepublic" in self.switches:
        #     return self.toggle_public(action)
        # elif not self.switches or if "public" in self.switches:
        #     return self.list_actions()
        else:
            self.msg("Invalid switch. See 'help @action'.")
    
    def new_action(self):
        """Create a new action."""
        if not self.args:
            self.msg("What action are you trying to take?")
            return
        crisis = None
        crisis_msg = ""
        if self.rhs:
            crisis = self.get_crisis(self.lhs)
            story = self.rhs
            crisis_msg = " to respond to %s" % str(crisis)
            if not crisis:
                return
        if not self.can_create(crisis):
            return
        if not self.rhs:
            story = self.lhs
        self.caller.Dominion.actions.create(story=story, crisis=crisis)
        self.msg("You have drafted a new action%s: %s" % (crisis_msg, story))
        return
    
    def get_crisis(self, arg):
        """Returns a Crisis from ID# in args"""
        pass
        
    def get_action(self, arg):
        """Returns an action from ID# args"""
        pass
        
    def can_create(self, crisis=None):
        #fucky crisis
        #ap
        #too many actions
        #already has one
        pass