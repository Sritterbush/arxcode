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
        @gmcrisis/sendresponses <crisis name>=<story update text>
        @gmcrisis/appendresponses <crisis name>
        
        @gmcrisis/update <crisis name>=<story update text, will make a gemit>

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
            qs = CrisisAction.objects.filter(sent=True)
        else:
            qs = CrisisAction.objects.filter(sent=False)
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
                    char = action.assistants.get(player__username__iexact=args[1]).player.db.char_ob
                except ObjectDoesNotExist:
                    self.msg("Assistant not found.")
                    return
            else:
                difficulty = int(args[1])
                char = action.dompc.player.db.char_ob
        except (IndexError, ValueError, TypeError):
            self.msg("Failed to parse skill string. Blame Apostate again.")
            return
        from world.stats_and_skills import do_dice_check
        result = do_dice_check(char, stat=stat, skill=skill, difficulty=difficulty)
        msg = "%s has called for %s to check %s + %s at difficulty %s.\n" % (self.caller, char, stat, skill, difficulty)
        msg += "The result is %s. A positive number is a success, a negative number is a failure." % result
        if action.rolls:
            msg = "\n" + msg
        action.rolls += msg
        action.save()
        self.msg("Appended message: %s" % msg)

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
        self.msg("{wCurrent GM story:{n %s" % action.story)
        self.msg("{wRolls:{n %s" % action.rolls)
        self.msg("{wGM Notes:{n %s" % action.gm_notes)

    def send_responses(self, create_update=True):
        try:
            crisis = Crisis.objects.get(name__iexact=self.lhs)
        except Crisis.DoesNotExist:
            self.msg("No crisis by that name: %s" % ", ".join(str(ob) for ob in Crisis.objects.all()))
            return
        qs = crisis.actions.filter(sent=False).exclude(story="")
        if not qs:
            self.msg("No messages need updates.")
            return
        date = datetime.now()
        if create_update:
            update = crisis.updates.create(desc=self.rhs, date=date)
        else:
            update = crisis.updates.last()
        if not update:
            self.msg("Create_update was false and no last update found.")
            return
        for ob in qs:
            ob.send(update)
        self.msg("Sent responses.")

    def func(self):
        if not self.args or (not self.lhs.isdigit() and not self.rhs) and "appendresponses" not in self.switches:
            self.list_actions()
            return
        if "sendresponses" in self.switches or "appendresponses" in self.switches:
            create = "sendresponses" in self.switches
            self.send_responses(create_update=create)
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
        +crisis/newaction <crisis #>=<action you are taking>
        +crisis/append <action #>=<additional text>
        +crisis/secret <action #>=<action you are taking>
        +crisis/secret/append <action #>=<additional text>
        +crisis/toggleview <action #>=<assistant>
        +crisis/cancel <action #>
        +crisis/invite <action #>=<player>
        +crisis/assist <action #>=<action you are taking>
        +crisis/assist/append <action #>=<additional text>
        +crisis/assist/secret <action #>=<action you are taking>
        +crisis/assist/secret/append <action #>=<additional text>
        +crisis/assist/toggleview <action #>
        +crisis/assist/cancel <action #>
        +crisis/decline <action #>
        +crisis/viewaction <action #>
        +crisis/addpoints <action #>=<points to add>
        +crisis/addresource <action#>=<type>,<amount>
        +crisis/addarmy <action #>=<army name or #>
        +crisis/question <action #>=<question>
        +crisis/togglepublic <action #>

    Crisis actions are queued and simultaneously resolved by GMs periodically. 
    To view crises that have since been resolved, use /old switch. A secret 
    action can be added after an action is submitted, and /toggleview allows 
    individual assistants (or the action's owner) to see it. Togglepublic can
    keep the action from being publically listed. The addition of resources,
    armies, and extra action points is taken into account when deciding outcomes.
    New actions cost 50 action points, while assisting costs 10.
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
        return self.caller.Dominion.actions.filter(sent=False)

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
        current_actions = list(self.current_actions) + [ass.crisis_action for ass in self.assisted_actions.filter(
                crisis_action__sent=False)]
        for ob in current_actions:
            table.add_row(ob.id, ob.crisis)
        self.msg(table)
        past_actions = self.caller.Dominion.actions.filter(sent=True)
        past_actions = list(past_actions) + [ob.crisis_action for ob in self.assisted_actions.filter(
            crisis_action__sent=True)]
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

    def invite_assistant(self):
        targ = self.caller.search(self.rhs)
        if not targ:
            return
        action = self.get_action()
        if not action:
            return
        if action.assistants.filter(id=targ.Dominion.id):
            self.msg("%s is already helping you.")
            return
        invitations = targ.db.crisis_action_invitations or []
        if action.id not in invitations:
            invitations.append(action.id)
        targ.db.crisis_action_invitations = invitations
        text = "%s has asked you to help crisis action #%s for %s.\n\n%s\n\nUse +crisis/assist to help." % (
            self.caller, action.id, action.crisis, action.action_text)
        targ.inform(text, category="Crisis action invitation")
        self.msg("You have invited %s to assist you in your crisis action." % targ)
        return

    def assist_action(self):
        invitations = self.caller.db.crisis_action_invitations or []
        if not self.rhs:
            try:
                actions = [CrisisAction.objects.get(id=act_id) for act_id in invitations]
                for act in actions:
                    if act.crisis.end_date < datetime.now() or act.sent:
                        invitations.remove(act.id)
            except (CrisisAction.DoesNotExist, ValueError, TypeError, AttributeError):
                pass
            self.msg("You have the following invitations: %s" % ", ".join(str(ob) for ob in invitations))
            return
        try:
            act_id = int(self.lhs)
            if act_id not in invitations:
                self.msg("You do not have an invitation to assist that crisis action.")
                return
            action = CrisisAction.objects.get(id=act_id)
        except (ValueError, CrisisAction.DoesNotExist):
            self.msg("Could not get a crisis action by that id.")
            return
        invitations.remove(act_id)
        self.caller.db.crisis_action_invitations = invitations
        crisis = action.crisis
        if crisis.end_date < datetime.now():
            self.msg("It is past the update time for that crisis.")
            return
        if self.caller.Dominion.actions.filter(crisis=crisis, sent=False):
            self.msg("You already have a pending action for that crisis, and cannot assist in another.")
            return
        if self.caller.Dominion.assisting_actions.filter(crisis_action__crisis=crisis).exclude(
                crisis_action__sent=True):
            self.msg("You are assisting pending actions for that crisis, and cannot assist another.")
            return
        if not self.caller.pay_action_points(10):
            self.msg("You do not have enough action points to respond to this crisis.")
            return
        action.assisting_actions.create(dompc=self.caller.Dominion, action=self.rhs)
        self.msg("Action created.")
        inform_staff("%s is assisting action %s for crisis %s" % (self.caller, action.id, crisis))
        action.dompc.player.inform("%s is now assisting action %s: %s" % (self.caller, action.id, self.rhs))
        return

    def new_action(self):
        crisis = self.get_crisis()
        if not crisis:
            return
        time = datetime.now()
        if crisis.end_date < time:
            self.msg("It is past the submit date for that crisis.")
            return
        if crisis.actions.filter(sent=False, dompc=self.caller.Dominion):
            self.msg("You have unresolved actions. Use /append instead.")
            return
        if not self.rhs:
            self.msg("Must specify an action.")
            return
        if not self.caller.pay_action_points(50):
            self.msg("You do not have enough action points to respond to this crisis.")
            return
        week = get_week()
        action = crisis.actions.create(dompc=self.caller.Dominion, action=self.rhs, week=week)
        self.msg("You are going to perform this action: %s" % self.rhs)
        inform_staff("%s has created a new crisis action for crisis %s: #%s" % (self.caller, crisis, action.id))

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

    def cancel_action(self):
        action = self.get_action(get_assisted=True, return_assistant="assist" in self.switches)
        if not action:
            return
        if hasattr(action, 'crisis_action'):
            parent = action.crisis_action
        else:
            parent = action
        if parent.story:
            self.msg("That has already had GM action taken.")
            return
        action.delete()
        self.msg("Action deleted.")

    def append_action(self):
        assisting = "assist" in self.switches
        action = self.get_action(get_assisted=assisting, return_assistant=assisting)
        if not action:
            return
        field_name = "action"
        if "secret" in self.switches:
            field_name = "secret_action"
        text = getattr(action, field_name) + "\n%s" % self.rhs 
        setattr(action, field_name, text)
        action.save()
        self.msg("Action is now: %s" % text)

    def set_secret_action(self):
        assisting = "assist" in self.switches
        action = self.get_action(get_assisted=assisting, return_assistant=assisting)
        if not action:
            return
        if action.secret_action:
            self.msg("You have unresolved secret actions. Use an append switch instead.")
            return
        action.secret_action = self.rhs
        action.save()
        self.msg("Secret action created.")
        inform_staff("%s adds a secret to action %s for crisis %s" % (self.caller, action.id, action.crisis))

    def add_action_points(self):
        action = self.adding_checks()
        if not action:
            return
        try:
            val = int(self.rhs)
            if val <= 0:
                raise ValueError
            if not self.caller.pay_action_points(val):
                self.msg("You do not have the action points to put more effort into this crisis.")
                return
        except (TypeError, ValueError):
            self.msg("You must specify a positive amount that you can afford.")
            return
        action.outcome_value += val
        action.save()
        self.msg("You add %s action points. Current action points allocated: %s" % (self.rhs, action.outcome_value))
    
    # retrieves action and checks if its crisis has been resolved
    def adding_checks(self):
        action = self.get_action(get_assisted=True)
        if not action:
            return
        time = datetime.now()
        crisis = action.crisis
        if crisis.end_date < time:
            self.msg("It is past the submit date for that crisis.")
            return
        return action
        
    def add_resource(self):
        action = self.adding_checks()
        if not action:
            return
        try:
            res_type = self.rhslist[0]
            val = int(self.rhslist[1])
            if val <= 0:
                raise ValueError
            res_types = ('silver', 'military', 'economic', 'social')
            if res_type not in res_types:
                self.msg("Must be one of the following: %s" % ", ".join(res_types))
                return
            if res_type == "silver":
                if val > self.caller.db.char_ob.db.currency:
                    self.msg("You cannot afford that.")
                    return
                self.caller.db.char_ob.pay_money(val)
            else:
                if not self.caller.pay_resources(res_type, val):
                    self.msg("You cannot afford that.")
                    return
        except IndexError:
            self.msg("You must specify a type of resource and an amount.")
            return
        except (TypeError, ValueError):
            self.msg("You must specify a positive amount that you can afford.")
            return
        # get parent action if we're an assistant
        if hasattr(action, 'crisis_action'):
            action = action.crisis_action
        total = getattr(action, res_type) + val
        setattr(action, res_type, total)
        action.save()
        self.msg("You add %s %s. New value: %s" % (val, res_type, total))

    def add_army(self):
        action = self.adding_checks()
        if not action:
            return
        # gonda get army
        from .models import Army, Orders
        try:
            if self.rhs.isdigit():
                army = Army.objects.get(id=int(self.rhs))
            else:
                army = Army.objects.get(name__iexact=self.rhs)
        except (AttributeError, Army.DoesNotExist):
            self.msg("No armies found by that name or number.")
            return
        # check permissions for army and adjust orders
        orders = army.send_orders(player=self.caller, order_type=Orders.CRISIS, action=action)
        if not orders:
            return
        self.msg("You have relayed orders for %s to assist with crisis action %s." % (army, action.id))

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

    def toggle_secret(self):
        action = self.get_action()
        if not action:
            return
        action.public = not action.public
        action.save()
        self.msg("Public status of action is now %s" % action.public)
        
    def toggle_secret_sharing(self):
        action = self.get_action(get_all=True)
        if not action:
            return
        if "assist" in self.switches:
            try:
                assist = action
                assist.share_secret = not assist.share_secret
                assist.save()
                self.msg("Your sharing of your secret action is set to %s" % assist.share_secret)
            except CrisisActionAssistant.DoesNotExist:
                self.msg("You are not assisting that action.")
            return
        try:
            targ = self.caller.search(self.rhs)
            if not targ:
                return
            assist = action.assisting_actions.get(dompc=targ.Dominion)
            assist.can_see_secret = not assist.can_see_secret
            assist.save()
            self.msg("%s's ability to see your secret actions is now %s." % (targ, assist.can_see_secret))
            return
        except CrisisActionAssistant.DoesNotExist:
            self.msg("No assistant for that action by that name.")

    def func(self):
        if not self.args and (not self.switches or "old" in self.switches):
            self.list_crises()
            return
        if not self.switches or "old" in self.switches:
            self.view_crisis()
            return
        if "newaction" in self.switches:
            self.new_action()
            return
        if "viewaction" in self.switches:
            self.view_action()
            return
        if "question" in self.switches:
            self.ask_question()
            return
        if "cancel" in self.switches:
            self.msg("This is temporarily disabled.")
            # self.cancel_action()
            return
        if "append" in self.switches:
            self.append_action()
            return
        if "togglepublic" in self.switches:
            self.toggle_secret()
            return
        if "toggleview" in self.switches:
            self.toggle_secret_sharing()
            return
        if "addpoints" in self.switches:
            self.add_action_points()
            return
        if "addresource" in self.switches:
            self.add_resource()
            return
        if "addarmy" in self.switches:
            self.add_army()
            return
        if "invite" in self.switches:
            self.invite_assistant()
            return
        if "secret" in self.switches:
            self.set_secret_action()
            return
        # banished assist to the bottom because it is a default thing
        if "assist" in self.switches:
            self.assist_action()
            return
        if "decline" in self.switches:
            try:
                act_id = int(self.args)
            except ValueError:
                self.msg("Must supply an action number.")
                return
            invitations = self.caller.db.crisis_action_invitations or []
            if act_id in invitations:
                invitations.remove(act_id)
            if invitations:
                self.caller.db.crisis_action_invitations = invitations
            else:
                self.caller.attributes.remove("crisis_action_invitations")
            self.msg("Your remaining invitations: %s" % ", ".join(str(ob) for ob in invitations))
            return
        self.msg("Invalid switch")
