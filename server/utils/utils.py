"""
General helper functions that don't fit neatly under any given category.

They provide some useful string and conversion methods that might
be of use when designing your own game.

"""
import re
import traceback
from django.conf import settings




def validate_name(name, formatting=True):
    """
    Checks if a name has only letters or apostrophes, or
    ansi formatting if flag is set
    """
    if formatting:
        return re.findall('^[\-\w\'\{\[\,\% ]+$', name)
    return re.findall('^[\w\']+$', name)

def inform_staff(message):
    """
    Sends a message to the 'Mudinfo' channel for staff announcements.
    """
    from evennia.comms.models import ChannelDB
    from datetime import datetime
    
    wizchan = ChannelDB.objects.filter(db_key=settings.CHANNEL_MUDINFO[0])[0]
    now = datetime.now().strftime("%X")
    try:
        wizchan.tempmsg("{r[%s, %s]:{n %s" % (wizchan.key, now, message))
    except Exception as err:
        print("ERROR when attempting utils.inform_staff() : %s" % err)

def setup_log(logfile):
    import logging
    fileh = logging.FileHandler(logfile, 'a')
    formatter = logging.Formatter(fmt=settings.LOG_FORMAT, datefmt=settings.DATE_FORMAT)
    fileh.setFormatter(formatter)   
    log = logging.getLogger()
    for hdlr in log.handlers:
        log.removeHandler(hdlr)
    log.addHandler(fileh)
    log.setLevel(logging.DEBUG)
    return log

def get_date():
    """
    Get in-game date as a string
    format is 'M/D/YEAR AR'
    """
    from ev import gametime
    time = gametime.gametime(format=True)
    month, day, year = time[1] + 1, time[3] + 1, time[0] + 1001
    day += (time[2] * 7)
    date = ("%s/%s/%s AR" % (month, day, year))
    return date

def get_week():
    "Gets the current week for dominion."
    from src.scripts.models import ScriptDB
    weekly = ScriptDB.objects.get(db_key="Weekly Update")
    return weekly.db.week

def idle_timer(session):
    import time
    "Takes session or object and returns time since last visible command"
    # If we're given character or player object, get the session
    if not session:
        return 0
    if not hasattr(session, "cmd_last_visible") and hasattr(session, "sessions"):
        if not session.sessions: return 0
        session = session.sessions[0]
    return time.time() - session.cmd_last_visible
