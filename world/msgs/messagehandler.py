"""
Messagehandler

This handler takes either a AccountDB or ObjectDB object and
processes the Msg objects they have in their related sets.
Msg() objects will be distinguished in how they function based
on their header field, which we'll parse and process here. The
header field will be a list of key:value pairs, separated by
semicolons.
"""

from server.utils.arx_utils import get_date, create_arx_message
from .handler_mixins import messengerhandler, journalhandler, msg_utils
from .managers import (VISION_TAG, COMMENT_TAG)


class MessageHandler(messengerhandler.MessengerHandler, journalhandler.JournalHandler):
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        # the ObjectDB instance
        super(MessageHandler, self).__init__(obj)
        # comments that obj has received about it
        self._comments = None
        self._rumors = None
        self._gossip = None
        self._visions = None

    @property
    def comments(self):
        if self._comments is None:
            self.build_commentdict()
        return self._comments

    @comments.setter
    def comments(self, value):
        self._comments = value

    @property
    def rumors(self):
        if self._rumors is None:
            self.build_rumorslist()
        return self._rumors

    @property
    def gossip(self):
        if self._gossip is None:
            self.build_gossiplist()
        return self._gossip

    @property
    def visions(self):
        if self._visions is None:
            self.build_visionslist()
        return self._visions

    # ---------------------------------------------------------
    # Setup/building methods
    # ---------------------------------------------------------

    def build_commentdict(self):
        """
        Builds a list of all comments we've received, not ones we've written.
        """
        comments = msg_utils.get_initial_queryset("Comment").about_character(self.obj)
        commentdict = {}
        for comment in comments:
            if comment.db_sender_objects.all():
                name = comment.db_sender_objects.all()[0].key.lower()
            else:
                name = comment.db_sender_external or 'none'
            comlist = commentdict.get(name, [])
            comlist.append(comment)
            commentdict[name] = comlist
        self._comments = commentdict
        return commentdict
    
    def build_rumorslist(self):
        """
        Returns a list of all rumor entries which we've heard (marked as a receiver for)
        """
        self._rumors = list(msg_utils.get_initial_queryset("Rumor").about_character(self.obj))
        return self._rumors
    
    def build_gossiplist(self):
        """
        Returns a list of all gossip entries we've heard (marked as a receiver for)
        """
        if self.obj.player_ob:
            self._gossip = list(msg_utils.get_initial_queryset("Rumor").all_read_by(self.obj.player_ob))
        else:
            self._gossip = self.build_rumorslist()

    def build_visionslist(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._visions = list(msg_utils.get_initial_queryset("Vision").about_character(self.obj))
        return self._visions

    # --------------------------------------------------------------
    # API/access methods
    # --------------------------------------------------------------

    def get_comments_by_sender(self, sender):
        """
        Checks messages our character has received and returns any comments made
        by a given sender. Sender can either be an ObjectDB (character object, etc)
        or a string, such as for an 'external' sender.
        """
        if not sender:
            name = 'none'
        elif hasattr(sender, 'key'):
            name = sender.key.lower()
        else:
            name = sender.lower()
        return self.comments.get(name, [])

    def add_comment(self, msg, commenter, date=""):
        """
        Creates a new comment written about us by a commenter. Commenter must be
        the object sending the message.
        """
        cls = msg_utils.lazy_import_from_str("Comment")
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        name = commenter.key.lower()
        msg = create_arx_message(commenter, msg, receivers=self.obj, header=header, cls=cls, tags=COMMENT_TAG)
        comlist = self.comments.get(name, [])
        comlist.insert(0, msg)
        self.comments[name] = comlist
        # NB: This check is actually necessary. When the property is first called
        # it will automatically build everything it finds from search, producing duplicate
        # But only if it's the first time it's called. So we check.
        if msg not in commenter.messages.white_journal:
            commenter.messages.white_journal.insert(0, msg)
        # comments made this week, for XP purposes
        self.num_comments += 1

    def add_vision(self, msg, sender, vision_obj=None):
        """adds a vision sent by a god or whatever"""
        cls = msg_utils.lazy_import_from_str("Vision")
        date = get_date()
        header = "date:%s" % date
        if not vision_obj:
            vision_obj = create_arx_message(sender, msg, receivers=self.obj, header=header, cls=cls, tags=VISION_TAG)
        else:
            self.obj.receiver_object_set.add(vision_obj)
        if vision_obj not in self.visions:
            self.visions.append(vision_obj)
        return vision_obj

    # ---------------------------------------------------------------------
    # Display methods
    # ---------------------------------------------------------------------

    @property
    def num_comments(self):
        return self.obj.db.num_comments or 0

    @num_comments.setter
    def num_comments(self, val):
        self.obj.db.num_comments = val
        
    @property
    def num_flashbacks(self):
        return self.obj.db.num_flashbacks or 0
        
    @num_flashbacks.setter
    def num_flashbacks(self, val):
        self.obj.db.num_flashbacks = val

    @property
    def num_weekly_journals(self):
        return self.num_journals + self.num_rel_updates + self.num_comments + self.num_flashbacks

    def reset_journal_count(self):
        self.num_journals = 0
        self.num_rel_updates = 0
        self.num_comments = 0
        self.num_flashbacks = 0
