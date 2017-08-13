"""
Commands for the 'Character' app that handles the roster,
stories, the timeline, etc.
"""

from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from .models import (Investigation, Clue, InvestigationAssistant, ClueDiscovery, Theory, RevelationDiscovery, SearchTag,
                     get_random_clue)
from server.utils.prettytable import PrettyTable
from evennia.utils.evtable import EvTable
from server.utils.arx_utils import inform_staff, check_break
from world.dominion.models import Agent, RPEvent
from django.db.models import Q
from world.stats_and_skills import VALID_STATS, VALID_SKILLS


class InvestigationFormCommand(MuxCommand):
    """
    ABC for creating commands based on investigations that process a form.
    """
    form_verb = "Creating"
    form_switches = ("topic", "target", "story", "stat", "skill", "cancel", "finish")
    ap_cost = 10

    def check_ap_cost(self, cost=None):
        if not cost:
            cost = self.ap_cost
            if cost < 0:
                cost = 0
        if self.caller.db.player_ob.pay_action_points(cost):
            return True
        else:
            self.msg("You cannot afford to do that action.")
            return False

    @property
    def form_attr(self):
        return "investigation_form"
    
    @property
    def investigation_form(self):
        return getattr(self.caller.db, self.form_attr)

    @property
    def related_manager(self):
        return self.caller.roster.investigations
    
    def disp_investigation_form(self):
        form = self.investigation_form
        if not form:
            return
        target, story, stat, skill = form[0], form[1], form[2], form[3]
        self.msg("%s an investigation:" % self.form_verb)
        self.msg("{w%s{n: %s" % (self.target_type.capitalize(), target))
        self.msg("{wStory{n: %s" % story)
        self.msg("{wStat{n: %s" % stat)
        self.msg("{wSkill{n: %s" % skill)

    @property
    def target_type(self):
        return "topic"
                 
    @property
    def finished_form(self):
        """Property that validates the form that has been created."""
        try:
            form = self.investigation_form
            topic, actions, stat, skill = form[0], form[1], form[2], form[3]
            if not topic:
                self.msg("You must have a %s defined." % self.target_type.lower())
                return
            if not actions:
                self.msg("You must have a story defined.")
                return
            return topic, actions, stat, skill
        except (TypeError, ValueError, IndexError, AttributeError):
            self.msg("Your investigation form is not yet filled out.")
            return False

    @property
    def start_cost(self):
        return 0

    def pay_costs(self):
        dompc = self.caller.db.player_ob.Dominion
        amt = dompc.assets.social
        amt -= self.start_cost
        if amt < 0:
            self.msg("It costs %s social resources to start a new investigation." % self.start_cost)
            return False
        self.msg("You spend %s social resources to start a new investigation." % self.start_cost)
        dompc.assets.social = amt
        dompc.assets.save()
        return True

    def mark_active(self, created_object):
        """
        Finishes setting up the created object with any fields that need to be filled out,
        and informs the caller of what was done, as well as announces to staff. Saves the
        created object.
        """
        pass

    def create_obj_from_form(self, form):
        """
        Create a new object from our related manager with the form we were given
        from finished form, with appropriate kwargs
        """
        kwargs = {self.target_type: form[0], "actions": form[1], "stat_used": form[2], "skill_used": form[3]}
        return self.related_manager.create(**kwargs)

    def do_finish(self):
        """
        the finished_form property checks if all
        the fields are valid. Further checks on whether the fields can
        be used are done by pay_costs. The object to be created is then
        created using our related_manager property, and the target is
        populated with add_target_to_obj. It's then setup with mark_active
        """
        form = self.finished_form
        if not form:
            return
        if not self.pay_costs():
            return
        ob = self.create_obj_from_form(form)
        self.mark_active(ob)       
        self.caller.attributes.remove(self.form_attr)

    def create_form(self):
        """
        Initially populates the form we use. Other switches will populate
        the fields, which will be used in do_finish()
        """
        investigation = ['', '', '', '', self.caller]
        setattr(self.caller.db, self.form_attr, investigation)
        self.disp_investigation_form()

    def get_target(self):
        """
        Sets the target of the object we'll create. For an investigation,
        this will be the topic. For an assisting investigation, it'll be the ID of the investigation.
        """
        if self.target_type == "topic" and check_break():
            clue = get_random_clue(self.args, self.caller.roster)
            if not clue:
                self.msg("Investigations that require writing a new clue are not allowed during the break.")
                self.msg("Pick a different topic or abort.")
                return
        self.investigation_form[0] = self.args
        self.disp_investigation_form()

    def check_skill(self):
        if self.args.lower() not in self.caller.db.skills:
            self.msg("You have no skill by the name of %s." % self.args)
            return
        return True

    def func(self):
        """
        Base version of the command that can be inherited. It allows for creation of the form with
        the 'new' switch, is populated with 'target', 'story', 'stat', and 'skill', aborted with 'cancel',
        and finished with 'finish'.
        """
        investigation = self.investigation_form
        if "new" in self.switches:
            self.create_form()
            return True
        if set(self.switches) & set(self.form_switches):
            if not investigation:
                self.msg("You need to create a form first with /new.")
                return True
            if "target" in self.switches or "topic" in self.switches:
                self.get_target()
                return True
            if "story" in self.switches:
                investigation[1] = self.args
                self.disp_investigation_form()
                return True
            if "stat" in self.switches:
                if not self.caller.attributes.get(self.args.lower()):
                    self.msg("No stat by the name of %s." % self.args)
                    return
                investigation[2] = self.args
                self.disp_investigation_form()
                return True
            if "skill" in self.switches:
                if not self.check_skill():
                    return
                investigation[3] = self.args
                self.disp_investigation_form()
                return True
            if "cancel" in self.switches:
                self.caller.attributes.remove(self.form_attr)
                self.msg("Investigation creation cancelled.")
                return True
            if "finish" in self.switches:
                self.do_finish()
                return True


class CmdAssistInvestigation(InvestigationFormCommand):
    """
    @helpinvestigate

    Usage:
        @helpinvestigate
        @helpinvestigate/new
        @helpinvestigate/retainer <retainer ID>
        @helpinvestigate/target <investigation ID #>
        @helpinvestigate/story <text of how you/your retainer help>
        @helpinvestigate/stat <stat to use for the check>
        @helpinvestigate/skill <additional skill besides investigation>
        @helpinvestigate/cancel
        @helpinvestigate/finish
        @helpinvestigate/stop
        @helpinvestigate/resume <id #>
        @helpinvestigate/changestory <id #>=<new story>
        @helpinvestigate/changestat <id #>=<new stat>
        @helpinvestigate/changeskill <id #>=<new skill>
        @helpinvestigate/actionpoints <id #>=<AP amount>
        @helpinvestigate/silver <id #>=<additional silver to spend>
        @helpinvestigate/resource <id #>=<resource type>,<amount>
        @helpinvestigate/retainer/stop <retainer ID>
        @helpinvestigate/retainer/resume <id #>=<retainer ID>
        @helpinvestigate/retainer/changestory <retainer ID>/<id #>=<story>
        @helpinvestigate/retainer/changestat <retainer ID>/<id #>=<stat>
        @helpinvestigate/retainer/changeskill <retainer ID>/<id #>=<skill>
        @helpinvestigate/retainer/silver, or /resource, etc., as above

    Helps with an investigation, or orders a retainer to help
    with the investigation. You may only help with one investigation
    at a time, and only if you are not actively investigating something
    yourself. You may stop helping an investigation with /stop, and
    resume it with /resume. To set a retainer to help the investigation,
    use the /retainer switch and supply their number. Entering an invalid
    retainer ID will switch back to you as being the investigation's helper.
    """
    key = "@helpinvestigate"
    aliases = ["+helpinvestigate", "helpinvestigate"]
    locks = "cmd:all()"
    help_category = "Investigation"
    form_verb = "Helping"
    change_switches = ("changestory", "changestat", "changeskill", "actionpoints", "silver", "resource", "resources")

    def pay_costs(self):
        return True

    @property
    def related_manager(self):
        return self.helper.assisted_investigations

    @property
    def form_attr(self):
        return "assist_investigation_form"

    @property
    def helper(self):
        """Returns caller or their retainer who they are using in the investigation"""
        try:
            return self.investigation_form[4] or self.caller
        except IndexError:
            return self.caller

    def disp_investigation_form(self):
        super(CmdAssistInvestigation, self).disp_investigation_form()
        self.msg("{wAssisting Character:{n %s" % self.helper)

    def check_eligibility(self, helper):
        helping = helper.assisted_investigations.filter(currently_helping=True)
        if helping:
            self.msg("%s is already helping an investigation: %s" % (helper, ", ".join(str(ob.investigation.id)
                                                                                       for ob in helping)))
            return False
        formid = self.investigation_form[0]
        if helper == self.caller:
            try:
                if self.caller.roster.investigations.filter(active=True):
                    self.msg("You cannot assist an investigation while having an active investigation.")
                    return False
                if self.caller.roster.investigations.get(id=formid):
                    self.msg("You cannot assist one of your own investigations. You must use a retainer.")
                    return False
            except (TypeError, ValueError, AttributeError, Investigation.DoesNotExist):
                pass

        return True

    def set_helper(self):
        if not self.investigation_form:
            self.msg("No form found. Use /new.")
            return
        try:
            helper = self.caller.db.player_ob.retainers.get(id=self.args).dbobj
            if not helper.db.abilities or helper.db.abilities.get("investigation_assistant", 0) < 1:
                self.msg("%s is not able to assist investigations." % helper)
                return
        except (AttributeError, ValueError, Agent.DoesNotExist):
            self.msg("No retainer by that number. Setting it to be you instead.")
            helper = self.caller
        if not self.check_eligibility(helper):
            return
        self.investigation_form[4] = helper
        self.disp_investigation_form()

    def disp_invites(self):
        invites = self.caller.db.investigation_invitations or []
        # check which are valid
        investigations = Investigation.objects.filter(id__in=invites, ongoing=True, active=True)
        investigations = investigations | self.caller.roster.investigations.filter(ongoing=True)
        self.msg("You are permitted to help the following investigations:\n%s" % "\n".join(
            "  %s (ID: %s)" % (str(ob), ob.id) for ob in investigations))
        invest_ids = [ob.id for ob in investigations]
        # prune out invitations to investigations that are not active
        invites = [num for num in invites if num in invest_ids]
        self.caller.db.investigation_invitations = invites

    @property
    def valid_targ_ids(self):
        invites = self.caller.db.investigation_invitations or []
        if self.helper != self.caller:
            for ob in self.caller.roster.investigations.filter(ongoing=True):
                invites.append(ob.id)
        return invites

    def get_target(self):
        if not self.args:
            self.disp_invites()
            return
        try:
            targ = int(self.args)
        except ValueError:
            self.msg("You must supply the ID of an investigation.")
            return
        if targ not in self.valid_targ_ids:
            self.msg("No investigation by that ID.")
            return
        # check that we can't do our own unless it's a retainer
        if self.investigation_form[4] == self.caller:
            if self.caller.roster.investigations.filter(ongoing=True, id=targ):
                self.msg("You cannot assist your own investigation.")
                return
        else:
            helper = self.investigation_form[4]
            if helper.assisted_investigations.filter(investigation_id=targ):
                self.msg("%s is already helping that investigation. You can /resume helping it." % helper)
                return False
        self.investigation_form[0] = targ
        self.disp_investigation_form()

    def mark_active(self, created_object):
        try:
            if self.helper.roster.investigations.filter(active=True):
                already_investigating = True
            else:
                already_investigating = False
        except AttributeError:
            already_investigating = False
        if not already_investigating and not self.check_ap_cost():
            return
        current_qs = self.helper.assisted_investigations.filter(currently_helping=True)
        if current_qs:
            current_qs.update(currently_helping=False)
            self.msg("%s was currently helping another investigation. Switching." % self.helper)
        if not already_investigating:
            created_object.currently_helping = True
            created_object.save()
            created_object.investigation.do_roll()
            self.msg("%s is now helping %s." % (self.helper, created_object.investigation))
        else:
            self.msg("You already have an active investigation. That must stop before you help another.\n"
                     "Once that investigation is no longer active, you may resume helping this investigation.")
        self.caller.attributes.remove(self.form_attr)

    @property
    def target_type(self):
        return "investigation"

    @property
    def finished_form(self):
        form = super(CmdAssistInvestigation, self).finished_form
        if not form:
            return
        invest_id, actions, stat, skill = form
        if invest_id not in self.valid_targ_ids:
            self.msg("That is not a valid ID of an investigation for %s to assist." % self.helper)
            self.msg("Valid IDs: %s" % ", ".join(self.valid_targ_ids))
            return
        try:
            investigation = Investigation.objects.get(id=invest_id)
        except Investigation.DoesNotExist:
            self.msg("No investigation by that ID found.")
            return
        return investigation, actions, stat, skill

    def disp_currently_helping(self, char):
        self.msg("%s and retainers is helping the following investigations:" % char)
        table = PrettyTable(["ID", "Character", "Investigation Owner", "Currently Helping"])
        investigations = list(char.assisted_investigations.all())
        for retainer in char.db.player_ob.retainers.all():
            try:
                retainer_investigations = list(retainer.dbobj.assisted_investigations.all())
            except AttributeError:
                continue
            if retainer_investigations:
                investigations.extend(retainer_investigations)
        for ob in investigations:
            table.add_row([str(ob.investigation.id), str(ob.char), str(ob.investigation.char),
                           str(ob.currently_helping)])
        self.msg(table)

    def check_skill(self):
        if self.args.lower() not in self.helper.db.skills:
            self.msg("%s has no skill by the name of %s." % (self.helper, self.args))
            return
        return True

    def view_investigation(self):
        try:
            ob = self.caller.assisted_investigations.get(investigation_id=self.args).investigation
        except (InvestigationAssistant.DoesNotExist, TypeError, ValueError):
            self.msg("Could not find an investigation you're helping by that number.")
            self.disp_currently_helping(self.caller)
            return
        self.msg(ob.display())

    def get_retainer_from_args(self, args):
        try:
            if args.isdigit():
                char = self.caller.player.retainers.get(id=args).dbobj
            else:
                char = self.caller.player.retainers.get(name=args).dbobj
            return char
        except (ValueError, TypeError, Agent.DoesNotExist):
            self.msg("Retainer not found by that name or number.")
            return

    def func(self):
        finished = super(CmdAssistInvestigation, self).func()
        if finished:
            return
        if not self.args and not self.switches:
            if self.investigation_form:
                self.disp_investigation_form()
            self.disp_invites()
            self.disp_currently_helping(self.caller)
            return
        if "retainer" in self.switches and len(self.switches) == 1:
            self.set_helper()
            return
        if "view" in self.switches or not self.switches:
            self.view_investigation()
            return
        if "stop" in self.switches:
            if "retainer" in self.switches:
                char = self.get_retainer_from_args(self.args)
                if not char:
                    return
            else:
                char = self.caller
            refund = 0
            for ob in char.assisted_investigations.filter(currently_helping=True):
                ob.currently_helping = False
                ob.save()
                refund += self.ap_cost
            self.msg("%s stopped assisting investigations." % char)
            if refund:
                self.caller.roster.action_points += refund
                self.caller.roster.save()
            return
        if "resume" in self.switches:
            if "retainer" in self.switches:
                try:
                    if self.rhs.isdigit():
                        char = self.caller.player.retainers.get(id=self.rhs).dbobj
                    else:
                        char = self.caller.player.retainers.get(name=self.rhs).dbobj
                except Agent.DoesNotExist:
                    self.msg("No retainer found by that ID or number.")
                    return
            else:  # not a retainer, just the caller. So check if they have an active investigation
                char = self.caller
                if self.caller.roster.investigations.filter(active=True):
                    self.msg("You currently have an active investigation, and cannot assist an investigation.")
                    return
            # check if they already are assisting something
            if char.assisted_investigations.filter(currently_helping=True):
                self.msg("%s is already assisting an investigation." % char)
                return
            try:
                ob = char.assisted_investigations.get(investigation__id=self.lhs)
            except (ValueError, TypeError, InvestigationAssistant.DoesNotExist):
                self.msg("Not helping an investigation by that number.")
                return
            except InvestigationAssistant.MultipleObjectsReturned:
                self.msg("Well, this is awkward. You are assisting that investigation multiple times. This shouldn't "
                         "be able to happen, but here we are.")
                inform_staff("BUG: %s is assisting investigation %s multiple times." % (char, self.lhs))
                return
            # check if they have action points to afford it
            if not self.check_ap_cost():
                return
            # all checks passed, mark it as currently being helped if the investigation exists
            ob.currently_helping = True
            ob.save()
            self.msg("Now helping %s." % ob.investigation)
            return
        if set(self.change_switches) & set(self.switches):
            if "retainer" in self.switches:
                lhs = self.lhs.split("/")
                try:
                    char = self.get_retainer_from_args(lhs[0])
                    if not char:
                        return
                    investigation_id = lhs[1]
                except (IndexError, TypeError, ValueError):
                    self.msg("You must specify <retainer ID>/<investigation ID>.")
                    return
            else:
                char = self.caller
                investigation_id = self.lhs
            try:
                ob = char.assisted_investigations.get(investigation__id=investigation_id)
                if "changestory" in self.switches:
                    ob.actions = self.rhs
                    field = "story"
                elif "changestat" in self.switches:
                    rhs = self.rhs.lower()
                    if rhs not in VALID_STATS:
                        self.msg("Not a valid stat.")
                        return
                    ob.stat_used = rhs
                    field = "stat"
                elif "changeskill" in self.switches:
                    rhs = self.rhs.lower()
                    if rhs not in VALID_SKILLS:
                        self.msg("Not a valid skill.")
                        return
                    ob.skill_used = rhs
                    field = "skill"
                elif "silver" in self.switches:
                    ob = ob.investigation
                    amt = self.caller.db.currency or 0.0
                    try:
                        val = int(self.rhs)
                        amt -= val
                        if amt < 0 or val <= 0:
                            raise ValueError
                        if val % 5000 or (ob.silver + val) > 50000:
                            self.msg("Silver must be a multiple of 5000, 50000 max.")
                            self.msg("Current silver: %s" % ob.silver)
                            return
                    except (TypeError, ValueError):
                        self.msg("You must specify a positive amount that is less than your money on hand.")
                        return
                    self.caller.pay_money(val)
                    ob.silver += val
                    ob.save()
                    # redo the roll with new difficulty
                    ob.do_roll()
                    self.msg("You add %s silver to the investigation." % val)
                    return
                elif "resource" in self.switches or "resources" in self.switches:
                    ob = ob.investigation
                    dompc = self.caller.db.player_ob.Dominion
                    try:
                        rtype, val = self.rhslist[0].lower(), int(self.rhslist[1])
                        if val <= 0:
                            raise ValueError
                        oamt = getattr(ob, rtype)
                        if oamt + val > 50:
                            self.msg("Maximum of 50 per resource. Current value: %s" % oamt)
                            return
                        current = getattr(dompc.assets, rtype)
                        current -= val
                        if current < 0:
                            self.msg("You do not have enough %s resources." % rtype)
                            return
                        setattr(dompc.assets, rtype, current)
                        dompc.assets.save()
                    except (TypeError, ValueError, IndexError, AttributeError):
                        self.msg("Invalid syntax.")
                        return
                    oamt += val
                    setattr(ob, rtype, oamt)
                    ob.save()
                    # redo the roll with new difficulty
                    ob.do_roll()
                    self.msg("You have added %s resources to the investigation." % val)
                    return
                elif "actionpoints" in self.switches:
                    ob = ob.investigation
                    if not ob.active:
                        self.msg("The investigation must be marked active to invest in it.")
                        return
                    # check if we can pay
                    try:
                        amt = int(self.rhs)
                        if amt <= 0:
                            raise ValueError
                        if amt % 5:
                            self.msg("Action points must be a multiple of 5")
                            self.msg("Current action points allocated: %s" % ob.action_points)
                            return
                        if not self.check_ap_cost(amt):
                            return
                    except (TypeError, ValueError):
                        self.msg("Amount of action points must be a positive number you can afford.")
                        return
                    # add action points and save
                    ob.action_points += amt
                    ob.save()
                    self.msg("New action point total is %s." % ob.action_points)
                    return
                else:
                    self.msg("Unrecognized switch.")
                    return
                ob.save()
                self.msg("Changed %s to: %s" % (field, self.rhs))
            except (ValueError, InvestigationAssistant.DoesNotExist):
                self.msg("%s isn't helping an investigation by that number." % char)
            return
        self.msg("Unrecognized switch.")


class CmdInvestigate(InvestigationFormCommand):
    """
    @investigate

    Usage:
        @investigate
        @investigate/history
        @investigate/view <id #>
        @investigate/active <id #>
        @investigate/silver <id #>=<additional silver to spend>
        @investigate/resource <id #>=<resource type>,<amount>
        @investigate/actionpoints <id #>=<additional points to spend>
        @investigate/changetopic <id #>=<new topic>
        @investigate/changestory <id #>=<new story>
        @investigate/changestat <id #>=<new stat>
        @investigate/changeskill <id #>=<new skill>
        @investigate/abandon <id #>
        @investigate/resume <id #>
        @investigate/requesthelp <id #>=<player>
        @investigate/new
        @investigate/topic <keyword to investigate>
        @investigate/story <text of how you do the investigation>
        @investigate/stat <stat to use for the check>
        @investigate/skill <additional skill to use besides investigation>
        @investigate/cancel
        @investigate/finish

    Investigation allows your character to attempt to discover secrets and
    unravel the various mysteries of the game. To start a new investigation,
    use @investigate/new, and then fill out the different required fields
    with /topic and /story before using /finish to end. /topic determines
    a keyword that influences what you can discover in your search, while
    /story is your description of how you are going about it, which GMs can
    read and modify your results accordingly. /stat and /skill allow you to
    specify which stat and skill seem appropriate to the story of your
    investigation, though the 'investigation' skill is always additionally
    used. Use /cancel to cancel the form.

    You may have many ongoing investigations, but only one may advance per
    week. You determine that by selecting the 'active' investigation. You
    may spend silver and resources to attempt to make your investigation
    more likely to find a result. Investigations may be abandoned with
    the /abandon switch, which marks them as no longer ongoing. They may be
    paused with the /pause switch, which marks them as inactive.

    """
    key = "@investigate"
    locks = "cmd:all()"
    help_category = "Investigation"
    aliases = ["+investigate", "investigate"]
    base_cost = 25
    model_switches = ("view", "active", "silver", "resource", "changetopic", "pause", "actionpoints",
                      "changestory", "abandon", "resume", "requesthelp", "changestat", "changeskill")

    # noinspection PyAttributeOutsideInit
    def get_help(self, caller, cmdset):
        doc = self.__doc__
        if caller.db.char_ob:
            caller = caller.db.char_ob
        self.caller = caller
        doc += "\n\nThe cost to make an investigation active is %s action points and %s resources." % (
            self.ap_cost, self.start_cost)
        return doc

    @property
    def ap_cost(self):
        try:
            cost = 50 - (self.caller.db.skills.get('investigation', 0) * 5)
            if cost < 0:
                cost = 0
            return cost
        except AttributeError:
            return 50

    def list_ongoing_investigations(self):
        qs = self.related_manager.filter(ongoing=True)
        table = PrettyTable(["ID", "Topic", "Active?"])
        for ob in qs:
            table.add_row([ob.id, ob.topic, "{wX{n" if ob.active else ""])
        self.msg("Ongoing investigations:")
        self.msg(str(table))

    def list_old_investigations(self):
        qs = self.related_manager.filter(ongoing=False)
        table = PrettyTable(["ID", "Topic"])
        for ob in qs:
            table.add_row([ob.id, ob.topic])
        self.msg("Old investigations")
        self.msg(str(table))

    @property
    def start_cost(self):
        caller = self.caller
        try:
            skill = caller.db.skills.get("investigation", 0)
            return self.base_cost - (5 * skill)
        except AttributeError:
            return self.base_cost

    def mark_active(self, created_object):
        if not (self.related_manager.filter(active=True) or
                self.caller.assisted_investigations.filter(currently_helping=True)):
            if not self.caller.assisted_investigations.filter(currently_helping=True):
                if self.caller.db.player_ob.pay_action_points(self.ap_cost):
                    created_object.active = True
                    self.msg("New investigation created. This has been set as your active investigation " +
                             "for the week, and you may add resources/silver to increase its chance of success.")
                else:
                    self.msg("New investigation created. You could not afford the action points to mark it active.")
            else:
                self.msg("New investigation created. This investigation is not active because you are " +
                         "currently assisting an investigation already.")
        else:
            self.msg("New investigation created. You already are participating in an active investigation " +
                     "for this week, but may still add resources/silver to increase its chance of success " +
                     "for when you next mark this as active.")
        self.msg("You may only have one active investigation per week, and cannot change it once " +
                 "it has received GM attention. Only the active investigation can progress.")
        created_object.save()
        staffmsg = "%s has started an investigation on %s." % (self.caller, created_object.topic)
        if created_object.targeted_clue:
            staffmsg += " They will roll to find clue %s." % created_object.targeted_clue
        else:
            staffmsg += " Their topic does not target a clue, and will automatically fail unless GM'd."
        inform_staff(staffmsg)

    def create_form(self):
        from evennia.scripts.models import ScriptDB
        from datetime import timedelta
        script = ScriptDB.objects.get(db_key="Weekly Update")
        day = timedelta(hours=24, minutes=5)
        if script.time_remaining < day:
            self.msg("It is too close to the end of the week to create another investigation.")
            return
        super(CmdInvestigate, self).create_form()

    def func(self):
        finished = super(CmdInvestigate, self).func()
        if finished:
            return
        caller = self.caller
        entry = caller.roster
        dompc = caller.db.player_ob.Dominion
        investigation = self.investigation_form
        if not self.args and not self.switches:
            if investigation:
                self.disp_investigation_form()
            self.list_ongoing_investigations()
            return
        if "history" in self.switches:
            # display history
            self.list_old_investigations()
            return
        if (set(self.switches) & set(self.model_switches)) or not self.switches:
            try:
                ob = self.related_manager.get(id=int(self.lhs))
            except (TypeError, ValueError):
                caller.msg("Must give ID of investigation.")
                return
            except Investigation.DoesNotExist:
                caller.msg("Investigation not found.")
                return
            if "resume" in self.switches:
                msg = "To mark an investigation as active, use /active."
                if ob.ongoing:
                    self.msg("Already ongoing. %s" % msg)
                    return
                ob.ongoing = True
                ob.save()
                caller.msg("Investigation has been marked to be ongoing. %s" % msg)
                return
            if "pause" in self.switches:
                if not ob.active:
                    self.msg("It was already inactive.")
                    return
                self.caller.roster.action_points += self.ap_cost
                self.caller.roster.save()
                ob.active = False
                ob.save()
                caller.msg("Investigation is no longer active.")
                return
            if "abandon" in self.switches or "stop" in self.switches:
                ob.ongoing = False
                if ob.active:
                    self.caller.roster.action_points += self.ap_cost
                    self.caller.roster.save()
                ob.active = False
                ob.save()
                asslist = []
                for ass in ob.active_assistants:
                    ass.currently_helping = False
                    ass.save()
                    asslist.append(str(ass.char))
                caller.msg("Investigation has been marked to no longer be ongoing nor active.")
                caller.msg("You can resume it later with /resume.")
                if asslist:
                    caller.msg("The following assistants have stopped helping: %s" % ", ".join(asslist))
                return
            if "view" in self.switches or not self.switches:
                caller.msg(ob.display())
                return
            if "active" in self.switches:
                if ob.active:
                    self.msg("It is already active.")
                    return
                try:
                    current_active = entry.investigations.get(active=True)
                except Investigation.DoesNotExist:
                    current_active = None
                if caller.assisted_investigations.filter(currently_helping=True):
                    self.msg("You are currently helping an investigation, and must stop first.")
                    return
                if check_break() and not ob.targeted_clue:
                    self.msg("Investigations that do not target a clue cannot be marked active during the break.")
                    return
                if current_active:
                    if not current_active.automate_result:
                        caller.msg("You already have an active investigation " +
                                   "that has received GMing this week, and cannot be switched.")
                        return
                    if not self.check_ap_cost():
                        return
                    current_active.active = False
                    current_active.save()
                else:  # check cost if we don't have a currently active investigation
                    if not self.check_ap_cost():
                        return
                # can afford it, proceed to turn off assisted investigations and mark active
                for ass in caller.assisted_investigations.filter(currently_helping=True):
                    ass.currently_helping = False
                    ass.save()
                    self.msg("No longer assisting in %s" % ass.investigation)
                ob.active = True
                ob.save()
                caller.msg("%s set to active." % ob)
                return
            if "silver" in self.switches:
                amt = caller.db.currency or 0.0
                try:
                    val = int(self.rhs)
                    amt -= val
                    if amt < 0 or val <= 0:
                        raise ValueError
                    if val % 5000 or (ob.silver + val) > 50000:
                        caller.msg("Silver must be a multiple of 5000, 50000 max.")
                        caller.msg("Current silver: %s" % ob.silver)
                        return
                except (TypeError, ValueError):
                    caller.msg("You must specify a positive amount that is less than your money on hand.")
                    return
                caller.pay_money(val)
                ob.silver += val
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You add %s silver to the investigation." % val)
                return
            if "actionpoints" in self.switches:
                if not ob.active:
                    self.msg("The investigation must be marked active to invest AP in it.")
                    return
                try:
                    val = int(self.rhs)
                    if val <= 0:
                        raise ValueError
                    if val % 5:
                        caller.msg("Action points must be a multiple of 5")
                        caller.msg("Current action points allocated: %s" % ob.action_points)
                        return
                    if not self.check_ap_cost(val):
                        return
                except (TypeError, ValueError):
                    caller.msg("You must specify a positive amount that you can afford.")
                    return
                ob.action_points += val
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You add %s action points to the investigation." % val)
                return
            if "resource" in self.switches or "resources" in self.switches:
                try:
                    rtype, val = self.rhslist[0].lower(), int(self.rhslist[1])
                    if val <= 0:
                        raise ValueError
                    oamt = getattr(ob, rtype)
                    if oamt + val > 50:
                        caller.msg("Maximum of 50 per resource. Current value: %s" % oamt)
                        return
                    current = getattr(dompc.assets, rtype)
                    current -= val
                    if current < 0:
                        caller.msg("You do not have enough %s resources." % rtype)
                        return
                    setattr(dompc.assets, rtype, current)
                    dompc.assets.save()
                except (TypeError, ValueError, IndexError, AttributeError):
                    caller.msg("Invalid syntax.")
                    return
                oamt += val
                setattr(ob, rtype, oamt)
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You have added %s resources to the investigation." % val)
                return
            if "changetopic" in self.switches:
                ob.topic = self.rhs
                ob.save()
                caller.msg("New topic is now %s." % self.args)
                return
            if "changestory" in self.switches:
                ob.actions = self.rhs
                ob.save()
                caller.msg("The new story of your investigation is:\n%s" % self.args)
                return
            if "changestat" in self.switches:
                if self.rhs not in VALID_STATS:
                    self.msg("That is not a valid stat name.")
                    return
                ob.stat_used = self.rhs
                ob.save()
                caller.msg("The new stat is: %s" % self.args)
                return
            if "changeskill" in self.switches:

                if self.rhs not in VALID_SKILLS:
                    self.msg("That is not a valid skill name.")
                    return
                ob.skill_used = self.rhs
                ob.save()
                caller.msg("The new skill is: %s" % self.args)
                return
            if "requesthelp" in self.switches:
                from typeclasses.characters import Character
                try:
                    char = Character.objects.get(db_key__iexact=self.rhs, roster__roster__name="Active")
                except Character.DoesNotExist:
                    self.msg("No active player found by that name.")
                    return
                if char == caller:
                    self.msg("You cannot invite yourself.")
                    return
                if char.assisted_investigations.filter(investigation=ob):
                    self.msg("They are already able to assist the investigation.")
                    return
                current = char.db.investigation_invitations or []
                if ob.id in current:
                    self.msg("They already have an invitation to assist this investigation.")
                    return
                if not (ob.active and ob.ongoing):
                    self.msg("You may only invite others to active investigations.")
                    return
                self.msg("Asking %s to assist with %s." % (char, ob))
                current.append(ob.id)
                char.db.investigation_invitations = current
                inform_msg = "%s has requested your help in their investigation, ID %s.\n" % (caller, ob.id)
                inform_msg += "To assist them, use the {w@helpinvestigate{n command, creating a "
                inform_msg += "form with {w@helpinvestigate/new{n, setting the target with "
                inform_msg += "{w@helpinvestigate/target %s{n, and filling in the other fields." % ob.id
                inform_msg += "\nThe current actions of their investigation are: %s" % ob.actions
                char.db.player_ob.inform(inform_msg, category="Investigation Request From %s" % self.caller,
                                         append=False)
                return
        caller.msg("Invalid switch.")
        return


class CmdAdminInvestigations(MuxPlayerCommand):
    """
    @gminvestigations
    
    Usage:
        @gminvest
        @gminvest/view <ID #>
        @gminvest/target <ID #>=<Clue #>
        @gminvest/randomtarget <ID #>
        @gminvest/roll <ID #>[=<roll mod>,<difficulty>]
        @gminvest/result <ID #>=<result string>
        @gminvest/cluemessage <ID #>=<message>
        @gminvest/setprogress <ID #>=<amount>
        @gminvest/search <character>=<keyword>

    Checks active investigations, and allows you to override their
    automatic results. You can /roll to see a result - base difficulty
    is 50 unless you override it. Specifying a result string will
    cause that to be returned to them in weekly maintenance, otherwise
    it'll process the event as normal to find a clue based on the topic.

    /search is used to search undiscovered clues that match a keyword for
    a given character to try to find possible matches.
    """
    key = "@gminvest"
    aliases = ["@gminvestigations"]
    locks = "cmd:perm(wizards)"
    help_category = "Investigation"
    
    @property
    def qs(self):
        return Investigation.objects.filter(active=True, ongoing=True,
                                            character__roster__name="Active")
    
    def disp_active(self):
        qs = list(self.qs)
        if len(qs) <= 20:
            table = EvTable("ID", "Char", "Topic", "Targeted Clue", "Roll", border="cells", width=78)
            for ob in qs:
                roll = ob.get_roll()
                roll = "{r%s{n" % roll if roll < 1 else "{w%s{n" % roll
                target = "{rNone{n" if not ob.targeted_clue else str(ob.targeted_clue)
                character = "{c%s{n" % ob.character
                table.add_row(ob.id, character, str(ob.topic), target, roll)
        else:
            table = PrettyTable(["ID", "Char", "Topic", "Targeted Clue", "Roll"])
            for ob in qs:
                roll = ob.get_roll()
                roll = "{r%s{n" % roll if roll < 1 else "{w%s{n" % roll
                target = "{rNone{n" if not ob.targeted_clue else str(ob.targeted_clue)[:30]
                character = "{c%s{n" % ob.character
                table.add_row([ob.id, character, str(ob.topic)[:15], target, roll])
        self.caller.msg(str(table))

    def set_roll(self, ob, roll, mod=0, diff=None):
        ob.roll = roll
        ob.save()
        self.msg("Recording their new roll as: %s." % roll)
        check = ob.check_success(modifier=mod, diff=diff)
        if check:
            self.msg("They will {wsucceed{n the check to discover a clue this week.")
        else:
            self.msg("They will {rfail{n the check to discover a clue this week.")

    def func(self):
        caller = self.caller
        if not self.args:
            self.disp_active()
            return
        if "search" in self.switches:
            player = self.caller.search(self.lhs)
            if not player:
                return
            undisco = player.roster.undiscovered_clues.filter(Q(desc__icontains=self.rhs) | Q(name__icontains=self.rhs)
                                                              | Q(search_tags__name__icontains=self.rhs)).distinct()
            self.msg("Clues that match: %s" % ", ".join("(ID:%s, %s)" % (ob.id, ob) for ob in undisco))
            return
        try:
            if "view" in self.switches or not self.switches:
                ob = Investigation.objects.get(id=int(self.args))
                caller.msg(ob.gm_display())
                return
            if "randomtarget" in self.switches:
                ob = Investigation.objects.get(id=int(self.args))
                ob.clue_target = None
                self.msg("%s now targets %s" % (ob, ob.targeted_clue))
                return
            if "target" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                try:
                    targ = Clue.objects.get(id=int(self.rhs))
                except Clue.DoesNotExist:
                    caller.msg("No clue by that ID.")
                    return
                if targ in ob.character.discovered_clues:
                    self.msg("|rThey already have that clue. Aborting.")
                    return
                ob.clue_target = targ
                ob.save()
                caller.msg("%s set to %s." % (ob, targ))
                return
            if "roll" in self.switches:
                mod = 0
                diff = None
                ob = self.qs.get(id=int(self.lhs))
                try:
                    mod = int(self.rhslist[0])
                    diff = int(self.rhslist[1])
                except IndexError:
                    pass
                roll = ob.do_roll(mod=mod, diff=diff)
                self.set_roll(ob, roll)
                return
            if "result" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                ob.result = self.rhs
                ob.save()
                caller.msg("Result is now:\n%s" % ob.result)
                return
            if "setprogress" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                self.set_roll(ob, int(self.rhs))
                return
        except (TypeError, ValueError):
            caller.msg("Arguments must be numbers.")
            return
        except Investigation.DoesNotExist:
            caller.msg("No Investigation by that ID.")
            return
        caller.msg("Invalid switch.")
        return


class CmdListClues(MuxPlayerCommand):
    """
    @clues
    
    Usage:
        @clues
        @clues <clue #>
        @clues/share <clue #>[,<clue #>...]=<target>[,<target2><target3>,...]
        @clues/search <text>

    Displays the clues that your character has discovered in game,
    or shares them with others. /search returns the clues that
    contain the text specified.
    """
    key = "@clues"
    locks = "cmd:all()"
    aliases = ["+clues", "@clue", "+clue", "@zoinks", "@jinkies"]
    help_category = "Investigation"

    def get_help(self, caller, cmdset):
        if caller.db.player_ob:
            caller = caller.db.player_ob
        doc = self.__doc__
        doc += "\n\nYour cost of sharing clues is %s." % caller.clue_cost
        return doc
    
    @property
    def finished_clues(self):
        try:
            return self.caller.roster.finished_clues
        except AttributeError:
            return ClueDiscovery.objects.none()
    
    def disp_clue_table(self):
        caller = self.caller
        table = PrettyTable(["{wClue #{n", "{wSubject{n"])
        clues = self.finished_clues.order_by('date')
        if "search" in self.switches:
            msg = "{wMatching Clues{n\n"
            clues = clues.filter(Q(message__icontains=self.args) | Q(clue__desc__icontains=self.args) |
                                 Q(clue__name__icontains=self.args))
        else:
            msg = "{wDiscovered Clues{n\n"
        for clue in clues:
            table.add_row([clue.id, clue.name])
        msg += str(table)
        caller.msg(msg, options={'box': True})

    def func(self):
        caller = self.caller
        clues = self.finished_clues
        if not self.args:
            if not clues:
                caller.msg("Nothing yet.")
                return
            self.disp_clue_table()
            return
        if "search" in self.switches:
            self.disp_clue_table()
            return
        if "share" in self.switches:
            clues_to_share = []
            for arg in self.lhslist:
                try:
                    clue = clues.get(id=arg)
                except (ClueDiscovery.DoesNotExist, ValueError, TypeError):
                    caller.msg("No clue found by that ID.")
                    continue
                if not clue.clue.allow_sharing:
                    self.msg("%s cannot be shared." % clue.clue)
                    return
                clues_to_share.append(clue)
            if not clues_to_share:
                return
            shared_names = []
            cost = len(self.rhslist) * len(clues_to_share) * self.caller.clue_cost
            if cost > self.caller.roster.action_points:
                self.msg("Sharing that many clues would cost %s action points." % cost)
                return
            for arg in self.rhslist:
                pc = caller.search(arg)
                if not pc:
                    continue
                tarchar = pc.db.char_ob
                calchar = caller.db.char_ob
                if not tarchar.location or tarchar.location != calchar.location:
                    self.msg("You can only share clues with someone in the same room. Please don't share clues without "
                             "at least some RP talking about it.")
                    continue
                for clue in clues_to_share:
                    clue.share(pc.roster)
                shared_names.append(str(pc.roster))
            if shared_names:
                self.caller.pay_action_points(cost)
                caller.msg("You have shared the clues '%s' with %s." % (
                    ", ".join(str(ob.clue) for ob in clues_to_share),
                    ", ".join(shared_names)))
            else:
                self.msg("Shared nothing.")
            return
        # get clue for display or sharing
        try:
            clue = clues.get(id=self.lhs)  
        except (ClueDiscovery.DoesNotExist, ValueError, TypeError):
            caller.msg("No clue found by that ID.")
            self.disp_clue_table()
            return
        if not self.switches:
            caller.msg(clue.display())
            return
        caller.msg("Invalid switch")
        return


class CmdListRevelations(MuxPlayerCommand):
    """
    @revelations
    
    Usage:
        @revelations
    """
    key = "@revelations"
    locks = "cmd:all()"
    help_category = "Investigation"

    def disp_rev_table(self):
        caller = self.caller
        table = PrettyTable(["{wRevelation #{n", "{wSubject{n"])
        revs = caller.roster.revelations.all()
        msg = "{wDiscovered Revelations{n\n"
        for rev in revs:
            table.add_row([rev.id, rev.revelation.name])
        msg += str(table)
        caller.msg(msg, options={'box': True})

    def func(self):
        if not self.args:
            self.disp_rev_table()
            return
        try:
            rev = self.caller.roster.revelations.get(id=self.args)
        except (ValueError, TypeError, RevelationDiscovery.DoesNotExist):
            self.msg("No revelation by that number.")
            self.disp_rev_table()
            return
        self.msg(rev.display())
        clues = self.caller.roster.finished_clues.filter(clue__revelations=rev.revelation)
        self.msg("Related Clues: %s" % ", ".join(str(clue.clue) for clue in clues))


class CmdListMysteries(MuxPlayerCommand):
    """
    @mysteries
    
    Usage:
        @mysteries
    """
    key = "@mysteries"
    locks = "cmd:all()"
    help_category = "Investigation"

    def func(self):
        if not self.args:
            return


class CmdTheories(MuxPlayerCommand):
    """
    @theories

    Usage:
        @theories
        @theories/mine
        @theories <theory ID #>
        @theories/share <theory ID #>=<player>[,<player2>,...]
        @theories/create <topic>=<description>
        @theories/addclue <theory ID #>=<clue ID #>
        @theories/rmclue <theory ID #>=<clue ID #>
        @theories/addrelatedtheory <your theory ID #>=<other's theory ID #>
        @theories/forget <theory ID #>
        @theories/editdesc <theory ID #>=<desc>
        @theories/edittopic <theory ID #>=<topic>
        @theories/shareall <theory ID #>=<player>
        @theories/readall <theory ID #>
        @theories/addeditor <theory ID #>=<player>
        @theories/rmeditor <theory ID #>=<player>

    Allows you to create and share theories your character comes up with,
    and associate them with clues and other theories. You may only create
    associations for theories that you created.

    /shareall allows you to also share any clue you know that is related
    to the theory specify.
    """
    key = "@theories"
    locks = "cmd:all()"
    help_category = "Investigation"

    def display_theories(self):
        table = EvTable("{wID #{n", "{wTopic{n")
        if "mine" in self.switches:
            qs = list(self.caller.created_theories.all().order_by('id'))
            qs += list(self.caller.editable_theories.all().order_by('id'))
        else:
            qs = self.caller.known_theories.all()
            qs.order_by('id')
        for theory in qs:
            table.add_row(theory.id, theory.topic)
        self.msg(table)

    def view_theory(self):
        try:
            theory = self.caller.known_theories.get(id=self.args)
        except (Theory.DoesNotExist, ValueError, TypeError):
            self.msg("No theory by that ID.")
            return
        self.msg(theory.display())
        known_clues = [ob.clue.id for ob in self.caller.roster.finished_clues]
        disp_clues = theory.related_clues.filter(id__in=known_clues)
        self.msg("{wRelated Clues:{n %s" % ", ".join(ob.name for ob in disp_clues))
        if "readall" in self.switches:
            for clue in disp_clues:
                clue_display = "{wName{n: %s\n\n%s\n" % (clue.name, clue.desc)
                self.msg(clue_display)

    def func(self):
        if not self.args:
            self.display_theories()
            return
        if not self.switches or "view" in self.switches or "readall" in self.switches:
            self.view_theory()
            return
        if "search" in self.switches:
            matches = self.caller.known_theories.filter(Q(topic__icontains=self.args) | Q(desc__icontains=self.args))
            self.msg("Matches: %s" % ", ".join(str(ob.id) for ob in matches))
            return
        if "create" in self.switches:
            theory = self.caller.created_theories.create(topic=self.lhs, desc=self.rhs)
            self.caller.known_theories.add(theory)
            self.msg("You have created a new theory.")
            return
        if "share" in self.switches or "shareall" in self.switches:
            try:
                theory = self.caller.known_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory found by that ID.")
                return
            targs = []
            for arg in self.rhslist:
                targ = self.caller.search(arg)
                if not targ:
                    continue
                targs.append(targ)
            if not targs:
                return
            clues = self.caller.roster.finished_clues.filter(clue__id__in=theory.related_clues.all())
            per_targ_cost = self.caller.clue_cost
            for targ in targs:
                if "shareall" in self.switches:
                    cost = len(targs) * len(clues) * per_targ_cost
                    if cost > self.caller.roster.action_points:
                        self.msg("That would cost %s action points." % cost)
                        return
                    try:
                        if targ.db.char_ob.location != self.caller.db.char_ob.location:
                            self.msg("You must be in the same room.")
                            continue
                    except AttributeError:
                        self.msg("One of you does not have a character object.")
                        continue
                    for clue in clues:
                        if not clue.clue.allow_sharing:
                            self.msg("%s cannot be shared. Skipping." % clue.clue)
                            continue
                        clue.share(targ.roster)
                        self.msg("Shared clue %s with %s" % (clue.name, targ))
                    self.caller.pay_action_points(cost)
                if theory in targ.known_theories.all():
                    self.msg("They already know that theory.")
                    continue
                targ.known_theories.add(theory)
                self.msg("Theory %s added to %s." % (self.lhs, targ))
                targ.inform("%s has shared a theory with you." % self.caller, category="Theories")
            return
        if "delete" in self.switches or "forget" in self.switches:
            try:
                theory = self.caller.known_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory by that ID.")
                return
            self.caller.known_theories.remove(theory)
            self.caller.editable_theories.remove(theory)
            self.msg("Theory forgotten.")
            if not theory.known_by.all():  # if no one knows about it now
                theory.delete()
            return
        if "addeditor" in self.switches or "rmeditor" in self.switches:
            try:
                theory = self.caller.created_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory by that ID.")
                return
            player = self.caller.search(self.rhs)
            if not player:
                return
            if "addeditor" in self.switches:
                player.editable_theories.add(theory)
                self.msg("%s added as an editor." % player)
                return
            if "rmeditor" in self.switches:
                player.editable_theories.remove(theory)
                self.msg("%s added as an editor." % player)
                return
        try:
            theory = Theory.objects.filter(Q(can_edit=self.caller) | Q(creator=self.caller)).distinct().get(id=self.lhs)
        except (Theory.DoesNotExist, ValueError):
            self.msg("You cannot edit a theory by that number.")
            return
        if "editdesc" in self.switches:
            theory.desc = self.rhs
            theory.save()
            self.msg("New desc is: %s" % theory.desc)
            for player in theory.known_by.all():
                if player == self.caller:
                    continue
                player.inform("%s has been edited." % theory, category="Theories")
            return
        if "edittopic" in self.switches:
            theory.topic = self.rhs
            theory.save()
            self.msg("New topic is: %s" % theory.topic)
            return
        if "addrelatedtheory" in self.switches or "rmrelatedtheory" in self.switches:
            try:
                other_theory = self.caller.known_theories.get(id=self.rhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("You do not know a theory by that id.")
                return
            if "addrelatedtheory" in self.switches:
                theory.related_theories.add(other_theory)
                self.msg("Theory added.")
            else:
                theory.related_theories.remove(other_theory)
                self.msg("Theory removed.")
            return
        if "addclue" in self.switches or "rmclue" in self.switches:
            try:
                clue = self.caller.roster.finished_clues.get(id=self.rhs)
            except (ClueDiscovery.DoesNotExist, ValueError, TypeError, AttributeError):
                self.msg("No clue by that ID.")
                return
            if "addclue" in self.switches:
                theory.related_clues.add(clue.clue)
                self.msg("Added clue %s to theory." % clue.name)
            else:
                theory.related_clues.remove(clue.clue)
                self.msg("Removed clue %s from theory." % clue.name)
            return
        self.msg("Invalid switch.")


class CmdPRPClue(MuxPlayerCommand):
    """
    Creates a clue for a PRP you ran

    Usage:
        +prpclue
        +prpclue/create
        +prpclue/event <event ID>
        +prpclue/name <clue name>
        +prpclue/desc <description>
        +prpclue/difficulty <investigation difficulty, 1-50>
        +prpclue/tags <tag 1>,<tag 2>,etc
        +prpclue/fake
        +prpclue/noinvestigate
        +prpclue/noshare
        +prpclue/finish
        +prpclue/abandon
        +prpclue/sendclue <clue ID>=<participant>
        +prpclue/listclues <event ID>

    Allows a GM to create custom clues for their PRP, and then send it to
    participants. Tags are the different keywords/phrases that allow it
    to be matched to an investigate. Setting a clue as fake means that it's
    false/a hoax. /noinvestigate and /noshare prevent investigating the
    clue or sharing it, respectively.

    Once the clue is created, it can be sent to any participant with the
    /sendclue switch.
    """
    key = "+prpclue"
    help_category = "Investigation"
    locks = "cmd: all()"
    aliases = ["prpclue", "@prpclue"]

    @property
    def gm_events(self):
        """
        All the events this caller has GM'd
        Returns:
            events (queryset): Queryset of RPEvents
        """
        return self.caller.Dominion.events_gmd.all()

    def list_gm_events(self):
        self.msg("Events you have GM'd:\n%s" % "\n".join("%s (#%s)" % (ob.name, ob.id) for ob in self.gm_events))

    def display_form(self):
        form = self.caller.db.clue_creation_form
        if not form:
            self.msg("You are not presently creating a clue for any of your events.")
            return
        event = None
        if form[2]:
            try:
                event = self.gm_events.get(id=form[2])
            except RPEvent.DoesNotExist:
                pass
        msg = "{wName{n: %s\n" % form[0]
        msg += "{wDesc{n: %s\n" % form[1]
        msg += "{wEvent:{n %s\n" % event
        msg += "{wDifficulty{n: %s\n" % form[3]
        msg += "{wTags:{n %s\n" % form[4]
        msg += "{wReal:{n %s\n" % form[5]
        msg += "{wCan Investigate:{n %s\n" % form[6]
        msg += "{wCan Share:{n %s\n" % form[7]
        self.msg(msg)
        return

    def get_event(self):
        try:
            event = self.gm_events.get(id=self.args)
            return event
        except (RPEvent.DoesNotExist, ValueError, TypeError):
            self.msg("No Event by that number.")
            self.list_gm_events()

    def func(self):
        if not self.args and not self.switches:
            self.list_gm_events()
            self.display_form()
            return
        if "abandon" in self.switches:
            self.caller.attributes.remove("clue_creation_form")
            self.msg("Abandoned.")
            return
        if "create" in self.switches:
            form = ["", "", None, 25, "", True, True, True]
            self.caller.db.clue_creation_form = form
            self.display_form()
            return
        if "listclues" in self.switches:
            event = self.get_event()
            if not event:
                return
            self.msg("Clues: %s" % ", ".join("%s (#%s)" % (clue, clue.id) for clue in event.clues.all()))
            return
        if "sendclue" in self.switches:
            try:
                clue = Clue.objects.filter(event__in=self.gm_events).distinct().get(id=self.lhs)
            except (TypeError, ValueError, Clue.DoesNotExist):
                self.msg("No clue found by that ID.")
                return
            targ = self.caller.search(self.rhs)
            if not targ:
                return
            if targ.Dominion not in clue.event.participants.all():
                self.msg("Target is not among the participants of that event.")
                return
            targ.roster.discover_clue(clue)
            self.msg("You have sent them a clue.")
            targ.inform("A new clue has been sent to you about event %s. Use @clues to view it." % clue.event,
                        category="Clue Discovery")
            return
        form = self.caller.db.clue_creation_form
        if not form:
            self.msg("Use /create to start a new form.")
            return
        if "finish" in self.switches:
            name = form[0]
            desc = form[1]
            if not (name and desc):
                self.msg("Both name and desc must be set.")
                return
            try:
                event = self.gm_events.get(id=form[2])
            except (RPEvent.DoesNotExist, TypeError, ValueError):
                self.msg("Event must be set.")
                return
            rating = form[3]
            tag_names = form[4].split(",")
            search_tags = []
            for tag_name in tag_names:
                try:
                    search_tag = SearchTag.objects.get(name__iexact=tag_name)
                except SearchTag.DoesNotExist:
                    search_tag = SearchTag.objects.create(name=tag_name)
                search_tags.append(search_tag)
            red_herring = not form[5]
            allow_investigation = form[6]
            allow_sharing = form[7]
            clue = event.clues.create(name=name, desc=desc, rating=rating, red_herring=red_herring,
                                      allow_investigation=allow_investigation, allow_sharing=allow_sharing)
            for search_tag in search_tags:
                clue.search_tags.add(search_tag)
            self.msg("Clue #%s created." % clue.id)
            inform_staff("Clue '%s' created for event '%s'." % (clue, event))
            self.caller.attributes.remove("clue_creation_form")
            return
        if "name" in self.switches:
            if Clue.objects.filter(name__iexact=self.args).exists():
                self.msg("There already is a clue by that name.")
                return
            form[0] = self.args
        if "desc" in self.switches:
            form[1] = self.args
        if "event" in self.switches:
            event = self.get_event()
            if not event:
                return
            form[2] = event.id
        if "difficulty" in self.switches:
            try:
                form[3] = int(self.args)
            except ValueError:
                self.msg("Must be a number.")
        if "tags" in self.switches:
            form[4] = self.args
        if "fake" in self.switches:
            form[5] = not form[5]
        if "noinvestigate" in self.switches:
            form[6] = not form[6]
        if "noshare" in self.switches:
            form[7] = not form[7]
        self.caller.db.clue_creation_form = form
        self.display_form()
