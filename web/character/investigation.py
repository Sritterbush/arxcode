"""
Commands for the 'Character' app that handles the roster,
stories, the timeline, etc.
"""

from django.conf import settings
from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand, MuxPlayerCommand
from .models import Investigation, Clue
from server.utils.prettytable import PrettyTable
from server.utils.utils import inform_staff

class CmdInvestigate(MuxCommand):
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
    form_switches = ("topic", "story", "stat", "skill", "cancel", "finish")
    model_switches = ("view", "active", "silver", "resource", "changetopic",
                      "changestory", "abandon", "resume")
    def disp_investigation_form(self):
        caller = self.caller
        form = caller.db.investigation_form
        if not form:
            return
        topic,story,stat,skill = form[0], form[1], form[2], form[3]
        caller.msg("Creating an investigation:")
        caller.msg("{wTopic{n: %s" % topic)
        caller.msg("{wStory{n: %s" % story)
        caller.msg("{wStat{n: %s" % stat)
        caller.msg("{wSkill{n: %s" % skill)

    def list_ongoing_investigations(self):
        caller = self.caller
        entry = caller.roster
        qs = entry.investigations.filter(ongoing=True)
        table = PrettyTable(["ID", "Topic", "Active?"])
        for ob in qs:
            table.add_row([ob.id, ob.topic, "{wX{n" if ob.active else ""])
        caller.msg("Ongoing investigations:")
        caller.msg(str(table))

    def list_old_investigations(self):
        caller = self.caller
        entry = caller.roster
        qs = entry.investigations.filter(ongoing=False)
        table = PrettyTable(["ID", "Topic"])
        for ob in qs:
            table.add_row([ob.id, ob.topic])
        caller.msg("Old investigations")
        caller.msg(str(table))

    @property
    def start_cost(self):
        caller = self.caller
        skill = caller.db.skills.get("investigation", 0)
        return self.base_cost - (5 * skill)
        
    def func(self):
        caller = self.caller
        entry = caller.roster
        dompc = caller.db.player_ob.Dominion
        investigation = caller.db.investigation_form
        if not self.args and not self.switches:
            if investigation:
                self.disp_investigation_form()
            self.list_ongoing_investigations()
            return
        if "history" in self.switches:
            # display history
            self.list_old_investigations()
            return
        if "new" in self.switches:
            investigation = ['', '', '', '']
            caller.db.investigation_form = investigation
            self.disp_investigation_form()
            return
        if set(self.switches) & set(self.form_switches):
            if not investigation:
                caller.msg("You need to create a form first with /new.")
                return
            if "topic" in self.switches:
                investigation[0] = self.args
                self.disp_investigation_form()
                return
            if "story" in self.switches:
                investigation[1] = self.args
                self.disp_investigation_form()
                return
            if "stat" in self.switches:
                investigation[2] = self.args
                self.disp_investigation_form()
                return
            if "skill" in self.switches:
                investigation[3] = self.args
                self.disp_investigation_form()
                return
            if "cancel" in self.switches:
                caller.attributes.remove("investigation_form")
                caller.msg("Investigation abandoned.")
                return
            if "finish" in self.switches:
                form = investigation
                topic,actions,stat,skill = form[0], form[1], form[2], form[3]
                if not topic:
                    caller.msg("You must have a topic defined.")
                    return
                if not actions:
                    caller.msg("You must have a story defined.")
                    return
                amt = dompc.assets.social
                amt -= self.start_cost
                if amt < 0:
                    caller.msg("It costs %s social resources to start a new investigation." % self.start_cost)
                    return
                caller.msg("You spend %s social resources to start a new investigation." % self.start_cost)
                dompc.assets.social = amt
                dompc.assets.save()
                ob = entry.investigations.create(topic=topic, actions=actions)
                if stat:
                    ob.stat_used = stat
                if skill:
                    ob.skill_used = skill
                if not entry.investigations.filter(active=True):
                    ob.active = True
                    caller.msg("New investigation created. This has been set as your active investigation " +
                               "for the week, and you may add resources/silver to increase its chance of success.")
                else:
                    caller.msg("New investigation created. You already have an active investigation for this week, " +
                               "but may still add resources/silver to increase its chance of success for when you next mark this as active.")
                caller.msg("You may only have one active investigation per week, and cannot change it once " +
                           "it has received GM attention. Only the active investigation can progress.")
                ob.save()
                staffmsg = "%s has started an investigation on %s." % (caller, ob.topic)
                if ob.targeted_clue:
                    staffmsg += " They will roll to find clue %s." % ob.targeted_clue
                else:
                    staffmsg += " Their topic does not target a clue, and will automatically fail unless GM'd."
                inform_staff(staffmsg)
                caller.attribute.remove("investigation_form")
                return
        if set(self.switches) & set(self.model_switches):
            try:
                ob = entry.investigations.get(id=int(self.lhs))
            except (TypeError, ValueError):
                caller.msg("Must give ID of investigation.")
                return
            except Investigation.DoesNotExist:
                caller.msg("Investigation not found.")
                return
            if "resume" in self.switches:
                ob.ongonig = True
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
        @gminvest/setclueprogress <ID #>=<amount>

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
        table = PrettyTable(["ID", "Char", "Topic", "Targeted Clue", "Difficulty"])
        for ob in self.qs:
            table.add_row([ob.id, ob.character, ob.topic, ob.targeted_clue, ob.difficulty])
        self.caller.msg(str(table))
    
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
                ob.roll = roll
                caller.msg("Recording their new roll as: %s." % roll)
                check = ob.check_success(modifier=mod, diff=diff)
                if check:
                    caller.msg("They will succeed the check to discover a clue this week.")
                else:
                    caller.msg("They will fail the check to discover a clue this week.")
                return
            if "result" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                ob.result = self.rhs
                ob.save()
                caller.msg("Result is now:\n%s" % ob.result)
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
