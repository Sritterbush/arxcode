from random import randint, choice
import combat_settings
from world.stats_and_skills import do_dice_check
from commands.cmdsets.combat import CombatCmdSet

from combat_settings import CombatError


class QueuedAction(object):
    """
    An action that a player queues in when it is not their turn,
    or automatically queued in for them if they are autoattacking.
    """
    def __init__(self, qtype="Pass", targ=None, msg="", atk_pen=0, dmg_mod=0):
        self.qtype = qtype
        self.targ = targ
        self.msg = msg
        self.atk_pen = atk_pen
        self.dmg_mod = dmg_mod

    def __str__(self):
        return self.qtype or "None"


# noinspection PyAttributeOutsideInit
class CombatHandler(object):
    """
    Stores information about the character in this particular
    fight - where they're standing (rank), how they might be
    attacking (weapon and combat_style).
    Properties to know:
    self.char - the character we're wrapped around
    self.weapon - the character's weapon if it exists
    self.shield - our shield if it exists
    self.initiative - current initiative roll
    self.status - "active" means they can fight
    self.afk_timer - time set when we were marked AFK
    self.votes_to_kick - how many people have voted us AFK
    self.lost_turn_counter - how many turns we have to sit idle
    self.blocker_list - people stopping us from fleeing
    self.block_flee - anyone we're stopping from fleeing
    self.covering_targs - who we're helping flee
    self.covered_by - people who are helping us flee
    
    Stuff about how we attack:
    self.can_be_blocked, self.can_be_dodged, self.can_be_parried - all about our attack type
    opposites are self.can_block, self.can_dodge, self.can_parry.
    self.riposte - determines whether we can hit someone who botches
    self.stance - "defensive" to "reckless". gives attack/defense mods
    
    CharacterCombatData has the following methods:
    roll_initiative() - sets initiative and a tiebreaker value for the character
    roll_attack(targ, penalty=0) - targ is a CharacterCombatData object, returns self.char's to-hit roll
    roll_defense(att, weapon=None, penalty=0) - att is a CharacterCombatData, returns self.char's defense roll
    roll_damage(targ, penalty=0) - returns self.char's damage roll
    roll_mitigation(att, weapon=None, roll=0) - returns self.char's mitigation roll
    roll_flee_success() - returns True or False, whether we succeed in fleeing
    """
    def __init__(self, character, combat=None):
        self.combat = combat
        self.char = character
        if character.db.num_living:
            self.multiple = True
            self.automated = True
            self.autoattack = True
            try:
                self.base_name = character.get_singular_name()
                self.plural_name = character.get_plural_name()
            except AttributeError:
                self.base_name = character.name
                self.plural_name = character.name
        else:
            self.multiple = False
            self.automated = False
            self.autoattack = character.db.autoattack or False
            self.base_name = character.name
            self.plural_name = character.name
        if not character.player:
            self.automated = True
            self.autoattack = True
        self._ready = False
        self.lethal = True
        self.initialize_values()

    @property
    def num(self):
        if self.multiple:
            try:
                return self.char.quantity
            except AttributeError:
                pass
        return 1

    @property
    def stance(self):
        _stance = self.char.db.combat_stance
        if _stance not in combat_settings.COMBAT_STANCES:
            return "balanced"
        return _stance

    @stance.setter
    def stance(self, val):
        self.char.db.combat_stance = val

    def initialize_values(self):
        character = self.char
        self.rank = 1  # combat rank/position. 1 is 'front line'
        self.shield = character.db.shield
        if hasattr(character, 'weapondata'):
            self.setup_weapon(character.weapondata)
        else:
            self.setup_weapon()
        self.defenders = character.db.defenders or []  # can be guarded by many
        if self.defenders:
            self.rank += 1
        self.guarding = character.db.guarding  # can only guard 1 character
        if self.guarding:
            self.rank -= 1
        self.initiative = 0
        self.tiebreaker = 0
        self.queued_action = None
        # one attack per character
        self.num_attacks = self.num
        # remaining attacks this round
        self.remaining_attacks = 0
        # whether or not we intentionally kill PCs
        self.do_lethal = False
        # list of targets for each of our attacks this round
        self.targets = []
        # last person we attacked
        self.prev_targ = None
        # list of valid foes for us to make into targets
        self.foelist = []
        self.friendlist = []
        self._ready = False  # ready to move on from phase 1
        self.last_defense_method = None  # how we avoided the last attack we stopped
        self.status = "active"
        # eventually may have a grid system, but won't use it yet
        # self.position = (0,0,0)
        # self.direction = 0 # facing forward
        self.afk_timer = None
        self.votes_to_kick = []  # if we're AFK
        self.lost_turn_counter = 0  # lose a turn whenever it's > 0
        self.block_flee = None  # Anyone we stop from fleeing
        self.blocker_list = []  # Anyone stopping us from fleeing
        self.covering_targs = []  # Covering their retreat
        self.covered_by = []  # Having your retreat covered
        self.formation = None
        self.flee_exit = None
        self.wants_to_end = False
        self.times_attacked = 0
        self._fatigue_penalty = 0
        self.fatigue_gained_this_turn = 0
        self.num_actions = 0  # used for fatigue calculation
        self.changed_stance = False
        
    def join_combat(self, combat):
        character = self.char
        self.combat = combat
        self.initialize_values()
        character.cmdset.add(CombatCmdSet, permanent=False)
        # add defenders/guards
        if character.db.defenders:
            for ob in character.db.defenders:
                self.add_defender(ob)
        if character.db.assigned_guards:
            for ob in character.db.assigned_guards:
                self.add_defender(ob)
        if combat:
            self.lethal = combat.ndb.lethal
        if not self.combat.ndb.initializing:
            self.reset()

    def leave_combat(self, combat):
        character = self.char
        # nonlethal combat leaves no lasting harm
        self.char.temp_dmg = 0
        if not self.lethal:
            character.wake_up(quiet=True)
        self.stop_covering()
        self.clear_blocked_by_list()
        self.clear_covered_by_list()
        guarding = self.guarding
        if guarding:
            guarding.combat.remove_defender(character)
        combat.msg("%s has left the fight." % character.name)
        character.cmdset.delete(CombatCmdSet)
        self.combat = None
        try:
            # remove temporary losses from MultiNpcs
            self.char.temp_losses = 0
        except AttributeError:
            pass

    def setup_weapon(self, weapon=None):
        self.weapon = weapon
        if weapon:  # various optional weapon fields w/default values
            self.combat_style = self.char.db.combat_style or "melee"
            self.attack_skill = self.weapon.get('attack_skill', 'brawl')
            self.attack_stat = self.weapon.get('attack_stat', 'dexterity')
            self.damage_stat = self.weapon.get('damage_stat', 'strength')
            self.weapon_damage = self.weapon.get('weapon_damage', 0)
            self.attack_type = self.weapon.get('attack_type', 'melee')
            self.can_be_parried = self.weapon.get('can_be_parried', True)
            self.can_be_blocked = self.weapon.get('can_be_blocked', True)
            self.can_be_dodged = self.weapon.get('can_be_dodged', True)
            self.can_parry = self.weapon.get('can_parry', True)
            self.can_riposte = self.weapon.get('can_riposte', True)
            self.difficulty_mod = self.weapon.get('difficulty_mod', 0)
            if self.shield:
                self.can_block = self.shield.db.can_block or False
            else:
                self.can_block = False
            self.can_dodge = True
            self.flat_damage_bonus = self.weapon.get('flat_damage', 0)
            # self.reach = self.weapon.get('reach', 1)
            # self.minimum_range = self.weapon.get('minimum_range', 0)
        else:  # unarmed combat
            self.combat_style = self.char.db.combat_style or "brawling"
            self.attack_skill = "brawl"
            self.attack_stat = "dexterity"
            self.damage_stat = "strength"
            self.weapon_damage = 0
            self.attack_type = "melee"
            self.can_be_parried = True
            self.can_be_blocked = True
            self.can_be_dodged = True
            self.can_parry = False
            self.can_riposte = True  # can't block swords with hands, but can punch someone
            self.can_block = False
            self.can_dodge = True
            # possibly use these in future
            # self.reach = 1 #number of ranks away from them they can hit
            # self.minimum_range = 0 #minimum ranks away to attack
            self.difficulty_mod = 0
            self.flat_damage_bonus = 0

    def display_stats(self):
        weapon = self.char.db.weapon
        dmg = self.char.db.damage or 0
        try:
            max_hp = self.char.max_hp
            hp = "%s/%s" % (max_hp - dmg, max_hp)
        except AttributeError:
            hp = "?/?"
        fdiff = int(self.num_actions) + 20
        try:
            armor_penalty = int(self.char.armor_penalties)
        except AttributeError:
            armor_penalty = 0
        fdiff += armor_penalty
        smsg = \
            """
                    {wStatus{n
{w==================================================================={n
{wHealth:{n %(hp)-25s {wFatigue Level:{n %(fatigue)-20s
{wDifficulty of Fatigue Rolls:{n %(fdiff)-4s {wStatus:{n %(status)-20s
{wCombat Stance:{n %(stance)-25s
{wPenalty to rolls from wounds:{n %(wound)s
           """ % {'hp': hp, 'fatigue': self.fatigue_penalty, 'fdiff': fdiff,
                  'status': self.status, 'stance': self.stance,
                  'wound': self.wound_penalty,
                  }
        omsg = \
            """
                    {wOffensive stats{n
{w==================================================================={n
{wWeapon:{n %(weapon)-20s
{wWeapon Damage:{n %(weapon_damage)-17s {wFlat Damage Bonus:{n %(flat)s
{wAttack Stat:{n %(astat)-19s {wDamage Stat:{n %(dstat)-20s
{wAttack Skill:{n %(askill)-18s {wAttack Type:{n %(atype)-20s
{wDifficulty Mod:{n %(dmod)-16s {wCan Be Parried:{n %(bparried)-20s
{wCan Be Blocked:{n %(bblocked)-16s {wCan Be Dodged:{n %(bdodged)-20s
{wAttack Roll Penalties:{n %(atkpen)-20s
           """ % {'weapon': weapon, 'weapon_damage': self.weapon_damage, 'astat': self.attack_stat,
                  'dstat': self.damage_stat, 'askill': self.attack_skill, 'atype': self.attack_type,
                  'dmod': self.difficulty_mod, 'bparried': self.can_be_parried,
                  'bblocked': self.can_be_blocked, 'bdodged': self.can_be_dodged,
                  'flat': self.flat_damage_bonus, 'atkpen': self.atk_penalties
                  }
        try:
            armor = self.char.armor
        except AttributeError:
            armor = self.char.db.armor or 0
        dmsg = \
            """
                    {wDefensive stats{n
{w==================================================================={n
{wMitigation:{n %(mit)-20s {wPenalty to Fatigue Rolls:{n %(apen)s
{wCan Parry:{n %(cparry)-21s {wCan Riposte:{n %(criposte)s
{wCan Block:{n %(cblock)-21s {wCan Dodge:{n %(cdodge)s
{wDefense Roll Penalties:{n %(defpen)-8s {wSoak Rating:{n %(soak)s""" % {
                'mit': armor, 'defpen': self.def_penalties,
                'apen': armor_penalty, 'cparry': self.can_parry,
                'criposte': self.can_riposte, 'cblock': self.can_block,
                'cdodge': self.can_dodge, 'soak': self.soak}
        if self.can_parry:
            dmsg += "\n{wParry Skill:{n %-19s {wParry Stat:{n %s" % (self.attack_skill, self.attack_stat)
        if self.can_dodge:
            dmsg += "\n{wDodge Skill:{n %-19s {wDodge Stat:{n %s" % (self.char.db.skills.get("dodge"), "dexterity")
            dmsg += "\n{wDodge Penalty:{n %s" % self.dodge_penalty
        msg = smsg + omsg + dmsg
        return msg

    def __str__(self):
        if self.multiple:
            return self.base_name
        return self.char.name

    def __repr__(self):
        return "<Class CombatHandler: %s>" % self.char

    def msg(self, mssg):
        self.char.msg(mssg)

    @property
    def valid_target(self):
        """
        Whether we're in the combat at all. Should not be valid in any way to interact
        with.
        """
        if not self.char:
            return False
        if not self.combat:
            return False
        if self.char.location != self.combat.obj:
            return False
        return True

    @property
    def can_fight(self):
        """
        Whether we're totally out of the fight. Can be killed, but no longer
        a combatant.
        """
        if not self.valid_target:
            return False
        if not self.char.conscious:
            return False
        return True

    @property
    def can_act(self):
        """
        Whether we can act this round. May be temporarily stunned.
        """
        if not self.can_fight:
            return False
        return self.status == "active"

    @property
    def ready(self):
        # if we're an automated npc, we are ALWAYS READY TO ROCK. BAM.
        return self.automated or self._ready

    @ready.setter
    def ready(self, value):
        # set whether or not a sissy-man non-npc is ready. Unlike npcs, which are ALWAYS READY. BOOYAH.
        self._ready = value

    @property
    def name(self):
        if not self.multiple:
            return self.char.name
        return "%s %s" % (self.num, self.plural_name)

    @property
    def singular_name(self):
        return self.base_name

    @property
    def wound_penalty(self):
        """
        A difficulty penalty based on how hurt we are. Penalty is
        1 per 10% damage. So over +10 diff if we're holding on from uncon.
        """
        # if we're a multi-npc, only the damaged one gets wound penalties
        if self.multiple and self.remaining_attacks != self.num_attacks:
            return 0
        # noinspection PyBroadException
        try:
            dmg = self.char.db.damage or 0
            base = int((dmg * 100.0) / (self.char.max_hp * 10.0))
            base -= (self.char.boss_rating * 10)
            if base < 0:
                base = 0
            return base
        except Exception:
            return 0

    @property
    def atk_penalties(self):
        base = (self.wound_penalty/2) + self.fatigue_atk_penalty()
        return base - self.char.attack_modifier

    @property
    def def_penalties(self):
        base = self.wound_penalty + self.fatigue_def_penalty()
        # it gets increasingly hard to defend the more times you're attacked per round
        overwhelm_penalty = self.times_attacked * 10
        if overwhelm_penalty > 40:
            overwhelm_penalty = 40
        base += overwhelm_penalty
        return base - self.char.defense_modifier

    @property
    def dodge_penalty(self):
        return int(self.char.armor_penalties * 1.25)

    @property
    def soak(self):
        val = self.char.db.stamina or 0
        val += self.char.db.willpower or 0
        if self.char.db.skills:
            val += self.char.db.skills.get("survival", 0)
        return val

    def reset(self):
        self.times_attacked = 0
        self.ready = False
        self.queued_action = None
        self.changed_stance = False
        self.fatigue_gained_this_turn = 0
        # check for attrition between rounds
        if self.multiple:
            self.num_attacks = self.num
        self.remaining_attacks = self.num_attacks

    def setup_phase_prep(self):
        # if we order them to stand down, they do nothing
        if self.automated:
            if self.wants_to_end:
                self.combat.vote_to_end(self.char)
                self.set_queued_action("pass")
                return
        self.setup_attacks()

    def setup_attacks(self):
        self.validate_targets()
        if self.autoattack:
            self.validate_targets(self.do_lethal)
            if self.targets and self.can_fight:
                targ = self.prev_targ
                if not targ:
                    targ = choice(self.targets)
                mssg = "{rYou attack %s.{n" % targ
                defenders = targ.combat.get_defenders()
                if defenders:
                    targ = choice(defenders)
                    mssg += " But {c%s{n gets in your way, and you attack them instead."
                if self.do_lethal:
                    self.set_queued_action("kill", targ, mssg, do_ready=False)
                else:
                    self.set_queued_action("attack", targ, mssg, do_ready=False)
            else:
                ready = False
                if self.automated:
                    self.wants_to_end = True
                    ready = True
                self.set_queued_action("pass", do_ready=ready)

    def validate_targets(self, lethal=False):
        """
        builds a list of targets from our foelist, making sure each
        target is in combat and meets our requirements. If lethal
        is false, we can only attack opponents that are conscious.
        """
        guarding = self.char.db.guarding
        if guarding:
            gdata = guarding.combat
            if gdata:
                for foe in gdata.foelist:
                    self.add_foe(foe)
        fighters = [ob.combat for ob in self.foelist]
        if not lethal:
            self.targets = [fighter.char for fighter in fighters if fighter.can_fight]
        else:
            self.targets = [fighter.char for fighter in fighters if fighter.valid_target]

    def add_foe(self, targ):
        """
        Adds a target to our foelist, and also checks for whoever is defending
        them, to add them as potential targets as well.
        """
        if targ in self.foelist or targ == self.char:
            return
        self.foelist.append(targ)
        if targ in self.friendlist:
            # YOU WERE LIKE A BROTHER TO ME
            # NOT A VERY GOOD BROTHER BUT STILL
            self.friendlist.remove(targ)
        defenders = targ.db.defenders or []
        for defender in defenders:
            # YOU'RE HIS PAL? WELL, FUCK YOU TOO THEN
            if defender not in self.friendlist and defender != self.char:
                self.add_foe(defender)

    def add_friend(self, friend):
        """
        FRIIIIIENDS, yes? FRIIIIIIIIENDS.
        """
        if friend in self.friendlist or friend == self.char:
            return
        self.friendlist.append(friend)
        if friend in self.foelist:
            # ALL IS FORGIVEN. YOU WERE LOST, AND NOW ARE FOUND
            self.foelist.remove(friend)
        defenders = friend.db.defenders or []
        for defender in defenders:
            # YOU'RE WITH HIM? OKAY, YOU'RE COOL
            if defender not in self.foelist and self.char != defender:
                self.add_friend(defender)

    def set_queued_action(self, qtype=None, targ=None, msg="", atk_pen=0, dmg_mod=0, do_ready=True):
        """
        Setup our type of queued action, remember targets,
        that sorta deal.
        """
        # remember that this is someone we wanted to attack
        if targ and targ not in self.foelist:
            self.add_foe(targ)
        self.queued_action = QueuedAction(qtype, targ, msg, atk_pen, dmg_mod)
        if do_ready:
            self.character_ready()

    def cancel_queued_action(self):
        self.queued_action = None

    def do_turn_actions(self, took_actions=False):
        """
        Takes any queued action we have and returns a result. If we have no
        queued action, return None. If our queued action can no longer be
        completed, return None. Otherwise, return a result.
        """
        if not self.combat:
            return
        if self.combat.ndb.shutting_down:
            return
        if self.combat.ndb.phase != 2:
            return False
        if not self.char.conscious:
            self.msg("You are no longer conscious and can take no action.")
            self.do_pass()
            return took_actions
        if self.char in self.combat.ndb.flee_success:
            # cya nerds
            self.combat.do_flee(self.char, self.flee_exit)
            return True
        q = self.queued_action       
        if not q:
            # we have no queued action, so player must act
            if self.automated:
                # if we're automated and have no action, pass turn
                self.do_pass()
            return took_actions
        lethal = q.qtype == "kill"
        if q.qtype == "pass" or q.qtype == "delay":
            delay = q.qtype == "delay"
            self.msg(q.msg)
            self.do_pass(delay=delay)
            return True
        self.validate_targets(lethal)
        if q.qtype == "attack" or q.qtype == "kill":
            # if we have multiple npcs in us, we want to spread out
            # our attacks. validate_targets will only show non-lethal targets
            targ = q.targ
            if not self.targets:
                self.msg("You no longer have any valid targets to autoattack.")
                if self.automated:
                    self.do_pass()
                return took_actions
            if targ not in self.targets:
                self.msg("%s is no longer a valid target to autoattack.")
                targ = choice(self.targets)
                self.msg("Attacking %s instead." % targ)
            else:
                self.msg(q.msg)
            if self.multiple:
                # while we never consecutively attack the same target twice, we still will
                # try to use a lot of our attacks on our 'main' target the player set for the npc
                if randint(1, 100) < 50:
                    targ = choice(self.targets)
                # if we have the same target as our last attack, try to attack someone else
                if targ == self.prev_targ and not targ.db.num_living:
                    self.targets.remove(targ)
                    if self.targets:
                        targ = choice(self.targets)
                    # add them back so our next attack could be the last guy
                    self.targets.append(self.prev_targ)
                defenders = targ.combat.get_defenders()
                # if our target selection has defenders, we hit one of them instead
                if defenders:
                    targ = choice(defenders)
            # set who we attacked
            self.prev_targ = targ
            self.do_attack(targ, attack_penalty=q.atk_pen, dmg_penalty=-q.dmg_mod)

    # noinspection PyMethodMayBeStatic
    def setup_defenders(self):
        """
        Determine list of CharacterCombatData objects of our defenders.
        """
        pass

    # noinspection PyMethodMayBeStatic
    def join_formation(self, newformation):
        """
        Leave our old formation and join new one, while taking with us all
        our defenders.
        """
        pass

    def roll_initiative(self):
        """Rolls and stores initiative for the character."""
        self.initiative = do_dice_check(self.char, stat_list=["dexterity", "composure"], stat_keep=True, difficulty=0)
        self.tiebreaker = randint(1, 1000000000)

    # noinspection PyUnusedLocal
    def roll_attack(self, targ, penalty=0):
        """
        Returns our roll to hit with an attack. Half of our roll is randomized.
        """
        diff = 2  # base difficulty before mods
        self.roll_fatigue()
        penalty += self.atk_penalties
        diff += penalty       
        diff += self.difficulty_mod
        roll = do_dice_check(self.char, stat=self.attack_stat, skill=self.attack_skill, difficulty=diff)
        if roll < 2:
            return roll
        return (roll/2) + randint(0, (roll/2))

    # noinspection PyUnusedLocal
    def roll_defense(self, attacker, weapon=None, penalty=0, a_roll=None):
        """
        Returns our roll to avoid being hit. We use the highest roll out of 
        parry, block, and dodge. Half of our roll is then randomized.
        """
        # making defense easier than attack to slightly lower combat lethality
        diff = -2  # base difficulty before mods
        self.roll_fatigue()
        penalty += self.def_penalties
        diff += penalty
        self.times_attacked += 1
        total = None
        att = attacker.combat
        if att.can_be_parried and self.can_parry:
            parry_diff = diff + 10
            parry_roll = int(do_dice_check(self.char, stat=self.attack_stat, skill=self.attack_skill,
                                           difficulty=parry_diff))
            if parry_roll > 1:
                parry_roll = (parry_roll/2) + randint(0, (parry_roll/2))
            total = parry_roll
        else:
            parry_roll = -1000
        if att.can_be_blocked and self.can_block:
            try:
                block_diff = diff + self.dodge_penalty
            except (AttributeError, TypeError, ValueError):
                block_diff = diff
            block_roll = int(do_dice_check(self.char, stat="dexterity", skill="dodge", difficulty=block_diff))
            if block_roll >= 2:
                block_roll = (block_roll/2) + randint(0, (block_roll/2))
            if not total:
                total = block_roll
            elif block_roll > 0:
                if total > block_roll:
                    total += block_roll/2
                else:
                    total = (total/2) + block_roll
            elif block_roll > total:
                total = (total + block_roll)/2
        else:
            block_roll = -1000
        if att.can_be_dodged and self.can_dodge:
            # dodging is easier than parrying
            dodge_diff = diff - 10
            try:
                dodge_diff += self.dodge_penalty
            except (AttributeError, TypeError, ValueError):
                pass
            dodge_roll = int(do_dice_check(self.char, stat="dexterity", skill="dodge", difficulty=dodge_diff))
            if dodge_roll >= 2:
                dodge_roll = (dodge_roll/2) + randint(0, (dodge_roll/2))
            if not total:
                total = dodge_roll
            elif dodge_roll > 0:
                # if total > dodge_roll:
                #     total += dodge_roll/2
                # else:
                #     total = (total/2) + dodge_roll
                total += dodge_roll
            elif dodge_roll > total:
                total = (total + dodge_roll)/2
        else:
            dodge_roll = -1000
        if total is None:
            total = -1000
        # return our highest defense roll
        if parry_roll > block_roll and parry_roll > dodge_roll:
            self.last_defense_method = "parries"
            return total
        if block_roll > parry_roll and block_roll > dodge_roll:
            self.last_defense_method = "blocks"
            return total
        self.last_defense_method = "dodges"
        return total

    # noinspection PyUnusedLocal
    def roll_damage(self, targ, penalty=0, dmgmult=1.0):
        """Returns our roll for damage against target."""
        keep_dice = self.weapon_damage + 1
        try:
            keep_dice += self.char.attributes.get(self.damage_stat)/2
        except (TypeError, AttributeError, ValueError):
            pass
        if keep_dice < 3:
            keep_dice = 3       
        diff = 0  # base difficulty before mods
        diff += penalty
        roll = do_dice_check(self.char, stat=self.damage_stat, stat_keep=True,
                             difficulty=diff, bonus_dice=self.weapon_damage, keep_override=keep_dice)
        roll += self.flat_damage_bonus
        roll = int(roll * dmgmult)
        if roll <= 0:
            roll = 1
        # 3/4ths of our damage is purely random
        return roll/4 + randint(0, ((roll * 3)/4)+1)

    # noinspection PyUnusedLocal
    def roll_mitigation(self, att, weapon=None, roll=0):
        """
        Returns our damage reduction against attacker. If the roll is
        higher than 15, that number is subtracted off our armor.
        """
        if hasattr(self.char, "armor"):
            armor = self.char.armor
        else:
            armor = self.char.db.armor_class or 0      
        # our soak is sta+willpower+survival
        armor += randint(0, (self.soak * 2)+1)
        roll -= 15  # minimum amount to pierce armor
        if roll > 0:
            armor -= roll
        if armor <= 0:
            return 0
        if armor < 2:
            return randint(0, armor)
        # half of our armor is random
        return (armor/2) + randint(0, (armor/2))

    def roll_fatigue(self):
        """
        Chance of incrementing our fatigue penalty. The difficulty is the
        number of combat actions we've taken plus our armor penalty.
        """
        if self.multiple:
            # figure out way later to track fatigue for units
            return
        if self.char.db.never_tire:
            return        
        armor_penalty = 0
        if hasattr(self.char, 'armor_penalties'):
            armor_penalty = self.char.armor_penalties
        penalty = armor_penalty
        self.num_actions += 1 + (0.12 * armor_penalty)
        penalty += self.num_actions + 25
        keep = self.fatigue_soak
        penalty = int(penalty)
        penalty = penalty/2 + randint(0, penalty/2)
        myroll = do_dice_check(self.char, stat_list=["strength", "stamina", "dexterity", "willpower"],
                               skill="athletics", keep_override=keep, difficulty=int(penalty), divisor=2)
        myroll += randint(0, 25)
        if myroll < 0 and self.fatigue_gained_this_turn < 1:
            self._fatigue_penalty += 0.5
            self.fatigue_gained_this_turn += 0.5

    @property
    def fatigue_soak(self):
        soak = max(self.char.db.willpower or 0, self.char.db.stamina or 0)
        try:
            soak += self.char.db.skills.get("athletics", 0)
        except (AttributeError, TypeError, ValueError):
            pass
        if soak < 2:
            soak = 2
        return soak

    @property
    def fatigue_penalty(self):
        fat = int(self._fatigue_penalty)
        soak = self.fatigue_soak
        fat -= soak
        if fat < 0:
            return 0
        return fat

    def fatigue_atk_penalty(self):
        fat = self.fatigue_penalty/2
        if fat > 30:
            return 30
        return fat

    def fatigue_def_penalty(self):
        return int(self.fatigue_penalty * 2.0)

    def roll_flee_success(self):
        """
        Determines if we can flee. Called during initiative. If successful,
        we're added to the list of people who can now gtfo. If someone is
        covering our retreat, we succeed automatically. We must outroll every
        player attempting to block us to flee otherwise.
        """
        if self.covered_by:
            return True
        myroll = do_dice_check(self.char, stat="dexterity", skill="dodge", difficulty=0)
        for guy in self.blocker_list:
            if myroll < do_dice_check(guy, stat="dexterity", skill="brawl", difficulty=0):
                return False
        return True

    def sense_ambush(self, attacker, sneaking=False, invis=False):
        """
        Returns the dice roll of our attempt to detect an ambusher.
        """
        diff = 0  # base difficulty
        if sneaking:
            diff += 15
        sense = self.char.sensing_check(difficulty=0, invis=invis)
        stealth = do_dice_check(attacker, stat="dexterity", skill="stealth")
        return sense - stealth
        
    def wake_up(self):
        if self.combat:
            self.combat.wake_up(self.char)
            
    def fall_asleep(self):
        if self.combat:
            self.combat.incapacitate(self.char)

    def character_ready(self):
        """
        Character is ready to proceed from phase 1. Once all
        characters hit ready, we move to phase 2.
        """
        character = self.char
        combat = self.combat
        if not combat:
            return
        if character not in combat.ndb.combatants:
            return
        if combat.ndb.phase == 2:
            combat.remove_afk(character)
            return
        if character.combat.ready:
            combat.ready_check(character)
            return
        combat.remove_afk(character)
        self.ready = True
        character.msg("You have marked yourself as ready to proceed.")
        combat_round = combat.ndb.rounds
        combat.ready_check()
        # if we didn't go to the next turn
        if combat.ndb.phase == 1 and combat.ndb.rounds == combat_round:
            combat.build_status_table()
            combat.display_phase_status(character, disp_intro=False)

    def do_attack(self, target, attack_penalty=0, defense_penalty=0,
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
        attacker = self.char
        combat = self.combat
        if combat.ndb.phase != 2:
            raise CombatError("Attempted to attack in wrong phase.")
        weapon = self.weapon
        d_fite = target.combat
        # modifiers from our stance (aggressive, defensive, etc)
        attack_penalty += combat_settings.STANCE_ATK_MOD[self.stance]
        defense_penalty += combat_settings.STANCE_DEF_MOD[d_fite.stance]
        # modifier if we're covering anyone's retreat
        if self.covering_targs:
            attack_penalty += 5
        if d_fite.covering_targs:
            defense_penalty += 5
        # attack roll so attacker is assumed
        a_roll = self.roll_attack(target, attack_penalty)
        # this is a defense roll so defender is assumed
        d_roll = d_fite.roll_defense(attacker, weapon, defense_penalty, a_roll)
        message = "%s attempts to attack %s. " % (self, d_fite)
        combat.msg("%s rolls %s to attack, %s rolls %s to defend." % (self, a_roll, d_fite, d_roll))
        # check if we were sleeping
        awake = target.db.sleep_status or "awake"
        if awake != "awake":
            message += "%s is %s and cannot stop the attack. " % (d_fite, awake)
            d_roll = -1000   
        result = a_roll - d_roll
        # handle botches. One botch per -10
        if a_roll < 0 and result < -30 and allow_botch:
            combat.msg(message, options={'roll': True})
            can_riposte = self.can_be_parried and d_fite.can_riposte
            if not target.conscious:
                can_riposte = False
            # asleep is very specific, being unconscious doesn't apply here
            if awake == "asleep":
                target.wake_up()
            self.handle_botch(a_roll, can_riposte, target, attack_penalty, defense_penalty,
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
            combat.msg(message)
            self.assign_damage(target, result, weapon, dmg_penalty, dmgmult)
        else:
            message += "%s %s the attack." % (d_fite, d_fite.last_defense_method)
            combat.msg(message)
        # asleep is very specific, being unconscious doesn't apply here
        if awake == "asleep":
            target.wake_up()
        if not free_attack:  # situations where a character gets a 'free' attack
            self.take_action()

    # noinspection PyUnusedLocal
    def handle_botch(self, roll, can_riposte=True, target=None,
                     attack_penalty=0, defense_penalty=0, dmg_penalty=0, free_attack=False):
        """
        Processes the results of botching a roll.
        """
        botcher = self.char
        combat = self.combat
        if can_riposte and target:
            combat.msg("%s {rbotches{n their attack, leaving themselves open to a riposte." % self)
            target.do_attack(botcher, attack_penalty, defense_penalty, dmg_penalty,
                             allow_botch=False, free_attack=True)
            if not free_attack:
                self.take_action()
            return        
        self.lost_turn_counter += 1
        combat.msg("%s {rbotches{n their attack, losing their next turn while recovering." % self)
        if not free_attack:
            self.take_action()

    def take_action(self, action_cost=1):
        """
        Record that we've used an attack and go to the next character's turn if we're out
        """
        self.remaining_attacks -= action_cost
        if not self.combat:
            return
        self.combat.remove_afk(self.char)
        if self.combat.ndb.phase == 2 and self.combat.ndb.active_character == self.char:
            if self.char in self.combat.ndb.initiative_list:
                self.combat.ndb.initiative_list.remove(self)
            # if we have remaining attacks, add us to the end
            if self.remaining_attacks > 0:
                self.combat.ndb.initiative_list.append(self)
            self.combat.next_character_turn()

    def assign_damage(self, target, roll, weapon=None, dmg_penalty=0, dmgmult=1.0):
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
        attacker = self.char
        combat = self.combat
        # stuff to mitigate damage here
        d_fite = target.combat
        lethal = combat.ndb.lethal
        # if damage is increased, it's pre-mitigation
        if dmgmult > 1.0:
            dmg = self.roll_damage(target, dmg_penalty, dmgmult)
        else:
            dmg = self.roll_damage(target, dmg_penalty)
        mit = d_fite.roll_mitigation(attacker, weapon, roll)
        combat.msg("%s rolled %s damage against %s's %s mitigation." % (self, dmg, d_fite, mit))
        dmg -= mit
        # if damage is reduced by multiplier, it's post mitigation
        if dmgmult < 1.0:
            dmg = int(dmg * dmgmult)
        if dmg <= 0:
            message = "%s fails to inflict any harm on %s." % (self, d_fite)
            combat.msg(message, options={'roll': True})
            return
        target.combat.take_damage(dmg, lethal)

    def take_damage(self, dmg, lethal=True, allow_one_shot=False):
        target = self.char
        loc = target.location
        # some flags so messaging is in proper order
        knock_uncon = False
        kill = False
        remove = False
        # max hp is (stamina * 10) + 10
        max_hp = target.max_hp
        wound = float(dmg) / float(max_hp)
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
        message = "%s takes {r%s{n damage." % (self, wound_desc)
        if lethal:
            target.dmg += dmg
        else:
            target.temp_dmg += dmg
        grace_period = False  # one round delay between incapacitation and death for PCs
        if target.dmg > target.max_hp:
            # if we're not incapacitated, we start making checks for it
            if target.conscious and not target.sleepless:
                # check is sta + willpower against % dmg past uncon to stay conscious
                diff = int((float(target.dmg - target.max_hp)/target.max_hp) * 100)
                consc_check = do_dice_check(target, stat_list=["stamina", "willpower"], skill="survival",
                                            stat_keep=True, difficulty=diff)
                message += "%s rolls stamina+willpower+survival against difficulty %s, getting %s." % (self, diff,
                                                                                                       consc_check)
                if consc_check > 0:
                    message += "%s remains capable of fighting despite their wounds." % self
                    grace_period = True  # even npc can't be killed if they make the first check
                    # we're done, so send the message for the attack
                else:
                    message += "%s is incapacitated from their wounds." % self
                    knock_uncon = True
                # for PCs who were knocked unconscious this round
                if not target.is_npc and not grace_period and not allow_one_shot:
                    grace_period = True  # always a one round delay before you can kill a player
            # PC/NPC who was already unconscious before attack, or an NPC who was knocked unconscious by our attack
            if not grace_period:  # we are allowed to kill the character
                diff = int((float(target.dmg - (2 * target.max_hp))/(2 * target.max_hp)) * 100)
                if diff < 0:
                    diff = 0
                if do_dice_check(target, stat_list=["stamina", "willpower"], skill="survival",
                                 stat_keep=True, difficulty=diff) > 0:
                    message = "%s remains alive, but close to death." % self
                    if target.combat.multiple:
                        # was incapacitated but not killed, but out of fight and now we're on another targ
                        if lethal:
                            target.dmg = 0
                        else:
                            target.temp_dmg = 0
                elif not target.combat.multiple:
                    if lethal:
                        kill = True
                    # remove a 'killed' character from combat whether it was a real death or fake
                    remove = True
                else:
                    if lethal:
                        kill = True
                    else:
                        knock_uncon = True
        if loc:
            loc.msg_contents(message, options={'roll': True})
        if knock_uncon:
            target.fall_asleep(uncon=True, lethal=lethal)
        if kill:
            target.death_process(lethal=lethal)
        if target.combat.multiple:
            try:
                if target.quantity <= 0:
                    remove = True
            except AttributeError:
                pass
        if self.combat and remove:
            self.combat.remove_combatant(target)
                    
    def do_flank(self, target, sneaking=False, invis=False, attack_guard=True):
        """
        Attempts to circle around a character. If successful, we get an
        attack with a bonus.
        """
        attacker = self.char
        combat = self.combat
        defenders = self.get_defenders()
        message = "%s attempts to move around %s to attack them while they are vulnerable. " % (attacker.name,
                                                                                                target.name)
        if defenders:
            # guards, have to go through them first
            for guard in defenders:
                g_fite = guard.combat
                if g_fite.sense_ambush(attacker, sneaking, invis) > 0:
                    if not attack_guard:
                        message += "%s sees them, and they back off." % guard.name
                        combat.msg(message)
                        combat.next_character_turn()
                        return
                    message += "%s stops %s but is attacked." % (guard.name, attacker.name)
                    combat.msg(message)
                    def_pen = -5 + combat_settings.STANCE_DEF_MOD[g_fite.stance]
                    self.do_attack(guard, attack_penalty=5, defense_penalty=def_pen)
                    return
        t_fite = target.combat
        if t_fite.sense_ambush(attacker, sneaking, invis) > 0:
            message += "%s moves in time to not be vulnerable." % target
            combat.msg(message)
            def_pen = -5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
            self.do_attack(target, attack_penalty=5, defense_penalty=def_pen)
            return
        message += "They succeed."
        self.msg(message)
        def_pen = 5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
        self.do_attack(target, attack_penalty=-5, defense_penalty=def_pen)

    def do_pass(self, delay=False):
        """
        Passes a combat turn for character. If it's their turn, next character goes.
        If it's not their turn, remove them from initiative list if they're in there
        so they don't get a turn when it comes up.
        """
        character = self.char
        combat = self.combat
        if not combat:
            return
        if delay:
            action_cost = 0
        else:
            action_cost = 1
        combat.msg("%s passes their turn." % character.name)
        self.take_action(action_cost)

    def do_flee(self, exit_obj):
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
        character = self.char
        combat = self.combat
        combat.remove_afk(character)
        if self.covering_targs:
            character.msg("You cannot attempt to run while covering others' retreat.")
            character.msg("Stop covering them first if you wish to try to run.")
            return
        if character not in combat.ndb.flee_success:
            if character in combat.ndb.fleeing:
                character.msg("You are already attempting to flee. If no one stops you, executing "
                              "flee next turn will let you get away.")
                return
            combat.ndb.fleeing.append(character)
            character.msg("If no one is able to stop you, executing flee next turn will let you run away.")
            character.msg("Attempting to flee does not take your action this turn. You may still take an action.")
            combat.msg("%s begins to try to withdraw from combat." % character.name, exclude=[character])
            self.flee_exit = exit_obj
            return
        # we can flee for the hills
        if not exit_obj.access(character, 'traverse'):
            character.msg("You are not permitted to flee that way.")
            return
        # this is the command that exit_obj commands use
        exit_obj.at_traverse(character, exit_obj.destination, allow_follow=False)
        combat.msg("%s has fled from combat." % character.name)
        combat.remove_combatant(character)

    def do_stop_flee(self, target):
        """
        Try to stop a character from fleeing. Lists of who is stopping who from running
        are all stored in lists inside the CombataData objects for every character
        in the fighter_data dict. Whether attempts to stop players from running works
        is determined at the start of each round when initiative is rolled. The person
        attempting to flee must evade every person attempting to stop them.
        """
        character = self.char
        combat = self.combat
        combat.remove_afk(character)
        t_fite = target.combat
        if self.block_flee == target:
            character.msg("You are already attempting to stop them from fleeing.")
            return
        if target in self.covering_targs:
            character.msg("It makes no sense to try to stop the retreat of someone you are covering.")
            return
        # check who we're currently blocking. we're switching from them
        prev_blocked = self.block_flee
        if prev_blocked:
            # if they're still in combat (in fighter data), we remove character from blocking them
            prev_blocked = prev_blocked.combat
            if prev_blocked:
                if character in prev_blocked.blocker_list:
                    prev_blocked.blocker_list.remove(character)
        # new person we're blocking
        self.block_flee = target
        if character not in t_fite.blocker_list:
            # add character to list of people blocking them
            t_fite.blocker_list.append(character)
        combat.msg("%s moves to stop %s from being able to flee." % (character.name, target.name))

    def add_defender(self, guard):
        """
        add_defender can be called as a way to enter combat, so we'll
        be handling a lot of checks and messaging here. If checks are
        successful, we add the guard to combat, and set them to protect the
        protected character.
        """
        protected = self.char
        combat = self.combat
        if not protected or not guard:
            return
        if not combat:
            return
        if protected.location != combat.ndb.combat_location or guard.location != combat.ndb.combat_location:
            return
        if guard.db.passive_guard:
            return
        if not guard.conscious:
            return
        if guard not in combat.ndb.combatants:
            combat.add_combatant(guard)
            guard.msg("{rYou enter combat to protect %s.{n" % protected.name)
        if guard not in self.defenders:
            self.defenders.append(guard)
            combat.msg("%s begins protecting %s." % (guard.name, protected.name))
        fdata = guard.combat
        if fdata:
            fdata.guarding = protected

    def remove_defender(self, guard):
        """
        If guard is currently guarding protected, make him stop doing so.
        Currently not having this remove someone from a .db.defenders
        attribute - these changes are on a per combat basis, which include
        removal for temporary reasons like incapacitation.
        """
        protected = self.char
        combat = self.combat
        if not protected or not guard:
            return
        if guard in self.defenders:
            self.defenders.remove(guard)
            if combat:
                combat.msg("%s is no longer protecting %s." % (guard.name, protected.name))

    def get_defenders(self):
        """
        Returns list of defenders of a target.
        """
        return [ob for ob in self.defenders if ob.combat.can_act]

    def clear_blocked_by_list(self):
        """
        Removes us from defending list for everyone defending us.
        """
        if self.blocker_list:
            for ob in self.blocker_list:
                ob = ob.combat
                if ob:
                    ob.block_flee = None

    def change_stance(self, new_stance):
        """
        Updates character's combat stance
        """
        self.char.msg("Stance changed to %s." % new_stance)
        self.stance = new_stance
        self.changed_stance = True

    def begin_covering(self, targlist):
        """
        Character covers the retreat of characters in targlist, represented by
        CharacterCombatData.covering_targs list and CharacterCombatData.covered_by
        list. Covered characters will succeed in fleeing automatically, but there
        are a number of restrictions. A covering character cannot be covered by
        anyone else.
        """
        character = self.char
        for targ in targlist:
            if targ in self.covered_by:
                character.msg("%s is already covering you. You cannot cover their retreat." % targ.name)
            elif targ in self.covering_targs:
                character.msg("You are already covering %s's retreat." % targ.name)
            elif targ == self.block_flee:
                character.msg("Why would you cover the retreat of someone you are trying to catch?")
            else:
                self.covering_targs.append(targ)
                targ.combat.covered_by.append(character)
                character.msg("You begin covering %s's retreat." % targ.name)
    
    def stop_covering(self, targ=None, quiet=True):
        """
        If target is not specified, remove everyone we're covering. Otherwise
        remove targ.
        """
        character = self.char
        if not targ:
            if character.combat.covering_targs:
                character.msg("You will no longer cover anyone's retreat.")
                character.combat.covering_targs = []
                return
            if not quiet:
                character.msg("You aren't covering anyone's retreat currently.")
            return
        character.combat.covering_targs.remove(targ)
        character.msg("You no longer cover %s's retreat." % targ.name)

    def clear_covered_by_list(self):
        """
        Removes us from list of anyone covering us.
        """
        character = self.char
        if self.covered_by:
            for covered_by_charob in self.covered_by:
                cov_data = covered_by_charob.combat
                if cov_data and cov_data.covering_targs:
                    self.stop_covering(character)
