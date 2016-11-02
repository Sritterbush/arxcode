"""
Commands for the 'Character' app that handles the roster,
stories, the timeline, etc.
"""

from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from .models import Investigation, Clue
from server.utils.prettytable import PrettyTable
from evennia.utils.evtable import EvTable
from server.utils.utils import inform_staff


class InvestigationFormCommand(MuxCommand):
    """
    ABC for creating commands based on investigations that process a form.
    """
    form_verb = "Creating"
    form_switches = ("topic", "target", "story", "stat", "skill", "cancel", "finish")

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
        target,story,stat,skill = form[0], form[1], form[2], form[3]
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
            topic,actions,stat,skill = form[0], form[1], form[2], form[3]
            if not topic:
                self.msg("You must have a %s defined." % self.target_type.lower())
                return
            if not actions:
                self.msg("You must have a story defined.")
                return
            return (topic, actions, stat, skill)
        except Exception:
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

    def mark_active(self, ob):
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
        topic,actions,stat,skill = form[0], form[1], form[2], form[3]
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
                self.msg("Investigation abandoned.")
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
        @helpinvestigate/stop <id #>
        @helpinvestigate/resume <id #>
        @helpinvestigate/retainerstop <id #>

    Helps with an investigation, or orders a retainer to help
    with the investigation. You may only help with one investigation
    at a time, and only if you are not actively investigating something
    yourself. You may stop helping an investigation with /stop, and
    resume it with /resume. To set a retainer to help the investigation,
    use the /retainer switch and supply their number. Entering an invalid
    retainer ID will switch back to you as being the investigation's helper.
    """
    key = "@helpinvestigate"
    alises = ["+helpinvestigate", "helpinvestigate"]
    locks = "cmd:all()"
    help_category = "Investigation"
    form_verb = "Helping"
    
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
        "Returns caller or their retainer who they are using in the investigation"
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
            self.msg("%s is already helping an investigation: %s" % (helper, ", ".join(str(ob.investigation.id) for ob in helping)))
            return False
        if helper == self.caller:
            try:
                if self.caller.roster.investigations.filter(active=True):
                    self.msg("You cannot assist an investigation while having an active investigation.")
                    return False
                formid = self.investigation_form[0]
                if self.caller.roster.investigations.get(id=formid):
                    self.msg("You cannot assist one of your own investigations. You must use a retainer.")
                    return False
            except Exception:
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
        except ArithmeticError:
            self.msg("No retainer by that number. Setting it to be you instead.")
            helper = self.caller
        if not self.check_eligibility(helper):
            return
        self.investigation_form[4] = helper
        self.disp_investigation_form()

    def disp_invites(self):
        invites = self.caller.db.investigation_invitations or []
        investigations = Investigation.objects.filter(id__in=invites, ongoing=True)
        investigations = investigations | self.caller.roster.investigations.filter(ongoing=True)
        self.msg("You are permitted to help the following investigations:\n%s" % \
                 "\n".join("  %s (ID: %s)" % (str(ob), ob.id) for ob in investigations))
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
        self.investigation_form[0] = targ
        self.disp_investigation_form()

    def mark_active(self, ob):
        try:
            current = ob.assisted_investigations.get(currently_helping=True)
            current.currently_helping = False
            current.save()
            self.msg("You were currently helping another investigation. Switching.")
        except Exception:
            pass
        ob.currently_helping = True
        ob.save()
        self.msg("%s is now helping %s." % (self.helper, ob))
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
        return (investigation, actions, stat, skill)

    def disp_currently_helping(self, char):
        self.msg("%s is helping the following investigations:" % char)
        table = PrettyTable(["ID", "Investigation Owner", "Currently Helping"])
        for ob in char.assisted_investigations.all():
            table.add_row([str(ob.investigation.id), str(ob.investigation.char), str(ob.currently_helping)])
        self.msg(table)

    def check_skill(self):
        if self.args.lower() not in self.helper.db.skills:
            self.msg("%s has no skill by the name of %s." % (self.helper, self.args))
            return
        return True
    
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
        if "retainer" in self.switches:
            self.set_helper()
            return
        

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
        @investigate/changetopic <id #>=<new topic>
        @investigate/changestory <id #>=<new story>
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
    the /abandon switch, which marks them as no longer ongoing.
        
    """
    key = "@investigate"
    locks = "cmd:all()"
    help_category = "Investigation"
    aliases = ["+investigate", "investigate"]
    base_cost = 25
    model_switches = ("view", "active", "silver", "resource", "changetopic",
                      "changestory", "abandon", "resume", "requesthelp")
    

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
        skill = caller.db.skills.get("investigation", 0)
        return self.base_cost - (5 * skill)

    def add_target_to_obj(self, ob, target):
        ob.topic = target

    def mark_active(self, ob):
        if not (self.related_manager.filter(active=True) or
                    self.caller.assisted_investigations.filter(currently_helping=True)):
            ob.active = True
            self.msg("New investigation created. This has been set as your active investigation " +
                       "for the week, and you may add resources/silver to increase its chance of success.")
        else:
            self.msg("New investigation created. You already are participating in an active investigation " +
                     "for this week, but may still add resources/silver to increase its chance of success " +
                     "for when you next mark this as active.")
        self.msg("You may only have one active investigation per week, and cannot change it once " +
                   "it has received GM attention. Only the active investigation can progress.")
        ob.save()
        staffmsg = "%s has started an investigation on %s." % (self.caller, ob.topic)
        if ob.targeted_clue:
            staffmsg += " They will roll to find clue %s." % ob.targeted_clue
        else:
            staffmsg += " Their topic does not target a clue, and will automatically fail unless GM'd."
        inform_staff(staffmsg)
        
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
        if set(self.switches) & set(self.model_switches):
            try:
                ob = self.related_manager.get(id=int(self.lhs))
            except (TypeError, ValueError):
                caller.msg("Must give ID of investigation.")
                return
            except Investigation.DoesNotExist:
                caller.msg("Investigation not found.")
                return
            if "resume" in self.switches:
                ob.ongoing = True
                ob.save()
                caller.msg("Investigation has been marked to be ongoing.")
                return
            if "abandon" in self.switches:
                ob.ongoing = False
                ob.active = False
                ob.save()
                caller.msg("Investigation has been marked to no longer be ongoing.")
                return
            if "view" in self.switches:
                caller.msg(ob.display())
                return
            if "active" in self.switches:
                try:
                    current_active = entry.investigations.get(active=True)
                except Investigation.DoesNotExist:
                    current_active = None
                if current_active:
                    if not current_active.automate_result:
                        caller.msg("You already have an active investigation " +
                                   "that has received GMing this week, and cannot be switched.")
                        return
                    if caller.assisted_investigations.filter(currently_helping=True):
                        self.msg("You are currently assisting with an investigation.")
                        return
                    current_active.active = False
                    current_active.save()
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
            if "resource" in self.switches or "resources" in self.switches:
                try:
                    rtype,val = self.rhslist[0].lower(), int(self.rhslist[1])
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
            if "requesthelp" in self.switches:
                try:
                    from typeclasses.characters import Character
                    char = Character.objects.get(db_key__iexact=self.rhs, roster__roster__name="Active")
                except Exception:
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
                self.msg("Asking %s to assist with %s." % (char, ob))
                current.append(ob.id)
                char.db.investigation_invitations = current
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
        @gminvest/roll <ID #>[=<roll mod>,<difficulty>]
        @gminvest/result <ID #>=<result string>
        @gminvest/cluemessage <ID #>=<message>
        @gminvest/setprogress <ID #>=<amount>

    Checks active investigations, and allows you to override their
    automatic results. You can /roll to see a result - base difficulty
    is 50 unless you override it. Specifying a result string will
    cause that to be returned to them in weekly maintenance, otherwise
    it'll process the event as normal to find a clue based on the topic.
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
        table = EvTable("ID", "Char", "Topic", "Targeted Clue", "Roll", border="cells", width=78)
        for ob in self.qs:
            roll = "{r%s{n" % ob.roll if ob.roll < 1 else "{w%s{n" % ob.roll
            table.add_row(ob.id, ob.character, str(ob.topic), str(ob.targeted_clue), roll)
        self.caller.msg(str(table))

    def set_roll(self, ob, roll, mod=0, diff=None):
        ob.roll = roll
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
        try:
            if "view" in self.switches or not self.switches:
                ob = Investigation.objects.get(id=int(self.args))
                caller.msg(ob.gm_display())
                return
            if "target" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                try:
                    targ = Clue.objects.get(id=int(self.rhs))
                except Clue.DoesNotExist:
                    caller.msg("No clue by that ID.")
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
            import traceback
            traceback.print_exc()
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
        @clues/share <clue #>=<target>
    """
    key = "@clues"
    locks = "cmd:all()"
    aliases = ["+clues", "@clue", "+clue", "@zoinks", "@jinkies"]
    help_category = "Investigation"
    
    @property
    def finished_clues(self):
        try:
            return self.caller.roster.finished_clues
        except Exception:
            return []
    
    def disp_clue_table(self):
        caller = self.caller
        table = PrettyTable(["{wClue #{n", "{wSubject{n"])
        clues = self.finished_clues
        msg = "{wDiscovered Clues{n\n"
        for clue in clues:
            table.add_row([clue.id, clue.name])
        msg += str(table)
        caller.msg(msg, options={'box':True})
    def func(self):
        caller = self.caller
        clues = self.finished_clues
        if not self.args:
            if not clues:
                caller.msg("Nothing yet.")
                return
            self.disp_clue_table()
            return
        # get clue for display or sharing
        try:
            clue = clues.get(id=self.lhs)  
        except Exception:
            caller.msg("No clue found by that ID.")
            self.disp_clue_table()
            return
        if not self.switches:
            caller.msg(clue.display())
            return
        if "share" in self.switches:
            pc = caller.search(self.rhs)
            if not pc:
                return
            clue.share(pc.roster)
            caller.msg("You have shared the clue '%s' with %s." % (clue, pc.roster))
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
    def func(self):
        caller = self.caller
        if not self.args:
            return

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
        caller = self.caller
        if not self.args:
            return
