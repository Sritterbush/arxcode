"""
Script to handle timing for events in the game.
"""

from django.conf import settings
from .scripts import Script
from world.dominion.models import RPEvent
from twisted.internet import reactor
from evennia.server.sessionhandler import SESSIONS
from evennia.utils.ansi import parse_ansi
import traceback
from server.utils.arx_utils import tdiff, tnow

LOGPATH = settings.LOG_DIR + "/rpevents/"
GMPATH = LOGPATH + "gm_logs/"


def delayed_start(event_id):
    # noinspection PyBroadException
    try:
        event = RPEvent.objects.get(id=event_id)
        from evennia.scripts.models import ScriptDB
        script = ScriptDB.objects.get(db_key="Event Manager")
        if event.id in script.db.cancelled:
            script.db.cancelled.remove(event.id)
            return
        script.start_event(event)
    except Exception:
        traceback.print_exc()


class EventManager(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Event Manager"
        self.desc = "Manages RP events and notifications"
        self.interval = 300
        self.persistent = True
        self.start_delay = True
        # we store everything as IDs of the event objects rather than the events themselves
        # due to serialization code not working on some django model instances
        self.db.idle_events = {}
        self.db.active_events = []
        self.db.pending_start = {}
        self.db.gm_logs = {}
        self.db.event_logs = {}
        self.db.cancelled = []

    def at_repeat(self):
        """
        Called every 5 minutes to update the timers. If we find an upcoming event
        based on date, we'll do an announcement if it starts between 55-60 mins,
        then another announcement if it's starting under 10 minutes. If under 5
        minutes, we schedule it to start.
        """
        for eventid in self.db.idle_events:
            # if the event has been idle for an hour, close it down
            if self.db.idle_events[eventid] >= 12:
                # noinspection PyBroadException
                try:
                    event = RPEvent.objects.get(id=eventid)
                    self.finish_event(event)
                except Exception:
                    traceback.print_exc()
                    del self.db.idle_events[eventid]
        # copy all active events to idle events for next check
        for eventid in self.db.active_events:
            self.db.idle_events[eventid] = self.db.idle_events.get(eventid, 0) + 1
        # check for new events to announce

        upcoming = RPEvent.objects.filter(finished=False)
        for event in upcoming:
            if event.id in self.db.active_events:
                continue
            diff = tdiff(event.date).total_seconds()
            if diff < 0:
                self.start_event(event)
                return
            if diff < 300:
                if event.id not in self.db.pending_start:                  
                    self.db.pending_start[event.id] = reactor.callLater(diff, delayed_start, event.id)
                return
            if diff < 600:
                self.announce_upcoming_event(event, diff)
                return
            if 1500 < diff <= 1800:
                self.announce_upcoming_event(event, diff)
                return
            if 3300 < diff <= 3600:
                self.announce_upcoming_event(event, diff)

    @staticmethod
    def announce_upcoming_event(event, diff):
        mins = int(diff/60)
        secs = diff % 60
        SESSIONS.announce_all("{wEvent: '%s' will start in %s minutes and %s seconds.{n" % (event.name, mins, secs))

    @staticmethod
    def get_event_location(event):
        loc = event.location
        if loc:
            return loc
        gms = event.gms.filter(player__db_is_connected=True)
        for gm in gms:
            loc = gm.player.db.char_ob.location
            if loc:
                return loc
        else:
            try:
                loc = event.main_host.db.char_ob.location
            except AttributeError:
                pass
        return loc

    # noinspection PyBroadException
    def start_event(self, event, location=None):
        # see if this was called from callLater, and if so, remove reference to it      
        if event.id in self.db.pending_start:
            del self.db.pending_start[event.id]

        # if we've already started, do nothing. Can happen due to queue
        if event.id in self.db.active_events:
            return
        # announce event start
        if location:
            loc = location
        else:
            loc = self.get_event_location(event)
        if loc:  # set up event logging, tag room
            loc.start_event_logging(event)
            start_str = "%s has started at %s." % (event.name, loc.name)
            if loc != event.location:
                event.location = loc
                event.save()
        else:
            start_str = "%s has started." % event.name
        border = "{w***********************************************************{n\n"
        if event.public_event:
            SESSIONS.announce_all(border)
            SESSIONS.announce_all(start_str)
            SESSIONS.announce_all(border)
        elif event.location:
            try:
                event.location.msg_contents(start_str, options={'box': True})
            except Exception:
                pass
        self.db.active_events.append(event.id)
        self.db.idle_events[event.id] = 0
        now = tnow()
        if now < event.date:
            # if we were forced to start early, update our date
            event.date = now
            event.save()
        # set up log for event
        event_logs = self.db.event_logs or {}
        gm_logs = self.db.gm_logs or {}
        # noinspection PyBroadException
        try:
            logname = "event_log_%s.txt" % event.id
            gmlogname = "gm_%s" % logname
            log = open(LOGPATH + logname, 'a+')
            gmlog = open(GMPATH + gmlogname, 'a+')
            event_logs[event.id] = logname
            gm_logs[event.id] = gmlogname
            open_logs = self.ndb.open_logs or []
            open_logs.append(log)
            self.ndb.open_logs = open_logs
            open_gm_logs = self.ndb.open_gm_logs or []
            open_gm_logs.append(gmlog)
            self.ndb.open_gm_logs = open_gm_logs
        except Exception:
            traceback.print_exc()
        self.db.event_logs = event_logs
        self.db.gm_logs = gm_logs

    def finish_event(self, event):
        loc = self.get_event_location(event)
        if loc:
            try:
                loc.stop_event_logging()
            except AttributeError:
                loc.db.current_event = None
                loc.msg_contents("{rEvent logging is now off for this room.{n")
                loc.tags.remove("logging event")
            end_str = "%s has ended at %s." % (event.name, loc.name)
        else:
            end_str = "%s has ended." % event.name
        SESSIONS.announce_all(end_str)
        event.finished = True
        event.save()
        if event.id in self.db.active_events:
            self.db.active_events.remove(event.id)
        if event.id in self.db.idle_events:
            del self.db.idle_events[event.id]
        self.do_awards(event)
        # noinspection PyBroadException
        try:
            log = open(LOGPATH + self.db.event_logs[event.id], 'r')
            log.close()
            gmlog = open(GMPATH + self.db.gm_logs[event.id], 'r')
            gmlog.close()
            del self.db.event_logs[event.id]
            del self.db.gm_logs[event.id]
        except Exception:
            traceback.print_exc()
        self.delete_event_post(event)

    def add_msg(self, eventid, msg, sender=None):
        # reset idle timer for event
        msg = parse_ansi(msg, strip_ansi=True)
        self.db.idle_events[eventid] = 0
        event = RPEvent.objects.get(id=eventid)
        # noinspection PyBroadException
        try:
            log = open(LOGPATH + self.db.event_logs[eventid], 'a+')
            msg = "\n" + msg + "\n"
            log.write(msg)
        except Exception:
            traceback.print_exc()
        if sender and sender.player and hasattr(sender.player, 'Dominion'):
            dompc = sender.player.Dominion
            if dompc not in event.participants.all():
                event.participants.add(dompc)
        event.save()

    def add_gmnote(self, eventid, msg):
        msg = parse_ansi(msg, strip_ansi=True)
        # noinspection PyBroadException
        try:
            log = open(GMPATH + self.db.gm_logs[eventid], 'a+')
            msg = "\n" + msg + "\n"
            log.write(msg)
        except Exception:
            traceback.print_exc()

    @staticmethod
    def do_awards(event):
        if not event.public_event:
            return
        qualified_hosts = [ob for ob in event.hosts.all() if ob in event.participants.all()]
        for host in qualified_hosts:
            if not host.player:
                continue
            # award karma
            try:
                account = host.player.roster.current_account
                account.karma += 1
                account.save()
            except (AttributeError, ValueError, TypeError):
                pass
            # award prestige
            if not host.assets or not event.celebration_tier:
                continue
            host.assets.adjust_prestige(event.prestige/len(qualified_hosts))

    def cancel_event(self, event):
        if event.id in self.db.pending_start:
            self.db.cancelled.append(event.id)
            del self.db.pending_start[event.id]
        self.delete_event_post(event)
        event.delete()

    def reschedule_event(self, event):
        diff = tdiff(event.date).total_seconds()
        if diff < 0:
            self.start_event(event)
            return

    @staticmethod
    def get_event_board():
        from typeclasses.bulletin_board.bboard import BBoard
        return BBoard.objects.get(db_key="events")

    def post_event(self, event, poster, post):
        board = self.get_event_board()
        board.bb_post(poster_obj=poster, msg=post, subject=event.name,
                      event=event)

    def delete_event_post(self, event):
        # noinspection PyBroadException
        try:
            board = self.get_event_board()
            post = board.posts.get(db_tags__db_key=event.tagkey,
                                   db_tags__db_data=event.tagdata)
            post.delete()
        except Exception:
            traceback.print_exc()
