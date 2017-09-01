"""
Managers for Msg app, mostly proxy models for comms.Msg
"""
from django.db.models import Q
from django.db.models.query import QuerySet
from evennia.comms.managers import MsgManager


WHITE_TAG = "white_journal"
BLACK_TAG = "black_journal"


# Q functions for our queries
def q_read_by_player(player):
    """
    Gets a Q() object representing a Msg read by this player
    Args:
        player: Player/Account object that read our message

    Returns:
        Q() object for Msgs read by this user
    """
    return Q(db_receivers_players=player)


def q_tagname(tag):
    """
    Gets a Q() object used for determining what type of Msg this is
    Args:
        tag (str): The key of the Tag that we use for determining our proxy

    Returns:
        Q() object for determining the type of Msg that we are
    """
    return Q(db_tags__db_key=tag)


def q_sender_character(character):
    """
    Gets a Q() object for a Character that wrote this message
    Args:
        character: Character object that wrote this

    Returns:
        Q() object for Msgs sent/written by this character
    """
    return Q(db_sender_objects=character)


def q_receiver_character(character):
    """
    Gets a Q() object for a Character that the Msg is about
    Args:
        character: Character object that is targeted by this Msg in some way

    Returns:
        Q() object for Msgs sent/written about this character
    """
    return Q(db_receivers_objects=character)


class MsgQuerySet(QuerySet):
    """
    Custom queryset for allowing us to chain together these methods with manager methods.
    """
    def all_read_by(self, user):
        """
        Returns queryset of Msg objects read by this user.
        Args:
            user: Player object that's read these Msgs.

        Returns:
            QuerySet of Msg objects (or proxies) that have been read by us.
        """
        return self.filter(q_read_by_player(user))

    def all_unread_by(self, user):
        """
        Returns queryset of Msg objects not read by this user.
        Args:
            user: Player object that hasn't read these Msgs.

        Returns:
            QuerySet of Msg objects (or proxies) that haven't been read by us.
        """
        return self.exclude(q_read_by_player(user))

    def by_character(self, character):
        """
        Gets queryset of Msg objects written by this character. Note that players can
        also send messages, and that is a different query.
        Args:
            character: Character who wrote this Msg

        Returns:
            QuerySet of Msg objects written by this character
        """
        return self.filter(q_sender_character(character))

    def about_character(self, character):
        """
        Gets queryset of Msg objects written about this character. Note that players can
        also receive messages, and that is a different query.
        Args:
            character: Character who received this Msg

        Returns:
            QuerySet of Msg objects written about this character
        """
        return self.filter(q_receiver_character(character))


class MsgProxyManager(MsgManager):
    white_query = q_tagname(WHITE_TAG)
    black_query = q_tagname(BLACK_TAG)
    all_journals_query = Q(white_query | black_query)

    def get_queryset(self):
        return MsgQuerySet(self.model)

    # so that custom queryset methods can be used after Model.objects
    def __getattr__(self, attr):
        return getattr(self.get_queryset(), attr)


class JournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(JournalManager, self).get_queryset().filter(self.all_journals_query)

    def all_permitted_journals(self, user):
        qs = self.get_queryset()
        if user.is_staff:
            return qs
        # get all White Journals plus Black Journals they've written
        return qs.filter(self.white_query | Q(self.black_query & q_sender_character(user.db.char_ob)))
        
        
class BlackJournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(BlackJournalManager, self).get_queryset().filter(self.black_query)
        
        
class WhiteJournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(WhiteJournalManager, self).get_queryset().filter(self.white_query)
        
        
class MessengerManager(MsgProxyManager):
    pass
