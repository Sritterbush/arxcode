"""
General helper functions that don't fit neatly under any given category.

They provide some useful string and conversion methods that might
be of use when designing your own game.

"""
import re
from django.conf import settings
from datetime import datetime


def validate_name(name, formatting=True, not_player=True):
    """
    Checks if a name has only letters or apostrophes, or
    ansi formatting if flag is set
    """
    if not not_player:
        player_conflict = False
    else:
        from evennia.players.models import PlayerDB
        player_conflict = PlayerDB.objects.filter(username__iexact=name)
    if player_conflict:
        return None
    if formatting:
        return re.findall('^[\-\w\'{\[,|%=_ ]+$', name)
    return re.findall('^[\w\']+$', name)


def inform_staff(message):
    """
    Sends a message to the 'Mudinfo' channel for staff announcements.
    """
    from evennia.comms.models import ChannelDB
    try:
        wizchan = ChannelDB.objects.get(db_key__iexact="staffinfo")
        now = tnow().strftime("%H:%M")
        wizchan.tempmsg("{r[%s]:{n %s" % (now, message))
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
    from typeclasses.scripts import gametime
    time = gametime.gametime(format=True)
    month, day, year = time[1] + 1, time[3] + 1, time[0] + 1001
    day += (time[2] * 7)
    date = ("%s/%s/%s AR" % (month, day, year))
    return date


def get_week():
    """Gets the current week for dominion."""
    from evennia.scripts.models import ScriptDB
    weekly = ScriptDB.objects.get(db_key="Weekly Update")
    return weekly.db.week


def tnow(aware=False):
    if aware:
        from django.utils import timezone
        return timezone.localtime(timezone.now())
    # naive datetime
    return datetime.now()


def tdiff(date):
    try:
        diff = date - tnow()
    except (TypeError, ValueError):
        diff = date - tnow(aware=True)
    return diff


def datetime_format(dtobj):
    """
    Takes a datetime object instance (e.g. from django's DateTimeField)
    and returns a string describing how long ago that date was.

    """

    year, month, day = dtobj.year, dtobj.month, dtobj.day
    hour, minute, second = dtobj.hour, dtobj.minute, dtobj.second
    now = datetime.now()

    if year < now.year:
        # another year
        timestring = str(dtobj.date())
    elif dtobj.date() < now.date():
        # another date, same year
        # put month before day because of FREEDOM
        timestring = "%02i-%02i %02i:%02i" % (month, day, hour, minute)
    elif hour < now.hour - 1:
        # same day, more than 1 hour ago
        timestring = "%02i:%02i" % (hour, minute)
    else:
        # same day, less than 1 hour ago
        timestring = "%02i:%02i:%02i" % (hour, minute, second)
    return timestring


def sub_old_ansi(text):
    text = text.replace('%r', '|/')
    text = text.replace('%R', '|/')
    text = text.replace('%t', '|-')
    text = text.replace('%T', '|-')
    text = text.replace('%b', '|_')
    text = text.replace('%cr', '|r')
    text = text.replace('%cR', '|[R')
    text = text.replace('%cg', '|g')
    text = text.replace('%cG', '|[G')
    text = text.replace('%cy', '|!Y')
    text = text.replace('%cY', '|[Y')
    text = text.replace('%cb', '|!B')
    text = text.replace('%cB', '|[B')
    text = text.replace('%cm', '|!M')
    text = text.replace('%cM', '|[M')
    text = text.replace('%cc', '|!C')
    text = text.replace('%cC', '|[C')
    text = text.replace('%cw', '|!W')
    text = text.replace('%cW', '|[W')
    text = text.replace('%cx', '|!X')
    text = text.replace('%cX', '|[X')
    text = text.replace('%ch', '|h')
    text = text.replace('%cn', '|n')
    return text


def strip_ansi(text):
    from evennia.utils.ansi import strip_ansi
    text = strip_ansi(text)
    text = text.replace('%r', '').replace('%R', '').replace('%t', '').replace('%T', '').replace('%b', '')
    text = text.replace('%cr', '').replace('%cR', '').replace('%cg', '').replace('%cG', '').replace('%cy', '')
    text = text.replace('%cY', '').replace('%cb', '').replace('%cB', '').replace('%cm', '').replace('%cM', '')
    text = text.replace('%cc', '').replace('%cC', '').replace('%cw', '').replace('%cW', '').replace('%cx', '')
    text = text.replace('%cX', '').replace('%ch', '').replace('%cn', '')
    return text


def broadcast(txt, format_announcement=True):
    from evennia.server.sessionhandler import SESSION_HANDLER
    if format_announcement:
        txt = "{wServer Announcement{n: %s" % txt
    txt = sub_old_ansi(txt)
    SESSION_HANDLER.announce_all(txt)


def raw(text):
    from evennia.utils.ansi import raw
    text = sub_old_ansi(text)
    text = text.replace('\n', '|/')
    text = raw(text)
    text = text.replace('|', '||')
    return text
