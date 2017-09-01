"""
A basic inform, as well as other in-game messages.
"""


from django.db import models
from evennia.comms.models import Msg
from .managers import (JournalManager, WhiteJournalManager, BlackJournalManager, MessengerManager, WHITE_TAG, BLACK_TAG)


# ------------------------------------------------------------
#
# Inform
#
# ------------------------------------------------------------

class Inform(models.Model):
    """
    Informs represent persistent messages sent from the server
    to a player. For communication between entities, like mail,
    Msg should be used. This will primarily be used in Dominion
    or other game events where players will be informed upon
    logging-in of what transpired. In Dominion, these messages
    are created during weekly maintenance, and the week # is
    stored as well.

    The Inform class defines the following properties:
        player - receipient of the inform
        message - Text that is sent to the player
        date_sent - Time the inform was sent
        is_unread - Whether the player has read the inform
        week - The # of the week during which this inform was created.
    """
    player = models.ForeignKey("players.PlayerDB", related_name="informs", blank=True, db_index=True)
    message = models.TextField("Information sent to players")
    # send date
    date_sent = models.DateTimeField(editable=False, auto_now_add=True, db_index=True)
    # the week # of the maintenance cycle during which this inform was created
    week = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    is_unread = models.BooleanField(default=True)
    # allow for different types of informs/reports
    category = models.CharField(blank=True, null=True, max_length=80)

    class Meta:
        app_label = "msgs"
        db_table = "comms_inform"

    @classmethod
    def bulk_inform(cls, players, text, category):
        bulk_list = []
        for ob in players:
            bulk_list.append(cls(player=ob, message=text, category=category))
        cls.objects.bulk_create(bulk_list)
        for player in players:
            player.announce_informs()


# noinspection PyUnresolvedReferences
class MarkReadMixin(object):
    """
    Proxy method for Msg that adds a few methods that most uses in Arx will share in common.
    """
    def mark_read(self, player):
        """
        Mark this Msg object as read by the player
        Args:
            player: Player who has read this Journal/Messenger/Board post/etc
        """
        self.db_receivers_players.add(player)

    def mark_unread(self, player):
        """
        Mark this Msg object as unread by the player
        Args:
            player: Player who has read this Journal/Messenger/Board post/etc
        """
        self.db_receivers_players.remove(player)
        
    def parse_header(self):
        """
        Given a message object, return a dictionary of the different
        key:value pairs separated by semicolons in the header
        """
        header = self.db_header
        if not header:
            return {}
        hlist = header.split(";")
        keyvalpairs = [pair.split(":") for pair in hlist]
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict


# different proxy classes for Msg objects
class Journal(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an in-game journal written by a Character.
    """
    class Meta:
        proxy = True
    objects = JournalManager()
    white_journals = WhiteJournalManager()
    black_journals = BlackJournalManager()

    @property
    def writer(self):
        """The person who wrote this journal."""
        try:
            return self.senders[0]
        except IndexError:
            pass

    @property
    def relationship(self):
        """Character who a journal is written about."""
        try:
            return self.db_receivers_objects.all()[0]
        except IndexError:
            pass

    def __str__(self):
        relationship = self.relationship
        rel_txt = " on %s" % relationship if relationship else ""
        return "<Journal written by %s%s>" % (self.writer, rel_txt)

    def tag_favorite(self, player):
        """
        Tags this journal as a favorite by the player. We create a custom tag on the Journal to represent that.
        Args:
            player: Player tagging this journal as a favorite.
        """
        self.tags.add("pid_%s_favorite" % player.id)

    def untag_favorite(self, player):
        """
        Removes tag marking this journal as a favorite of the player if it's present.
        Args:
            player: Player removing this journal as a favorite.
        """
        self.tags.remove("pid_%s_favorite" % player.id)
        
    def convert_to_black(self):
        self.db_header = self.db_header.replace("white", "black")
        self.tags.add(BLACK_TAG, category="msg")
        self.tags.remove(WHITE_TAG, category="msg")
        self.save()


class Messenger(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an in-game journal written by a Character.
    """
    class Meta:
        proxy = True
    objects = MessengerManager()