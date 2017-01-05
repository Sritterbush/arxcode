"""
Combat Manager. This is where the magic happens. And by magic,
we mean characters dying, most likely due to vile sorcery.

The Combat Manager is invoked by a character starting combat
with the +fight command. Anyone set up as a defender of either
of those two characters is pulled into combat automatically.
Otherwise, players can enter into combat that is in progress
with the appropriate defend command, or by a +fight command
to attack one of the belligerent parties.

Turn based combat has the obvious drawback that someone who
is AFK or deliberately not taking their turn completely halts
the action. There isn't an easy solution to this. GMs will
have tools to skip someone's turn or remove them from combat,
and a majority vote by all parties can cause a turn to proceed
even when someone has not taken their turn.

Phase 1 is the setup phase. This phase is designed to have a
pause before deciding actions so that other people can join
combat. Characters who join in later phases will not receive
a combat turn, and will be added to the fight in the following
turn. Phase 1 is also when players can vote to end the combat.
Every player MUST enter a command to continue for combat to
proceed. There will never be a case where a character can be
AFK and in combat. It is possible to vote a character out of
combat due to AFK in order for things to proceed. Immediately
after every current combatant selects to continue, the participants
are locked in and we go to phase 2.

Phase 2 is the action phase. Initiative is rolled, and then
each player must take an action when it is their turn. 'pass'
is a valid action. Each combat action is resolved during the
character's turn. Characters who are incapacitated lose their
action. Characters who join combat during Phase 2 must wait
for the following turn to be allowed a legal action.
"""

from typeclasses.scripts.scripts import Script as BaseScript
from evennia.utils.utils import fill, dedent, list_to_string
from server.utils.prettytable import PrettyTable
from commands.cmdsets.combat import CombatCmdSet
from world.stats_and_skills import do_dice_check
from twisted.internet import reactor

from operator import attrgetter
import time
import combat_settings
from combat_settings import CombatError
from combatant import CharacterCombatData
from world.dominion.battle import Formation


COMBAT_INTRO = combat_settings.COMBAT_INTRO
PHASE1_INTRO = combat_settings.PHASE1_INTRO
PHASE2_INTRO = combat_settings.PHASE2_INTRO
MAX_AFK = combat_settings.MAX_AFK
ROUND_DELAY = combat_settings.ROUND_DELAY


class CharFormation(Formation):
    pass
        

class CombatManager(BaseScript):
    """
    Players are added via add_combatant or add_observer. These are invoked
    by commands in normal commandsets. Characters added receive the combat
    commandset, which give commands that invoke the other methods.
    
    Turns proceed based on every combatant submitting an action, which is a
    dictionary of combatant IDs to their actions. Dead characters are moved
    to observer status, incapacitated characters are moved to a special
    list to denote that they're still in combat but can take no action.
    Attribute references to the combat manager script are stored in the room
    location under room.ndb.combat_manager, and inside each character in the
    combat under character.ndb.combat_manager.
    Note that all the data for the combat manager is stored inside non-database
    attributes, since it is designed to be non-persistent. If there's a server
    reset, combat will end.
    Non-database attributes:
    self.ndb.combatants - list of everyone active in the fight. If it's empty, combat ends
    self.ndb.observers - People passively watching the fight
    self.ndb.incapacitated - People who are too injured to act, but still can be attacked
    self.ndb.fighter_data - CharacterCombatData for each combatant. dict with character.id as keys
    self.ndb.combat_location - room where script happens
    self.ndb.initiative_list - CharacterCombatData for each fighter. incapacitated chars aren't in it
    self.ndb.active_character - Current turn of player in phase 2. Not used in phase 1
    self.ndb.phase - Phase 1 or 2. 1 is setup, 2 is resolution
    self.ndb.afk_check - anyone we're checking to see if they're afk
    self.ndb.votes_to_end - anyone voting to end combat
    self.ndb.flee_success - Those who can run this turn
    self.ndb.fleeing - Those intending to try to run

    Admin Methods:
    self.msg() - Message to all combatants/observers.
    self.end_combat() - shut down the fight
    self.next_character_turn() - move to next character in initiative list in phase 2
    self.add_observer(character)
    self.add_combatant(character)
    self.remove_combatant(character)
    self.move_to_observer(character)
    """

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "CombatManager"
        self.desc = "Manages the combat state for a group of combatants"
        # Not persistent because if someone goes LD, we don't want them reconnecting
        # in combat a week later with no way to leave it. Intentionally quitting out
        # to avoid combat will just need to be corrected with rules enforcement.
        self.persistent = False
        self.interval = ROUND_DELAY
        self.start_delay = True
        self.ndb.combatants = []  # those actively involved in fight
        self.ndb.observers = []  # sent combat data, but cannot act
        self.ndb.incapacitated = []  # in combat, but with few valid actions
        self.ndb.fighter_data = {}  # dict of char.id to CharacterCombatData
        self.ndb.combat_location = self.obj  # room of the fight
        self.ndb.initiative_list = []  # CharacterCombatData of characters in order of initiative
        self.ndb.active_character = None  # who is currently acting during phase 2
        self.ndb.phase = 1
        self.ndb.afk_check = []  # characters who are flagged afk until they take an action
        self.ndb.votes_to_end = []  # if all characters vote yes, combat ends
        self.ndb.flee_success = []  # if we're here, the character is allowed to flee on their turn
        self.ndb.fleeing = []  # if we're here, they're attempting to flee but haven't rolled yet
        self.ndb.lethal = not self.obj.tags.get("nonlethal_combat")
        self.ndb.max_rounds = 250
        self.ndb.rounds = 0
        # to ensure proper shutdown, prevent some timing errors
        self.ndb.shutting_down = False
        self.ndb.status_table = None

    def at_start(self):
        pass

    def at_repeat(self):
        # reset the script timers
        if self.ndb.shutting_down:
            return
        # proceed to combat
        if self.ndb.phase == 1:
            self.ready_check()
        self.display_phase_status_to_all()

    def get_fighter_data(self, f_id):
        return self.ndb.fighter_data.get(f_id, None)
    
    def is_valid(self):
        """
        Check if still has combatants. Incapacitated characters are still
        combatants, just with very limited options - they can either pass
        turn or vote to end the fight. The fight ends when all combatants
        either pass they turn or choose to end. Players can be forced out
        of active combat if they are AFK, moved to observer status.
        """
        if self.ndb.shutting_down:
            return False
        if self.ndb.combatants:
            return True
        return False

    # ----Methods for passing messages to characters-------------
    @staticmethod
    def send_intro_message(character, combatant=True):
        """
        Displays intro message of combat to character
        """
        if not combatant:
            msg = fill("{mYou are now in observer mode for a fight. {n" +
                       "Most combat commands will not function. To " +
                       "join the fight, use the {w+fight{n command.")
        else:
            msg = "{rEntering combat mode.{n\n"
            msg += "\n\n" + fill(COMBAT_INTRO)
        character.msg(msg)
        return

    @staticmethod
    def phase_1_intro(character):
        """
        Displays info about phase 1 to character
        """
        character.msg(PHASE1_INTRO)

    @staticmethod
    def phase_2_intro(character):
        """
        Displays info about phase 2 to character
        """
        character.msg(PHASE2_INTRO)

    def display_phase_status(self, character, disp_intro=True):
        """
        Gives message based on the current combat phase to character.cmdset
        In phase 1, just list combatants and observers, anyone marked AFK,
        dead, whatever, and any votes to end.
        In phase 2, list initiative order and who has the current action.
        """
        if self.ndb.phase == 1:
            if disp_intro:
                self.phase_1_intro(character)
            character.msg("{wCurrent combatants:{n %s" % list_to_string(self.ndb.combatants))
            character.msg(str(self.ndb.status_table))
            return
        if self.ndb.phase == 2:
            if disp_intro:
                self.phase_2_intro(character)
            if self.ndb.active_character:
                character.msg("{wIt is {c%s's {wturn to act.{n" % self.ndb.active_character.name)
                character.msg(str(self.ndb.status_table))
            return

    def build_status_table(self):
        table = PrettyTable(["{wName{n", "{wDamage{n", "{wFatigue{n", "{wAction{n", "{wReady?{n"])
        for char in self.ndb.combatants:
            com = self.ndb.fighter_data.get(char.id, None)
            if not com:
                continue
            name = com.name
            dmg = str(char.db.damage)
            fatigue = str(com.fatigue_penalty)
            action = str(com.queued_action)
            rdy = str(com.ready)
            table.add_row([name, dmg, fatigue, action, rdy])
        self.ndb.status_table = table

    def display_phase_status_to_all(self, intro=False):
        msglist = self.ndb.combatants + self.ndb.observers
        self.build_status_table()
        for ob in msglist:
            self.display_phase_status(ob, disp_intro=intro)
    
    def msg(self, message, exclude=None, options=None):
        """
        Sends a message to all objects in combat/observers except for
        individuals in the exclude list.
        """
        # those in incapacitated list should still be in combatants also
        msglist = self.ndb.combatants + self.ndb.observers
        if not exclude:
            exclude = []
        msglist = [ob for ob in msglist if ob not in exclude]
        for ob in msglist:
            mymsg = message
            ob.msg(mymsg, options)

    # ------------------------------------------------------------------
    # -----Methods for handling combat actions--------------------------
    def do_attack(self, attacker, target, attack_penalty=0, defense_penalty=0,
                  dmg_penalty=0, allow_botch=True, free_attack=False):
        """
        Processes an attack between a single attacker and a defender. This
        method is caller by the combat command set, via an attack command.
        Mods are determined by switches in the attack command or other
        attributes set in the attacker, target, or the environment when
        the attack command is used. By the time we're here, the final target
        has been determined and the mods have been calculated. All penalties
        are positive numbers as they increase the difficulty of checks. Bonuses
        are negative values, as they reduce difficulties to 0 or less.
        """
        if self.ndb.phase != 2:
            raise CombatError("Attempted to attack in wrong phase.")
        self.remove_afk(attacker)
        fite = self.ndb.fighter_data
        a_fite = fite[attacker.id]
        weapon = a_fite.weapon
        d_fite = fite[target.id]
        # modifiers from our stance (aggressive, defensive, etc)
        attack_penalty += combat_settings.STANCE_ATK_MOD[a_fite.stance]
        defense_penalty += combat_settings.STANCE_DEF_MOD[d_fite.stance]
        # modifier if we're covering anyone's retreat
        if a_fite.covering_targs:
            attack_penalty += 5
        if d_fite.covering_targs:
            defense_penalty += 5
        a_roll = a_fite.roll_attack(d_fite, attack_penalty)
        d_roll = d_fite.roll_defense(a_fite, weapon, defense_penalty, a_roll)
        message = "%s attempts to attack %s. " % (a_fite, d_fite)
        self.msg("%s rolls %s to attack, %s rolls %s to defend." % (a_fite, a_roll, d_fite, d_roll))
        # check if we were sleeping
        awake = target.db.sleep_status or "awake"
        if awake != "awake":
            message += "%s is %s and cannot stop the attack. " % (d_fite, awake)
            d_roll = -1000   
        result = a_roll - d_roll
        # handle botches. One botch per -10
        if a_roll < 0 and result < -30 and allow_botch:
            self.msg(message, options={'roll': True})
            can_riposte = a_fite.can_be_parried and d_fite.can_riposte
            if target in self.ndb.incapacitated or awake != "awake":
                can_riposte = False
            if target not in self.ndb.incapacitated and awake == "asleep":
                target.wake_up()
            self.handle_botch(attacker, a_roll, can_riposte, target, attack_penalty, defense_penalty,
                              dmg_penalty, free_attack)
            return
        if result > -16:
            if -5 > result >= -15:
                dmgmult = 0.25
                message += "Attack barely successful."
            elif 5 > result >= -5:
                dmgmult = 0.5
                message += "Attack slightly successful."
            elif 15 > result >= 5:
                dmgmult = 0.75
                message += "Attack somewhat successful."
            else:  # 15 or higher over defense roll
                dmgmult = 1.0
                message += "Attack successful."
            self.msg(message)
            self.assign_damage(attacker, target, result, weapon, dmg_penalty, dmgmult)
        else:
            message += "%s %s the attack." % (d_fite, d_fite.last_defense_method)
            self.msg(message)
        # if we were asleep before the attack and aren't incapacitated, we wake up
        if target not in self.ndb.incapacitated and awake == "asleep":
            target.wake_up()
        if not free_attack:  # situations where a character gets a 'free' attack
            a_fite.remaining_attacks -= 1
            if a_fite.remaining_attacks <= 0:
                self.next_character_turn()

    # noinspection PyUnusedLocal
    def handle_botch(self, botcher, roll, can_riposte=True, target=None,
                     attack_penalty=0, defense_penalty=0, dmg_penalty=0, free_attack=False):
        """
        Processes the results of botching a roll.
        """
        b_fite = self.ndb.fighter_data[botcher.id]
        if can_riposte and target:
            self.msg("%s {rbotches{n their attack, leaving themselves open to a riposte." % b_fite)
            self.do_attack(target, botcher, attack_penalty, defense_penalty, dmg_penalty,
                           allow_botch=False, free_attack=True)
            if not free_attack:
                self.next_character_turn()
            return        
        b_fite.lost_turn_counter += 1
        self.msg("%s {rbotches{n their attack, losing their next turn while recovering." % b_fite)
        if not free_attack:
            b_fite.remaining_attacks -= 1
            if b_fite.remaining_attacks <= 0:
                self.next_character_turn()

    def assign_damage(self, attacker, target, roll, weapon=None, dmg_penalty=0, dmgmult=1.0):
        """
        Assigns damage after a successful attack. During this stage, all
        attempts to avoid damage entirely have failed, and not damage will
        be reduced, and its effects on the character will be explored,
        including possible death. Characters who are incapacitated are
        moved to the appropriate dictionary. Health rating is 10xsta + 10.
        Unconsciousness checks are after health rating is exceeded. When
        damage is double health rating, death checks begin. Player characters
        will always fall unconscious first, then be required to make death
        checks after further damage, with the exception of extraordinary
        situations. NPCs, on the other hand, can be killed outright.
        """
        # stuff to mitigate damage here
        fite = self.ndb.fighter_data
        a_fite = fite[attacker.id]
        d_fite = fite[target.id]
        # if damage is increased, it's pre-mitigation
        if dmgmult > 1.0:
            dmg = a_fite.roll_damage(d_fite, dmg_penalty, dmgmult)
        else:
            dmg = a_fite.roll_damage(d_fite, dmg_penalty)
        mit = d_fite.roll_mitigation(a_fite, weapon, roll)
        self.msg("%s rolled %s damage against %s's %s mitigation." % (a_fite, dmg, d_fite, mit))
        dmg -= mit
        # if damage is reduced by multiplier, it's post mitigation
        if dmgmult < 1.0:
            dmg = int(dmg * dmgmult)
        if dmg <= 0:
            message = "%s fails to inflict any harm on %s." % (a_fite, d_fite)
            self.msg(message, options={'roll': True})
            return
        # max hp is (stamina * 10) + 10
        max_hp = target.max_hp
        wound = float(dmg)/float(max_hp)
        if wound <= 0.1:
            wound_desc = "minor"
        elif 0.1 < wound <= 0.25:
            wound_desc = "moderate"
        elif 0.25 < wound <= 0.5:
            wound_desc = "serious"
        elif 0.5 < wound <= 0.75:
            wound_desc = "very serious"
        elif 0.75 < wound < 2.0:
            wound_desc = "critical"
        else:
            wound_desc = "extremely critical"
        message = "%s inflicts {r%s{n damage to %s." % (a_fite, wound_desc, d_fite)
        self.obj.msg_contents(message, options={'roll': True})
        target.dmg += dmg
        grace_period = False  # one round delay between incapacitation and death for PCs
        if target.dmg > target.max_hp:
            # if we're not incapacitated, we start making checks for it
            if target not in self.ndb.incapacitated:
                # check is sta + willpower against dmg past uncon to stay conscious
                diff = target.dmg - target.max_hp
                consc_check = do_dice_check(target, stat_list=["stamina", "willpower"], skill="survival",
                                            stat_keep=True, difficulty=diff)
                self.msg("%s rolls stamina+willpower+survival against difficulty %s, getting %s." % (d_fite, diff,
                                                                                                     consc_check))
                if consc_check > 0:
                    message = "%s remains capable of fighting despite their wounds." % d_fite
                    grace_period = True  # even npc can't be killed if they make the first check
                    # we're done, so send the message for the attack
                    self.msg(message)
                else:
                    message = "%s is incapacitated from their wounds." % d_fite
                    self.incapacitate(target)
                # for PCs who were knocked unconscious this round
                if not target.db.npc and not grace_period:
                    grace_period = True  # always a one round delay before you can kill a player
                    self.msg(message)
            # PC/NPC who was already unconscious before attack, or an NPC who was knocked unconscious by our attack
            if not grace_period:  # we are allowed to kill the character
                diff = target.dmg - (2 * target.max_hp)
                if diff < 0:
                    diff = 0
                if do_dice_check(target, stat_list=["stamina", "willpower"], skill="survival",
                                 stat_keep=True, difficulty=diff) > 0:
                    message = "%s remains alive, but close to death." % d_fite
                    self.msg(message)
                    if d_fite.multiple:
                        # was incapaciated but not killed, but out of fight and now we're on another targ
                        target.db.damage = 0
                elif not d_fite.multiple:
                    self.msg(message)
                    if self.ndb.lethal:
                        target.death_process()
                    else:
                        target.db.damage = 0
                    self.remove_combatant(target)
                else:
                    if self.ndb.lethal:
                        target.death_process()
                    else:
                        self.incapacitate(target)
                    
    def incapacitate(self, character):
        """
        Character falls unconscious due to wounds.
        """
        ifite = self.ndb.fighter_data[character.id]   
        if not ifite.multiple:
            self.ndb.incapacitated.append(character)        
            ifite.status = "incapacitated"
            if hasattr(character, "fall_asleep"):
                character.fall_asleep(uncon=True)
        else:
            ifite.num -= 1
            if ifite.num <= 0:
                self.remove_combatant(character)
            self.msg("There are %s remaining." % ifite.num)

    def wake_up(self, character):
        """
        Called by character.wake_up() to update us in combat. When
        trying to wake up a character, calls should go there, not
        here.
        """
        if character in self.ndb.incapacitated:
            self.ndb.incapacitated.remove(character)
        self.ndb.fighter_data[character.id].status = "active"
        
    def do_flank(self, attacker, target, sneaking=False, invis=False, attack_guard=True):
        """
        Attempts to circle around a character. If successful, we get an
        attack with a bonus.
        """
        self.remove_afk(attacker)
        defenders = self.get_defenders(target)
        message = "%s attempts to move around %s to attack them while they are vulnerable. " % (attacker.name,
                                                                                                target.name)
        if defenders:
            # guards, have to go through them first
            for guard in defenders:
                g_fite = self.ndb.fighter_data[guard.id]
                if g_fite.sense_ambush(attacker, sneaking, invis) > 0:
                    if not attack_guard:
                        message += "%s sees them, and they back off." % guard.name
                        self.msg(message)
                        self.next_character_turn()
                        return
                    message += "%s stops %s but is attacked." % (guard.name, attacker.name)
                    self.msg(message)
                    def_pen = -5 + combat_settings.STANCE_DEF_MOD[g_fite.stance]
                    self.do_attack(attacker, guard, attack_penalty=5, defense_penalty=def_pen)
                    return
        t_fite = self.ndb.fighter_data[target.id]
        if t_fite.sense_ambush(attacker, sneaking, invis) > 0:
            message += "%s moves in time to not be vulnerable." % target
            self.msg(message)
            def_pen = -5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
            self.do_attack(attacker, target, attack_penalty=5, defense_penalty=def_pen)
            return
        message += "They succeed."
        self.msg(message)
        def_pen = 5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
        self.do_attack(attacker, target, attack_penalty=-5, defense_penalty=def_pen)

    def check_char_active(self, character):
        """
        Returns True if the character is in our fighter data
        and has a status of True, False otherwise.
        """
        try:
            g_fite = self.ndb.fighter_data[character.id]
            if g_fite.status == "active":
                if character.location != self.obj:
                    del self.ndb.fighter_data[character.id]
                    return False
                if not character.conscious:
                    return False
                return True
        except KeyError:
            return False

    def do_pass(self, character):
        """
        Passes a combat turn for character. If it's their turn, next character goes.
        If it's not their turn, remove them from initiative list if they're in there
        so they don't get a turn when it comes up.
        """
        self.remove_afk(character)
        self.msg("%s passes their turn." % character.name)
        if self.ndb.active_character == character:
            self.next_character_turn()
            return
        c_data = self.ndb.fighter_data.get(character.id, None)
        if c_data in self.ndb.initiative_list:
            self.ndb.initiative_list.remove(c_data)

    def do_flee(self, character, exit_obj):
        """
        Character attempts to flee from combat. If successful, they are
        removed from combat and leave the room. Because of the relatively
        unlimited travel system we have out of combat in Arx, we want to
        restrict movement immediately at the start of combat, as otherwise
        simply leaving is trivial. Currently we don't support combat with
        characters in other spaces, and require a new combat to start every
        time you chase someone down in some extended chase scene. This may
        not be the best implementation, but it's what we're going with for
        now.
        Flee works by flagging the character as attempting to flee. They're
        added to an attempting to flee list. If someone stops them, they're
        removed from the list. Executing the command when already in the
        list will complete it successfully.
        """
        self.remove_afk(character)
        if self.ndb.fighter_data[character.id].covering_targs:
            character.msg("You cannot attempt to run while covering others' retreat.")
            character.msg("Stop covering them first if you wish to try to run.")
            return
        if character not in self.ndb.flee_success:
            if character in self.ndb.fleeing:
                character.msg("You are already attempting to flee. If no one stops you, executing "
                              "flee next turn will let you get away.")
                return
            self.ndb.fleeing.append(character)
            character.msg("If no one is able to stop you, executing flee next turn will let you run away.")
            character.msg("Attempting to flee does not take your action this turn. You may still take an action.")
            self.msg("%s begins to try to withdraw from combat." % character.name, exclude=[character])
            self.get_fighter_data(character.id).flee_exit = exit_obj
            return
        # we can flee for the hills
        if not exit_obj.access(character, 'traverse'):
            character.msg("You are not permitted to flee that way.")
            return
        # this is the command that exit_obj commands use
        exit_obj.at_traverse(character, exit_obj.destination)
        self.msg("%s has fled from combat." % character.name)
        self.remove_combatant(character)
  
    def do_stop_flee(self, character, target):
        """
        Try to stop a character from fleeing. Lists of who is stopping who from running
        are all stored in lists inside the CombataData objects for every character
        in the fighter_data dict. Whether attempts to stop players from running works
        is determined at the start of each round when initiative is rolled. The person
        attempting to flee must evade every person attempting to stop them.
        """
        self.remove_afk(character)
        a_fite = self.ndb.fighter_data[character.id]
        t_fite = self.ndb.fighter_data[target.id]
        if a_fite.block_flee == target:
            character.msg("You are already attempting to stop them from fleeing.")
            return
        if target in a_fite.covering_targs:
            character.msg("It makes no sense to try to stop the retreat of someone you are covering.")
            return
        # check who we're currently blocking. we're switching from them
        prev_blocked = a_fite.block_flee
        if prev_blocked:
            # if they're still in combat (in fighter data), we remove character from blocking them
            prev_blocked = self.ndb.fighter_data.get(prev_blocked)
            if prev_blocked:
                if character in prev_blocked.blocker_list:
                    prev_blocked.blocker_list.remove(character)
        # new person we're blocking
        a_fite.block_flee = target
        if character not in t_fite.blocker_list:
            # add character to list of people blocking them
            t_fite.blocker_list.append(character)
        self.msg("%s moves to stop %s from being able to flee." % (character.name, target.name))

    def add_defender(self, protected, guard):
        """
        add_defender can be called as a way to enter combat, so we'll
        be handling a lot of checks and messaging here. If checks are
        successful, we add the guard to combat, and set them to protect the
        protected character.
        """
        if not protected or not guard:
            return
        if protected.location != self.ndb.combat_location or guard.location != self.ndb.combat_location:
            return
        if guard.db.passive_guard:
            return
        if not guard.conscious:
            return
        if guard not in self.ndb.combatants:
            self.add_combatant(guard)
            guard.msg("{rYou enter combat to protect %s.{n" % protected.name)
        fite = self.ndb.fighter_data
        fdata = fite.get(protected.id)
        if fdata and guard not in fdata.defenders:
            fdata.defenders.append(guard)
            self.msg("%s begins protecting %s." % (guard.name, protected.name))
            self.ndb.fighter_data = fite
        fdata = fite.get(guard.id)
        if fdata:
            fdata.guarding = protected
            self.ndb.fighter_data = fite

    def remove_defender(self, protected, guard):
        """
        If guard is currently guarding protected, make him stop doing so.
        Currently not having this remove someone from a .db.defenders
        attribute - these changes are on a per combat basis, which include
        removal for temporary reasons like incapacitation.
        """
        if not protected or not guard:
            return
        fite = self.ndb.fighter_data
        fdata = fite.get(protected.id)
        if fdata and guard in fdata.defenders:
            fdata.defenders.remove(guard)
            self.msg("%s is no longer protecting %s." % (guard.name, protected.name))
            self.ndb.fighter_data = fite

    def get_defenders(self, target):
        """
        Returns list of defenders of a target.
        """
        return [ob for ob in self.ndb.fighter_data.get(target.id).defenders if self.check_char_active(ob)]

    def clear_defended_by_list(self, character):
        """
        Removes us from defending list for everyone defending us.
        """
        c_fite = self.ndb.fighter_data.get(character.id, None)
        if c_fite and c_fite.blocker_list:
            for ob in c_fite.blocker_list:
                ob = self.ndb.fighter_data.get(ob.id, None)
                if ob:
                    ob.block_flee = None
    
    def change_stance(self, character, new_stance):
        """
        Updates character's combat stance
        """
        character.msg("Stance changed to %s." % new_stance)
        fighter = self.ndb.fighter_data[character.id]
        fighter.stance = new_stance
        fighter.changed_stance = True

    def begin_covering(self, character, targlist):
        """
        Character covers the retreat of characters in targlist, represented by
        CharacterCombatData.covering_targs list and CharacterCombatData.covered_by
        list. Covered characters will succeed in fleeing automatically, but there
        are a number of restrictions. A covering character cannot be covered by
        anyone else.
        """
        c_data = self.ndb.fighter_data[character.id]
        for targ in targlist:
            if targ in c_data.covered_by:
                character.msg("%s is already covering you. You cannot cover their retreat." % targ.name)
            elif targ in c_data.covering_targs:
                character.msg("You are already covering %s's retreat." % targ.name)
            elif targ == c_data.block_flee:
                character.msg("Why would you cover the retreat of someone you are trying to catch?")
            else:
                c_data.covering_targs.append(targ)
                self.ndb.fighter_data[targ.id].covered_by.append(character)
                character.msg("You begin covering %s's retreat." % targ.name)
    
    def stop_covering(self, character, targ=None, quiet=True):
        """
        If target is not specified, remove everyone we're covering. Otherwise
        remove targ.
        """
        if not targ:
            if self.ndb.fighter_data[character.id].covering_targs:
                character.msg("You will no longer cover anyone's retreat.")
                self.ndb.fighter_data[character.id].covering_targs = []
                return
            if not quiet:
                character.msg("You aren't covering anyone's retreat currently.")
            return
        self.ndb.fighter_data[character.id].covering_targs.remove(targ)
        character.msg("You no longer cover %s's retreat." % targ.name)

    def clear_covered_by_list(self, character):
        """
        Removes us from list of anyone covering us.
        """
        c_fite = self.ndb.fighter_data.get(character.id, None)
        if c_fite and c_fite.covered_by:
            for covered_by_charob in c_fite.covered_by:
                cov_data = self.ndb.fighter_data.get(covered_by_charob.id, None)
                if cov_data and cov_data.covering_targs:
                    self.stop_covering(covered_by_charob, character)

    # ---------------------------------------------------------------------
    # -----Admin Methods for OOC character status: adding, removing, etc----
    def add_combatant(self, character, adder=None):
        """
        Adds a character to combat. The adder is the character that started
        the process, and the return message is sent to them. We return None
        if they're already fighting, since then it's likely a state change
        in defending or so on, and messages will be sent from elsewhere.
        """
        # if we're already fighting, nothing happens
        if character in self.ndb.combatants:
            if character == adder:
                return "You are already in the fight."
            cdata = self.get_fighter_data(character.id)
            if cdata and adder:
                cdata.add_foe(adder)
                adata = self.get_fighter_data(adder.id)
                if adata:
                    adata.add_foe(character)
            return "%s is already fighting." % character.key
        # check if attackable
        if not character.db.attackable:
            return "%s is not attackable." % character.key
        if character.location != self.obj:
            return "%s is not in the same room as the fight." % character.key
        # if we were in observer list, we stop since we're participant now
        self.remove_observer(character)
        self.send_intro_message(character, combatant=True)
        self.ndb.combatants.append(character)
        cdata = CharacterCombatData(character, self)
        self.ndb.fighter_data[character.id] = cdata    
        character.ndb.charcombatdata = cdata
        character.ndb.combat_manager = self
        character.cmdset.add(CombatCmdSet, permanent=False)
        if character.db.defenders:
            for ob in character.db.defenders:
                self.add_defender(character, ob)
        if character.db.assigned_guards:
            for ob in character.db.assigned_guards:
                self.add_defender(character, ob)
        reactor.callLater(1, cdata.reset)
        if character == adder:
            return "{rYou have entered combat.{n"
        # if we have an adder, they're fighting one another. set targets
        elif adder in self.ndb.combatants:
            # make sure adder is a combatant, not a GM
            adata = self.get_fighter_data(adder.id)
            if adata:
                cdata.add_foe(adder)
                cdata.prev_targ = adder
                adata.add_foe(character)
                adata.prev_targ = character
        return "You have added %s to a fight." % character.name

    def character_ready(self, character):
        """
        Character is ready to proceed from phase 1. Once all
        characters hit ready, we move to phase 2.
        """
        if character not in self.ndb.combatants:
            return
        if self.ndb.phase == 2:
            self.remove_afk(character)
            return
        if self.ndb.fighter_data[character.id].ready:
            self.ready_check(character)
            return
        self.remove_afk(character)
        self.ndb.fighter_data[character.id].ready = True
        character.msg("You have marked yourself as ready to proceed.")
        self.ready_check()

    def ready_check(self, checker=None):
        """
        Check all combatants. If all ready, move to phase 2. If checker is
        set, it's a character who is already ready but is using the command
        to see a list of who might not be, so the message is only sent to them.
        """
        ready = []
        not_ready = []
        if not self.ndb.combatants:
            self.msg("No combatants found. Exiting.")
            self.end_combat()
            return
        if not self or not self.pk or self.ndb.shutting_down:
            self.end_combat()
            return
        active_combatants = [ob for ob in self.ndb.combatants if ob not in self.ndb.incapacitated]
        if not active_combatants:
            self.msg("All combatants are incapacitated. Exiting.")
            self.end_combat()
            return
        for char in self.ndb.combatants:
            if self.ndb.fighter_data[char.id].ready:
                ready.append(char)
            elif char in self.ndb.incapacitated:
                ready.append(char)
            else:
                not_ready.append(char)
        if not_ready:  # not ready for phase 2, tell them why
            if checker:
                checker.msg("{wCharacters who are ready:{n " + list_to_string(ready))
                checker.msg("{wCharacter who have not yet hit 'continue' or queued an action:{n " +
                            list_to_string(not_ready))
            else:
                self.msg("{wCharacters who are ready:{n " + list_to_string(ready))
                self.msg("{wCharacter who have not yet hit 'continue':{n " + list_to_string(not_ready))
        else:
            try:
                self.start_phase_2()
            except ValueError:
                self.end_combat()

    def afk_check(self, checking_char, char_to_check):
        """
        Prods a character to make a response. If the character is not in the
        afk_check list, we add them and send them a warning message, then update
        their combat data with the AFK timer. Subsequent checks are votes to
        kick the player if they have been AFK longer than a given idle timer.
        Any action removes them from AFK timer and resets the AFK timer in their
        combat data as well as removes all votes there.
        """
        # No, they can't vote themselves AFK as a way to escape combat
        if checking_char == char_to_check:
            checking_char.msg("You cannot vote yourself AFK to leave combat.")
            return
        if char_to_check not in self.ndb.combatants:
            checking_char.msg("Can only check AFK on someone in the fight.")
            return
        fite = self.ndb.fighter_data
        if self.ndb.phase == 1 and fite[char_to_check.id].ready:
            checking_char.msg("That character is already ready to proceed " +
                              "with combat. They are not holding up the fight.")
            return
        if self.ndb.phase == 2 and not self.ndb.active_character == char_to_check:
            checking_char.msg("It is not their turn to act. You may only " +
                              "vote them AFK if they are holding up the fight.")
            return
        if char_to_check not in self.ndb.afk_check:
            char_to_check.msg("{w%s is checking if you are AFK. Please take" +
                              " an action within a few minutes.{n" % checking_char.name)
            checking_char.msg("You have nudged %s to take an action." % char_to_check.name)
            self.ndb.afk_check.append(char_to_check)
            fite[char_to_check.id].afk_timer = time.time()  # current time
            return
        # character is in the AFK list. Check if they've been gone long enough to vote against
        elapsed_time = time.time() - fite[char_to_check.id].afk_timer
        if elapsed_time < MAX_AFK:
            msg = "It has been %s since %s was first checked for " % (elapsed_time, char_to_check.name)
            msg += "AFK. They have %s seconds to respond before " % (MAX_AFK - elapsed_time)
            msg += "votes can be lodged against them to remove them from combat."
            checking_char.msg(msg)
            return
        # record votes. if we have enough votes, boot 'em.
        votes = fite[char_to_check.id].votes_to_kick
        if checking_char in votes:
            checking_char.msg("You have already voted for their removal. Every other player " +
                              "except for %s must vote for their removal." % char_to_check.name)
            return
        votes.append(checking_char)
        if votes >= len(self.ndb.combatants) - 1:
            self.msg("Removing %s from combat due to inactivity." % char_to_check.name)
            self.move_to_observer(char_to_check)
            return
        char_to_check.msg("A vote has been lodged for your removal from combat due to inactivity.")
        pass
    
    def remove_afk(self, character):
        """
        Removes a character from the afk_check list after taking a combat
        action. Resets relevant fields in combat data
        """
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
            self.ndb.fighter_data[character.id].afk_timer = None
            self.ndb.fighter_data[character.id].votes_to_kick = []
            character.msg("You are no longer being checked for AFK.")
            return

    def move_to_observer(self, character):
        """
        If a character is marked AFK or dies, they are moved from the
        combatant list to the observer list.
        """
        self.remove_combatant(character)
        self.add_observer(character)

    def remove_combatant(self, character, in_shutdown=False):
        """
        Remove a character from combat altogether. Do a ready check if
        we're in phase one.
        """
        self.stop_covering(character)
        c_fite = self.get_fighter_data(character.id)
        if character in self.ndb.combatants:
            self.ndb.combatants.remove(character)
        if character in self.ndb.fleeing:
            self.ndb.fleeing.remove(character)
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
        self.clear_defended_by_list(character)
        self.clear_covered_by_list(character)
        
        self.msg("%s has left the fight." % character.name)
        character.cmdset.delete(CombatCmdSet)
        character.ndb.combat_manager = None
        character.ndb.charcombatdata = []
        # nonlethal combat leaves no lasting harm
        if not self.ndb.lethal:
            # set them to what they were before the fight and wake them up
            character.dmg = c_fite.prefight_damage
            try:
                character.wake_up(quiet=True)
            except AttributeError:
                pass
        # if we're already shutting down, avoid redundant messages
        if len(self.ndb.combatants) < 2 and not in_shutdown:
            # We weren't shutting down and don't have enough fighters to continue. end the fight.
            self.end_combat()
            return
        if self.ndb.phase == 1 and not in_shutdown:
            self.ready_check()
            return
        if self.ndb.phase == 2 and not in_shutdown:
            if character in self.ndb.initiative_list:
                self.ndb.initiative_list.remove(character)
                return
            if self.ndb.active_character == character:
                self.next_character_turn()

    def add_observer(self, character):
        """
        Character becomes a non-participating observer. This is usually
        for GMs who are watching combat, but other players may be moved
        to this - dead characters are no longer combatants, nor are
        characters who have been marked as AFK.
        """
        self.send_intro_message(character, combatant=False)
        self.display_phase_status(character, disp_intro=False)
        if character not in self.ndb.observers:
            character.ndb.combat_manager = self
            self.ndb.observers.append(character)
            return
        
    def remove_observer(self, character, quiet=True):
        """
        Leave observer list, either due to stop observing or due to
        joining the fight
        """
        if character in self.ndb.observers:
            character.msg("You stop spectating the fight.")
            self.ndb.observers.remove(character)
            return
        if not quiet:
            character.msg("You were not an observer, but stop anyway.")

    def build_initiative_list(self):
        """
        Rolls initiative for each combatant, resolves ties, adds them
        to list in order from first to last. Sets current character
        to first character in list.
        """
        for fighter in self.ndb.fighter_data.values():
            fighter.roll_initiative()
        self.ndb.initiative_list = sorted([data for data in self.ndb.fighter_data.values()
                                           if data.char not in self.ndb.incapacitated],
                                          key=attrgetter('initiative', 'tiebreaker'),
                                          reverse=True)

    def next_character_turn(self):
        """
        It is now a character's turn in the iniative list. They will
        be prompted to take an action. If there is no more characters,
        end the turn when this is called and start over at Phase 1.
        """
        if self.ndb.shutting_down:
            return
        if not self.ndb.initiative_list:
            self.start_phase_1()
            return
        char_data = self.ndb.initiative_list.pop(0)
        acting_char = char_data.char
        self.ndb.active_character = acting_char
        # check if they went LD, teleported, or something
        if acting_char.location != self.ndb.combat_location:
            self.msg("%s is no longer here. Removing them from combat." % acting_char.name)
            self.remove_combatant(acting_char)
            return self.next_character_turn()
        # For when we put in subdue/hostage code
        if char_data.status != "active":
            acting_char.msg("It would be your turn, but you cannot act. Passing your turn.")
            self.msg("%s cannot act." % acting_char.name, exclude=[acting_char])
            return self.next_character_turn()
        # turns lost from botches or other effects
        if char_data.lost_turn_counter > 0:
            char_data.remaining_attacks -= 1
            char_data.lost_turn_counter -= 1    
            if char_data.remaining_attacks == 0:
                acting_char.msg("It would be your turn, but you are recovering from a botch. Passing.")
                self.msg("%s is recovering from a botch and loses their turn." % acting_char.name,
                         exclude=[acting_char])
                return self.next_character_turn()                 
        self.msg("{wIt is now{n {c%s's{n {wturn.{n" % acting_char.name, exclude=[acting_char])
        if self.ndb.initiative_list:
            self.msg("{wTurn order for remaining characters:{n %s" % list_to_string(self.ndb.initiative_list))
        result = char_data.do_turn_actions()
        if not result and self.ndb.phase == 2:
            mssg = dedent("""
            It is now {wyour turn{n to act in combat. Please give a little time to make
            sure other players have finished their poses or emits before you select
            an action. For your character's action, you may either pass your turn
            with the {wpass{n command, or execute a command like {wattack{n. Once you
            have executed your command, control will pass to the next character, but
            please describe the results of your action with appropriate poses.
            """)
            acting_char.msg(mssg)

    def start_phase_1(self):
        """
        Setup for phase 1, the 'setup' phase. We'll mark all current
        combatants as being non-ready. Characters will need to hit the
        'continue' command to be marked as ready. Once all combatants
        have done so, we move to phase 2. Alternately, everyone can
        vote to end the fight, and then we're done.
        """
        if self.ndb.shutting_down:
            return
        self.ndb.phase = 1
        self.ndb.active_character = None
        self.ndb.votes_to_end = []
        allchars = self.ndb.combatants + self.ndb.observers
        if not allchars:
            return
        for char in self.ndb.combatants:
            self.ndb.fighter_data[char.id].reset()
        self.force_repeat()
        self.ndb.rounds += 1
        if self.ndb.rounds >= self.ndb.max_rounds:
            self.end_combat()
    
    def start_phase_2(self):
        """
        Setup for phase 2, the 'resolution' phase. We build the list
        for initiative, which will be a list of CombatCharacterData
        objects from self.ndb.fighter_data.values(). Whenever it comes
        to a character's turn, they're popped from the front of the
        list, and it remains their turn until they take an action.
        Any action they take will call the next_character_turn() to
        proceed, and when there are no more characters, we go back
        to phase 1.
        """
        if self.ndb.shutting_down:
            return
        self.ndb.phase = 2
        # determine who can flee this turn
        self.ndb.flee_success = []
        # if they were attempting to flee last turn, roll for them
        for char in self.ndb.fleeing:
            c_fite = self.ndb.fighter_data[char.id]
            if c_fite.roll_flee_success():  # they can now flee
                self.ndb.flee_success.append(char)
        # see if people woke up or fell unconscious
        for char in self.ndb.combatants:
            awake = char.db.asleep_status
            if awake == "awake" and char in self.ndb.incapacitated:
                self.ndb.incapacitated.remove(char)
            if (awake == "asleep" or awake == "unconscious") and char not in self.ndb.incapacitated:
                self.ndb.incapacitated.append(char)
        self.build_initiative_list()
        self.force_repeat()
        self.next_character_turn()

    def vote_to_end(self, character):
        """
        Allows characters to vote to bring the fight to a conclusion.
        """
        if character in self.ndb.votes_to_end:
            character.msg("You have already voted to end the fight.")
            mess = ""
        else:
            mess = "%s has voted to end the fight.\n" % character.name
            self.ndb.votes_to_end.append(character)
        not_voted = [ob for ob in self.ndb.combatants if ob and ob not in self.ndb.votes_to_end]
        # only let conscious people vote
        not_voted = [ob for ob in not_voted if self.get_fighter_data(ob.id)
                     and self.get_fighter_data(ob.id).status == "active"
                     and not self.get_fighter_data(ob.id).wants_to_end]
        if not not_voted:
            self.msg("All parties have voted to end combat.")
            self.end_combat()
            return
        if character not in self.ndb.combatants:
            character.msg("Only participants in the fight may vote to end it.")
            return
        if self.ndb.votes_to_end:
            mess += "{wThe following characters have also voted to end:{n %s\n" % list_to_string(self.ndb.votes_to_end)
        mess += "{wFor the fight to end, the following characters must vote to end:{n "
        mess += "%s" % list_to_string(not_voted)
        self.msg(mess)
    
    def end_combat(self):
        """
        Shut down combat.
        """
        self.msg("Ending combat.")
        self.ndb.shutting_down = True
        for char in self.ndb.combatants[:]:
            self.remove_combatant(char, in_shutdown=True)
        for char in self.ndb.observers[:]:
            self.remove_observer(char)
        self.obj.ndb.combat_manager = None
        self.stop()  # delete script
