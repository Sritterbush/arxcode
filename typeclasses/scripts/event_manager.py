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
from server.utils.utils import tdiff, tnow

LOGPATH = settings.LOG_DIR + "/rpevents/"
GMPATH = LOGPATH + "gm_logs/"

def delayed_start(event_id):   
    try:
        event = RPEvent.objects.get(id=event_id)
        from evennia.scripts.models import ScriptDB
        script = ScriptDB.objects.get(db_key = "Event Manager")
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

    def announce_upcoming_event(self, event, diff):
        mins = int(diff/60)
        secs = diff % 60
        SESSIONS.announce_all("{wEvent: '%s' will start in %s minutes and %s seconds.{n" % (event.name, mins, secs))

    def start_event(self, event):
        # see if this was called from callLater, and if so, remove reference to it      
        if event.id in self.db.pending_start:
            del self.db.pending_start[event.id]

        # if we've already started, do nothing. Can happen due to queue
        if event.id in self.db.active_events:
            return
        # announce event start
        loc = event.location
        loc.msg_contents("{rEvent logging is now on for this room.{n")
        loc.db.current_event = event.id
        border = "{w***********************************************************{n\n"
        SESSIONS.announce_all(border)
        SESSIONS.announce_all("%s has started at %s." % (event.name, loc.name))
        SESSIONS.announce_all(border)
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
        try:
            logname = "event_log_%s.txt" % (event.id)
            gmlogname = "gm_%s" % logname
            log = open(LOGPATH + logname, 'a+')
            gmlog = open(GMPATH + gmlogname, 'a+')
            event_logs[event.id] = logname
            gm_logs[event.id] = gmlogname
        except Exception:
            traceback.print_exc()
        self.db.event_logs = event_logs
        self.db.gm_logs = gm_logs

    def finish_event(self, event):
        loc = event.location
        loc.db.current_event = None
        SESSIONS.announce_all("%s has ended at %s." % (event.name, loc.name))
        event.finished = True
        event.save()
        if event.id in self.db.active_events:
            self.db.active_events.remove(event.id)
        if event.id in self.db.idle_events:
            del self.db.idle_events[event.id]
        loc.msg_contents("{rEvent logging is now off for this room.{n")
        self.do_awards(event)
        try:
            log = open(LOGPATH + self.db.event_logs[event.id], 'r')
            log.close()
            gmlog = open(GMPATH + self.db.gm_logs[event.id], 'r')
            gmlog.close()
            del self.db.event_logs[event.id]
            del self.db.gm_logs[event.id]
        except Exception:
            traceback.print_exc()

    def add_msg(self, eventid, msg, sender=None):
        # reset idle timer for event
        msg = parse_ansi(msg, strip_ansi=True)
        self.db.idle_events[eventid] = 0
        event = RPEvent.objects.get(id=eventid)
        try:
            log = open(LOGPATH + self.db.event_logs[eventid], 'a+')
            msg = "\n" + msg
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
        event = RPEvent.objects.get(id=eventid)
        try:
            log = open(GMPATH + self.db.gm_logs[eventid], 'a+')
            msg = "\n" + msg
            log.write(msg)
        except Exception:
            traceback.print_exc()

    def do_awards(self, event):
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
            except Exception:
                pass
            # award prestige
            if not host.assets or not event.celebration_tier:
                continue
            host.assets.adjust_prestige(event.prestige/len(qualified_hosts))

    def cancel_event(self, event):
        if event.id in self.db.pending_start:
            self.db.cancelled.append(event.id)
            del self.db.pending_start[event.id]
        event.delete()

    def reschedule_event(self, event, date):
        diff = tdiff(event.date).total_seconds()
        if diff < 0:
            self.start_event(event)
            return



   
