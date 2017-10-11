from datetime import datetime

from django.db.models import Q

from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.utils.evtable import EvTable

from server.utils.arx_utils import inform_staff, get_week

from world.dominion.models import Crisis, CrisisAction, CrisisActionAssistant


class CmdAction(MuxPlayerCommand):
    """
    A character's story actions that a GM responds to.
    
    Usage:
        @action/newaction [<crisis #>=]<action you're taking>
        @action/tldr <action #>=<summary of your action>
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
    max_requests = 2
    num_days = 30
    
    def func(self):
        if not self.args:
            self.list_actions()
        if "newaction" in self.switches:
            return self.new_action()
        action = self.get_action(self.lhs)
        if not action:
            return
        if "stat" in self.switches or "skill" in self.switches:
            return self.set_stat_or_skill(action)
        if "tldr" in self.switches or "summary" in self.switches:
            return self.set_action_field(action, "summary", self.rhs)
        elif "ooc" in self.switches:
            return self.set_action_field(action, "ooc_intent", self.rhs, "OOC intentions for the action")
        elif "cancel" in self.switches:
            return self.cancel_action(action)
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
        else:
            self.msg("Invalid switch. See 'help @action'.")
            
    @property
    def dompc(self):
        """Shortcut for getting their dominion playerornpc object"""
        return self.caller.Dominion
            
    def list_actions(self):
        """Prints a table of the actions we've taken"""
        table = EvTable("ID", "Crisis", "Status")
        actions = self.dompc.actions.all()
        for action in actions:
            table.add_row(action.id, action.crisis, action.status)
        self.msg(table)
    
    def new_action(self):
        """Create a new action."""
        if not self.args:
            self.msg("What action are you trying to take?")
            return
        crisis = None
        crisis_msg = ""
        story = self.lhs
        if self.rhs:
            crisis = self.get_crisis(self.lhs)
            story = self.rhs
            crisis_msg = " to respond to %s" % str(crisis)
            if not crisis:
                return
        if not self.can_create(crisis):
            return
        self.dompc.actions.create(story=story, crisis=crisis)
        self.msg("You have drafted a new action%s: %s" % (crisis_msg, story))
    
    def get_crisis(self, arg):
        """Returns a Crisis from ID# in args."""
        try:
            if arg.isdigit():
                return Crisis.objects.get(id=arg)
            else:
                return Crisis.objects.get(name__iexact=arg)
        except Crisis.DoesNotExist:
            self.msg("No crisis matches %s." % arg)
        
    def get_action(self, arg, return_assist=True):
        """Returns an action we are involved in from ID# args.
        
            Args:
                arg (str): String to use to find the ID of the crisis action.
                return_assist (bool): Whether to return a CrisisActionAssistant instead if caller is an assistant.
                
            Returns:
                A CrisisAction or a CrisisActionAssistant depending if the caller is the owner of the main action or
                an assistant.
        """
        try:
            dompc = self.dompc
            action = CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct().get(id=arg)
            if return_assist:
                try:
                    action = action.assisting_actions.get(assistant=dompc)
                except CrisisActionAssistant.DoesNotExist:
                    pass
            return action
        except CrisisAction.DoesNotExist:
            self.msg("No action found by that ID.")
            self.list_actions()
    
    def get_my_actions(self, crisis=False, assists=False):
        """Returns caller's actions."""
        dompc = self.dompc
        if not assists:
            actions = dompc.actions.all()
        else:
            actions = CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct()
        if not crisis:
            actions = actions.filter(crisis__isnull=True)
        return actions
        
    def can_create(self, crisis=None):
        """Checks criteria for creating a new action."""
        if crisis and not self.can_set_crisis(crisis):
            return False
        my_draft = self.get_my_actions().filter(db_date_submitted__isnull=True).last()
        if my_draft:
            self.msg("You have drafted an action which needs to be submitted or canceled: %s" % my_draft.id)
            return False
        if not self.caller.pay_action_points(50):
            self.msg("You do not have enough action points.")
            return False
        return True
        
    def can_set_crisis(self, crisis):
        """Checks criteria for linking to a Crisis."""
        time = datetime.now()
        if crisis.end_date < time:
            self.msg("It is past the submit date for that crisis.")
            return False
        elif crisis.check_taken_action(dompc=self.dompc):
            self.msg("You have already submitted action for this stage of the crisis.")
            return False
        
    def set_stat_or_skill(self, action):
        """Sets a stat or skill for action or assistant"""
        if "skill" in self.switches:
            field_name = "skill"
        else:
            field_name = "stat"
        #TODO: make sure action is editable
        self.set_action_field(action, field_name, self.rhs)
        
    def set_action_field(self, action, field_name, value, verbose_name=None):
        if field_name == "ooc_intent" and action.ooc_intent:
            # TODO: if field exists, the command is being used to add a follow-up question
            # This may be better off as a method that points to set_action_field
            pass
        #TODO: make sure action is editable
        setattr(action, field_name, value)
        action.save()
        verbose_name = verbose_name or field_name
        self.msg("%s set to %s." % (verbose_name, value))
        
    def cancel_action(self, action):
        if not action.check_can_cancel():
            self.msg("You cannot cancel the action at this time.")
            return
        action.cancel()
        self.msg("Action cancelled.")
        
    def submit_action(self, action):
        """I love a bishi."""
        if not action.crisis:
            from datetime import timedelta
            offset = timedelta(days=-self.num_days)
            old = datetime.now() + offset
            recent_actions = self.get_my_actions().filter(db_date_submitted__gte=old)
            if recent_actions.count() >= self.max_requests:
                self.msg("You are permitted to make %s requests every %s days. Recent actions: %s" \
                         % (self.max_requests, self.num_days, ", ".join(ob.id for ob in recent_actions)))
                return
        #TODO
        pass