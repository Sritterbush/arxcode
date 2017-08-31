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
from server.utils.arx_utils import get_date


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

    # -----------------------------------------------------------------
    # A number of static methods, used for processing. They could be
    # helper functions in the module, but I'd rather not pollute the
    # namespace with a whole bunch of different functions that need
    # to be inherited when you want to parse a message.
    # -----------------------------------------------------------------
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
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict
    
    @staticmethod
    def get_date_from_header(msg):
        # type: (msg) -> str
        header = MessageHandler.parse_header(msg)
        return header.get('date', None)

    def get_sender_name(self, msg):
        senders = msg.senders
        if senders:
            sender = senders[0]
            if sender:
                if sender.db.longname:
                    realname = sender.db.longname
                else:
                    realname = sender.key
            else:

                realname = "Unknown Sender"
        else:
            realname = "Unknown Sender"
        header = MessageHandler.parse_header(msg)
        name = header.get('spoofed_name', None) or ""
        if not name:
            return realname
        if self.obj.check_permstring("builders"):
            name = "%s {w(%s){n" % (name, realname)
        return name
    
    @staticmethod
    def create_date_header(icdate):
        return "date:%s" % icdate

    @staticmethod
    def tag_favorite(msg, player):
        msg.tags.add("pid_%s_favorite" % player.id)

    @staticmethod
    def untag_favorite(msg, player):
        msg.tags.remove("pid_%s_favorite" % player.id)

    def create_messenger_header(self, icdate):
        header = "date:%s" % icdate
        name = self.obj.db.spoofed_messenger_name
        if name:
            header += ";spoofed_name:%s" % name
        return header

    # ---------------------------------------------------------
    # Setup/building methods
    # ---------------------------------------------------------

    def build_commentdict(self):
        """
        Builds a list of all comments we've received, not ones we've written.
        """
        comments = list(_GA(self.obj, 'receiver_object_set').filter(db_tags__db_key="comment"))
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
        rels = _GA(self.obj, 'sender_object_set').filter(db_tags__db_key="relationship")
        jtype = "white_journal" if white else "black_journal"
        rels = list(rels.filter(db_tags__db_key=jtype))
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
        self._rumors = list(_GA(self.obj, 'receiver_object_set').filter(db_tags__db_key="rumors"
                                                                        ).order_by('-db_date_created'))
        return self._rumors
    
    def build_gossiplist(self):
        """
        Returns a list of all gossip entries we've heard (marked as a receiver for)
        """
        if self.obj.player_ob:
            self._gossip = list(self.obj.player_ob.receiver_player_set.filter(db_tags__db_key="gossip"
                                                                              ).order_by('-db_date_created'))
        else:
            self._gossip = list(_GA(self.obj, 'receiver_object_set').filter(db_tags__db_key="gossip"
                                                                            ).order_by('-db_date_created'))

    def build_visionslist(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._visions = list(_GA(self.obj, 'receiver_object_set').filter(db_tags__db_key="visions"
                                                                         ).order_by('-db_date_created'))
        return self._visions

    def build_whitejournal(self):
        """
        Returns a list of all 'white journal' entries our character has written.
        """
        self._white_journal = list(_GA(self.obj, 'sender_object_set').filter(db_tags__db_key="white_journal"
                                                                             ).order_by('-db_date_created'))
        return self._white_journal

    def build_blackjournal(self):
        """
        Returns a list of all 'black journal' entries our character has written.
        """
        self._black_journal = list(_GA(self.obj, 'sender_object_set').filter(db_tags__db_key="black_journal"
                                                                             ).order_by('-db_date_created'))
        return self._black_journal

    def build_messenger_history(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._messenger_history = list(_GA(self.obj, 'receiver_object_set').filter(db_tags__db_key="messenger"
                                                                                   ).order_by('-db_date_created'))
        return self._messenger_history

    @staticmethod
    def get_event(msg):
        from world.dominion.models import RPEvent
        from evennia.typeclasses.tags import Tag
        try:
            tag = msg.db_tags.get(db_key__isnull=False,
                                  db_data__isnull=False,
                                  db_category="event")
            return RPEvent.objects.get(id=tag.db_data)
        except (Tag.DoesNotExist, Tag.MultipleObjectsReturned, AttributeError,
                TypeError, ValueError, RPEvent.DoesNotExist):
            return None

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
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        name = commenter.key.lower()
        msg = create_message(commenter, msg, receivers=self.obj, header=header)
        msg.tags.add("comment", category="msg")
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
        """adds message to our journal"""
        if not white:
            try:
                p_id = self.obj.player_ob.id
                blacklock = "read: perm(Builders) or pid(%s)." % p_id
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
        """creates a new journal message and returns it"""
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        j_tag = "white_journal" if white else "black_journal"
        msg = create_message(self.obj, msg, receivers=self.obj.player_ob,
                             header=header)
        msg.tags.add(j_tag, category="msg")
        msg = self.add_to_journals(msg, white)
        # journals made this week, for xp purposes
        num_journals = self.obj.db.num_journals or 0
        num_journals += 1
        self.obj.db.num_journals = num_journals
        return msg

    def add_event_journal(self, event, msg, white=True, date=""):
        """Creates a new journal about event and returns it"""
        msg = self.add_journal(msg, white, date)
        tagkey = event.name.lower()
        category = "event"
        data = str(event.id)
        msg.tags.add(tagkey, category=category, data=data)
        return msg

    def add_relationship(self, msg, targ, white=True, date=""):
        """creates a relationship and adds relationship to our journal"""
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        name = targ.key.lower()
        receivers = [targ, self.obj.player_ob]
        msg = create_message(self.obj, msg, receivers=receivers, header=header)
        msg.tags.add("relationship", category="msg")
        j_tag = "white_journal" if white else "black_journal"
        msg.tags.add(j_tag, category="msg")
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

    def add_vision(self, msg, sender, vision_obj=None):
        """adds a vision sent by a god or whatever"""
        date = get_date()
        header = "date:%s" % date
        if not vision_obj:
            vision_obj = create_message(sender, msg, receivers=self.obj, header=header)
            vision_obj.tags.add("visions", category="msg")
        else:
            self.obj.receiver_object_set.add(vision_obj)
        if vision_obj not in self.visions:
            self.visions.append(vision_obj)
        return vision_obj

    def receive_messenger(self, msg):
        """marks us as having received the message"""
        if not msg or not msg.pk:
            self.obj.msg("This messenger appears to have been deleted.")
            return
        self.obj.receiver_object_set.add(msg)
        # remove the pending message from the associated player
        player_ob = self.obj.player_ob
        player_ob.receiver_player_set.remove(msg)
        if msg not in self.messenger_history:
            self.messenger_history.insert(0, msg)
        qs = self.obj.receiver_object_set.filter(db_tags__db_key="messenger").exclude(
            db_tags__db_key="preserve").order_by('db_date_created')
        if qs.count() > 30:
            self.del_messenger(qs.first())
        return msg

    def create_messenger(self, msg, date=""):
        """
        Here we create the msg object and return it to the command to handle.
        They'll attach the msg object to each receiver as an attribute, who
        can then call receive_messenger on the stored msg.
        """
        if not date:
            date = get_date()
        header = self.create_messenger_header(date)
        msg = create_message(self.obj, msg, receivers=None, header=header)
        msg.tags.add("messenger", category="msg")
        return msg

    def del_messenger(self, msg):
        if msg in self.messenger_history:
            self.messenger_history.remove(msg)
        self.obj.receiver_object_set.remove(msg)
        # only delete the messenger if no one else has a copy
        if not msg.db_receivers_objects.all() and not msg.db_receivers_players.all():
            msg.delete()

    # ---------------------------------------------------------------------
    # Display methods
    # ---------------------------------------------------------------------
    
    def disp_entry(self, entry):
        date = self.get_date_from_header(entry)
        msg = "{wDate:{n %s\n" % date
        event = self.get_event(entry)
        if event:
            msg += "{wEvent:{n %s\n" % event.name
        msg += "{wOOC Date:{n %s\n\n" % entry.db_date_created.strftime("%x %X")
        msg += entry.db_message
        try:
            ob = self.obj.player_ob
            # don't bother to mark player receivers for a messenger
            if ob not in entry.receivers and "messenger" not in entry.tags.all():
                entry.receivers = ob
        except (AttributeError, TypeError):
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
        # noinspection PyBroadException
        try:
            subjects = entry.db_receivers_objects.all()
            if subjects:
                msg += "Written about: {c%s{n\n" % ", ".join(ob.key for ob in subjects)
            msg += self.disp_entry(entry)
            # mark the player as having read this
            if caller:
                if caller.player_ob:
                    caller = caller.player_ob
                entry.receivers = caller
        except Exception:  # Catch possible database errors, or bad formatting, etc
            import traceback
            traceback.print_exc()
            msg = "Error in retrieving journal. It may have been deleted and the server has not yet synchronized."
        return msg

    def search_journal(self, text):
        """
        Returns all matches for text in character's journal
        """
        receivers = self.obj.sender_object_set.filter(db_tags__db_key="white_journal",
                                                      db_receivers_objects__db_key__iexact=text)
        tags = self.obj.sender_object_set.filter(db_tags__db_key="white_journal").filter(
                                                 db_header__icontains=text)
        body = self.obj.sender_object_set.filter(db_tags__db_key="white_journal",
                                                 db_message__icontains=text)
        total = set(list(receivers) + list(tags) + list(body))
        return total

    def size(self, white=True):
        if white:
            return len(self.white_journal)
        else:
            return len(self.black_journal)

    @property
    def num_weekly_journals(self):
        return (self.obj.db.num_journals or 0) + (self.obj.db.num_rel_updates or 0) + (self.obj.db.num_comments or 0)

    def reset_journal_count(self):
        self.obj.db.num_journals = 0
        self.obj.db.num_rel_updates = 0
        self.obj.db.num_comments = 0

    def convert_short_rel_to_long_rel(self, character, rel_key, white=True):
        """
        Converts a short relationship held in our self.obj to a
        long relationship instead.
        :type character: ObjectDB
        :type rel_key: str
        :type white: bool
        """
        entry_list = self.obj.db.relationship_short[rel_key]
        found_entry = None
        for entry in entry_list:
            if entry[0].lower() == character.key.lower():
                found_entry = entry
                break
        entry_list.remove(found_entry)
        if not entry_list:
            del self.obj.db.relationship_short[rel_key]
        else:
            self.obj.db.relationship_short[rel_key] = entry_list
        msg = found_entry[1]
        self.add_relationship(msg, character, white=white)

    def delete_journal(self, msg):
        if msg in self.white_journal:
            self.white_journal.remove(msg)
        if msg in self.black_journal:
            self.black_journal.remove(msg)
        for rel_list in self.white_relationships.values():
            if msg in rel_list:
                rel_list.remove(msg)
        for rel_list in self.black_relationships.values():
            if msg in rel_list:
                rel_list.remove(msg)
        msg.delete()

    def convert_to_black(self, msg):
        self.white_journal.remove(msg)
        msg.db_header = msg.db_header.replace("white", "black")
        msg.tags.add("black_journal", category="msg")
        msg.tags.remove("white_journal", category="msg")
        self.add_to_journals(msg, white=False)
        msg.save()
