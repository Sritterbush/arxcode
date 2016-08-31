"""
A basic inform, as well as other in-game messages.
"""

from datetime import datetime
from django.conf import settings
from django.db import models





#------------------------------------------------------------
#
# Inform
#
#------------------------------------------------------------

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
