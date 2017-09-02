"""
Managers for Msg app, mostly proxy models for comms.Msg
"""
from django.db.models import Q
from django.db.models.query import QuerySet
from evennia.comms.managers import MsgManager


WHITE_TAG = "white_journal"
BLACK_TAG = "black_journal"
VISION_TAG = "visions"
MESSENGER_TAG = "messenger"
RELATIONSHIP_TAG = "relationship"
GOSSIP_TAG = "gossip"
RUMOR_TAG = "rumors"
COMMENT_TAG = "comment"
POST_TAG = "board post"
TAG_CATEGORY = "msg"
_get_model_from_tags = None


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
    
    
def q_msgtag(tag):
    """
    Gets a Q object of the tagname with the tag category.
    
        Args:
            tag (str): The key of the Tag.
            
        Returns:
            Q() object of the tag key with the tag category
    """
    return Q(q_tagname(tag) & Q(db_category=TAG_CATEGORY))


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


def q_favorite_of_player(player):
    """
    Gets a Q() object for Msgs tagged as the player's favorite
    Args:
        player: Checking this player's favorite Msgs

    Returns:
        Q() object for the query that represents their favorites
    """
    tag_name = "pid_%s_favorite" % player.id
    return q_tagname(tag_name)


# noinspection PyProtectedMember
def reload_model_as_proxy(msg):
    """
    Given a Msg object, we want to clear it from the cache, find the appropriate
    Proxy class for it, and return it so that it's now loaded into memory. Once
    it's there, it'll stay there due to SharedMemoryModel
    Args:
        msg:Msg object we're reloading

    Returns:

    """
    global _get_model_from_tags
    if _get_model_from_tags is None:
        from .models import get_model_from_tags as _get_model_from_tags
    # check if we're already a proxy. If so, no reason to reload it
    if msg._meta.proxy:
        return msg
    dbid = msg.id
    model = _get_model_from_tags(msg.tags.all())
    if not model:
        return msg
    type(msg).flush_from_cache(msg, force=True)
    msg = model.objects.get(id=dbid)
    return msg


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

    def written_by(self, character):
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

    def favorites_of(self, player):
        """
        Gets queryset of Msg objects marked as a favorite by this player.
        Args:
            player: Player who flagged this as a favorite

        Returns:
            QuerySet of Msg objects tagged as a favorite by this player
        """
        return self.filter(q_favorite_of_player(player))

    def white(self):
        return self.filter(q_msgtag(WHITE_TAG))

    def black(self):
        return self.filter(q_msgtag(BLACK_TAG))

    def get(self, *args, **kwargs):
        ret = super(MsgQuerySet, self).get(*args, **kwargs)
        return reload_model_as_proxy(ret)


class MsgProxyManager(MsgManager):
    white_query = q_msgtag(WHITE_TAG)
    black_query = q_msgtag(BLACK_TAG)
    all_journals_query = Q(white_query | black_query)
    relationship_query = q_msgtag(RELATIONSHIP_TAG)

    def get_queryset(self):
        return MsgQuerySet(self.model)

    # so that custom queryset methods can be used after Model.objects
    def __getattr__(self, attr):
        return getattr(self.get_queryset(), attr)

    def relationships(self):
        return self.get_queryset().filter(self.relationship_query)

    def get(self, *args, **kwargs):
        return self.get_queryset().get(*args, **kwargs)


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
    def get_queryset(self):
        return super(MessengerManager, self).get_queryset().filter(q_msgtag(MESSENGER_TAG))


class VisionManager(MsgProxyManager):
    def get_queryset(self):
        return super(VisionManager, self).get_queryset().filter(q_msgtag(VISION_TAG))


class CommentManager(MsgProxyManager):
    def get_queryset(self):
        return super(CommentManager, self).get_queryset().filter(q_msgtag(COMMENT_TAG))


class PostManager(MsgProxyManager):
    def get_queryset(self):
        return super(PostManager, self).get_queryset().filter(q_msgtag(POST_TAG))
        
    def for_board(self, board):
        return self.get_queryset().about_character(board)


class RumorManager(MsgProxyManager):
    def get_queryset(self):
        return super(RumorManager, self).get_queryset().filter(q_msgtag(GOSSIP_TAG) | q_msgtag(RUMOR_TAG))
