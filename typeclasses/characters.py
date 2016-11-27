"""
Characters

Characters are (by default) Objects setup to be puppeted by Players.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""
from evennia import DefaultCharacter
from typeclasses.mixins import MsgMixins, ObjectMixins, NameMixins
from world.msgs.messagehandler import MessageHandler
from evennia.utils.utils import lazy_property
import time
from world.stats_and_skills import do_dice_check


class Character(NameMixins, MsgMixins, ObjectMixins, DefaultCharacter):
    """
    The Character defaults to reimplementing some of base Object's hook methods with the
    following functionality:

    at_basetype_setup - always assigns the DefaultCmdSet to this object type
                    (important!)sets locks so character cannot be picked up
                    and its commands only be called by itself, not anyone else.
                    (to change things, use at_object_creation() instead).
    at_after_move - Launches the "look" command after every move.
    at_post_unpuppet(player) -  when Player disconnects from the Character, we
                    store the current location in the pre_logout_location Attribute and
                    move it to a None-location so the "unpuppeted" character
                    object does not need to stay on grid. Echoes "Player has disconnected" 
                    to the room.
    at_pre_puppet - Just before Player re-connects, retrieves the character's
                    pre_logout_location Attribute and move it back on the grid.
    at_post_puppet - Echoes "PlayerName has entered the game" to the room.

    """
    def at_object_creation(self):
        """
        Called once, when this object is first created.
        """
        # setting up custom attributes for ArxMUSH
        # BriefMode is for toggling brief descriptions from rooms
        self.db.briefmode = False
        # identification attributes about our player
        self.db.player_ob = None
        self.db.gender = "Female"
        self.db.age = 20
        self.db.concept = "None"
        self.db.fealty = "None"
        self.db.marital_status = "single"
        self.db.family = "None"
        self.db.dice_string = "Default Dicestring"
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.db.attackable = True
        self.db.skills = {}
        self.db.abilities = {}
        self.at_init()
        self.locks.add("delete:perm(Immortals);tell:all()")

    @property
    def is_character(self):
        return True
        
    @lazy_property
    def messages(self):    
        return MessageHandler(self)

    def at_after_move(self, source_location):
        """
        Hook for after movement. Look around, with brief determining how much detail we get.
        :param source_location: Room
        :return:
        """
        table = self.db.sitting_at_table
        if table and source_location != self.location:
            table.leave(self)
        if self.db.briefmode:
            string = "{c%s{n" % self.location.name
            string += self.location.return_contents(self, show_places=False)
            string += self.location.event_string()
            self.msg(string)
        else:
            self.execute_cmd('look')
        if self.ndb.waypoint:
            if self.location == self.ndb.waypoint:
                self.msg("You have reached your destination.")
                self.ndb.waypoint = None
                return
            dirs = self.get_directions(self.ndb.waypoint)
            if dirs:
                self.msg("You sense your destination lies through the %s." % dirs)
            else:
                self.msg("You've lost track of how to get to your destination.")
                self.ndb.waypoint = None

    def return_appearance(self, pobject, detailed=False, format_desc=False, show_contents=False):
        """
        This is a convenient hook for a 'look'
        command to call.
        """
        if not pobject:
            return
        # get and identify all objects
        if pobject is self or pobject.check_permstring("builders"):
            detailed = True
        strip_ansi = pobject.db.stripansinames
        string = "{c%s{n" % self.get_fancy_name()
        # Health appearance will also determine whether we
        # use an alternate appearance if we are dead.
        health_appearance = self.get_health_appearance()
        # desc used to be db.desc. May use db.desc for temporary values,
        # such as illusions, masks, etc
        desc = self.desc     
        if self.db.use_alt_desc and self.db.desc:
            desc = self.db.desc
        if strip_ansi:
            try:
                from evennia.utils.ansi import parse_ansi
                desc = parse_ansi(desc, strip_ansi=True)
            except (AttributeError, ValueError, TypeError, UnicodeDecodeError):
                pass
        if desc:
            extras = self.return_extras(pobject)
            if extras:
                extras += "\n"
            string += "\n\n%s%s" % (extras, desc)
        if health_appearance:
            string += "\n\n%s" % health_appearance
        string += self.return_contents(pobject, detailed, strip_ansi=strip_ansi)
        return string

    @property
    def species(self):
        return self.db.species or "Human"

    def return_extras(self, pobject):
        """
        Return a string from glancing at us
        :param pobject: Character
        :return:
        """
        hair = self.db.haircolor or ""
        hair = hair.capitalize()
        eyes = self.db.eyecolor or ""
        eyes = eyes.capitalize()
        skin = self.db.skintone or ""
        skin = skin.capitalize()
        height = self.db.height or ""
        species = self.species
        gender = self.db.gender or ""
        gender = gender.capitalize()
        age = self.db.age
        if pobject.check_permstring("builders"):
            true_age = self.db.real_age
            if true_age and true_age != age:
                pobject.msg("{wThis true age is:{n %s" % true_age)
        string = """
{w.---------------------->Physical Characteristics<---------------------.{n
{w|                                                                     |{n
{w| Species:{n %(species)-14s {wGender:{n %(gender)-15s {wAge:{n %(age)-15s{w|{n 
{w| Height:{n %(height)-15s {wEye Color:{n %(eyes)-15s                  {w|{n
{w| Hair Color:{n %(hair)-11s {wSkin Tone:{n %(skin)-17s                {w|{n
{w.---------------------------------------------------------------------.{n
""" % ({'species': species, 'hair': hair, 'eyes': eyes, 'height': height, 'gender': gender, 'age': age, 'skin': skin})
        return string
    
    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.
        """
        if self.db.health_status and self.db.health_status == "dead":
            return
        self.db.health_status = "dead"
        self.db.container = True
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % self.name)
        try:
            from commands.cmdsets import death
            cmds = death.DeathCmdSet
            if cmds.key not in [ob.key for ob in self.cmdset.all()]:
                self.cmdset.add(cmds, permanent=True)
        except Exception as err:
            print "<<ERROR>>: Error when importing death cmdset: %s" % err
        from server.utils.arx_utils import inform_staff
        if not self.db.npc:
            inform_staff("{rDeath{n: Character {c%s{n has died." % self.key)

    def resurrect(self, *args, **kwargs):
        """
        Cue 'Bring Me Back to Life' by Evanessence.
        """
        self.db.health_status = "alive"
        self.db.container = False
        if self.location:
            self.location.msg_contents("{w%s has returned to life.{n" % self.name)
        try:
            from commands.cmdsets import death
            self.cmdset.delete(death.DeathCmdSet)
        except Exception as err:
            print "<<ERROR>>: Error when importing mobile cmdset: %s" % err

    def fall_asleep(self, uncon=False):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if uncon:
            self.db.sleep_status = "unconscious"
        else:
            self.db.sleep_status = "asleep"
        if self.location:
            self.location.msg_contents("%s falls %s." % (self.name, self.db.sleep_status))
        try:
            from commands.cmdsets import sleep
            cmds = sleep.SleepCmdSet
            if cmds.key not in [ob.key for ob in self.cmdset.all()]:
                self.cmdset.add(cmds, permanent=True)
        except Exception as err:
            print "<<ERROR>>: Error when importing death cmdset: %s" % err

    @property
    def conscious(self):
        return self.db.sleep_status == "awake" and self.db.health_status != "dead"

    def wake_up(self, quiet=False):
        """
        Wakes up.
        """
        woke = False
        if self.db.sleep_status != "awake":
            self.db.sleep_status = "awake"
            woke = True
        if self.db.health_status == "dead":
            woke = False
        if self.location:
            if not quiet and woke:
                self.location.msg_contents("%s wakes up." % self.name)
            combat = self.location.ndb.combat_manager
            if combat and self in combat.ndb.combatants:
                combat.wake_up(self)
        try:
            from commands.cmdsets import sleep
            self.cmdset.delete(sleep.SleepCmdSet)
        except Exception as err:
            print "<<ERROR>>: Error when importing mobile cmdset: %s" % err
        return

    def get_health_appearance(self):
        """
        Return a string based on our current health.
        """
        name = self.name
        if self.db.health_status == "dead":
            return "%s is currently dead." % name
        wound = float(self.dmg)/float(self.max_hp)
        if wound <= 0:
            msg = "%s is in perfect health." % name
        elif 0 < wound <= 0.1:
            msg = "%s is very slightly hurt." % name
        elif 0.1 < wound <= 0.25:
            msg = "%s is moderately wounded." % name
        elif 0.25 < wound <= 0.5:
            msg = "%s is seriously wounded." % name
        elif 0.5 < wound <= 0.75:
            msg = "%s is very seriously wounded." % name
        elif 0.75 < wound <= 2.0:
            msg = "%s is critically wounded." % name
        else:
            msg = "%s is very critically wounded, possibly dying." % name
        awake = self.db.sleep_status
        if awake and awake != "awake":
            msg += " They are %s." % awake
        return msg
    
    def recovery_test(self, diff_mod=0, free=False):
        """
        A mechanism for healing characters. Whenever they get a recovery
        test, they heal the result of a willpower+stamina roll, against
        a base difficulty of 0. diff_mod can change that difficulty value,
        and with a higher difficulty can mean it can heal a negative value,
        resulting in the character getting worse off. We go ahead and change
        the player's health now, but leave the result of the roll in the
        caller's hands to trigger other checks - death checks if we got
        worse, unconsciousness checks, whatever.
        """
        diff = 0 + diff_mod
        roll = do_dice_check(self, stat_list=["willpower", "stamina"], difficulty=diff)
        if roll > 0:
            self.msg("You feel better.")
        else:
            self.msg("You feel worse.")
        damage_to_apply = self.dmg - roll  # how much dmg character has after the roll
        if damage_to_apply < 0:
            damage_to_apply = 0  # no remaining damage
        self.db.damage = damage_to_apply
        if not free:
            self.db.last_recovery_test = time.time()
        return roll

    def sensing_check(self, difficulty=15, invis=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        roll = do_dice_check(self, stat="perception", stat_keep=True, difficulty=difficulty)
        return roll

    def get_fancy_name(self, short=False):
        """
        Returns either an illusioned name, a long_name with titles, or our key.
        """
        if self.db.false_name:
            return self.db.false_name
        if not short and self.db.longname:
            return self.db.longname
        return self.db.colored_name or self.key
    
    def _get_worn(self):
        """Returns list of items in inventory currently being worn."""
        worn_list = []
        for ob in self.contents:
            if ob.db.worn_by == self:
                worn_list.append(ob)
        return worn_list
    
    def _get_armor(self):
        """
        Returns armor value of all items the character is wearing plus any
        armor in their attributes.
        """
        armor = self.db.armor_class or 0
        for ob in self.worn:
            try:
                ob_armor = ob.armor or 0
            except AttributeError:
                ob_armor = 0
            armor += ob_armor
        return armor

    def _get_armor_penalties(self):
        penalty = 0
        for ob in self.worn:
            try:
                penalty += ob.penalty
            except (AttributeError, ValueError, TypeError):
                pass
        return penalty
    armor_penalties = property(_get_armor_penalties)

    def _get_maxhp(self):
        """Returns our max hp"""
        hp = self.db.stamina or 0
        hp *= 20
        hp += 20
        bonus = self.db.bonus_max_hp or 0
        hp += bonus
        return hp
    
    def _get_current_damage(self):
        """Returns how much damage we've taken."""
        dmg = self.db.damage or 0
        return dmg

    def _set_current_damage(self, dmg):
        if dmg < 1:
            dmg = 0
        self.db.damage = dmg
        self.start_recovery_script()

    def start_recovery_script(self):
        # start the script if we have damage
        start_script = self.dmg > 0
        scripts = [ob for ob in self.scripts.all() if ob.key == "Recovery"]
        if scripts:
            if start_script:
                scripts[0].start()
            else:
                scripts[0].stop()
        elif start_script:
            self.scripts.add("typeclasses.scripts.recovery.Recovery")
        
    # @property
    # def name(self):
    #     return self.get_fancy_name(short=True)
    
    # note - setter properties do not work with the typeclass system
    armor = property(_get_armor)
    
    @property
    def worn(self):
        return self._get_worn()
    
    max_hp = property(_get_maxhp)
    
    dmg = property(_get_current_damage, _set_current_damage)

    def adjust_xp(self, value):
        """
        Spend or earn xp. Total xp keeps track of all xp we've earned on this
        character, and isn't lowered by spending xp. Checks for having sufficient
        xp should be before this takes place, so we'll raise an exception if they
        can't pay the cost.
        """
        if not self.db.total_xp:
            self.db.total_xp = 0
        if not self.db.xp:
            self.db.xp = 0
        if value > 0:
            self.db.total_xp += value
            try:
                self.roster.adjust_xp(value)
            except (AttributeError, ValueError, TypeError):
                pass
        else:
            if self.db.xp < abs(value):
                raise ValueError("Bad value passed to adjust_xp -" +
                                 " character did not have enough xp to pay for the value.")
        self.db.xp += value

    def follow(self, targ):
        if not targ.ndb.followers:
            targ.ndb.followers = []
        targ.msg("%s starts to follow you. To remove them as a follower, use 'ditch'." % self.name)
        if self not in targ.ndb.followers:
            targ.ndb.followers.append(self)
        self.msg("You start to follow %s. To stop following, use 'follow' with no arguments." % targ.name)
        self.ndb.following = targ
        
    def stop_follow(self):
        f_targ = self.ndb.following
        if not f_targ:
            return
        self.msg("You stop following %s." % f_targ.name)
        if f_targ.ndb.followers:
            f_targ.ndb.followers.remove(self)
            f_targ.msg("%s stops following you." % self.name)
        self.ndb.following = None

    def get_fakeweapon(self):
        return self.db.fakeweapon
        
    def _get_weapondata(self):
        wpndict = self.get_fakeweapon() or {}
        if wpndict:
            return wpndict
        wpn = self.db.weapon
        if not wpn:
            return wpndict
        wpndict['attack_skill'] = wpn.db.attack_skill or 'crushing melee'
        wpndict['attack_stat'] = wpn.db.attack_stat or 'dexterity'
        wpndict['damage_stat'] = wpn.db.damage_stat or 'strength'
        try:
            wpndict['weapon_damage'] = wpn.damage_bonus or 0
        except AttributeError:
            wpndict['weapon_damage'] = wpn.db.damage_bonus or 0
        wpndict['attack_type'] = wpn.db.attack_type or 'melee'
        wpndict['can_be_parried'] = wpn.db.can_be_parried or True
        wpndict['can_be_blocked'] = wpn.db.can_be_blocked or True
        wpndict['can_be_dodged'] = wpn.db.can_be_dodged or True
        wpndict['can_parry'] = wpn.db.can_parry or False
        wpndict['can_riposte'] = wpn.db.can_parry or wpn.db.can_riposte or False
        wpndict['reach'] = wpn.db.weapon_reach or 1
        wpndict['minimum_range'] = wpn.db.minimum_range or 0
        try:
            wpndict['difficulty_mod'] = wpn.difficulty_mod or 0
        except AttributeError:
            wpndict['difficulty_mod'] = wpn.db.difficulty_mod or 0
        try:
            wpndict['flat_damage'] = wpn.flat_damage or 0
        except AttributeError:
            wpndict['flat_damage'] = wpn.db.flat_damage_bonus or 0
        return wpndict

    weapondata = property(_get_weapondata)

    @property
    def weapons_hidden(self):
        """Returns True if we have a hidden weapon, false otherwise"""
        try:
            return self.weapondata['hidden_weapon']
        except (AttributeError, KeyError):
            return False

    def msg_watchlist(self, msg):
        """
        Sends a message to all players who are watching this character if
        we are not hiding from watch.
        """
        watchers = self.db.watched_by or []
        pc = self.db.player_ob
        if not pc:
            return
        if not watchers or pc.db.hide_from_watch:
            return
        for watcher in watchers:
            spam = watcher.ndb.journal_spam or []
            if self not in spam:
                watcher.msg(msg)
                spam.append(self)
                watcher.ndb.journal_spam = spam

    def _get_max_support(self):
        try:
            dompc = self.db.player_ob.Dominion
            total = 0
            for member in dompc.memberships.filter(deguilded=False):
                total += member.pool_share
            for ren in dompc.renown.all():
                total += ren.level
            return total
        except (TypeError, AttributeError, ValueError):
            return 0
    max_support = property(_get_max_support)

    @property
    def guards(self):
        return self.db.assigned_guards or []

    @property
    def num_guards(self):
        return sum(ob.quantity for ob in self.guards)

    @property
    def present_guards(self):
        return [ob for ob in self.guards if ob.location == self.location]

    @property
    def num_armed_guards(self):
        try:
            return sum([ob.num_armed_guards for ob in self.present_guards])
        except TypeError:
            return 0

    @property
    def max_guards(self):
        try:
            return 15 - (self.db.social_rank or 10)
        except TypeError:
            return 5

    def get_directions(self, room):
        """
        Uses the ObjectDB manager and repeated related_set calls in order
        to find the exit in the current room that directly points to it.
        """
        loc = self.location
        if not loc:
            return
        x_ori = loc.db.x_coord
        y_ori = loc.db.y_coord
        x_dest = room.db.x_coord
        y_dest = room.db.y_coord
        check_exits = []
        try:
            x = x_dest - x_ori
            y = y_dest - y_ori
            dest = ""
            if y > 0:
                dest += "north"
            if y < 0:
                dest += "south"
            check_exits.append(dest)
            if x > 0:
                dest += "east"
                check_exits.append("east")
            if x < 0:
                dest += "west"
                check_exits.append("west")
            check_exits.insert(0, dest)
            for dirname in check_exits:
                if loc.locations_set.filter(db_key__iexact=dirname):
                    return "{c" + dirname + "{n"
            dest = "{c" + dest + "{n roughly. Please use '{w@map{n' to determine an exact route"
        except (AttributeError, TypeError, ValueError):
            import traceback
            print "Error in using directions for rooms: %s, %s" % (loc.id, room.id)
            print "origin is (%s,%s), destination is (%s, %s)" % (x_ori, y_ori, x_dest, y_dest)
            traceback.print_exc()
            self.msg("Rooms not properly set up for @directions. Logging error.")
            return
        # try to find it through traversal
        base_query = "db_destination_id"
        exit_name = []
        iterations = 0
        # anything beyond 10 squares becomes extremely lengthy
        max_iter = 5
        while not exit_name and iterations < max_iter:
            q_add = "db_destination__locations_set__" * iterations
            query = q_add + base_query
            filter_dict = {query: room.id}
            exit_name = loc.locations_set.filter(**filter_dict)[0:1]
            iterations += 1
        if not exit_name:
            return "{c" + dest + "{n"
        return "{c" + str(exit_name[0]) + "{n"

    def at_post_puppet(self):
        """
        Called just after puppeting has completed.

        :type self: DefaultCharacter
        """
        watched_by = self.db.watched_by or []
        super(Character, self).at_post_puppet()
        try:
            if self.db.pending_messengers:
                self.messenger_notification(2)
        except (AttributeError, ValueError, TypeError):
            import traceback
            traceback.print_exc()
        if self.db.player_ob and not self.db.player_ob.db.hide_from_watch:
            for watcher in watched_by:
                watcher.msg("{wA player you are watching, {c%s{w, has entered the game.{n" % self.key)
        guards = self.guards
        for guard in guards:
            if guard.discreet:
                continue
            docked_location = guard.db.docked
            if docked_location and docked_location == self.location:
                guard.summon()

    def at_post_unpuppet(self, player, session=None):
        """
        We stove away the character when the player goes ooc/logs off,
        otherwise the character object will remain in the room also after the
        player logged off ("headless", so to say).

        :type self: DefaultCharacter
        :type player: Player
        :type session: Session
        """
        super(Character, self).at_post_unpuppet(player, session)
        watched_by = self.db.watched_by or []
        if self.db.player_ob and not self.db.player_ob.db.hide_from_watch:
            for watcher in watched_by:
                watcher.msg("{wA player you are watching, {c%s{w, has left the game.{n" % self.key)
        table = self.db.sitting_at_table
        if table:
            table.leave(self)
        guards = self.db.assigned_guards or []
        for guard in guards:
            try:
                if guard.location:
                    guard.dismiss()
            except AttributeError:
                continue

    def messenger_notification(self, num_times=1):
        from twisted.internet import reactor
        num_times -= 1
        if self.db.pending_messengers:
            # send messages to our player object so even an @ooc player will see them
            player = self.db.player_ob
            if not player or not player.is_connected:
                return
            player.msg("{mYou have %s messengers waiting.{n" % len(self.db.pending_messengers))
            self.msg("(To receive a messenger, type 'receive messenger')")
            if num_times > 0:
                reactor.callLater(600, self.messenger_notification, num_times)
            else:
                # after the first one, we only tell them once an hour
                reactor.callLater(3600, self.messenger_notification, num_times)

    @property
    def portrait(self):
        try:
            return self.roster.profile_picture
        except AttributeError:
            return None

    def get_absolute_url(self):
        from django.core.urlresolvers import reverse
        return reverse('character:sheet', kwargs={'object_id': self.id})

    @property
    def combat_data(self):
        from typeclasses.scripts.combat.combatant import CharacterCombatData
        return CharacterCombatData(self, None)

    def view_stats(self, viewer, combat=False):
        from commands.commands.roster import display_attributes, display_skills
        display_attributes(viewer, self)
        display_skills(viewer, self)
        if combat:
            viewer.msg(self.combat_data.display_stats())
