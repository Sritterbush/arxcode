"""
A basic inform, as well as other in-game messages.
"""


from django.db import models
from evennia.comms.models import Msg
from .managers import (WHITE_TAG, BLACK_TAG, JournalManager, WhiteJournalManager, BlackJournalManager,)


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


# different proxy classes for Msg objects
class Journal(Msg):
    """
    Proxy model for Msg that represents an in-game journal written by a Character.
    """
    objects = JournalManager()
    white_journals = WhiteJournalManager()
    black_journals = BlackJournalManager()
    
    class Meta:
        proxy = True
        
        

