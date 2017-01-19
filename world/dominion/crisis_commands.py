from evennia.commands.default.muxcommand import MuxPlayerCommand
from .models import Crisis, CrisisAction, ActionOOCQuestion
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
        @gmcrisis/check <action #>=<stat> + <skill> at <diff>
        @gmcrisis/gmnotes <action #>=<ooc notes>/<crisis value>
        @gmcrisis/outcome <action #>=<IC notes>
        @gmcrisis/sendresponses

    Use /needgm/listactions or /needgm/listquestions to list ones
    that have not been answered.
    """
    key = "@gmcrisis"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def list_actions(self):
        if "old" in self.switches:
            qs = CrisisAction.objects.filter(sent=True)
        else:
            qs = CrisisAction.objects.filter(sent=False)
        if "needgm" in self.switches:
            qs = qs.filter(story__exact="")
        if "list_questions" in self.switches:
            qs = qs.filter(questions__answers__isnull=True)
        table = EvTable("{w#{n", "{wCrisis{n", "{wPlayer{n", "{wAnswered{n", "{wQuestions{n", "{wDate Set{n",
                        width=78, border="cells")
        for ob in qs:
            date = "--" if not ob.crisis.end_date else ob.crisis.end_date.strftime("%x %X")
            questions = "{rYes{n" if ob.questions.filter(answers__isnull=True) else "{wNo{n"
            table.add_row(ob.id, ob.crisis.name, str(ob.dompc), "{wYes{n" if ob.story else "{rNo{n", questions, date)
        self.msg(table)

    def do_check(self, action):
        try:
            args = self.rhs.split("+")
            stat = args[0].strip()
            args = args[1].split(" at ")
            skill = args[0].strip()
            difficulty = int(args[1])
        except (IndexError, ValueError, TypeError):
            self.msg("Failed to parse skill string. Blame Apostate again.")
            return
        char = action.dompc.player.db.char_ob
        from world.stats_and_skills import do_dice_check
        result = do_dice_check(char, stat=stat, skill=skill, difficulty=difficulty)
        msg = "%s has called for %s to check %s + %s at difficulty %s.\n" % (self.caller, char, stat, skill, difficulty)
        msg += "The result is %s. A positive number is a success, a negative number is a failure." % result
        if action.rolls:
            msg = "\n" + msg
        action.rolls += msg
        action.save()

    def answer_question(self, action):
        question = action.questions.last()
        question.answers.create(text=self.rhs)
        self.msg("Question: %s\nAnswer: %s" % (question.text, self.rhs))

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

    def send_responses(self):
        qs = CrisisAction.objects.filter(sent=False).exclude(story="")
        for ob in qs:
            ob.send()
        self.msg("Sent responses.")

    def func(self):
        if not self.args and "sendresponses" not in self.switches:
            self.list_actions()
            return
        if "sendresponses" in self.switches:
            self.send_responses()
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
    Take an action for a crisis

    Usage:
        +crisis
        +crisis <#>
        +crisis/newaction <crisis #>=<action you are taking>
        +crisis/secretaction <crisis #>=<action you are taking>
        +crisis/viewaction <action #>
        +crisis/question <action #>=<question>

    Takes an action for a given crisis that is currently going on.
    Actions are queued in and then all simultaneously resolved by
    GMs periodically.
    """
    key = "+crisis"
    locks = "cmd:all()"
    help_category = "Dominion"

    @property
    def viewable_crises(self):
        if self.caller.check_permstring("builders"):
            return Crisis.objects.filter(resolved=False)
        return Crisis.objects.filter(resolved=False).filter(
            Q(public=True) |
            Q(required_clue__discoveries__in=self.caller.roster.finished_clues))

    @property
    def current_actions(self):
        return self.caller.Dominion.actions.filter(sent=False)

    def list_crises(self):
        qs = self.viewable_crises
        table = EvTable("{w#{n", "{wName{n", "{wDesc{n", "{wRating{n", "{wUpdates On{n", width=78, border="cells")
        for ob in qs:
            date = "--" if not ob.end_date else ob.end_date.strftime("%x %X")
            table.add_row(ob.id, ob.name, ob.headline, ob.rating, date)
        self.msg(table)
        self.msg("{wYour actions:{n")
        table = EvTable("{w#{n", "{wCrisis{n")
        for ob in self.current_actions:
            table.add_row(ob.id, ob.crisis)
        self.msg(table)

    def get_crisis(self):
        try:
            return self.viewable_crises.get(id=self.lhs)
        except (Crisis.DoesNotExist, ValueError):
            self.msg("Crisis not found by that #.")
            return

    def view_crisis(self):
        crisis = self.get_crisis()
        if not crisis:
            return
        self.msg(crisis.display())
        return

    def new_action(self):
        crisis = self.get_crisis()
        if not crisis:
            return
        if crisis.actions.filter(sent=False, dompc=self.caller.Dominion):
            self.msg("You have unresolved actions.")
            return
        if not self.rhs:
            self.msg("Must specify an action.")
            return
        week = get_week()
        public = "secretaction" not in self.switches
        crisis.actions.create(dompc=self.caller.Dominion, action=self.rhs, public=public, week=week)
        self.msg("You are going to perform this action: %s" % self.rhs)
        inform_staff("%s has created a new crisis action: %s" % (self.caller, self.rhs))

    def get_action(self):
        try:
            return self.current_actions.get(id=self.lhs)
        except (CrisisAction.DoesNotExist, ValueError):
            self.msg("No crisis found by that id.")
            return

    def view_action(self):
        action = self.get_action()
        if not action:
            return
        msg = action.view_action(self.caller, disp_pending=True, disp_old=True)
        if not msg:
            msg = "You are not able to view that action."
        self.msg(msg)

    def ask_question(self):
        action = self.get_action()
        if not action:
            return
        try:
            question = action.questions.get(answers__isnull=True)
            self.msg("Found an unanswered question. Appending your question to it.")
            question.text += "\n%s" % self.rhs
        except ActionOOCQuestion.DoesNotExist:
            question = action.questions.create(text="")
        question.text += self.rhs
        question.save()
        self.msg("Asked the question: %s" % self.rhs)
        inform_staff("%s has asked a question about a crisis action: %s" % (self.caller, self.rhs))

    def func(self):
        if not self.args and not self.switches:
            self.list_crises()
            return
        if not self.switches:
            self.view_crisis()
            return
        if "newaction" in self.switches or "secretaction" in self.switches:
            self.new_action()
            return
        if "viewaction" in self.switches:
            self.view_action()
            return
        if "question" in self.switches:
            self.ask_question()
            return
        self.msg("Invalid switch")
