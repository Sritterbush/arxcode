"""
Handler for Messengers
"""
from world.dominion.models import CraftingMaterials, CraftingMaterialType
from world.msgs.handler_mixins.msg_utils import get_initial_queryset, lazy_import_from_str
from world.msgs.handler_mixins.handler_base import MsgHandlerBase
from world.msgs.managers import q_msgtag, PRESERVE_TAG, MESSENGER_TAG, reload_model_as_proxy
from server.utils.arx_utils import get_date, create_arx_message, inform_staff


class MessengerHandler(MsgHandlerBase):
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        super(MessengerHandler, self).__init__(obj)
        self._messenger_history = None

    @property
    def messenger_history(self):
        if self._messenger_history is None:
            self.build_messenger_history()
        return self._messenger_history

    @messenger_history.setter
    def messenger_history(self, value):
        self._messenger_history = value

    def create_messenger_header(self, icdate):
        header = "date:%s" % icdate
        name = self.spoofed_name
        if name:
            header += ";spoofed_name:%s" % name
        return header

    @property
    def messenger_qs(self):
        return get_initial_queryset("Messenger").about_character(self.obj)

    def build_messenger_history(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._messenger_history = list(self.messenger_qs)
        return self._messenger_history

    def preserve_messenger(self, msg):
        pres_count = self.messenger_qs.filter(q_msgtag(PRESERVE_TAG)).count()
        if pres_count >= 200:
            self.msg("You are preserving the maximum amount of messages allowed.")
            return
        if msg.preserved:
            self.msg("That message is already being preserved.")
            return
        msg.preserve()
        self.msg("This message will no longer be automatically deleted.")
        return True

    def create_messenger(self, msg, date=""):
        """
        Here we create the msg object and return it to the command to handle.
        They'll attach the msg object to each receiver as an attribute, who
        can then call receive_messenger on the stored msg.
        """
        cls = lazy_import_from_str("Messenger")
        if not date:
            date = get_date()
        header = self.create_messenger_header(date)
        msg = create_arx_message(self.obj, msg, receivers=None, header=header, cls=cls, tags=MESSENGER_TAG)
        return msg

    def del_messenger(self, msg):
        if msg in self.messenger_history:
            self.messenger_history.remove(msg)
        self.obj.receiver_object_set.remove(msg)
        # only delete the messenger if no one else has a copy
        if not msg.receivers:
            msg.delete()

    @property
    def spoofed_name(self):
        return self.obj.db.spoofed_messenger_name

    @spoofed_name.setter
    def spoofed_name(self, name):
        """Setter for spoofed name. If no name is specified, remove it."""
        if not name:
            self.obj.attributes.remove("spoofed_messenger_name")
            self.obj.msg("You will no longer send messengers with a fake name.")
            return
        self.obj.db.spoofed_messenger_name = name
        self.obj.msg("You will now send messengers by the name %s" % name)

    @property
    def discreet_servant(self):
        return self.obj.db.discreet_messenger

    @discreet_servant.setter
    def discreet_servant(self, val):
        if not val:
            self.obj.attributes.remove("discreet_messenger")
            self.obj.msg("You will not receive messages discreetly.")
            return
        self.obj.db.discreet_messenger = val
        self.obj.msg("%s will now deliver messages to you discreetly if they are in the same room." % val)

    @property
    def pending_messengers(self):
        if self.obj.db.pending_messengers is None:
            self.obj.db.pending_messengers = []
        return self.obj.db.pending_messengers

    @pending_messengers.setter
    def pending_messengers(self, val):
        self.obj.db.pending_messengers = val

    def unpack_pending_messenger(self, msgtuple):
        """
        A pending messenger is a tuple of several different values. We'll return values for any that we have, and
        defaults for everything else.
        Args:
            msgtuple: An iterable of values that we'll unpack.

        Returns:
            A string representing the messenger name, the Messenger object itself, any delivered object, silver,
            a tuple of crafting materials and their amount, and who this was forwarded by, if anyone.
        """
        messenger_name = "A messenger"
        msg = None
        delivered_object = None
        money = None
        mats = None
        forwarded_by = None
        try:
            import numbers
            msg = msgtuple[0]
            delivered_object = msgtuple[1]
            money_tuple = msgtuple[2]
            # check if the messenger is of old format, pre-conversion. Possible to sit in database for a long time
            if isinstance(money_tuple, numbers.Real):
                money = money_tuple
            elif money_tuple:
                money = money_tuple[0]
                if len(money_tuple) > 1:
                    mats = money_tuple[1]
                    try:
                        mats = (CraftingMaterialType.objects.get(id=mats[0]), mats[1])
                    except (CraftingMaterialType.DoesNotExist, TypeError, ValueError):
                        mats = None
            messenger_name = msgtuple[3] or "A messenger"
            forwarded_by = msgtuple[4]
        except IndexError:
            pass
        except TypeError:
            import traceback
            traceback.print_exc()
            self.msg("The message object was in the wrong format, possibly a result of a database error.")
            inform_staff("%s received a buggy messenger." % self.obj)
            return
        return msg, delivered_object, money, mats, messenger_name, forwarded_by

    def handle_delivery(self, obj, money, mats):
        if obj:
            obj.move_to(self.obj, quiet=True)
            self.msg("{gYou also have received a delivery!")
            self.msg("{wYou receive{n %s." % obj)
        if money and money > 0:
            self.obj.currency += money
            self.msg("{wYou receive %s silver coins.{n" % money)
        if mats:
            material, amt = mats
            dompc = self.obj.player_ob.Dominion
            try:
                mat = dompc.assets.materials.get(type=material)
                mat.amount += amt
                mat.save()
            except CraftingMaterials.DoesNotExist:
                dompc.assets.materials.create(type=material, amount=amt)
            self.msg("{wYou receive %s %s.{n" % (amt, material))

    def notify_of_messenger_arrival(self, messenger_name):
        """
        Let the character know they've received a messenger. If they have a discreet servant, only they're informed,
        otherwise the room will know.
        Args:
            messenger_name: Name of the messenger that is used.
        """
        discreet = self.discreet_servant
        try:
            if discreet.location == self.obj.location:
                self.msg("%s has discreetly informed you of a message delivered by %s." % (discreet, messenger_name))
            else:
                discreet = None
        except AttributeError:
            discreet = None
        if not discreet:
            ignore = [ob for ob in self.obj.location.contents if ob.db.ignore_messenger_deliveries and ob != self.obj]
            self.obj.location.msg_contents("%s arrives, delivering a message to {c%s{n before departing." % (
                messenger_name, self.obj.name), exclude=ignore)

    def check_valid_unread_messenger(self, unread):
        if isinstance(unread, basestring):
            self.msg("Your pending_messengers attribute was corrupted in the database conversion. "
                     "Sorry! Ask a GM to see if they can find which messages were yours.")
            self.obj.db.pending_messengers = []
            return
        if not unread:
            self.msg("You have no messengers waiting to be received.")
            return
        return True

    def receive_pending_messenger(self):
        unread = self.pending_messengers
        if not self.check_valid_unread_messenger(unread):
            return
        # get msg object and any delivered obj
        msg, obj, money, mats, messenger_name, forwarded_by = self.unpack_pending_messenger(unread.pop())
        self.pending_messengers = unread
        # adds it to our list of old messages
        self.receive_messenger(msg)
        self.notify_of_messenger_arrival(messenger_name)
        self.display_messenger(msg)
        # handle anything delivered
        self.handle_delivery(obj, money, mats)
        if forwarded_by:
            self.msg("{yThis message was forwarded by {c%s{n." % forwarded_by)

    def display_messenger(self, msg):
        if not msg:
            self.msg("It appears this messenger was deleted already. If this appears to be an error, "
                     "inform staff please.")
            return
        name = self.get_sender_name(msg)
        mssg = "{wSent by:{n %s\n" % name
        mssg += self.disp_entry(msg)
        self.msg(mssg, options={'box': True})

    def receive_messenger(self, msg):
        """marks us as having received the message"""
        if not msg or not msg.pk:
            self.obj.msg("This messenger appears to have been deleted.")
            return
        msg = reload_model_as_proxy(msg)
        self.obj.receiver_object_set.add(msg)
        # remove the pending message from the associated player
        player_ob = self.obj.player_ob
        player_ob.receiver_player_set.remove(msg)
        # add msg to our messenger history
        if msg not in self.messenger_history:
            self.messenger_history.insert(0, msg)
        # delete our oldest messenger that isn't marked to preserve
        qs = self.messenger_qs.exclude(q_msgtag(PRESERVE_TAG)).order_by('db_date_created')
        if qs.count() > 30:
            self.del_messenger(qs.first())
        return msg
