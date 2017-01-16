"""
Job/Request and character application command module.

Jobs and Apps will be two more manager objects that will
be cloned and set to some staff location or carried around
on the superuser. While a little clunky that they are in-
game objects, it allows for easy @ex, and doesn't require
database migration to add in their functionality.

"""
from django.conf import settings
from server.utils import prettytable, helpdesk_api
from web.helpdesk.models import Ticket, Queue
from server.utils.arx_utils import inform_staff
from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.objects.models import ObjectDB
import traceback
from web.character.models import Roster, RosterEntry, PlayerAccount, AccountHistory
from typeclasses.bulletin_board.bboard import BBoard


def get_jobs_manager(caller):
    """
    returns jobs manager object
    """
    jobs_manager = ObjectDB.objects.get_objs_with_attr("jobs_manager")
    jobs_manager = [ob for ob in jobs_manager if hasattr(ob, 'is_jobs_manager') and ob.is_jobs_manager()]
    if not jobs_manager:
        caller.msg("Jobs Manager object not found.")
        return
    if len(jobs_manager) > 1:
        caller.msg("Warning. More than one Jobs Manager object found.")
    return jobs_manager[0]


def get_apps_manager(caller):
    """
    returns apps manager object
    """
    apps_manager = ObjectDB.objects.get_objs_with_attr("apps_manager")
    apps_manager = [ob for ob in apps_manager if hasattr(ob, 'is_apps_manager') and ob.is_apps_manager()]
    if not apps_manager:
        caller.msg("Apps Manager object not found.")
        return
    if len(apps_manager) > 1:
        caller.msg("Warning. More than one Apps Manager object found.")
    return apps_manager[0]


class CmdJob(MuxPlayerCommand):
    """
    @job - read an unread post from boards you are subscribed to

    Usage:
        @job - List all open tickets
        @job/only - only main Queue
        @job <#> - info about particular ticket
        @job/close <#>=<notes> - close ticket #
        @job/move <#>=<queue>
        @job/delete <#>
        @job/old - List 20 most recent closed tickets
        @job/old <#> - info about closed ticket
        @job/moreold <start ID>, <end ID>
        @job/followup <#>=<message> - add update to ticket #
        @job/priority <#>=<priority number>
        @job/low = List low priority messages
        @job/check <ticket #>/<stat> + <skill> at <diff>=<character>

    Notes when closing a ticket are only seen by GM staff. A mail
    will automatically be sent to the player with <notes> when
    closing a ticket. Please remember to be polite and respectful
    of players when answering tickets.

    To view other queues, use @bug, @code, @gm, @typo, or @prp.
    """
    key = "@job"
    aliases = ["@jobs", "@bug", "@code", "@gm", "@typo", "@prp"]
    help_category = "Admin"
    locks = "cmd:perm(job) or perm(Builders)"

    @property
    def queues_from_args(self):
        if self.cmdstring == "@code":
                queues = Queue.objects.filter(slug="Code")
        elif self.cmdstring == "@bug":
            queues = Queue.objects.filter(slug="Bugs")
        elif self.cmdstring == "@gm":
            queues = Queue.objects.filter(slug="Story")
        elif self.cmdstring == "@typo":
            queues = Queue.objects.filter(slug="Typo")
        elif self.cmdstring == "@prp":
            queues = Queue.objects.filter(slug="PRP")
        elif "only" in self.switches:
            queues = Queue.objects.filter(slug="Request")
        else:
            queues = Queue.objects.all()
        return queues

    def display_open_tickets(self):
        unassigned_tickets = Ticket.objects.select_related('queue').filter(
                                assigned_to__isnull=True,
                                queue__in=self.queues_from_args
                                ).exclude(
                                status=Ticket.CLOSED_STATUS,
                                )
        if "low" in self.switches:
            unassigned_tickets = unassigned_tickets.filter(priority__gt=5)
        else:
            unassigned_tickets = unassigned_tickets.filter(priority__lte=5)
        joblist = unassigned_tickets
        if not joblist:
            self.msg("No open tickets.")
            return
        table = prettytable.PrettyTable(["{w#",
                                         "{wPlayer",
                                         "{wRequest",
                                         "{wPriority",
                                         "{wQueue"])
        for ticket in joblist:
            if ticket.priority == 1:
                prio = "{r%s{n" % ticket.priority
            else:
                prio = "{w%s{n" % ticket.priority
            q = Queue.objects.get(id=ticket.queue_id)
            table.add_row([str(ticket.id), str(ticket.submitting_player.key), str(ticket.title)[:20], prio, q.slug])
        self.msg("{wOpen Tickets:{n\n%s" % table)

    def func(self):
        """Implement the command"""
        caller = self.caller
        args = self.args
        switches = self.switches
        if not args and not switches or 'low' in switches or 'only' in switches:
            # list all open tickets
            self.display_open_tickets()
            return
        if args and (not switches or 'old' in switches):
            # list individual ticket specified by args
            # ticket = [ticket_id, playob, request_string, date_submit, gm_ob, gm_notes, date_answer, optional_title]
            try:
                ticknum = int(args)
            except ValueError:
                self.display_open_tickets()
                caller.msg("Usage: Argument must be a ticket number.") 
                return
            try:
                ticket = Ticket.objects.get(id=ticknum)
            except Ticket.DoesNotExist:
                self.display_open_tickets()
                caller.msg("No ticket found by that number.")   
                return
            caller.msg("\n{wQueue:{n %s" % ticket.queue)
            caller.msg("{wTicket Number:{n %s" % ticket.id)
            if ticket.submitting_player:
                caller.msg("{wPlayer:{n %s" % ticket.submitting_player.key)
            caller.msg("{wDate submitted:{n %s" % ticket.created)
            caller.msg("{wLast modified:{n %s" % ticket.modified)
            caller.msg("{wTitle:{n %s" % ticket.title)
            room = ticket.submitting_room
            if room:
                caller.msg("{wLocation:{n %s (#%s)" % (room, room.id))
            caller.msg("{wPriority:{n %s" % ticket.priority)
            caller.msg("{wRequest:{n %s" % ticket.description)
            if ticket.assigned_to:
                caller.msg("{wGM:{n %s" % ticket.assigned_to.key)
                caller.msg("{wGM Notes:{n %s" % ticket.resolution)
            for followup in ticket.followup_set.all():
                caller.msg("{wFollowup by:{n %s" % followup.user)
                caller.msg("{wComment:{n %s" % followup.comment)
            return
        if 'old' in switches and not args:
            # list closed tickets
            # closed & resolved tickets, assigned to current user
            tickets_closed_resolved = Ticket.objects.select_related('queue').filter(
                                        status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS]).filter(
                queue__in=self.queues_from_args)
            joblist = list(tickets_closed_resolved)
            if not joblist:
                caller.msg("No closed tickets.")
                return
            # get 20 most recent
            joblist = joblist[-20:]
            table = prettytable.PrettyTable(["{w#",
                                             "{wPlayer",
                                             "{wRequest",
                                             "{wQueue"])
            for ticket in joblist:
                table.add_row([str(ticket.id), str(ticket.submitting_player), str(ticket.title)[:20],
                               ticket.queue.slug])
            caller.msg("{wClosed Tickets:{n\n%s" % table)
            return
        if 'moreold' in switches:
            # list closed tickets
            tickets_closed_resolved = Ticket.objects.select_related('queue').filter(
                status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS]).filter(
                queue__in=self.queues_from_args).filter(id__gte=self.lhslist[0], id__lte=self.lhslist[1])
            joblist = list(tickets_closed_resolved)
            if not joblist:
                caller.msg("No closed tickets.")
                return
            table = prettytable.PrettyTable(["{w#",
                                             "{wPlayer",
                                             "{wRequest",
                                             "{wQueue"])
            for ticket in joblist:
                table.add_row([str(ticket.id), str(ticket.submitting_player), str(ticket.title)[:20],
                               ticket.queue.slug])
            caller.msg("{wClosed Tickets:{n\n%s" % table)
            return
        if 'check' in switches:
            try:
                largs = self.lhs.split("/")
                ticket = Ticket.objects.get(id=largs[0])
                largs = largs[1].split("+")
                stat = largs[0].strip()
                largs = largs[1].split(" at ")
                skill = largs[0].strip()
                difficulty = int(largs[1])
            except (IndexError, TypeError, ValueError):
                self.msg("Invalid syntax. It's Apostate's fault that it's a complicated syntax so yell at him.")
                return
            except Ticket.DoesNotExist:
                self.msg("Ticket not found.")
                return
            try:
                char = caller.search(self.rhs).db.char_ob
            except AttributeError:
                self.msg("No character found.")
                return
            if char.attributes.get(stat) is None:
                self.msg("Error. The stat %s for the player is undefined. You probably switched stat and skill." % stat)
                self.msg("Otherwise, set the stat for the character to be 0.")
                return
            result = helpdesk_api.do_check(caller, ticket, stat, skill, difficulty, char)
            if result:
                self.msg(result)
            else:
                self.msg("Error in trying to make check.")
            return
        try:
            ticket = Ticket.objects.get(id=self.lhs)
        except (ValueError, Ticket.DoesNotExist):
            self.msg("No ticket found by that number.")
            return
        if 'close' in switches:
            # Closing a ticket. Check formatting first
            lhs = self.lhs
            rhs = self.rhs
            if not args or not lhs or not rhs:
                caller.msg("Usage: @job/close <#>=<GM Notes>")
                return
            try:
                numticket = int(lhs)
            except ValueError:
                caller.msg("Must give a number for the open ticket.")
                return
            if helpdesk_api.resolve_ticket(caller, numticket, rhs):
                caller.msg("Ticket successfully closed.")
                inform_staff("{w%s has closed a ticket.{n" % caller.key.capitalize())
                return
            else:
                caller.msg("Ticket closure failed for unknown reason.")
                return
        if 'followup' in switches or 'update' in switches:
            lhs = self.lhs
            rhs = self.rhs
            if not lhs or not rhs:
                caller.msg("Usage: @job/followup <#>=<msg>")
                return
            if helpdesk_api.add_followup(caller, ticket, rhs):
                caller.msg("Followup added.")
                return
            caller.msg("Error in followup.")
            return

        if 'move' in switches:
            if not self.lhs or not self.rhs:
                self.msg("Usage: @job/move <#>=<msg>")
                return
            try:
                queue = Queue.objects.get(slug__iexact=self.rhs)
            except Queue.DoesNotExist:
                self.msg("Queue must be one of the following: %s" % ", ".join(ob.slug for ob in Queue.objects.all()))
                return
            ticket.queue = queue
            ticket.save()
            self.msg("Ticket %s is now in queue %s." % (ticket.id, queue))
            return
        if 'delete' in switches:
            if ticket.queue.slug == "Story":
                self.msg("Cannot delete a storyaction. Please move it to a different queue first.")
                return
            ticket.delete()
            self.msg("Ticket #%s deleted." % self.lhs)
            return
        if 'priority' in switches:
            try:
                ticket.priority = int(self.rhs)
            except (TypeError, ValueError):
                self.msg("Must be a number.")
            ticket.save()
            self.msg("Ticket new priority is %s." % self.rhs)
            return
        if 'approve' in switches:
            pass
        if 'deny' in switches:
            pass
        caller.msg("Invalid switch for @job.")
               

class CmdRequest(MuxPlayerCommand):
    """
    +request - Make a request for GM help

    Usage:
       +request <message>
       +request <title>=<message>
       +911 <title>=<message>
       bug <report>
       typo <report>
       +featurerequest <report>
       +request/followup <#>=<message>
       +request <#>
       +storyrequest <title>=<action you wish to take>
       +prprequest <title>=<question about a player run plot>

    Send a message to the GMs for help. This is usually because
    of wanting to take some action that requires GM intervention,
    such as a plot idea or some other in-game activity, but can
    also be for simple requests to have descriptions or other
    aspects of your character editted/changed.

    To request GMing of an action you wish to take, use the
    +storyrequest command. There is a restriction of how often this
    command may be used.

    To request information about a player-run-plot that you wish
    to run, use +prprequest.

    +911 is used for emergencies and has an elevated priority.
    Use of this for non-emergencies is prohibited.

    'typo' may be used to report errors in descriptions or formatting.
    'bug' is used for reporting game errors in code.
    '+featurerequest' is used for making requests for code changes.
    '+storyrequest' is used for asking for GM resolution of IC actions.
    '+prprequest' is used for asking questions about a PRP.
    """

    key = "+request"
    aliases = ["@request", "+requests", "@requests", "+911", "+ineedanadult",
               "bug", "typo", "+featurerequest", "+storyrequest", "+prprequest"]
    help_category = "Admin"
    locks = "cmd:perm(request) or perm(Players)"

    def display_ticket(self, ticket):
        self.msg("\n{wTicket #:{n %s" % ticket.id)
        self.msg("{wQueue:{n %s" % ticket.queue)
        self.msg("{wRequest:{n %s" % ticket.description)
        self.msg("{wGM Notes:{n %s" % ticket.resolution)
        for followup in ticket.followup_set.all():
            self.msg("{wFollowup discussion:{n %s" % followup.comment)

    def list_tickets(self):
        self.msg("{wClosed tickets:{n %s" % ", ".join(str(ticket.id) for ticket in self.caller.tickets.filter(
                status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS])))
        self.msg("{wOpen tickets:{n %s" % ", ".join(str(ticket.id) for ticket in self.caller.tickets.filter(
            status=Ticket.OPEN_STATUS)
        ))
        self.msg("Use {w+request <#>{n to view an individual ticket.")
        self.msg("Use {w+request/followup <#>=<comment>{n to add a comment.")

    def check_recent_story_action(self):
        from datetime import datetime, timedelta
        num_days = 30
        max_requests = 2
        date = datetime.now()
        offset = timedelta(days=-num_days)
        date = date + offset
        actions = self.caller.tickets.filter(queue__slug="Story", created__gte=date)
        if actions.count() < max_requests:
            return False
        self.msg("You have submitted requests for GMing for a storyaction on: %s." % ", ".join(
            ob.created.strftime("%x") for ob in actions))
        self.msg("You are only permitted to make %s requests every %s days." % (max_requests, num_days))
        return True

    def func(self):
        """Implement the command"""
        caller = self.caller
        args = self.args
        priority = 5
        if "followup" in self.switches or "comment" in self.switches:
            if not self.lhs or not self.rhs:
                caller.msg("Missing arguments required.")
                ticketnumbers = ", ".join(ticket.id for ticket in caller.tickets.all())
                caller.msg("Your tickets: %s" % ticketnumbers)
                return
            try:
                ticket = caller.tickets.get(id=self.lhs)
                helpdesk_api.add_followup(caller, ticket, self.rhs, mail_player=False)
                caller.msg("Followup added.")
                return
            except (Ticket.DoesNotExist, ValueError):
                caller.msg("No ticket found by that number.")
                return
        cmdstr = self.cmdstring.lower()
        if cmdstr == '+911':
            priority = 1
        if not self.lhs:
            self.list_tickets()
            return
        if self.lhs.isdigit():
            try:
                ticket = caller.tickets.get(id=self.lhs)
            except (Ticket.DoesNotExist, ValueError):
                self.msg("No ticket by that number.")
                self.list_tickets()
                return
            self.display_ticket(ticket)
            return
        optional_title = None
        if self.lhs and self.rhs:
            args = self.rhs
            optional_title = self.lhs
        email = caller.email
        if email == "dummy@dummy.com":
            email = None
        if cmdstr == "bug":
            optional_title = "Bug Report"
            args = self.args
            queue = settings.BUG_QUEUE_ID
        elif cmdstr == "typo":
            optional_title = "Typo found"
            queue = Queue.objects.get(slug="Typo").id
        elif cmdstr == "+featurerequest":
            optional_title = "Features"
            queue = Queue.objects.get(slug="Code").id
        elif cmdstr == "+storyrequest":
            optional_title = "Action"
            queue = Queue.objects.get(slug="Story").id
            if self.check_recent_story_action():
                return
        elif cmdstr == "+prprequest":
            optional_title = "PRP"
            queue = Queue.objects.get(slug="PRP").id
        else:
            queue = settings.REQUEST_QUEUE_ID
        if helpdesk_api.create_ticket(caller, args, priority, queue=queue, send_email=email,
                                      optional_title=optional_title):
            caller.msg("Thank you for submitting a request to the GM staff. Your ticket has been added "
                       "to the queue.")
            return
        else:
            caller.msg("Ticket submission has failed for unknown reason. Please inform the administrators.")
            return


class CmdApp(MuxPlayerCommand):
    """
    @app - Manage character applications

    Usage:
       @app - List all pending applications
       @app <character> - List all pending apps for character
       @app <#> - List app # for character
       @app/approve <#>=<notes>
       @app/deny <#>=<notes>
       @app/old - List all old applications
       @app/old <number to display>
       @app/oldchar <character> - List all old apps for character
       @app/email <email addr> - List all apps for email
       @app/delete <#> - Delete an app
       @app/fixemail <#> - change email for an app
       @app/resend <#> - re-send the same email for app(after fixing email)

    Manages character applications.
    """

    key = "@app"
    aliases = ["@apps"]
    help_category = "Admin"
    locks = "cmd:perm(request) or perm(Builders)"

    def func(self):
        """Implement the command"""

        caller = self.caller
        args = self.args
        switches = self.switches
        apps = get_apps_manager(caller)
        if not apps:
            caller.msg("Apps manager not found! Please inform the administrators.")
            return
        if not args and not switches:
            # '@app'
            # List all pending applications
            all_apps = apps.view_all_apps()
            if not all_apps:
                caller.msg("No applications found.")
                return
            # application[9] field is 'True' if pending/open
            pend_list = [app for app in all_apps.values() if app[9]]
            if not pend_list:
                caller.msg("No pending applications found.")
                return
            # app = [app_num, char_ob, email, date_submit, application_string,
            # gm_ob, date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate"])
            for app in pend_list:
                table.add_row([app[0], app[1].key.capitalize(), app[2], app[3]])
            caller.msg("{wApplications for Characters pending approval:\n%s" % table)
            caller.msg("To view a particular application, @app <app number>")
            caller.msg("To view closed applications, use @app/old")
            return
        if args and not switches and not args.isdigit():
            # '@app <character>'
            # List all pending apps for a particular character
            apps_for_char = apps.view_all_apps_for_char(args)
            if not apps_for_char:
                caller.msg("No applications found.")
                return
            pend_list = [ob for ob in apps_for_char if ob[9]]
            if not pend_list:
                caller.msg("No pending applications found.")
                return
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob,
            # date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate"])
            for app in pend_list:
                table.add_row([app[0], app[1].key.capitalize(), app[2], app[3]])
            caller.msg("{wPending applications for %s:\n%s" % (args, table))
            caller.msg("To view a specific application, @app <app number>")
            return
        if args and args.isdigit() and (not switches or 'old' in switches):
            # '@app <#>
            # List a given ticket by
            app = apps.view_app(int(args))
            if not app:
                caller.msg("No application by that number for that character.")
                return
            email = app[2]
            alts = RosterEntry.objects.filter(current_account__email=email)
            caller.msg("{wCharacter:{n %s" % app[1].key.capitalize())
            caller.msg("{wApp Email:{n %s" % email)
            if alts:
                caller.msg("{wCurrent characters:{n %s" % ", ".join(str(ob) for ob in alts))
            caller.msg("{wDate Submitted:{n %s" % app[3])
            caller.msg("{wApplication:{n %s" % app[4])
            if not app[9]:
                caller.msg("{wGM:{n %s" % app[5])
                caller.msg("{wDate Answered:{n %s" % app[6])
                caller.msg("{wGM Notes:{n %s" % app[7])
                caller.msg("{wApproved:{n %s" % app[8])
            return
        if 'approve' in switches:
            # @app/approve <#>=<notes>
            # mark a character as approved, then send an email to the player
            if not self.lhs or not self.rhs or not self.lhs.isdigit():
                caller.msg("Usage: @app/approve <#>=<notes>")
                return
            app = apps.view_app(int(self.lhs))
            if apps.close_app(int(self.lhs), caller, self.rhs, True):
                caller.msg("Application successfully approved.") 
                if app and app[1]:
                    inform_staff("{w%s has approved %s's application.{n" % (caller.key.capitalize(),
                                                                            app[1].key.capitalize()))
                try:
                    
                    entry = RosterEntry.objects.get(character__id=app[1].id,
                                                    player__id=app[1].db.player_ob.id)
                    active_roster = Roster.objects.get(name="Active")
                    entry.roster = active_roster
                    try:
                        account = PlayerAccount.objects.get(email=app[2])
                    except PlayerAccount.DoesNotExist:
                        account = PlayerAccount.objects.create(email=app[2])
                    entry.current_account = account
                    entry.save()
                    # clear cache so the character is moved correctly
                    entry.character.flush_from_cache(force=True)
                    entry.player.flush_from_cache(force=True)
                    if not AccountHistory.objects.filter(account=account, entry=entry):
                        from datetime import datetime
                        date = datetime.now()
                        AccountHistory.objects.create(entry=entry, account=account, start_date=date)
                    try:
                        from commands.cmdsets.starting_gear import setup_gear_for_char
                        if not entry.character:
                            raise ValueError("No character found for setup gear")
                        setup_gear_for_char(entry.character)
                    except ValueError:
                        traceback.print_exc()                   
                except (RosterEntry.DoesNotExist, RosterEntry.MultipleObjectsReturned, Roster.DoesNotExist,
                        Roster.MultipleObjectsReturned, AttributeError, ValueError, TypeError):
                    print("Error when attempting to mark closed application as active.")
                    traceback.print_exc()
                try:
                    from world.dominion.setup_utils import setup_dom_for_char
                    setup_dom_for_char(app[1])
                except (ValueError, TypeError):
                    # will throw an exception if Dominion already set up
                    pass
                try:
                    bb = BBoard.objects.get(db_key__iexact="Roster Changes")
                    msg = "%s now has a new player and is on the active roster." % app[1]
                    subject = "%s now active" % app[1]
                    bb.bb_post(self.caller, msg, subject=subject, poster_name="Roster")
                except BBoard.DoesNotExist:
                    self.msg("Board not found for posting announcement")
                return
            else:
                caller.msg("Application closure failed.")
                return
        if 'delete' in switches:
            try:
                apps.delete_app(caller, int(self.args))
                return
            except (ValueError, TypeError):
                caller.msg("Could not delete an app for value of %s." % self.args)
                return
        if 'deny' in switches:
            # @app/deny <#>=<notes>
            # mark a character as declined, then send an email to the player
            if not self.lhs or not self.rhs or not self.lhs.isdigit():
                caller.msg("Usage: @app/deny <#>=<notes>")
                return
            if apps.close_app(int(self.lhs), caller, self.rhs, False):
                caller.msg("Application successfully declined.")
                app = apps.view_app(int(self.lhs))
                if app and app[1]:
                    inform_staff("{w%s has declined %s's application.{n" %
                                 (caller.key.capitalize(), app[1].key.capitalize()))
                return
            else:
                caller.msg("Application closure failed.")
                return
        if 'old' in switches:
            # List all non-pending applications
            all_apps = apps.view_all_apps()
            if not all_apps:
                caller.msg("No applications found.")
                return
            # application[9] field is 'True' if pending/open
            pend_list = [_app for _app in all_apps.values() if not _app[9]]
            pend_list.sort(key=lambda appl: appl[0])
            if not pend_list:
                caller.msg("No closed applications found.")
                return
            if not self.args:
                pend_list = pend_list[-20:]
            else:
                try:
                    pend_list = pend_list[-int(self.args):]
                except (TypeError, ValueError):
                    caller.msg("Could not display entries for that range.")
                    return
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob,
            #  date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate",
                                             "{wApproved"])
            for app in pend_list:
                table.add_row([app[0], app[1].key.capitalize(), app[2], app[3][:9], str(app[8])])
            caller.msg("{wOld/Closed applications for characters:\n%s" % table)
            caller.msg("To view a particular application, @app <app number>")
            return
            pass
        if 'oldchar' in switches:
            apps_for_char = apps.view_all_apps_for_char(args)
            if not apps_for_char:
                caller.msg("No applications found.")
                return
            pend_list = [ob for ob in apps_for_char if not ob[9]]
            if not pend_list:
                caller.msg("No closed applications found.")
                return
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob,
            # date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate",
                                             "{wGM",
                                             "{wApproved"])
            for app in pend_list:
                table.add_row([app[0], app[1].key.capitalize(), app[2], app[3][:9], app[5].key, str(app[8])])
            caller.msg("{wOld/Closed applications for %s:\n%s" % (args, table))
            caller.msg("To view a particular application, @app <app number>")
            return
        if 'email' in switches:
            apps_for_email = apps.view_apps_for_email(args)
            if not apps_for_email:
                caller.msg("No applications found.")
                return
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate"])
            for app in apps_for_email:
                table.add_row([app[0], app[1].key.capitalize(), app[2], app[3]])
            caller.msg("{wApplications for %s:\n%s" % (args, table))
            caller.msg("To view a particular application, @app <app number>")
            return
        if 'fixemail' in switches:
            try:
                if apps.fix_email(int(self.lhs), caller, self.rhs):
                    caller.msg("App email changed to %s." % self.rhs)
                return
            except (TypeError, ValueError, AttributeError):
                caller.msg("Must provide an app # and an email address.")
                return
        if 'resend' in switches:
            try:
                apps.resend(int(self.lhs), caller)
                return
            except (ValueError, TypeError, AttributeError):
                caller.msg("Must provide a valid app #.")
                return
        caller.msg("Invalid switch for @app.")
