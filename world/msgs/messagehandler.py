"""
Messagehandler

This handler takes either a PlayerDB or ObjectDB object and
processes the Msg objects they have in their related sets.
Msg() objects will be distinguished in how they function based
on their header field, which we'll parse and process here. The
header field will be a list of key:value pairs, separated by
semicolons.
"""

from evennia.utils.create import create_message
from world.utils.utils import get_date
from twisted.internet import reactor

_GA = object.__getattribute__

class MessageHandler(object):
    def __init__(self, obj):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        # the ObjectDB instance
        self.obj = obj
        # comments that obj has received about it
        self._comments = {}
        # White Journal entries that obj has written
        self._white_journal = {}
        # Black Journal entries that obj has written
        self._black_journal = {}
        # Relationships obj has written in their White Journal
        self._white_relationships = {}
        # Relationships obj has written in their Black Journal
        self._black_relationships = {}
        self._messenger_history = []
        self._rumors = []
        self._gossip = []
        self._visions = []


    @property
    def comments(self):
        if not self._comments:
            self.build_commentdict()
        return self._comments

    @comments.setter
    def comments(self, value):
        self._comments = value

    @property
    def white_journal(self):
        if not self._white_journal:
            self.build_whitejournal()
        return self._white_journal

    @white_journal.setter
    def white_journal(self, value):
        self._white_journal = value

    @property
    def black_journal(self):
        if not self._black_journal:
            self.build_blackjournal()
        return self._black_journal

    @black_journal.setter
    def black_journal(self, value):
        self._black_journal = value

    @property
    def white_relationships(self):
        if not self._white_relationships:
            self.build_relationshipdict(True)
        return self._white_relationships
    
    @white_relationships.setter
    def white_relationships(self, value):
        self._white_relationships = value

    @property
    def black_relationships(self):
        if not self._black_relationships:
            self.build_relationshipdict(False)
        return self._black_relationships
    
    @black_relationships.setter
    def black_relationships(self, value):
        self._black_relationships = value

    @property
    def messenger_history(self):
        if not self._messenger_history:
            self.build_messenger_history()
        return self._messenger_history
    
    @messenger_history.setter
    def messenger_history(self, value):
        self._messenger_history = value

    @property
    def rumors(self):
        if not self._rumors:
            self.build_rumorslist()
        return self._rumors
    @property
    def gossip(self):
        if not self._gossip:
            self.build_gossiplist()
        return self._gossip

    @property
    def visions(self):
        if not self._visions:
            self.build_visionslist()
        return self._visions


    #-----------------------------------------------------------------
    # A number of static methods, used for processing. They could be
    # helper functions in the module, but I'd rather not pollute the
    # namespace with a whole bunch of different functions that need
    # to be inherited when you want to parse a message.
    #-----------------------------------------------------------------
    @staticmethod
    def parse_header(msg):
        """
        Given a message object, return a dictionary of the different
        key:value pairs separated by semicolons in the header
        """
        header = msg.db_header
        if not header:
            return {}
        hlist = header.split(";")
        keyvalpairs = [pair.split(":") for pair in hlist]
        keydict = {pair[0].strip():pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict
    
    @staticmethod
    def get_date_from_header(msg):
        header = MessageHandler.parse_header(msg)
        return header.get('date', None)
    
    @staticmethod
    def create_comment_header(icdate):
        return "journal:white_journal;type:comment;date:%s" % icdate

    @staticmethod
    def create_journal_header(icdate, white=True):
        jtype = "white_journal" if white else "black_journal"
        return "journal:%s;type:entry;date:%s" % (jtype, icdate)

    @staticmethod
    def create_relationship_header(icdate, white=True):
        jtype = "white_journal" if white else "black_journal"
        return "journal:%s;type:relationship;date:%s" % (jtype, icdate)

    @staticmethod
    def create_messenger_header(icdate):
        return "type:messenger;date:%s" % icdate

    #---------------------------------------------------------
    # Setup/building methods
    #---------------------------------------------------------

    def build_commentdict(self):
        """
        Builds a list of all comments we've received, not ones we've written.
        """
        comments = list(_GA(self.obj, 'receiver_object_set').filter(db_header__icontains="comment"))
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

    def build_relationshipdict(self, white=True):
        """
        Builds a dictionary of names of people we have relationships with to a list
        of relationship Msgs we've made about that character.
        """
        rels = _GA(self.obj, 'sender_object_set').filter(db_header__icontains="relationship")
        jtype = "white_journal" if white else "black_journal"
        rels = list(rels.filter(db_header__icontains=jtype))
        relsdict = {}
        for rel in rels:
            if rel.db_receivers_objects.all():
                name = rel.db_receivers_objects.all()[0].key.lower()
                relslist = relsdict.get(name, [])
                relslist.append(rel)
                relsdict[name] = relslist
        if white:
            self._white_relationships = relsdict
        else:
            self._black_relationships = relsdict
        return relsdict
    
    def build_rumorslist(self):
        """
        Returns a list of all rumor entries which we've heard (marked as a receiver for)
        """
        self._rumors = list(_GA(self.obj, 'receiver_object_set').filter(db_header__icontains="rumor").order_by('-db_date_created'))
        return self._rumors
    
    def build_gossiplist(self):
        """
        Returns a list of all gossip entries we've heard (marked as a receiver for)
        """
        if self.obj.db.player_ob:
            self._gossip = list(self.obj.db.player_ob.receiver_player_set.filter(db_header__icontains="gossip").order_by('-db_date_created'))
        else:
            self._gossip = list(_GA(self.obj, 'receiver_object_set').filter(db_header__icontains="gossip").order_by('-db_date_created'))

    def build_visionslist(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._visions = list(_GA(self.obj, 'receiver_object_set').filter(db_header__icontains="visions").order_by('-db_date_created'))
        return self._visions
        
    
    def build_whitejournal(self):
        """
        Returns a list of all 'white journal' entries our character has written.
        """
        self._white_journal = list(_GA(self.obj,'sender_object_set').filter(db_header__icontains="white_journal").order_by('-db_date_created'))
        return self._white_journal

    def build_blackjournal(self):
        """
        Returns a list of all 'black journal' entries our character has written.
        """
        self._black_journal = list(_GA(self.obj, 'sender_object_set').filter(db_header__icontains="black_journal").order_by('-db_date_created'))
        return self._black_journal

    def build_messenger_history(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._messenger_history = list(_GA(self.obj, 'receiver_object_set').filter(db_header__icontains="messenger").order_by('-db_date_created'))
        return self._messenger_history

    #--------------------------------------------------------------
    # API/access methods
    #--------------------------------------------------------------

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
        if not date:
            date = get_date()
        header = self.create_comment_header(date)
        name = commenter.key.lower()
        msg = create_message(commenter, msg, receivers=self.obj, header=header)
        comlist = self.comments.get(name, [])
        comlist.insert(0, msg)
        self.comments[name] = comlist
        # NB: This check is actually necessary. When the property is first called
        # it will automatically build everything it finds from search, producing duplicate
        # But only if it's the first time it's called. So we check.
        if msg not in commenter.messages.white_journal:
            commenter.messages.white_journal.insert(0, msg)
        # comments made this week, for XP purposes
        num_comments = commenter.db.num_comments or 0
        num_comments += 1
        commenter.db.num_comments = num_comments

    def add_to_journals(self, msg, white=True):
        "adds message to our journal"
        if not white:
            try:
                id = self.obj.db.player_ob.id
                blacklock = "read: perm(Builders) or pid(%s)." % id
            except AttributeError:
                blacklock = "read: perm(Builders)"
            msg.locks.add(blacklock)
            if msg not in self.black_journal:
                self.black_journal.insert(0, msg)
        else:
            if msg not in self.white_journal:
                self.white_journal.insert(0, msg)
        return msg

    def add_journal(self, msg, white=True, date=""):
        "creates a new journal message and returns it"
        if not date:
            date = get_date()
        header = self.create_journal_header(date, white)
        msg = create_message(self.obj, msg, receivers=self.obj.db.player_ob,
                             header=header)
        msg = self.add_to_journals(msg, white)
        # journals made this week, for xp purposes
        num_journals = self.obj.db.num_journals or 0
        num_journals += 1
        self.obj.db.num_journals = num_journals
        return msg

    def add_event_journal(self, event, msg, white=True, date=""):
        "Creates a new journal about event and returns it"
        msg = self.add_journal(msg, white, date)
        msg.event = event
        msg.save()
        return msg

    def add_relationship(self, msg, targ, white=True, date=""):
        "creates a relationship and adds relationship to our journal"
        if not date:
            date = get_date()
        header = self.create_relationship_header(date, white)
        name = targ.key.lower()
        receivers = [targ, self.obj.db.player_ob]
        msg = create_message(self.obj, msg, receivers=receivers, header=header)
        msg = self.add_to_journals(msg, white)
        rels = self.white_relationships if white else self.black_relationships
        relslist = rels.get(name, [])
        if msg not in relslist:
            relslist.insert(0, msg)
        rels[name] = relslist
        # number of relationship updates this week, for xp purposes
        num_rels = self.obj.db.num_rel_updates or 0
        num_rels += 1
        self.obj.db.num_rel_updates = num_rels
        return msg

    def add_vision(self, msg, sender):
        "adds a vision sent by a god or whatever"
        date = get_date()
        header = "type:visions;date:%s" % date
        msg = create_message(sender, msg, receivers=self.obj, header=header)
        if msg not in self.visions:
            self.visions.append(msg)
        return msg

    def receive_messenger(self, msg):
        "marks us as having received the message"
        from django.db.models import Q
        self.obj.receiver_object_set.add(msg)
        if msg not in self.messenger_history:
            self.messenger_history.insert(0, msg)
        qs = self.obj.receiver_object_set.filter(Q(db_header__icontains="messenger")
                                                 & ~Q(db_header__icontains="preserve")).order_by('db_date_created')
        if qs.count() > 30:
           self.del_messenger(qs.first()) 
        return msg

    def send_messenger(self, msg, date=""):
        """
        Here we create the msg object and return it to the command to handle.
        They'll attach the msg object to each receiver as an attribute, who
        can then call receive_messenger on the stored msg.
        """
        if not date:
            date = get_date()
        header = self.create_messenger_header(date)
        msg = create_message(self.obj, msg, receivers=None, header=header)
        return msg

    def del_messenger(self, msg):
        if msg in self.messenger_history:
            self.messenger_history.remove(msg)
        self.obj.receiver_object_set.remove(msg)
        # only delete the messenger if no one else has a copy
        if not msg.db_receivers_objects.all():
            msg.delete()
            
    
    #---------------------------------------------------------------------
    # Display methods
    #---------------------------------------------------------------------
    
    def disp_entry(self, entry):
        date = self.get_date_from_header(entry)
        msg = "{wDate:{n %s\n" % date
        if entry.event:
            msg += "{wEvent:{n %s\n" % entry.event
        msg += "{wOOC Date:{n %s\n\n" % entry.db_date_created.strftime("%x %X")
        msg += entry.db_message
        try:
            ob = self.obj.db.player_ob
            # don't bother to mark player receivers for a messenger
            if ob not in entry.receivers and "messenger" not in msg.db_header:
                entry.receivers = ob
        except Exception:
            pass
        return msg
        
    def disp_entry_by_num(self, num=1, white=True, caller=None):
        if white:
            journal = self.white_journal
            jname = "white journal"
        else:
            journal = self.black_journal
            jname = "black reflection"
        msg = "Message {w#%s{n for {c%s{n's %s:\n" % (num, self.obj, jname)
        num -= 1
        entry = journal[num]
        if caller and not white:
            if not entry.access(caller, 'read'):
                return False
        try:
            subjects = entry.db_receivers_objects.all()
            if subjects:
                msg += "Written about: {c%s{n\n" % ", ".join(ob.key for ob in subjects)
            msg += self.disp_entry(entry)
            # mark the player as having read this
            if caller:
                if caller.db.player_ob:
                    caller = caller.db.player_ob
                entry.receivers = caller
        except Exception:
            msg = "Error in retrieving journal. It may have been deleted and the server has not yet synchronized."
        return msg

    def search_journal(self, text):
        """
        Returns all matches for text in character's journal
        """
        receivers = self.obj.sender_object_set.filter(db_header__icontains="white_journal",
                                                      db_receivers_objects__db_key__iexact=text)
        tags = self.obj.sender_object_set.filter(db_header__icontains="white_journal").filter(
                                                 db_header__icontains=text)
        body = self.obj.sender_object_set.filter(db_header__icontains="white_journal",
                                                 db_message__icontains=text)
        total = set(list(receivers) + list(tags) + list(body))
        return total

    def size(self, white=True):
        if white:
            return len(self.white_journal)
        else:
            return len(self.black_journal)

    




