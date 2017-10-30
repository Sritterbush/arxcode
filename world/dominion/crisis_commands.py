from datetime import datetime

from evennia.commands.default.muxcommand import MuxPlayerCommand
from .models import Crisis, CrisisAction, ActionOOCQuestion, CrisisActionAssistant
from evennia.utils.evtable import EvTable
from server.utils.arx_utils import inform_staff, get_week
from django.db.models import Q


class CmdGMCrisis(MuxPlayerCommand):
    """
    GMs a crisis

    Usage:
        @gmcrisis
        @gmcrisis <action #>
        @gmcrisis/create <name>/<headline>=<desc>
        @gmcrisis/listquestions
        @gmcrisis/needgm
        @gmcrisis/old
        @gmcrisis/answerquestion <action #>=<answer>
        @gmcrisis/check[/asst] <action #>=<stat> + <skill> at <diff>[,asst]
        @gmcrisis/gmnotes <action #>=<ooc notes>/<crisis value>
        @gmcrisis/outcome <action #>=<IC notes>
        
        @gmcrisis/update <crisis name>=<gemit text>[/<ooc notes>]
        @gmcrisis/update/nogemit <as above>

    Use /needgm or /needgm/listquestions to list ones
    that have not been answered. To use this command properly, use /check to make
    checks for players, then write /gmnotes and their /outcome for each action.
    That will make the action ready to be sent. Then use /sendresponses to send
    all the actions out simultaneously, which will create a new update for that
    crisis with the text provided and point all those actions to that update.

    If you happen to forget actions in an update, use /appendresponses to send
    them out for the last update.
    """
    key = "@gmcrisis"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def list_actions(self):
        from server.utils.prettytable import PrettyTable
        if "old" in self.switches:
            qs = CrisisAction.objects.filter(status=CrisisAction.PUBLISHED, crisis__isnull=False)
        else:
            qs = CrisisAction.objects.exclude(crisis__isnull=True).exclude(status__in=(CrisisAction.PUBLISHED,
                                                                                       CrisisAction.CANCELLED))
        if "needgm" in self.switches:
            qs = qs.filter(story__exact="")
        if "listquestions" in self.switches:
            qs = qs.filter(questions__isnull=False, questions__answers__isnull=True)
        if self.args:
            qs = qs.filter(Q(crisis__name__iexact=self.args) |
                           Q(dompc__player__username__iexact=self.args))
        table = PrettyTable(["{w#{n", "{wCrisis{n", "{wPlayer{n", "{wAnswered{n", "{wQuestions{n", "{wDate Set{n"])
        for ob in qs:
            date = "--" if not ob.crisis.end_date else ob.crisis.end_date.strftime("%x")
            questions = "{rYes{n" if ob.questions.filter(answers__isnull=True) else "{wNo{n"
            table.add_row([ob.id, ob.crisis.name, str(ob.dompc), "{wYes{n" if ob.story else "{rNo{n", questions, date])
        self.msg(table)

    def do_check(self, action):
        try:
            args = self.rhs.split("+")
            stat = args[0].strip()
            args = args[1].split(" at ")
            skill = args[0].strip()
            if "asst" in self.switches:
                args = args[1].split(",")
                difficulty = int(args[0])
                from django.core.exceptions import ObjectDoesNotExist
                try:
                    action = action.assisting_actions.get(dompc__player__username__iexact=args[1])
                except ObjectDoesNotExist:
                    self.msg("Assistant not found.")
                    return
            else:
                difficulty = int(args[1])
        except (IndexError, ValueError, TypeError):
            self.msg("Failed to parse skill string. Blame Apostate again.")
            return
        result = action.do_roll(stat=stat, skill=skill, difficulty=difficulty)
        self.msg("Roll result is: %s" % result)

    def answer_question(self, action):
        action.add_answer(gm=self.caller, text=self.rhs)
        self.msg("Answer added.")

    def add_gm_notes(self, action):
        rhs = self.rhs.split("/")
        notes = rhs[0]
        try:
            val = int(rhs[1])
        except (IndexError, ValueError, TypeError):
            val = 0
        action.gm_notes = notes
        action.outcome_value = val
        action.save()
        self.msg("Notes set to : %s." % notes)

    def add_outcome(self, action):
        action.story = self.rhs
        action.save()
        self.msg("Story set to: %s" % self.rhs)

    def view_action(self, action):
        view_answered = "old" in self.switches
        self.msg(action.view_action(self.caller, disp_pending=True, disp_old=view_answered))
        
    def create_update(self):
        try:
            crisis = Crisis.objects.get(name__iexact=self.lhs)
        except Crisis.DoesNotExist:
            self.msg("No crisis by that name.")
            return
        rhs = self.rhs.split("/")
        gemit = rhs[0]
        gm_notes = None
        if len(rhs) > 1:
            gm_notes = rhs[1]
        crisis.create_update(gemit, self.caller, gm_notes, do_gemit="nogemit" not in self.switches)
        inform_staff("%s has updated crisis %s." % (self.caller, crisis))

    def func(self):
        if not self.args or (not self.lhs.isdigit() and not self.rhs):
            self.list_actions()
            return
        if "update" in self.switches:
            self.create_update()
            return
        if "create" in self.switches:
            lhs = self.lhs.split("/")
            if len(lhs) < 2:
                self.msg("Bad args.")
                return
            name, headline = lhs[0], lhs[1]
            desc = self.rhs
            Crisis.objects.create(name=name, headline=headline, desc=desc)
            self.msg("Crisis created. Make gemits or whatever for it.")
            return
        try:
            action = CrisisAction.objects.get(id=self.lhs)
        except (CrisisAction.DoesNotExist, ValueError):
            self.list_actions()
            self.msg("{rNot found.{n")
            return
        if self.args and not self.switches:
            self.view_action(action)
            return
        if "answerquestion" in self.switches:
            self.answer_question(action)
            return
        if "check" in self.switches:
            self.do_check(action)
            return
        if "gmnotes" in self.switches:
            self.add_gm_notes(action)
            return
        if "outcome" in self.switches:
            self.add_outcome(action)
            return
        self.msg("Invalid switch")


class CmdCrisisAction(MuxPlayerCommand):
    """
    Take action for a current crisis

    Usage:
        +crisis [#]
        +crisis/old <#>

    Crisis actions are queued and simultaneously resolved by GMs periodically. 
    To view crises that have since been resolved, use /old switch. A secret 
    action can be added after an action is submitted, and /toggleview allows 
    individual assistants (or the action's owner) to see it. Togglepublic can
    keep the action from being publically listed. The addition of resources,
    armies, and extra action points is taken into account when deciding outcomes.
    New actions cost 50 action points, while assisting costs 10.

    To create a new action, use the @action command.
    """
    key = "+crisis"
    aliases = ["crisis"]
    locks = "cmd:all()"
    help_category = "Dominion"

    @property
    def viewable_crises(self):
        qs = Crisis.objects.viewable_by_player(self.caller).order_by('end_date')
        if "old" in self.switches:
            qs = qs.filter(resolved=True)
        return qs

    @property
    def current_actions(self):
        return self.caller.Dominion.actions.exclude(status=CrisisAction.PUBLISHED)

    @property
    def assisted_actions(self):
        return self.caller.Dominion.assisting_actions.all()

    def list_crises(self):
        qs = self.viewable_crises
        if "old" not in self.switches:
            qs = qs.filter(resolved=False)
        table = EvTable("{w#{n", "{wName{n", "{wDesc{n", "{wUpdates On{n", width=78, border="cells")
        for ob in qs:
            date = "--" if not ob.end_date else ob.end_date.strftime("%m/%d")
            table.add_row(ob.id, ob.name, ob.headline, date)
        table.reformat_column(0, width=7)
        table.reformat_column(1, width=20)
        table.reformat_column(2, width=40)
        table.reformat_column(3, width=11)
        self.msg(table)
        self.msg("{wYour pending actions:{n")
        table = EvTable("{w#{n", "{wCrisis{n")
        current_actions = list(self.current_actions) + [ass.crisis_action for ass in self.assisted_actions.exclude(
            crisis_action__status=CrisisAction.PUBLISHED)]
        for ob in current_actions:
            table.add_row(ob.id, ob.crisis)
        self.msg(table)
        past_actions = self.caller.past_participated_actions
        if past_actions:
            table = EvTable("{w#{n", "{wCrisis{n")
            self.msg("{wYour past actions:{n")
            for ob in past_actions:
                table.add_row(ob.id, ob.crisis)
            self.msg(table)

    def get_crisis(self):
        try:
            if not self.switches or "old" in self.switches:
                return self.viewable_crises.get(id=self.lhs)
            return self.viewable_crises.get(resolved=False, id=self.lhs)
        except (Crisis.DoesNotExist, ValueError):
            self.msg("Crisis not found by that #.")
            return

    def view_crisis(self):
        crisis = self.get_crisis()
        if not crisis:
            return
        self.msg(crisis.display())
        return

    def get_action(self, get_all=False, get_assisted=False, return_assistant=False):
        dompc = self.caller.Dominion
        if not get_all and not get_assisted:
            qs = self.current_actions
        else:
            qs = CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct()
        try:
            action = qs.get(id=self.lhs)
            if not action.pk:
                self.msg("That action has been deleted.")
                return
            if return_assistant:
                try:
                    return action.assisting_actions.get(dompc=dompc)
                except CrisisActionAssistant.DoesNotExist:
                    self.msg("You are not assisting that crisis action.")
                    return
            return action
        except (CrisisAction.DoesNotExist, ValueError):
            self.msg("No action found by that id. Remember to specify the number of the action, not the crisis. " +
                     "Use /assist if trying to change your assistance of an action.")
        return

    def view_action(self):
        action = self.get_action(get_all=True, get_assisted=True)
        if not action:
            return
        msg = action.view_action(self.caller, disp_pending=True, disp_old=True)
        if not msg:
            msg = "You are not able to view that action."
        self.msg(msg)

    def func(self):
        if not self.args and (not self.switches or "old" in self.switches):
            self.list_crises()
            return
        if not self.switches or "old" in self.switches:
            self.view_crisis()
            return
        if "viewaction" in self.switches:
            self.view_action()
            return
        self.msg("Invalid switch")
