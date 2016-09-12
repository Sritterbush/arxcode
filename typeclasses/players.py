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
     aliases (list of strings) - aliases to the object. Will be saved to database as AliasDB entries but returned as strings.
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
     search(ostring, global_search=False, attribute_name=None, use_nicks=False, location=None, ignore_errors=False, player=False)
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
        self.db.newmail = False
        self.db.readmails = set()
        self.db.char_ob = None
        self.db.player_email = ""
        self.nicks.add('pub', 'public', category="channel")

    def at_post_login(self, session=None):
        """
        Called at the end of the login process, just before letting
        them loose. This is called before an eventual Character's
        at_post_login hook.
        """
        self.db._last_puppet = self.db.char_ob or self.db._last_puppet
        super(Player, self).at_post_login(session)
        if self.db.newmail:
            self.msg("{y*** You have new mail. ***{n")
        if self.db.new_comments:
            self.msg("{wYou have new comments.{n")
        self.db.afk = ""
        try:
            unread = self.informs.filter(is_unread=True).count()
            if unread:
                self.msg("{w*** You have %s unread informs. Use @informs to read them. ***{n" % unread)
        except Exception:
            pass
        pending = self.db.pending_messages or []
        for msg in pending:
            self.msg(msg, box=True)
        self.db.pending_messages = []
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
        except AttributeError:
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
        self.db.newmail = True

    def get_fancy_name(self):
        return self.key.capitalize()
    name = property(get_fancy_name)

    def inform(self, message, category=None, week=0, append=True):
        if not append:
            self.informs.create(message=message, category=category)
        else:
            informs = self.informs.filter(category=category, week=week,
                                          is_unread=True)
            if informs:
                inform = informs[0]
                inform.message += "\n\n" + message
                inform.save()
            else:
                self.informs.create(message=message, category=category,
                                    week=week)
        self.msg("{yYou have new informs. Use {w@inform {yto read them.{n")

    def send_or_queue_msg(self, message):
        if self.is_connected:
            self.msg(message, box=True)
            return
        pending = self.db.pending_messages or []
        pending.append(message)
        self.db.pending_messages = pending

    def get_all_sessions(self):
        return self.sessions.all()

    def search(self, searchdata, return_puppet=False, search_object=False,
               nofound_string=None, multimatch_string=None, **kwargs):
        """
        This is similar to `DefaultObject.search` but defaults to searching
        for Players only.

        Args:
            searchdata (str or int): Search criterion, the Player's
                key or dbref to search for.
            return_puppet (bool, optional): Instructs the method to
                return matches as the object the Player controls rather
                than the Player itself (or None) if nothing is puppeted).
            search_object (bool, optional): Search for Objects instead of
                Players. This is used by e.g. the @examine command when
                wanting to examine Objects while OOC.
            nofound_string (str, optional): A one-time error message
                to echo if `searchdata` leads to no matches. If not given,
                will fall back to the default handler.
            multimatch_string (str, optional): A one-time error
                message to echo if `searchdata` leads to multiple matches.
                If not given, will fall back to the default handler.

        Return:
            match (Player, Object or None): A single Player or Object match.
        Notes:
            Extra keywords are ignored, but are allowed in call in
            order to make API more consistent with
            objects.objects.DefaultObject.search.

        """
        from evennia.players.models import PlayerDB
        from evennia.players.players import _AT_SEARCH_RESULT
        # handle me, self and *me, *self
        if isinstance(searchdata, basestring):
            # handle wrapping of common terms
            if searchdata.lower() in ("me", "*me", "self", "*self",):
                return self
        if search_object:
            matches = ObjectDB.objects.object_search(searchdata)
        else:
            matches = PlayerDB.objects.player_search(searchdata)
        matches = _AT_SEARCH_RESULT(matches, self, query=searchdata,
                                    nofound_string=nofound_string,
                                    multimatch_string=multimatch_string)
        if matches and return_puppet:
            try:
                return matches.puppet
            except AttributeError:
                return None
        return matches


# previously Guest was here, inheriting from DefaultGuest
# removed it in order to resolve namespace conflicts for typeclasses app

