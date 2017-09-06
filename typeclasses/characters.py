"""
Characters

Characters are (by default) Objects setup to be puppeted by Players.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""
from evennia.objects.objects import DefaultCharacter
from typeclasses.mixins import MsgMixins, ObjectMixins, NameMixins
from world.msgs.messagehandler import MessageHandler
from world.msgs.languagehandler import LanguageHandler
from evennia.utils.utils import lazy_property, variable_from_module
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
        self.db.gender = "Female"
        self.db.age = 20
        self.db.concept = "None"
        self.db.fealty = "None"
        self.db.marital_status = "single"
        self.db.family = "None"
        self.db.dice_string = "Default Dicestring"
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
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

    @lazy_property
    def languages(self):
        return LanguageHandler(self)

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
            self.msg(self.at_look(self.location))
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
        if self.ndb.following and self.ndb.following.location != self.location:
            self.stop_follow()
        if self.db.room_title:
            self.attributes.remove("room_title")

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
        # desc is our current appearance, can be fake. self.perm_desc is 'true' form
        desc = self.desc
        # to do: check to see through disguises
        if strip_ansi:
            try:
                from evennia.utils.ansi import parse_ansi
                desc = parse_ansi(desc, strip_ansi=True)
            except (AttributeError, ValueError, TypeError, UnicodeDecodeError):
                pass
        script = self.appearance_script
        if desc:
            extras = self.return_extras(pobject)
            if extras:
                extras += "\n"
            string += "\n\n%s%s" % (extras, desc)
        if script:
            scent = script.db.scent
            if scent:
                string += "\n\n%s" % scent
        if health_appearance:
            string += "\n\n%s" % health_appearance
        string += self.return_contents(pobject, detailed, strip_ansi=strip_ansi)
        return string

    @property
    def species(self):
        return self.db.species or "Human"

    @property
    def appearance_script(self):
        scripts = self.scripts.get("Appearance")
        if scripts:
            return scripts[0]

    def return_extras(self, pobject):
        """
        Return a string from glancing at us
        :param pobject: Character
        :return:
        """
        mask = self.db.mask
        if not mask:
            hair = self.db.haircolor or ""
            eyes = self.db.eyecolor or ""
            skin = self.db.skintone or ""
            height = self.db.height or ""
            species = self.species
            gender = self.db.gender or ""
            age = self.db.age
        else:
            hair = mask.db.haircolor or "--"
            eyes = mask.db.eyecolor or "--"
            skin = mask.db.skintone or "--"
            height = mask.db.height or "--"
            species = mask.db.species or "--"
            gender = mask.db.gender or "--"
            age = mask.db.age or "--"
        hair = hair.capitalize()
        eyes = eyes.capitalize()
        skin = skin.capitalize()
        gender = gender.capitalize()
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
        if self.db.health_status == "dead":
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
            print("<<ERROR>>: Error when importing death cmdset: %s" % err)
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
            print("<<ERROR>>: Error when importing mobile cmdset: %s" % err)
        # we'll also be asleep when we're dead, so that we're resurrected unconscious if we're brought back
        self.fall_asleep(uncon=True, quiet=True)

    def fall_asleep(self, uncon=False, quiet=False, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if uncon:
            self.db.sleep_status = "unconscious"
        else:
            self.db.sleep_status = "asleep"
        if self.location and not quiet:
            self.location.msg_contents("%s falls %s." % (self.name, self.db.sleep_status))
        try:
            from commands.cmdsets import sleep
            cmds = sleep.SleepCmdSet
            if cmds.key not in [ob.key for ob in self.cmdset.all()]:
                self.cmdset.add(cmds, permanent=True)
        except Exception as err:
            print("<<ERROR>>: Error when importing sleep cmdset: %s" % err)

    @property
    def conscious(self):
        return ((self.db.sleep_status != "unconscious" and self.db.sleep_status != "asleep")
                and self.db.health_status != "dead")

    def wake_up(self, quiet=False):
        """
        Wakes up.
        """
        if self.db.health_status == "dead":
            return
        if self.location:
            if not quiet and not self.conscious:
                self.location.msg_contents("%s wakes up." % self.name)
        try:
            from commands.cmdsets import sleep
            self.cmdset.delete(sleep.SleepCmdSet)
        except Exception as err:
            print("<<ERROR>>: Error when importing mobile cmdset: %s" % err)
        self.db.sleep_status = "awake"
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
        elif 0.75 < wound <= self.death_threshold:
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
        # no helping us if we're dead
        if self.db.health_status == "dead":
            return
        diff = 0 + diff_mod
        roll = do_dice_check(self, stat_list=["willpower", "stamina"], difficulty=diff)
        self.change_health(roll)
        if not free:
            self.db.last_recovery_test = time.time()
        return roll
        
    def change_health(self, amount):
        """
        Change character's health and give them feedback about it.
        """
        wound = float(abs(amount))/float(self.max_hp)
        if wound <= 0:
            wound_str = "no "
        elif wound <= 0.25:
            wound_str = "a little "
        elif wound <= 0.5:
            wound_str = "somewhat "
        elif wound <= 0.75:
            wound_str = "a lot "
        else:
            wound_str = "incredibly "
        if amount > 0:
            self.msg("You feel %sbetter." % wound_str)
        else:
            self.msg("You feel %sworse." % wound_str)
        # ignore temporary damage so we don't convert it to real
        self.real_dmg -= amount
        if self.dmg <= self.max_hp and self.db.sleep_status != "awake":
            self.wake_up()

    def sensing_check(self, difficulty=15, invis=False, allow_wake=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        if not self.conscious and not allow_wake:
            return -100
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
        return [ob for ob in self.contents if ob.db.currently_worn]
    
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
        return int(round(armor))

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
        hp += self.boss_rating * 100
        return hp

    @property
    def death_threshold(self):
        """
        Multiplier on how much higher our damage must be than our max health for us to
        roll to survive dying.

        Returns:
            float: Multiplier before death checks happen
        """
        return 1.25
    
    def _get_current_damage(self):
        """Returns how much damage we've taken."""
        dmg = self.db.damage or 0
        dmg += self.temp_dmg
        return dmg

    def _set_current_damage(self, dmg):
        if dmg < 1:
            dmg = 0
        self.db.damage = dmg
        self.start_recovery_script()

    @property
    def temp_dmg(self):
        if self.ndb.temp_dmg is None:
            self.ndb.temp_dmg = 0
        return self.ndb.temp_dmg

    @temp_dmg.setter
    def temp_dmg(self, val):
        self.ndb.temp_dmg = val

    @property
    def real_dmg(self):
        return self.db.damage or 0

    @real_dmg.setter
    def real_dmg(self, dmg):
        self._set_current_damage(dmg)

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
    
    worn = property(_get_worn)
    
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
            try:
                f_targ.ndb.followers.remove(self)
                f_targ.msg("%s stops following you." % self.name)
            except (ValueError, TypeError, AttributeError):
                pass
        self.ndb.following = None

    def get_fakeweapon(self):
        return self.db.fakeweapon
        
    def _get_weapondata(self):
        wpndict = self.get_fakeweapon() or {}
        wpn = self.db.weapon
        if wpn:
            wpndict['attack_skill'] = wpn.db.attack_skill or 'crushing melee'
            wpndict['attack_stat'] = wpn.db.attack_stat or 'dexterity'
            wpndict['damage_stat'] = wpn.db.damage_stat or 'strength'
            try:
                wpndict['weapon_damage'] = wpn.damage_bonus or 0
            except AttributeError:
                wpndict['weapon_damage'] = wpn.db.damage_bonus or 0
            wpndict['attack_type'] = wpn.db.attack_type or 'melee'
            wpndict['can_be_parried'] = wpn.db.can_be_parried
            wpndict['can_be_blocked'] = wpn.db.can_be_blocked
            wpndict['can_be_dodged'] = wpn.db.can_be_dodged
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
        boss_rating = self.boss_rating
        if boss_rating:
            wpndict['weapon_damage'] = wpndict.get('weapon_damage', 1) + boss_rating
            wpndict['flat_damage'] = wpndict.get('flat_damage', 0) + boss_rating * 10
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
        pc = self.player_ob
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
                
    @property
    def social_value(self):
        """Value used for calculating support based on social stats/skills
        
            returns: int
        """
        total = 0
        try:
            from world.stats_and_skills import SOCIAL_SKILLS
            total += self.db.charm * 3
            total += self.db.intellect
            total += self.db.command
            total += self.db.composure
            skills = self.db.skills
            total += sum(skills.get(attr, 0) for attr in SOCIAL_SKILLS) * 2
            return total / 3
        except (TypeError, ValueError, AttributeError):
            return total / 3

    def _get_max_support(self):
        try:
            dompc = self.player_ob.Dominion
            remaining = 0
            for member in dompc.memberships.filter(deguilded=False):
                remaining += member.pool_share
            for ren in dompc.renown.all():
                remaining += ren.level
        except (TypeError, AttributeError, ValueError):
            return 0
        interval = self.social_value
        multiplier = 1.0
        total = 0
        if interval <= 0:
            return 0
        while multiplier > 0:
            if interval >= remaining:
                total += remaining * multiplier
                return int(total)
            total += interval * multiplier
            multiplier -= 0.25
            remaining -= interval
        return int(total)
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
            print("Error in using directions for rooms: %s, %s" % (loc.id, room.id))
            print("origin is (%s,%s), destination is (%s, %s)" % (x_ori, y_ori, x_dest, y_dest))
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

        :type self: Character
        """

        super(Character, self).at_post_puppet()
        try:
            self.messages.messenger_notification(2, force=True)
        except (AttributeError, ValueError, TypeError):
            import traceback
            traceback.print_exc()

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

        :type self: Character
        :type player: Player
        :type session: Session
        """
        super(Character, self).at_post_unpuppet(player, session)
        if not self.sessions.count():
            table = self.db.sitting_at_table
            if table:
                table.leave(self)
            guards = self.db.assigned_guards or []
            for guard in guards:
                try:
                    if guard.location and 'persistent_guard' not in guard.tags.all():
                        guard.dismiss()
                except AttributeError:
                    continue

    @property
    def portrait(self):
        from web.character.models import Photo
        try:
            return self.roster.profile_picture
        except (AttributeError, Photo.DoesNotExist):
            return None

    def get_absolute_url(self):
        from django.core.urlresolvers import reverse
        return reverse('character:sheet', kwargs={'object_id': self.id})

    @lazy_property
    def combat(self):
        from typeclasses.scripts.combat.combatant import CombatHandler
        return CombatHandler(self, None)

    def view_stats(self, viewer, combat=False):
        from commands.commands.roster import display_stats, display_skills, display_abilities
        display_stats(viewer, self)
        display_skills(viewer, self)
        display_abilities(viewer, self)
        if combat:
            viewer.msg(self.combat.display_stats())

    @property
    def posecount(self):
        return self.db.pose_count or 0

    @posecount.setter
    def posecount(self, val):
        self.db.pose_count = val

    def announce_move_from(self, destination, msg=None, mapping=None):
        """
        Called if the move is to be announced. This is
        called while we are still standing in the old
        location.
        Args:
            destination (Object): The place we are going to.
            msg (str, optional): a replacement message.
            mapping (dict, optional): additional mapping objects.
        """
        def format_string(viewer):
            if msg:
                return msg
            if secret:
                return "%s is leaving." % self.get_display_name(viewer)
            else:
                return "%s is leaving, heading for %s." % (self.get_display_name(viewer),
                                                           destination.get_display_name(viewer))
        if not self.location:
            return
        secret = False
        if mapping:
            secret = mapping.get('secret', False)
        for obj in self.location.contents:
            if obj != self:
                string = format_string(obj)
                obj.msg(string)

    def announce_move_to(self, source_location, msg=None, mapping=None):
        """
        Called after the move if the move was not quiet. At this point
        we are standing in the new location.

        Args:
            source_location (Object): The place we came from
            msg (str, optional): the replacement message if location.
            mapping (dict, optional): additional mapping objects.

        You can override this method and call its parent with a
        message to simply change the default message.  In the string,
        you can use the following as mappings (between braces):
            object: the object which is moving.
            exit: the exit from which the object is moving (if found).
            origin: the location of the object before the move.
            destination: the location of the object after moving.

        """
        if not source_location and self.location.has_player:
            # This was created from nowhere and added to a player's
            # inventory; it's probably the result of a create command.
            string = "You now have %s in your possession." % self.get_display_name(self.location)
            self.location.msg(string)
            return

        secret = False
        if mapping:
            secret = mapping.get('secret', False)

        def format_string(viewer):
            if msg:
                return msg
            if secret:
                return "%s arrives." % self.get_display_name(viewer)
            else:
                from_str = " from %s" % source_location.get_display_name(viewer) if source_location else ""
                return "%s arrives%s." % (self.get_display_name(viewer), from_str)

        for obj in self.location.contents:
            if obj != self:
                string = format_string(obj)
                obj.msg(string)

    @property
    def can_crit(self):
        try:
            if self.roster.roster.name == "Active":
                return True
            else:
                return False
        except AttributeError:
            return False

    @property
    def titles(self):
        full_titles = self.db.titles or []
        return ", ".join(str(ob) for ob in full_titles)

    @property
    def is_npc(self):
        if self.tags.get("npc"):
            return True
        try:
            if self.roster.roster.name == "Unavailable":
                return True
        except AttributeError:
            pass
        return False

    @property
    def attackable(self):
        return not bool(self.tags.get("unattackable"))

    @property
    def boss_rating(self):
        try:
            return int(self.db.boss_rating)
        except (TypeError, ValueError):
            return 0

    @boss_rating.setter
    def boss_rating(self, value):
        self.db.boss_rating = value

    @property
    def sleepless(self):
        """Cannot fall unconscious - undead, etc"""
        return bool(self.tags.get("sleepless"))

    @property
    def defense_modifier(self):
        return self.db.defense_modifier or 0

    @defense_modifier.setter
    def defense_modifier(self, value):
        self.db.defense_modifier = value

    @property
    def attack_modifier(self):
        base = self.db.attack_modifier or 0
        return base + (self.boss_rating * 10)

    @attack_modifier.setter
    def attack_modifier(self, value):
        self.db.attack_modifier = value

    def search(self,  # type: Character
               searchdata, global_search=False, use_nicks=True, typeclass=None, location=None,
               attribute_name=None, quiet=False, exact=False, candidates=None, nofound_string=None,
               multimatch_string=None, use_dbref=True):
        from django.conf import settings
        # if we're staff, we just use the regular search method
        if self.check_permstring("builders"):
            return super(Character, self).search(searchdata, global_search=global_search, use_nicks=use_nicks,
                                                 typeclass=typeclass, location=location,
                                                 attribute_name=attribute_name, quiet=quiet, exact=exact,
                                                 candidates=candidates, nofound_string=nofound_string,
                                                 multimatch_string=multimatch_string, use_dbref=use_dbref)
        # we're not staff. We get search results, then throw out matches of people wearing masks that were by their key
        results = super(Character, self).search(searchdata, global_search=global_search, use_nicks=use_nicks,
                                                typeclass=typeclass, location=location, attribute_name=attribute_name,
                                                quiet=True, exact=exact, candidates=candidates,
                                                nofound_string=nofound_string, multimatch_string=multimatch_string,
                                                use_dbref=use_dbref)
        # we prune results of keys for masked (false_name) objects in results
        results = [ob for ob in results if not ob.db.false_name or searchdata.lower() != ob.key.lower()]
        # quiet means that messaging is handled elsewhere
        if quiet:
            return results
        # call the _AT_SEARCH_RESULT func to transform our results and send messages
        _AT_SEARCH_RESULT = variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))
        return _AT_SEARCH_RESULT(results, self, query=searchdata,  nofound_string=nofound_string,
                                 multimatch_string=multimatch_string)

    def can_be_trained_by(self, trainer):
        """
        Checks if we can be trained by trainer. If False, send a message to trainer and let them know why. The default
        implementation will just return True, but this is overridden in Retainers, for example.

        Args:
            trainer: Character to check training

        Returns:
            True if we can be trained, False otherwise.
        """
        if self.db.trainer:
            trainer.msg("They have already been trained.")
            return False
        return True

    def post_training(self, trainer, trainer_msg="", targ_msg=""):
        """
        Handles bookkeeping after this character is trained.

        Args:
            trainer: Character that trained us.
            trainer_msg (str): Message to send to trainer
            targ_msg (str): Message to send to this Character

        Returns:
            True if everything went off. Used for trying to catch extremely elusive caching errors.
        """
        from server.utils.arx_utils import trainer_diagnostics
        currently_training = trainer.db.currently_training or []
        # num_trained is redundancy to attempt to prevent cache errors.
        num_trained = trainer.db.num_trained or len(currently_training)
        if num_trained < len(currently_training):
            num_trained = len(currently_training)
        num_trained += 1
        self.db.trainer = trainer
        currently_training.append(self)
        trainer.db.currently_training = currently_training
        trainer.db.num_trained = num_trained
        if trainer_msg:
            trainer.msg(trainer_msg)
        if targ_msg:
            self.msg(targ_msg)
        print "Character.post_training call: %s" % trainer_diagnostics(trainer)
        return True

    def show_online(self, caller, check_puppet=True):
        """

        Args:
            caller: Player who is checking to see if they can see us online
            check_puppet: Whether the Character needs an active puppet to show as online

        Returns:
            True if we're online and the player has privileges to see us. False otherwise
        """
        if check_puppet:
            if not self.sessions.all():
                return False
            player = self.player
        else:
            player = self.player_ob
        if not player:
            return False
        if not player.db.hide_from_watch:
            return True
        if caller.check_permstring("builders"):
            return True
        # we're hiding from watch and caller is not staff, so they don't see us online
        return False

    @property
    def player(self):
        return self.account

    @player.setter
    def player(self, value):
        self.account = value
