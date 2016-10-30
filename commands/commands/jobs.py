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
from server.utils.utils import inform_staff
from evennia.commands.default.muxcommand import MuxPlayerCommand
from evennia.objects.models import ObjectDB
import traceback
from web.character.models import Roster, RosterEntry, PlayerAccount, AccountHistory

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
        @job <#> - info about particular ticket
        @job/close <#>=<notes> - close ticket #
        @job/move <#>=<queue>
        @job/delete <#>
        @job/old - List 20 most recent closed tickets
        @job/old <#> - info about closed ticket
        @job/moreold <#> - List # of recent closed tickets
        @job/followup <#>=<message> - add update to ticket #

    Notes when closing a ticket are only seen by GM staff. A mail
    will automatically be sent to the player with <notes> when
    closing a ticket. Please remember to be polite and respectful
    of players when answering tickets.
    """
    key = "@job"
    aliases = ["@jobs", "@bug", "@code"]
    help_category = "Admin"
    locks = "cmd:perm(job) or perm(Builders)"

    def display_open_tickets(self):
        if self.cmdstring == "@code":
                queues = Queue.objects.filter(slug="Code")
        elif self.cmdstring == "@bug":
            queues = Queue.objects.filter(slug="Bugs")
        else:
            queues = Queue.objects.all()
        unassigned_tickets = list(Ticket.objects.select_related('queue').filter(
                                assigned_to__isnull=True,
                                queue__in=queues
                                ).exclude(
                                status=Ticket.CLOSED_STATUS,
                                ))
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
        "Implement the command"
        caller = self.caller
        args = self.args
        switches = self.switches
        if not args and not switches:
            #list all open tickets 
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
            q = Queue.objects.get(id=ticket.queue_id)
            caller.msg("\n{wQueue:{n %s" % q)
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
            tickets_closed_resolved =  list(Ticket.objects.select_related('queue').filter(
                                        status__in = [Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS]))
            joblist = tickets_closed_resolved
            if not joblist:
                caller.msg("No closed tickets.")
                return
            #get 20 most recent
            joblist = joblist[-20:]
            table = prettytable.PrettyTable(["{w#",
                                             "{wPlayer",
                                             "{wRequest",
                                             "{wGM"])
            for ticket in joblist:
                table.add_row([str(ticket.id), str(ticket.submitting_player.key), str(ticket.title), str(ticket.assigned_to.key)])
            caller.msg("{wClosed Tickets:{n\n%s" % table)
            return
        if 'moreold' in switches:
            # list closed tickets
            tickets_closed_resolved =  list(Ticket.objects.select_related('queue').filter(
                                        status__in = [Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS]))
            joblist = tickets_closed_resolved
            if not joblist:
                caller.msg("No closed tickets.")
                return
            try:
                numjobs = int(args)
            except ValueError:
                caller.msg("Must give a number for # of closed tickets to display.")
                return
            #get 20 most recent
            joblist = joblist[-numjobs:]
            table = prettytable.PrettyTable(["{w#",
                                             "{wPlayer",
                                             "{wRequest",
                                             "{wGM"])
            for ticket in joblist:
                table.add_row([str(ticket.id), str(ticket.submitting_player), str(ticket.title), str(ticket.assigned_to)])
            caller.msg("{wClosed Tickets:{n\n%s" % table)
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
            ticket = Ticket.objects.get(id=numticket)
            if not ticket:
                caller.msg("No open ticket found for that number.")
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
            try:
                ticket = Ticket.objects.get(id=int(lhs))
            except Exception:
                caller.msg("No ticket found for that number.")
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
            try:
                ticket = Ticket.objects.get(id=self.lhs)
            except Ticket.DoesNotExist:
                self.msg("Invalid ticket number.")
            ticket.queue = queue
            ticket.save()
            self.msg("Ticket %s is now in queue %s." % (ticket.id, queue))
            return
        if 'delete' in switches:
            try:
                ticket = Ticket.objects.get(id=self.lhs)
            except Ticket.DoesNotExist:
                self.msg("No ticket by that number.")
                return
            ticket.delete()
            self.msg("Ticket #%s deleted." % self.lhs)
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
       feedback <report>
       +request/followup <#>=<message>

    Send a message to the GMs for help. This is usually because
    of wanting to take some action that requires GM intervention,
    such as a plot idea or some other in-game activity, but can
    also be for simple requests to have descriptions or other
    aspects of your character editted/changed.

    +911 is used for emergencies and has an elevated priority.
    Use of this for non-emergencies is prohibited.

    'typo' may be used to report errors in descriptions or formatting.
    'bug' is used for reporting game errors in code.
    'feedback' is used for making suggestions on different game systems.
    """

    key = "+request"
    aliases = ["@request","+requests","@requests", "+911", "+ineedanadult",
               "bug", "typo", "feedback"]
    help_category = "Admin"
    locks = "cmd:perm(request) or perm(Players)"

    def func(self):
        "Implement the command"
        caller = self.caller
        args = self.args
        priority = 5
        if "followup" in self.switches:
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
            except Exception:
                caller.msg("No ticket found by that number.")
                return
        cmdstr = self.cmdstring.lower()
        if cmdstr == '+911': priority = 1
        if not self.lhs:
            open_tickets = caller.tickets.filter(status=Ticket.OPEN_STATUS)
            if not open_tickets:
                caller.msg("No open tickets found.")
                return
            for ticket in open_tickets:
                caller.msg("\n{wTicket #:{n %s" % ticket.id)
                caller.msg("{wRequest:{n %s" % ticket.description)
                caller.msg("{wGM Notes:{n %s" % ticket.resolution)
                for followup in ticket.followup_set.all():
                    caller.msg("{wFollowup discussion:{n %s" % followup.comment)
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
        elif cmdstr == "feedback":
            optional_title = "Feedback"
            queue = Queue.objects.get(slug="Code").id
        else:
            queue = settings.REQUEST_QUEUE_ID
        if helpdesk_api.create_ticket(caller, args, priority, queue=queue, send_email=email, optional_title=optional_title):
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
        "Implement the command"

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
            #application[9] field is 'True' if pending/open
            pend_list = [app for app in all_apps.values() if app[9]]
            if not pend_list:
                caller.msg("No pending applications found.")
                return
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate"])
            for app in pend_list:
                table.add_row( [app[0], app[1].key.capitalize(), app[2], app[3]] )
            caller.msg("{wApplications for Characters pending approval:\n%s" % table)
            caller.msg("To view a particular application, @app <app number>")
            caller.msg("To view closed applications, use @app/old")
            return
        if args and not switches and not args.isdigit():
            # '@app <character>'
            #List all pending apps for a particular character
            apps_for_char = apps.view_all_apps_for_char(args)
            if not apps_for_char:
                caller.msg("No applications found.")
                return
            pend_list = [ob for ob in apps_for_char if ob[9]]
            if not pend_list:
                caller.msg("No pending applications found.")
                return
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate"])
            for app in pend_list:
                table.add_row( [app[0], app[1].key.capitalize(), app[2], app[3]] )
            caller.msg("{wPending applications for %s:\n%s" % (args, table))
            caller.msg("To view a specific application, @app <app number>")
            return
        if args and args.isdigit() and (not switches or 'old' in switches):
            # '@app <#>
            #List a given ticket by
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
                    inform_staff("{w%s has approved %s's application.{n" %
                                    (caller.key.capitalize(), app[1].key.capitalize()))
                try:
                    
                    entry = RosterEntry.objects.get(character__id=app[1].id,
                                                    player__id=app[1].db.player_ob.id)
                    active_roster = Roster.objects.get(name="Active")
                    entry.roster = active_roster
                    try:
                        account = PlayerAccount.objects.get(email=app[2])
                    except Exception:
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
                    except Exception:
                        traceback.print_exc()                   
                except Exception:
                    print "Error when attempting to mark closed application as active."
                    traceback.print_exc()
                try:
                    from world.dominion.setup_utils import setup_dom_for_char
                    setup_dom_for_char(app[1])
                except Exception:
                    # will throw an exception if Dominion already set up
                    pass
                return
            else:
                caller.msg("Application closure failed.")
                return
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
            return
        if 'old' in switches:
            # List all non-pending applications
            all_apps = apps.view_all_apps()
            if not all_apps:
                caller.msg("No applications found.")
                return
            #application[9] field is 'True' if pending/open
            pend_list = [_app for _app in all_apps.values() if not _app[9]]
            pend_list.sort(key=lambda app: app[0])
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
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate",
                                             "{wApproved"])
            for app in pend_list:
                table.add_row( [app[0], app[1].key.capitalize(), app[2], app[3][:9], str(app[8])] )
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
            # app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending]
            table = prettytable.PrettyTable(["{w#",
                                             "{wCharacter",
                                             "{wEmail",
                                             "{wDate",
                                             "{wGM",
                                             "{wApproved"])
            for app in pend_list:
                table.add_row( [app[0], app[1].key.capitalize(), app[2], app[3][:9], app[5].key, str(app[8])] )
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
                table.add_row( [app[0], app[1].key.capitalize(), app[2], app[3]] )
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

