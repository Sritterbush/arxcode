"""
A slightly different implementation of channels specific to arx.
We use Msg objects for our chat history rather than log files,
and have some different switches/commands, such as who, last, etc.

Minor changes overall, but with functionality players have become
accustomed to.
"""

from evennia.commands import command
from evennia.comms.models import ChannelDB, Msg
from server.utils.arx_utils import datetime_format
from evennia.utils.logger import tail_log_file


class ArxChannelCommand(command.Command):
    """
    {channelkey} channel

    {channeldesc}

    Usage:
       {lower_channelkey}  <message>
       {lower_channelkey} last
       {lower_channelkey}/history
       {lower_channelkey} who
       {lower_channelkey} mute
       {lower_channelkey} on
       {lower_channelkey} off

    This is a channel. If you have subscribed to it, you can send to
    it by entering its name or alias, followed by the text you want to
    send.
    """
    # this flag is what identifies this cmd as a channel cmd
    # and branches off to the system send-to-channel command
    # (which is customizable by admin)
    is_channel = True
    key = "general"
    help_category = "Channel Names"
    obj = None
    display_history = False
    num_messages = 20

    def parse(self):
        """
        Simple parser
        """
        # cmdhandler sends channame:msg here.
        channelname, msg = self.args.split(":", 1)
        if msg.startswith("/history"):
            self.display_history = True
            arg = msg[8:]
            try:
                self.num_messages = int(arg) if arg else 20
            except ValueError:
                pass
        else:
            self.display_history = False
            self.num_messages = 20
        self.args = (channelname.strip(), msg.strip())

    def func(self):
        """
        Create a new message and send it to channel, using
        the already formatted input.
        """
        channelkey, msg = self.args
        caller = self.caller
        player = caller.db.player_ob
        if not msg:
            self.msg("Say what?")
            return
        channel = ChannelDB.objects.get_channel(channelkey)

        if not channel:
            self.msg("Channel '%s' not found." % channelkey)
            return
        if msg == "on":
            if player:
                caller = player
            temp_mute = caller.db.temp_mute_list or []
            if channel in temp_mute:
                temp_mute.remove(channel)
            if channel.unmute(caller):
                self.msg("You unmute channel %s." % channel)
                return
            caller.execute_cmd("addcom %s" % channelkey)
            return
        if not channel.has_connection(caller):
            string = "You are not connected to channel '%s'."
            self.msg(string % channelkey)
            return
        if not channel.access(caller, 'send'):
            string = "You are not permitted to send to channel '%s'."
            self.msg(string % channelkey)
            return
        if "%r" in msg or "{/" in msg or "|/" in msg:
            caller.msg("Channel messages may not contain newline characters.")
            return
        if msg == "who" or msg == "?" or msg == "all" or msg == "list":
            self.msg("{w%s:{n\n %s" % (channel, channel.wholist))
            return
        if msg == 'last' or msg.startswith("last "):
            msglist = msg.split()
            # check if it wasn't just a message starting with 'last'
            # eg: 'last week we blah blah'
            if len(msglist) == 1 or (len(msglist) == 2 and msglist[1].isdigit()):
                self.num_messages = 20
                if len(msglist) == 2:
                    self.num_messages = int(msglist[1])
                self.display_history = True
        if self.display_history:
            # chan_messages = list(Msg.objects.get_messages_by_channel(channel.id))
            # if len(chan_messages) > 200:
            #     del_list = chan_messages[:-200]
            #     chan_messages = chan_messages[-200:]
            #     for mssg in del_list:
            #         channel.delete_chan_message(mssg)
            # caller.msg("Messages in %s:\n" % channel.key)
            # if len(chan_messages) > self.num_messages:
            #     last_messages = chan_messages[-self.num_messages:]
            # else:
            #     last_messages = chan_messages
            # for msg in last_messages:
            #     caller.msg("{w%s{n %s" % (datetime_format(msg.date_created), msg.message))
            log_file = channel.attributes.get("log_file", default="channel_%s.log" % channel.key)
            # send_msg = lambda lines: self.msg("".join(line.split("[-]", 1)[1]
            #                                           if "[-]" in line else line for line in lines))

            def send_msg(lines):
                msgs = "".join(line for line in lines)
                self.msg(msgs)
            self.msg("{wChannel history for %s:{n" % self.key)
            tail_log_file(log_file, 0, self.num_messages, callback=send_msg)
            return
        if msg == "off" or msg == "mute":
            if player:
                caller = player
            if msg == "mute":
                channel.temp_mute(caller)
                return
            muted = channel.mute(caller)
            if muted:
                caller.msg("You stop listening to channel '%s'." % channel.key)
            else:
                caller.msg("You already muted channel '%s'." % channel.key)
            return
        if player in channel.mutelist or caller in channel.mutelist:
            self.msg("You have that channel muted.")
            return
        channel.msg(msg, senders=caller.db.char_ob or caller, keep_log=True, online=True)
        # if Msg.objects.get_messages_by_channel(channel.id).count() > 200:
        #     earliest = Msg.objects.get_messages_by_channel(channel.id).earliest('db_date_created')
        #     channel.delete_chan_message(earliest)
