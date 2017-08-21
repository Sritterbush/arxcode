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
    if not text:
        return ""
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
    from evennia.scripts.models import ScriptDB
    if format_announcement:
        txt = "{wServer Announcement{n: %s" % txt
    txt = sub_old_ansi(txt)
    SESSION_HANDLER.announce_all(txt)
    try:
        events = ScriptDB.objects.get(db_key="Event Manager")
        events.add_gemit(txt)
    except ScriptDB.DoesNotExist:
        pass


def raw(text):
    """
    Escape text with Arx-specific codes
    
        Args:
            text: the text string to escape
            
        Returns:
            text: Text with escaped codes
            
    First we transform arx-specific codes into the equivalent
    ansi codes that Evennia uses. Then we escape them all,
    returning the escaped string.
    """
    from evennia.utils.ansi import raw as evennia_raw
    if not text:
        return ""
    # get Evennia codes from the Arx-specific codes
    text = sub_old_ansi(text)
    # if any were turned into newlines, we substitute the code
    text = text.replace('\n', '|/')
    # escape all of them
    text = evennia_raw(text)
    return text


def check_break(caller=None):
    """
    Checks if staff are currently on break

        Args:
            caller (ObjectDB or PlayerDB): object to .msg our end date
    Returns:
        (bool): True if we're on our break, false otherwise

    If staff are currently on break, we send an error message to a caller
    if passed along as args, then return True.
    """
    from evennia.server.models import ServerConfig
    end_date = ServerConfig.objects.conf("end_break_date")
    if not end_date:
        return False
    if end_date > datetime.now():
        if caller:
            caller.msg("That is currently disabled due to staff break.")
            caller.msg("Staff are on break until %s." % end_date.strftime("%x %X"))
        return True
    return False


def delete_empty_tags():
    from evennia.typeclasses.tags import Tag
    empty = Tag.objects.filter(objectdb__isnull=True, playerdb__isnull=True, msg__isnull=True, helpentry__isnull=True,
                               scriptdb__isnull=True, channeldb__isnull=True)
    empty.delete()


def trainer_diagnostics(trainer):
    """
    Gets a string of diagnostic information
    Args:
        trainer: Character object that's doing training

    Returns:
        String of diagnostic information about trainer and its attributes.
    """
    from django.core.exceptions import ObjectDoesNotExist
    msg = "%s: id: %s" % (repr(trainer), id(trainer))

    def get_attr_value(attr_name):
        ret = ", %s: " % attr_name
        try:
            attr = trainer.db_attributes.get(db_key=attr_name)
            ret += "id: %s, value: %s" % (attr.id, attr.value)
        except (AttributeError, ObjectDoesNotExist):
            ret += "no value"
        return ret
    msg += get_attr_value("currently_training")
    msg += get_attr_value("num_trained")
    return msg