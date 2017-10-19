from datetime import datetime

from django.db.models import Q

from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.utils.evtable import EvTable

from server.utils.arx_utils import inform_staff, get_week

from world.dominion.models import Crisis, CrisisAction, CrisisActionAssistant, ActionSubmissionError


class CmdAction(MuxPlayerCommand):
    """
    A character's story actions that a GM responds to.
    
    Usage:
        @action/newaction [<crisis #>=]<story of action>
        @action/tldr <action #>=<title or brief summary>
        @action/category <action #>=<category>
        @action/roll <action #>=<stat>,<skill>
        @action/ooc <action #>=<ooc intent, then post-submission questions>
        @action/cancel <action #>
        @action/submit <action #>
    Options:
        @action[/public] [<action #>]
        @action/invite <action #>=<character>
        @action/setaction <action #>=<action text>
        @action/setsecret[/traitor] <action #>=<secret action>
        @action/setcrisis <action #>=<crisis #>
        @action/add <action #>,<resource or 'ap' or 'army'>=<amount or army ID#>
        @action/makepublic <action #>
        @action/toggletraitor <action #>
        @action/toggleattend <action #>
        
    Creating /newaction costs Action Points (ap). Requires summary, category,
    stat/skill for dice check, and /ooc specifics about this single action's
    intent. Use /submit after all options, when ready for GM review. GMs may 
    require more info or ask you to edit with /setaction and /submit again. 
    Categories: combat, scouting, support, diplomacy, sabotage, research.
    
    With /invite you ask others to assist your action. They use /setaction or
    /cancel, and require all the same fields, except category. A covert action 
    can be added with /setsecret. Optional /traitor (and /toggletraitor) switch
    makes your dice roll detract from goal. With /setcrisis this becomes your 
    response to a Crisis. Allocate resources with /add by specifying which type
    (ap, army, social, silver, etc.,) and amount, or the ID# of the army. The 
    /makepublic switch allows everyone to see your action after a GM publishes 
    an outcome.
    
    Using /toggleattend switches whether your character is physically present,
    or arranging for the action's occurance in other ways. One action may be 
    attended per crisis update; all others must be passive to represent 
    simultaneous response by everyone involved. Up to 5 attendees are allowed
    per crisis response action.
    """
    key = "@action"
    locks = "cmd:all()"
    help_category = "Dominion"
    max_requests = 2
    num_days = 30
    action_categories = ("combat", "scouting", "support", "diplomacy", "sabotage", "research")
    requires_editable_switches = ("roll", "tldr", "summary", "category", "submit", "invite", \
                                  "setaction", "setcrisis", "add", "toggletraitor", "toggleattend")
    requires_unpublished_switches = ("ooc", "cancel")
    requires_owner_switches = ("invite", "makepublic", "category", "setcrisis")
    
    def func(self):
        if not self.args:
            self.list_actions()
        if "newaction" in self.switches:
            return self.new_action()
        action = self.get_action(self.lhs)
        if not action:
            return
        if not self.check_valid_switch_for_action_type(action):
            return
        if "makepublic" in self.switches:
            return self.make_public(action)
        if set(self.switches) & set(self.requires_editable_switches):
            # PS - NV is fucking amazing
            return self.do_requires_editable_switches(action)
        if set(self.switches) & set(self.requires_unpublished_switches):
            return self.do_requires_unpublished_switches(action)
        else:
            self.msg("Invalid switch. See 'help @action'.")
            
    def check_valid_switch_for_action_type(self, action):
        """
        Checks if the specified switches require the main action, and if so, whether our action is the main action.
        
            Args:
                action (CrisisAction or CrisisActionAssistant): action or assisting action
                
            Returns:
                True or False for whether we're okay to proceed.
        """
        if not (set(self.switches) & set(self.requires_owner_switches)):
            return True
        if action.is_main_action:
            return True
        self.msg("Those switches can only be performed on the main action.")
        return False
        
    def make_public(self, action):
        if action.public:
            self.msg("That action has already been made public.")
            return
        self.set_action_field(action, "public", True)
            
    def do_requires_editable_switches(self, action):
        if not action.editable:
            return self.send_no_edits_msg()
        if "roll" in self.switches:
            return self.set_roll(action)
        if "tldr" in self.switches or "summary" in self.switches:
            return self.set_summary(action)
        elif "category" in self.switches:
            return self.set_category(action)
        # elif "submit" in self.switches:
        #     return self.submit_action(action)
        # elif "invite" in self.switches:
        #     return self.invite_assistant(action)
        # elif "setaction" in self.switches:
        #     return self.set_action(action)
        # elif "setcrisis" in self.switches:
        #     return self.set_crisis(action)
        # elif "add" in self.switches:
        #     return self.add_resource(action)
        elif "toggletraitor" in self.switches:
            return self.toggle_traitor(action)
        # elif "toggleattend" in self.switches:
        #     return self.toggle_attend(action)
        
    def do_requires_unpublished_switches(self, action):
        if action.status in (CrisisAction.PUBLISHED, CrisisAction.PENDING_PUBLISH):
            return self.send_no_edits_msg()
        elif "ooc" in self.switches:
            return self.set_ooc(action)
        elif "cancel" in self.switches:
            return self.cancel_action(action)
            
    @property
    def dompc(self):
        """Shortcut for getting their dominion playerornpc object"""
        return self.caller.Dominion
            
    def send_no_edits_msg(self):
        self.msg("You cannot edit that action at this time.")
            
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
        
    def set_category(self, action):
        if not hasattr(action, 'category'):
            self.msg("Only the main action has a category.")
            return
        if self.rhs not in self.action_categories:
            self.msg("Usage: @action/category <action #>=<category>\n" \
                     "Categories: %s" % ", ".join(self.action_categories))
            return
        self.set_action_field(action, 'category', self.rhs)
        
    def set_action_field(self, action, field_name, value, verbose_name=None):
        setattr(action, field_name, value)
        action.save()
        verbose_name = verbose_name or field_name
        self.msg("%s set to %s." % (verbose_name, value))
      
    def set_roll(self, action):
        """Sets a stat and skill for action or assistant"""
        if not self.rhs[1]:
            self.msg("Usage: @action/roll <action #>=<stat>,<skill>")
            return
        field_name = "stat"
        self.set_action_field(action, field_name, self.rhs[0])
        field_name = "skill"
        return self.set_action_field(action, field_name, self.rhs[1])
        
    def set_summary(self, action):
        return self.set_action_field(action, "summary", self.rhs)
      
    def set_ooc(self, action):
        """
        Sets our ooc intent, or if we're already submitted and have an intent set, it asks a question.
        """
        if not action.submitted:
            action.set_ooc_intent(self.rhs)
            self.msg("You have set your ooc intent to be: %s" % self.rhs)
        else:
            self.msg("You have submitted a question: %s" % self.rhs)
        
    def cancel_action(self, action):
        if not action.check_can_cancel():
            self.msg("You cannot cancel the action at this time.")
            return
        action.cancel()
        self.msg("Action cancelled.")
        
    def submit_action(self, action):
        """I love a bishi. He too will submit."""
        if action.is_main_action and not self.check_action_against_maximum_allowed(action):
            return
        try:
            action.submit()
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            self.msg("You have submitted your action.")
    
    def check_action_against_maximum_allowed(self, action):
        if action.status != CrisisAction.DRAFT or action.crisis:
            return True
        from datetime import timedelta
        offset = timedelta(days=-self.num_days)
        old = datetime.now() + offset
        recent_actions = self.get_my_actions().filter(db_date_submitted__gte=old)
        if recent_actions.count() < self.max_requests:
            return True
        else:
            self.msg("You are permitted to make %s requests every %s days. Recent actions: %s" \
                     % (self.max_requests, self.num_days, ", ".join(ob.id for ob in recent_actions)))
    
    def toggle_traitor(self, action):
        action.traitor = not action.traitor
        color = "{r" if action.traitor else "{w"
        action.save()
        self.msg("Traitor is now set to: %s%s{n" % (color, action.traitor))
