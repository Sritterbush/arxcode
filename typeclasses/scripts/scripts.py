"""
Scripts

Scripts are powerful jacks-of-all-trades. They have no in-game
existence and can be used to represent persistent game systems in some
circumstances. Scripts can also have a time component that allows them
to "fire" regularly or a limited number of times.

There is generally no "tree" of Scripts inheriting from each other.
Rather, each script tends to inherit from the base Script class and
just overloads its hooks to have it perform its function.

"""

from evennia.scripts.scripts import DefaultScript, ExtendedLoopingCall
from evennia.scripts.models import ScriptDB
from evennia.comms import channelhandler

_SESSIONS = None

FLUSHING_INSTANCES = False
SCRIPT_FLUSH_TIMERS = {}


def restart_scripts_after_flush():
    """After instances are flushed, validate scripts so they're not dead for a long period of time"""
    global FLUSHING_INSTANCES
    ScriptDB.objects.validate()
    FLUSHING_INSTANCES = False


class Script(DefaultScript):
    """
    A script type is customized by redefining some or all of its hook
    methods and variables.

    * available properties

     key (string) - name of object
     name (string)- same as key
     aliases (list of strings) - aliases to the object. Will be saved
              to database as AliasDB entries but returned as strings.
     dbref (int, read-only) - unique #id-number. Also "id" can be used.
     date_created (string) - time stamp of object creation
     permissions (list of strings) - list of permission strings

     desc (string)      - optional description of script, shown in listings
     obj (Object)       - optional object that this script is connected to
                          and acts on (set automatically by obj.scripts.add())
     interval (int)     - how often script should run, in seconds. <0 turns
                          off ticker
     start_delay (bool) - if the script should start repeating right away or
                          wait self.interval seconds
     repeats (int)      - how many times the script should repeat before
                          stopping. 0 means infinite repeats
     persistent (bool)  - if script should survive a server shutdown or not
     is_active (bool)   - if script is currently running

    * Handlers

     locks - lock-handler: use locks.add() to add new lock strings
     db - attribute-handler: store/retrieve database attributes on this
                        self.db.myattr=val, val=self.db.myattr
     ndb - non-persistent attribute handler: same as db but does not
                        create a database entry when storing data

    * Helper methods

     start() - start script (this usually happens automatically at creation
               and obj.script.add() etc)
     stop()  - stop script, and delete it
     pause() - put the script on hold, until unpause() is called. If script
               is persistent, the pause state will survive a shutdown.
     unpause() - restart a previously paused script. The script will continue
                 from the paused timer (but at_start() will be called).
     time_until_next_repeat() - if a timed script (interval>0), returns time
                 until next tick

    * Hook methods (should also include self as the first argument):

     at_script_creation() - called only once, when an object of this
                            class is first created.
     is_valid() - is called to check if the script is valid to be running
                  at the current time. If is_valid() returns False, the running
                  script is stopped and removed from the game. You can use this
                  to check state changes (i.e. an script tracking some combat
                  stats at regular intervals is only valid to run while there is
                  actual combat going on).
      at_start() - Called every time the script is started, which for persistent
                  scripts is at least once every server start. Note that this is
                  unaffected by self.delay_start, which only delays the first
                  call to at_repeat().
      at_repeat() - Called every self.interval seconds. It will be called
                  immediately upon launch unless self.delay_start is True, which
                  will delay the first call of this method by self.interval
                  seconds. If self.interval==0, this method will never
                  be called.
      at_stop() - Called as the script object is stopped and is about to be
                  removed from the game, e.g. because is_valid() returned False.
      at_server_reload() - Called when server reloads. Can be used to
                  save temporary variables you want should survive a reload.
      at_server_shutdown() - called at a full server shutdown.

    """
    def at_idmapper_flush(self):
        """If we're flushing this object, make sure the LoopingCall is gone too"""
        ret = super(Script, self).at_idmapper_flush()
        if ret:
            try:
                from twisted.internet import reactor
                global FLUSHING_INSTANCES
                paused_time = self.ndb._task.next_call_time()
                callcount = self.ndb._task.callcount
                self._stop_task()
                SCRIPT_FLUSH_TIMERS[self.id] = (paused_time, callcount)
                if not FLUSHING_INSTANCES:
                    FLUSHING_INSTANCES = True
                    reactor.callLater(2, restart_scripts_after_flush)
            except Exception:
                import traceback
                traceback.print_exc()
        return ret

    def start(self, force_restart=False):
        ret = super(Script, self).start(force_restart=force_restart)
        # restart task if it's missing when we're marked as active
        if not self.ndb._task and self.is_active:
            self.ndb._task = ExtendedLoopingCall(self._step_task)
            try:
                start_delay, callcount = SCRIPT_FLUSH_TIMERS[self.id]
                del SCRIPT_FLUSH_TIMERS[self.id]
                now = False
            except (KeyError, ValueError, TypeError):
                now = not self.db_start_delay
                start_delay = None
                callcount = 0
            self.ndb._task.start(self.db_interval, now=now, start_delay=start_delay, count_start=callcount)
        return ret


class CheckSessions(Script):
    "Check sessions regularly."
    def at_script_creation(self):
        "Setup the script"
        self.key = "sys_session_check"
        self.desc = "Checks sessions so they are live."
        self.interval = 60  # repeat every 60 seconds
        self.persistent = True

    def at_repeat(self):
        "called every 60 seconds"
        global _SESSIONS
        if not _SESSIONS:
            from evennia.server.sessionhandler import SESSIONS as _SESSIONS
        #print "session check!"
        #print "ValidateSessions run"
        _SESSIONS.validate_sessions()


class ValidateScripts(Script):
    "Check script validation regularly"
    def at_script_creation(self):
        "Setup the script"
        self.key = "sys_scripts_validate"
        self.desc = "Validates all scripts regularly."
        self.interval = 3600  # validate every hour.
        self.persistent = True

    def at_repeat(self):
        "called every hour"
        #print "ValidateScripts run."
        ScriptDB.objects.validate()


class ValidateChannelHandler(Script):
    "Update the channelhandler to make sure it's in sync."
    def at_script_creation(self):
        "Setup the script"
        self.key = "sys_channels_validate"
        self.desc = "Updates the channel handler"
        self.interval = 3700  # validate a little later than ValidateScripts
        self.persistent = True

    def at_repeat(self):
        "called every hour+"
        #print "ValidateChannelHandler run."
        channelhandler.CHANNELHANDLER.update()
