"""
Channel

The channel class represents the out-of-character chat-room usable by
Players in-game. It is mostly overloaded to change its appearance, but
channels can be used to implement many different forms of message
distribution systems.

Note that sending data to channels are handled via the CMD_CHANNEL
syscommand (see evennia.syscmds). The sending should normally not need
to be modified.

"""

from evennia import DefaultChannel
from evennia.comms.models import Msg
from evennia.utils.utils import make_iter

class Channel(DefaultChannel):
    """
    Working methods:
        at_channel_creation() - called once, when the channel is created
        has_connection(player) - check if the given player listens to this channel
        connect(player) - connect player to this channel
        disconnect(player) - disconnect player from channel
        access(access_obj, access_type='listen', default=False) - check the
                    access on this channel (default access_type is listen)
        delete() - delete this channel
        message_transform(msg, emit=False, prefix=True,
                          sender_strings=None, external=False) - called by
                          the comm system and triggers the hooks below
        msg(msgobj, header=None, senders=None, sender_strings=None,
            persistent=None, online=False, emit=False, external=False) - main
                send method, builds and sends a new message to channel.
        tempmsg(msg, header=None, senders=None) - wrapper for sending non-persistent
                messages.
        distribute_message(msg, online=False) - send a message to all
                connected players on channel, optionally sending only
                to players that are currently online (optimized for very large sends)

    Useful hooks:
        channel_prefix(msg, emit=False) - how the channel should be
                  prefixed when returning to user. Returns a string
        format_senders(senders) - should return how to display multiple
                senders to a channel
        pose_transform(msg, sender_string) - should detect if the
                sender is posing, and if so, modify the string
        format_external(msg, senders, emit=False) - format messages sent
                from outside the game, like from IRC
        format_message(msg, emit=False) - format the message body before
                displaying it to the user. 'emit' generally means that the
                message should not be displayed with the sender's name.

        pre_join_channel(joiner) - if returning False, abort join
        post_join_channel(joiner) - called right after successful join
        pre_leave_channel(leaver) - if returning False, abort leave
        post_leave_channel(leaver) - called right after successful leave
        pre_send_message(msg) - runs just before a message is sent to channel
        post_send_message(msg) - called just after message was sent to channel

    """
    def delete_chan_message(self, message):
        """
        When given a message object, if the message has other
        receivers, just remove the channels inside the message so
        that the other receivers don't lose the message. Otherwise,
        delete it completely.
        """
        if self not in message.channels:
            return
        if message.receivers:
            # remove the channel from the message, but leave msg
            # intact for other receivers
            del message.channels
            return
        message.delete()
        
    def distribute_message(self, msg, online=False):
        """
        Method for grabbing all listeners that a message should be sent to on
        this channel, and sending them a message.
        """
        # get all players connected to this channel and send to them
        for entity in self.subscriptions.all():
            try:
                entity.msg(msg.message, from_obj=msg.senders,
                           options={"from_channel":self.id})
            except AttributeError as e:
                logger.log_trace("%s\nCannot send msg to %s" % (e, entity))

    def channel_prefix(self, msg=None, emit=False):
        """
        How the channel should prefix itself for users. Return a string.
        """
        # use color if defined
        if self.db.colorstr:
            return '%s[%s]{n ' % (self.db.colorstr, self.key)
        # else default is whether it's private or not
        if self.locks.get('listen').strip() != "listen:all()":
            return '{y[%s]{n ' % self.key
        return '{w[%s]{n ' % self.key

    def pose_transform(self, msg, sender_string):
        """
        Detects if the sender is posing, and modifies the message accordingly.
        """
        pose = False
        message = msg.message
        message_start = message.lstrip()
        if message_start.startswith((':', ';')):
            pose = True
            message = message[1:]
            if not message.startswith((':', "'", ',')):
                if not message.startswith(' '):
                    message = ' ' + message
        sender_string = "{c%s{n" % sender_string
        if pose:
            return '%s%s' % (sender_string, message)
        else:
            return '%s: %s' % (sender_string, message)
   
    def msg(self, msgobj, header=None, senders=None, sender_strings=None,
            persistent=False, online=False, emit=False, external=False):
        """
        Send the given message to all players connected to channel. Note that
        no permission-checking is done here; it is assumed to have been
        done before calling this method. The optional keywords are not used if
        persistent is False.

        msgobj - a Msg/TempMsg instance or a message string. If one of the
                 former, the remaining keywords will be ignored. If a string,
                 this will either be sent as-is (if persistent=False) or it
                 will be used together with header and senders keywords to
                 create a Msg instance on the fly.
        senders - an object, player or a list of objects or players.
                 Optional if persistent=False.
        sender_strings - Name strings of senders. Used for external
                connections where the sender is not a player or object. When
                this is defined, external will be assumed.
        external - Treat this message agnostic of its sender.
        persistent (default False) - ignored if msgobj is a Msg or TempMsg.
                If True, a Msg will be created, using header and senders
                keywords. If False, other keywords will be ignored.
        online (bool) - If this is set true, only messages people who are
                online. Otherwise, messages all players connected. This can
                make things faster, but may not trigger listeners on players
                that are offline.
        emit (bool) - Signals to the message formatter that this message is
                not to be directly associated with a name.
        """
        if senders:
            senders = make_iter(senders)
        else:
            senders = []
        if isinstance(msgobj, basestring):
            # given msgobj is a string
            msg = msgobj
            # saves message if the channel allows logging and message should be persistent
            if persistent and self.db.keep_log:
                msgobj = Msg()
            else:
                # Use TempMsg, so this message is not stored.
                msgobj = TempMsg()
            msgobj.header = header
            msgobj.message = msg
            msgobj.channels = [self]  # add this channel

        if not msgobj.senders:
            msgobj.senders = senders
        msgobj = self.pre_send_message(msgobj)
        if not msgobj:
            return False
        msgobj = self.message_transform(msgobj, emit=emit,
                                        sender_strings=sender_strings,
                                        external=external)
        self.distribute_message(msgobj, online=online)
        self.post_send_message(msgobj)
        # need save at end to capture all attributes of saved Msg()
        if persistent and self.db.keep_log:
            msgobj.save()
        return True

    def tempmsg(self, message, header=None, senders=None):
        """
        A wrapper for sending non-persistent messages. Note that this will
        still be a persistent message if the channel's logging is turned on.
        By default, channel logging is False, so a temp message being captured
        should only happen by intent.
        """
        self.msg(message, senders=senders, header=header, persistent=False)



