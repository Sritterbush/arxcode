"""
Player

The Player represents the game "account" and each login has only one
Player object. A Player is what chats on default channels but has no
other in-game-world existance. Rather the Player puppets Objects (such
as Characters) in order to actually participate in the game world.


Guest

Guest players are simple low-level accounts that are created/deleted
on the fly and allows users to test the game without the committment
of a full registration. Guest accounts are deactivated by default; to
activate them, add the following line to your settings file:

    GUEST_ENABLED = True

You will also need to modify the connection screen to reflect the
possibility to connect with a guest account. The setting file accepts
several more options for customizing the Guest account system.

"""

from evennia import DefaultPlayer
from typeclasses.mixins import MsgMixins


class Player(MsgMixins, DefaultPlayer):
    """
    This class describes the actual OOC player (i.e. the user connecting
    to the MUD). It does NOT have visual appearance in the game world (that
    is handled by the character which is connected to this). Comm channels
    are attended/joined using this object.

    It can be useful e.g. for storing configuration options for your game, but
    should generally not hold any character-related info (that's best handled
    on the character level).

    Can be set using BASE_PLAYER_TYPECLASS.


    * available properties

     key (string) - name of player
     name (string)- wrapper for user.username
     aliases (list of strings) - aliases to the object. Will be saved to database as AliasDB entries
     but returned as strings.
     dbref (int, read-only) - unique #id-number. Also "id" can be used.
     date_created (string) - time stamp of object creation
     permissions (list of strings) - list of permission strings

     user (User, read-only) - django User authorization object
     obj (Object) - game object controlled by player. 'character' can also be used.
     sessions (list of Sessions) - sessions connected to this player
     is_superuser (bool, read-only) - if the connected user is a superuser

    * Handlers

     locks - lock-handler: use locks.add() to add new lock strings
     db - attribute-handler: store/retrieve database attributes on this self.db.myattr=val, val=self.db.myattr
     ndb - non-persistent attribute handler: same as db but does not create a database entry when storing data
     scripts - script-handler. Add new scripts to object with scripts.add()
     cmdset - cmdset-handler. Use cmdset.add() to add new cmdsets to object
     nicks - nick-handler. New nicks with nicks.add().

    * Helper methods

     msg(text=None, **kwargs)
     swap_character(new_character, delete_old_character=False)
     execute_cmd(raw_string, session=None)
     search(ostring, global_search=False, attribute_name=None, use_nicks=False, location=None, ignore_errors=False,
     player=False)
     is_typeclass(typeclass, exact=False)
     swap_typeclass(new_typeclass, clean_attributes=False, no_default=True)
     access(accessing_obj, access_type='read', default=False)
     check_permstring(permstring)

    * Hook methods (when re-implementation, remember methods need to have self as first arg)

     basetype_setup()
     at_player_creation()

     - note that the following hooks are also found on Objects and are
       usually handled on the character level:

     at_init()
     at_cmdset_get(**kwargs)
     at_first_login()
     at_post_login(session=None)
     at_disconnect()
     at_message_receive()
     at_message_send()
     at_server_reload()
     at_server_shutdown()

    """
    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name
    
    def at_player_creation(self):
        """
        This is called once, the very first time
        the player is created (i.e. first time they
        register with the game). It's a good place
        to store attributes all players should have,
        like configuration values etc.
        """
        # set an (empty) attribute holding the characters this player has
        lockstring = "attrread:perm(Wizards);attredit:perm(Wizards);attrcreate:perm(Wizards)"
        self.attributes.add("_playable_characters", [], lockstring=lockstring)
        self.db.mails = []
        self.db.readmails = set()
        self.db.char_ob = None

    # noinspection PyBroadException
    def at_post_login(self, session=None):
        """
        Called at the end of the login process, just before letting
        them loose. This is called before an eventual Character's
        at_post_login hook.
        :type self: PlayerDB
        :type session: Session
        """
        self.db._last_puppet = self.db.char_ob or self.db._last_puppet
        super(Player, self).at_post_login(session)
        if self.tags.get("new_mail"):
            self.msg("{y*** You have new mail. ***{n")
        if self.db.new_comments:
            self.msg("{wYou have new comments.{n")
        self.db.afk = ""
        self.announce_informs()
        pending = self.db.pending_messages or []
        for msg in pending:
            self.msg(msg, options={'box': True})
        self.db.pending_messages = []
        if self.assigned_to.filter(status=1, priority__lte=5):
            self.msg("{yYou have unresolved tickets assigned to you. Use @job/mine to view them.{n")
            return
        # in this mode we should have only one character available. We
        # try to auto-connect to it by calling the @ic command
        # (this relies on player.db._last_puppet being set)
        self.execute_cmd("@bbsub/quiet story updates")
        try:
            from commands.commands.bboards import get_unread_posts
            get_unread_posts(self)
        except Exception:
            pass
        try:
            if self.roster.frozen:
                self.roster.frozen = False
                self.roster.save()
            if self.roster.roster.name == "Inactive":
                from web.character.models import Roster
                try:
                    active = Roster.objects.get(name="Active")
                    self.roster.roster = active
                    self.roster.save()
                except Roster.DoesNotExist:
                    pass
            watched_by = self.db.char_ob.db.watched_by or []
            if self.sessions.count() == 1 and not self.db.hide_from_watch:
                for watcher in watched_by:
                    watcher.msg("{wA player you are watching, {c%s{w, has connected.{n" % self)
        except AttributeError:
            pass

    # noinspection PyBroadException
    def announce_informs(self):
        try:
            unread = self.informs.filter(is_unread=True).count()
            if unread:
                self.msg("{w*** You have %s unread informs. Use @informs to read them. ***{n" % unread)
        except Exception:
            pass

    def is_guest(self):
        """
        Overload in guest object to return True
        """
        return False
    
    def at_first_login(self):
        """
        Only called once, the very first
        time the user logs in.
        """
        self.execute_cmd("addcom pub=public")
        pass

    def mail(self, message, subject=None, sender=None, receivers=None):
        """
        Sends a mail message to player.
        """
        from django.utils import timezone
        sentdate = timezone.now().strftime("%x %X")
        mail = (sender, subject, message, sentdate, receivers)
        if not self.db.mails:
            self.db.mails = []
        self.db.mails.append(mail)
        if sender:
            from_str = " from {c%s{y" % sender.capitalize()
        else:
            from_str = ""
        self.msg("{yYou have new mail%s. Use {w'mail %s' {yto read it.{n" % (from_str, len(self.db.mails)))
        self.tags.add("new_mail")

    def get_fancy_name(self):
        return self.key.capitalize()

    # noinspection PyAttributeOutsideInit
    def set_name(self, value):
        self.key = value
    name = property(get_fancy_name, set_name)

    def inform(self, message, category=None, week=0, append=True):
        if not append:
            inform = self.informs.create(message=message, category=category)
        else:
            informs = self.informs.filter(category=category, week=week,
                                          is_unread=True)
            if informs:
                inform = informs[0]
                inform.message += "\n\n" + message
                inform.save()
            else:
                inform = self.informs.create(message=message, category=category,
                                             week=week)
        index = list(self.informs.all()).index(inform) + 1
        self.msg("{yYou have new informs. Use {w@inform %s{y to read them.{n" % index)

    def send_or_queue_msg(self, message):
        if self.is_connected:
            self.msg(message, options={'box': True})
            return
        pending = self.db.pending_messages or []
        pending.append(message)
        self.db.pending_messages = pending

    def get_all_sessions(self):
        return self.sessions.all()

    @property
    def public_orgs(self):
        """
        Return public organizations we're in.
        """
        try:
            return self.Dominion.public_orgs
        except AttributeError:
            return []

    @property
    def current_orgs(self):
        try:
            return self.Dominion.current_orgs
        except AttributeError:
            return []

    def pay_resources(self, rtype, amt):
        """
        Attempt to pay resources. If we don't have enough,
        return False.
        """
        try:
            assets = self.Dominion.assets
            current = getattr(assets, rtype)
            if current < amt:
                return False
            setattr(assets, rtype, current - amt)
            assets.save()
            return True
        except AttributeError:
            return False

    def gain_resources(self, rtype, amt):
        """
        Attempt to gain resources. If something goes wrong, we return 0. We call pay_resources with a negative
        amount, and if returns true, we return the amount to show what we gained.
        """
        if self.pay_resources(rtype, -amt):
            return amt
        return 0

    def pay_action_points(self, amt):
        """
        Attempt to pay action points. If we don't have enough,
        return False.
        """
        try:
            if self.roster.action_points != self.db.char_ob.roster.action_points:
                self.roster.refresh_from_db(fields=("action_points",))
                self.db.char_ob.roster.refresh_from_db(fields=("action_points",))
            if self.roster.action_points < amt:
                return False
            self.roster.action_points -= amt
            self.roster.save()
            self.msg("{wYou use %s action points and have %s remaining this week.{n" % (amt, self.roster.action_points))
            # force refresh in inventory command next time it's used to be sure values sync up
            self.db.char_ob.ndb.stale_ap = True
            return True
        except AttributeError:
            return False

    @property
    def retainers(self):
        try:
            return self.Dominion.assets.agents.filter(unique=True)
        except AttributeError:
            return []

    @property
    def agents(self):
        try:
            return self.Dominion.assets.agents.all()
        except AttributeError:
            return []

    def get_absolute_url(self):
        try:
            return self.db.char_ob.get_absolute_url()
        except AttributeError:
            pass

    def at_post_disconnect(self):
        if not self.sessions.all():
            watched_by = self.db.char_ob and self.db.char_ob.db.watched_by or []
            if not watched_by:
                return
            if not self.db.hide_from_watch:
                for watcher in watched_by:
                    watcher.msg("{wA player you are watching, {c%s{w, has disconnected.{n" % self.key.capitalize())
            self.previous_log = self.current_log
            self.current_log = []
            self.db.lookingforrp = False
            temp_muted = self.db.temp_mute_list or []
            for channel in temp_muted:
                channel.unmute(self)
            self.attributes.remove('temp_mute_list')

    def log_message(self, from_obj, text):
        from evennia.utils.utils import make_iter
        if not self.tags.get("private_mode"):
            text = text.strip()
            from_obj = make_iter(from_obj)[0]
            tup = (from_obj, text)
            if tup not in self.current_log and from_obj != self and from_obj != self.db.char_ob:
                self.current_log.append((from_obj, text))

    @property
    def current_log(self):
        if self.ndb.current_log is None:
            self.ndb.current_log = []
        return self.ndb.current_log

    @current_log.setter
    def current_log(self, val):
        self.ndb.current_log = val

    @property
    def previous_log(self):
        if self.db.previous_log is None:
            self.db.previous_log = []
        return self.db.previous_log

    @previous_log.setter
    def previous_log(self, val):
        self.db.previous_log = val

    @property
    def flagged_log(self):
        if self.db.flagged_log is None:
            self.db.flagged_log = []
        return self.db.flagged_log

    @flagged_log.setter
    def flagged_log(self, val):
        self.db.flagged_log = val

    def report_player(self, player):
        charob = player.db.char_ob
        log = []
        for line in (list(self.previous_log) + list(self.current_log)):
            if line[0] == charob or line[0] == player:
                log.append(line)
        self.flagged_log = log

    @property
    def allow_list(self):
        if self.db.allow_list is None:
            self.db.allow_list = []
        return self.db.allow_list
    
    @property
    def block_list(self):
        if self.db.block_list is None:
            self.db.block_list = []
        return self.db.block_list

    @property
    def clues_shared_modifier_seed(self):
        from world.stats_and_skills import SOCIAL_SKILLS, SOCIAL_STATS
        seed = 0
        pc = self.db.char_ob
        for stat in SOCIAL_STATS:
            seed += pc.attributes.get(stat) or 0
        # do not be nervous. I love you. <3
        seed += sum([pc.db.skills.get(ob, 0) for ob in SOCIAL_SKILLS])
        seed += pc.db.skills.get("investigation", 0) * 3
        return seed

    @property
    def clue_cost(self):
        return int(100.0/float(self.clues_shared_modifier_seed + 1)) + 1
        
    @property
    def participated_storyrequests(self):
        """Storyrequests we participated in"""
        from web.helpdesk.models import Ticket
        from django.db.models import Q
        return Ticket.objects.filter(Q(queue__slug__iexact="story") & Q(
            Q(submitting_player=self) | Q(participants=self))).distinct()

    def show_online(self, caller, check_puppet=False):
        """
        Checks if we're online and caller has privileges to see that
        Args:
            caller: Player checking if we're online
            check_puppet: Whether to check if we're currently puppeting our character object

        Returns:
            True if they see us as online, False otherwise.
        """
        if not self.db.char_ob:
            return True
        return self.db.char_ob.show_online(caller, check_puppet)

    @property
    def player_ob(self):
        return None

    @property
    def char_ob(self):
        try:
            return self.roster.character
        except AttributeError:
            pass
