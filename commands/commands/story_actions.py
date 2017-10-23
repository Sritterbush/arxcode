from datetime import datetime

from django.db.models import Q

from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.utils.evtable import EvTable

from server.utils.arx_utils import inform_staff, get_week
from server.utils.exceptions import ActionSubmissionError

from world.dominion.models import Crisis, CrisisAction, CrisisActionAssistant


class CmdAction(MuxPlayerCommand):
    """
    A character's story actions that a GM responds to.
    
    Usage:
        @action/newaction [<crisis #>=]<story of action>
        @action/tldr <action #>=<title>
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
        @action/add <action#>=<resource or 'ap' or 'army'>,<amount or army ID#>
        @action/makepublic <action #>
        @action/toggletraitor <action #>
        @action/toggleattend <action #>
        @action/noscene <action #>
        
    Creating /newaction costs Action Points (ap). Requires title, category,
    stat/skill for dice check, and /ooc specifics about this single action's
    intent. Use /submit after all options, when ready for GM review. GMs may 
    require more info or ask you to edit with /setaction and /submit again. 
    Categories: combat, scouting, support, diplomacy, sabotage, research.
    
    With /invite you ask others to assist your action. They use /setaction or
    /cancel, and require all the same fields except category. A covert action 
    can be added with /setsecret. Optional /traitor (and /toggletraitor) switch
    makes your dice roll detract from goal. With /setcrisis this becomes your 
    response to a Crisis. Allocate resources with /add by specifying a type
    (ap, army, social, silver, etc.) and amount, or the ID# of your army. The 
    /makepublic switch allows everyone to see your action after a GM publishes 
    an outcome. If you prefer offscreen resolution, use /noscene toggle.
    
    Using /toggleattend switches whether your character is physically present,
    or arranging for the action's occurance in other ways. One action may be 
    attended per crisis update; all others must be passive to represent 
    simultaneous response by everyone involved. Up to 5 attendees are allowed
    per crisis response action, unless it is /noscene.
    """
    key = "@action"
    locks = "cmd:all()"
    help_category = "Dominion"
    action_categories = ("combat", "scouting", "support", "diplomacy", "sabotage", "research")
    requires_draft_switches = ("invite", "setcrisis")
    requires_editable_switches = ("roll", "tldr", "title", "category", "submit", "invite", \
                                  "setaction", "setcrisis", "add", "toggletraitor", "toggleattend")
    requires_unpublished_switches = ("ooc", "cancel", "noscene")
    requires_owner_switches = ("invite", "makepublic", "category", "setcrisis", "noscene")
    
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
        if set(set.switches) & set(self.requires_draft_switches):
            return self.do_requires_draft_switches(action)
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
    
    def do_requires_draft_switches(self, action):
        if not action.status == CrisisAction.DRAFT:
            return self.send_too_late_msg
        elif "invite" in self.switches:
            return self.invite_assistant(action)
        elif "setcrisis" in self.switches:
            return self.set_crisis(action)
    
    def do_requires_editable_switches(self, action):
        if not action.editable:
            return self.send_no_edits_msg()
        if "roll" in self.switches:
            return self.set_roll(action)
        if "tldr" in self.switches or "title" in self.switches:
            return self.set_topic(action)
        elif "category" in self.switches:
            return self.set_category(action)
        elif "submit" in self.switches:
            return self.submit_action(action)
        elif "setaction" in self.switches:
            return self.set_action(action)
        elif "add" in self.switches:
            return self.add_resource(action)
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
        elif "noscene" in self.switches:
            return self.toggle_noscene(action)
            
    @property
    def dompc(self):
        """Shortcut for getting their dominion playerornpc object"""
        return self.caller.Dominion
            
    def send_no_edits_msg(self):
        self.msg("You cannot edit that action at this time.")
        
    def send_too_late_msg(self):
        self.msg("Can only be done while the action is in Draft status.")
            
    def list_actions(self):
        """Prints a table of the actions we've taken"""
        table = EvTable("ID", "Crisis", "Category", "Attend", "Status")
        actions = self.dompc.actions.all()
        for action in actions:
            table.add_row(action.id, action.crisis, action.category, action.attending, action.status)
        self.msg(table)
    
    def send_no_args_msg(self, noun):
        if not noun:
            noun = "args"
        self.msg("You need to include %s." % noun)
    
    def new_action(self):
        """Create a new action."""
        if not self.args:
            return self.send_no_args_msg("a story")
        crisis = None
        crisis_msg = ""
        story = self.lhs
        if self.rhs:
            crisis = self.get_valid_crisis(self.lhs)
            story = self.rhs
            crisis_msg = " to respond to %s" % str(crisis)
            if not crisis:
                return
        if not self.can_create(crisis):
            return
        action = self.dompc.actions.create(story=story, crisis=crisis)
        self.msg("You have drafted a new action%s: %s" % (crisis_msg, story))
        if crisis:
            self.warn_crisis_omnipresence(action)
    
    def get_action(self, arg):
        """Returns an action we are involved in from ID# args.
        
            Args:
                arg (str): String to use to find the ID of the crisis action.
                
            Returns:
                A CrisisAction or a CrisisActionAssistant depending if the caller is the owner of the main action or
                an assistant.
        """
        try:
            dompc = self.dompc
            action = CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct().get(id=arg)
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
    
    def get_valid_crisis(self, name_or_id):
        try:
            qs = Crisis.objects.viewable_by_player(self.caller)
            if name_or_id.isdigit():
                return qs.get(id=name_or_id)
            return qs.get(name__iexact=name_or_id)
        except Crisis.DoesNotExist:
            self.msg("No crisis found by that name or ID.")
    
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
        try:
            crisis.raise_creation_errors(self.dompc)
        except ActionSubmissionError as err:
            self.msg(err)
            return False
        return True
        
    def set_category(self, action):
        if not action.is_main_action:
            self.msg("Only the main action has a category.")
            return
        if not self.rhs:
            return self.send_no_args_msg("a category")
        if self.rhs not in self.action_categories:
            self.send_no_args_msg("one of these categories: %s" % ", ".join(self.action_categories))
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
        
    def set_topic(self, action):
        if not self.rhs:
            return self.send_no_args_msg("a title")
        if len(self.rhs) > 80:
            self.send_no_args_msg("a shorter title; aim for under 80 characters")
            return
        return self.set_action_field(action, "topic", self.rhs)
      
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
        action.cancel()
        self.msg("Action cancelled.")
        
    def submit_action(self, action):
        """I love a bishi. He too will submit."""
        try:
            action.submit()
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            self.msg("You have submitted your action.")
            
    def toggle_noscene(self, action):
        action.prefer_offscreen = not action.prefer_offscreen
        action.save()
        color = "{r" if action.prefer_offscreen else "{w"
        self.msg("Preference for offscreen resolution set to: %s%s" % (color, action.prefer_offscreen))
    
    def toggle_traitor(self, action):
        action.traitor = not action.traitor
        color = "{r" if action.traitor else "{w"
        action.save()
        self.msg("Traitor is now set to: %s%s{n" % (color, action.traitor))
        
    def invite_assistant(self, action):
        player = self.caller.search(self.rhs)
        if not player:
            return
        dompc = player.Dominion
        try:
            action.invite(dompc)
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            self.msg("You have invited %s to join your action." % dompc)
    
    def set_action(self, action):
        if not self.rhs:
            return self.send_no_args_msg("a story")
        if not action.is_main_action:
            try:
                action.set_action(self.rhs)
            except ActionSubmissionError as err:
                self.msg(err)
                return
            else:
                self.msg("%s now has your assistance: %s" % (action.crisis_action, self.rhs))
        else:
            self.set_action_field(action, "actions", self.rhs)
        if action.crisis:
            self.do_passive_warnings(action)
            
    def warn_crisis_overcrowd(self, action):
        try:
            action.check_crisis_overcrowd()
        except ActionSubmissionError as err:
            self.msg("{yWarning:{n " + err)
                
    def warn_crisis_omnipresence(self, action):
        try:
            action.check_crisis_omnipresence()
        except ActionSubmissionError as err:
            self.msg("{yWarning:{n " + err)
    
    def do_passive_warnings(self, action):
        self.warn_crisis_omnipresence(action) 
        if not action.prefer_offscreen:
            self.warn_crisis_overcrowd(action)
    
    def set_crisis(self, action):
        if not self.rhs:
            action.crisis = None
            action.save()
            self.msg("Your action no longer targets any crisis.")
            return
        crisis = self.get_valid_crisis(self.rhs)
        if not crisis:
            return
        if not self.can_set_crisis(crisis):
            return
        action.crisis = crisis
        action.save()
        self.msg("You have set the action to be for crisis: %s" % crisis)
        self.do_passive_warnings(action)

    def add_resource(self, action):
        if not self.rhs[1]:
            self.send_no_args_msg("a resource type such as 'economic' or 'ap' and the amount. Or 'army' and an army ID#")
            return
        r_type, value = self.rhs
        try:
            action.add_resource(r_type, value)
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            if r_type.lower() == "army":
                self.msg("You have successfully relayed new orders to that army.")
                return
            else:
                totals = action.view_total_resources_msg()
                self.msg("{c%s{n %s added. Action %s" % (value, r_type, totals))
                
    def toggle_attend(self, action):
        if action.attending:
            action.attending = False
            action.save()
            self.msg("You are marked as no longer attending the action.")
            return
        action.mark_attending()
        self.msg("You have marked yourself as physically being present for that action.")
