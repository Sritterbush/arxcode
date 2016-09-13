"""
General helper functions that don't fit neatly under any given category.

They provide some useful string and conversion methods that might
be of use when designing your own game.

"""
import re
import traceback
from django.conf import settings
from datetime import datetime




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
    try:
        wizchan = ChannelDB.objects.get(db_key__iexact="mudinfo")
        now = tnow().strftime("%X")    
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
    from typeclasses.scripts import gametime
    time = gametime.gametime(format=True)
    month, day, year = time[1] + 1, time[3] + 1, time[0] + 1001
    day += (time[2] * 7)
    date = ("%s/%s/%s AR" % (month, day, year))
    return date

def get_week():
    "Gets the current week for dominion."
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
    except Exception:
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

def convert_all_rooms():
    from evennia.objects.models import ObjectDB
    from django.conf import settings
    qs = ObjectDB.objects.filter(db_typeclass_path__icontains="room")
    for ob in qs:
        ob.db_typeclass_path = settings.BASE_ROOM_TYPECLASS
        ob.save()
