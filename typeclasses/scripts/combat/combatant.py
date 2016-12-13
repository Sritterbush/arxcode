from random import randint, choice
import combat_settings
from world.stats_and_skills import do_dice_check


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


class CharacterCombatData(object):
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
    def __init__(self, character, combat):
        self.combat = combat
        self.char = character
        # for healing us to how we were before in nonlethal fights
        self.prefight_damage = character.db.damage or 0
        if character.db.num_living:
            self.multiple = True
            self.num = character.db.num_living
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
            self.num = 1
            self.automated = False
            self.autoattack = character.db.autoattack or False
            self.base_name = character.name
            self.plural_name = character.name
        if not character.player:
            self.automated = True
            self.autoattack = True
        self.rank = 1  # combat rank/position. 1 is 'front line'
        self.shield = character.db.shield
        if hasattr(character, 'weapondata'):
            print "Found weapondata for %s" % self.char
            self.setup_weapon(character.weapondata)
            print "weapon = %s" % self.weapon
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
        self.stance = character.db.combat_stance  # defensive, aggressive, etc
        if self.stance not in combat_settings.COMBAT_STANCES:
            self.stance = "balanced"
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

    # noinspection PyAttributeOutsideInit
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

    def msg(self, mssg):
        self.char.msg(mssg)

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
            return int((dmg * 100.0) / (self.char.max_hp * 10.0))
        except Exception:
            return 0

    @property
    def atk_penalties(self):
        return self.wound_penalty + self.fatigue_atk_penalty()

    @property
    def def_penalties(self):
        return self.wound_penalty + self.fatigue_def_penalty()

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
            # if we order them to stand down, they do nothing
            if self.wants_to_end:
                self.combat.vote_to_end(self.char)
                self.set_queued_action("pass")
                return
        self.remaining_attacks = self.num_attacks
        self.validate_targets()
        if self.autoattack:
            self.validate_targets(self.do_lethal)
            if self.targets and self.status == "active":
                targ = self.prev_targ
                if not targ:
                    targ = choice(self.targets)
                mssg = "{rYou attack %s.{n" % targ
                defenders = self.combat.get_defenders(targ)
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
            gdata = self.combat.get_fighter_data(guarding.id)
            if gdata:
                for foe in gdata.foelist:
                    self.add_foe(foe)
        fighters = [self.combat.get_fighter_data(ob.id) for ob in self.foelist if self.combat.get_fighter_data(ob.id)]
        if not lethal:
            self.targets = [fighter.char for fighter in fighters if fighter.status == 'active']
        else:
            self.targets = [fighter.char for fighter in fighters]

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
            self.combat.character_ready(self.char)

    def do_turn_actions(self, took_actions=False):
        """
        Takes any queued action we have and returns a result. If we have no
        queued action, return None. If our queued action can no longer be
        completed, return None. Otherwise, return a result.
        """
        if self.combat.ndb.phase != 2:
            return False
        remaining_attacks = self.remaining_attacks
        if self.char in self.combat.ndb.flee_success:
            # cya nerds
            self.combat.do_flee(self.char, self.flee_exit)
            return True
        q = self.queued_action       
        if not q:
            # we have no queued action, so player must act
            if self.automated:
                # if we're automated and have no action, pass turn
                self.combat.do_pass(self.char)
            return took_actions
        lethal = q.qtype == "kill"
        if q.qtype == "pass":
            self.combat.do_pass(self.char)
            self.msg(q.msg)
            return True
        self.validate_targets(lethal)
        if q.qtype == "attack" or q.qtype == "kill":
            # if we have multiple npcs in us, we want to spread out
            # our attacks. validate_targets will only show non-lethal targets
            targ = q.targ
            if not self.targets:
                self.msg("You no longer have any valid targets to autoattack.")
                if self.automated:
                    self.combat.do_pass(self.char)
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
                defenders = self.combat.get_defenders(targ)
                # if our target selection has defenders, we hit one of them instead
                if defenders:
                    targ = choice(defenders)
            # set who we attacked
            self.prev_targ = targ
            self.combat.do_attack(self.char, targ, attack_penalty=q.atk_pen, dmg_penalty=-q.dmg_mod)
        # check to make sure that remaining attacks was decremented by attacking
        if self.remaining_attacks == remaining_attacks:
            self.remaining_attacks -= 1
        if self.remaining_attacks > 0:
            return self.do_turn_actions(took_actions=True)
        else:
            if self.combat.ndb.active_char == self.char:
                self.combat.next_character_turn()
            return True

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
        Returns our roll to hit with an attack. Targ is not a charater
        object, but CombatData object. Half of our roll is randomized.
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
    def roll_defense(self, att, weapon=None, penalty=0, a_roll=None):
        """
        Returns our roll to avoid being hit. Att is not character, but
        CombatData object. We use the highest roll out of parry, block,
        and dodge. Half of our roll is then randomized.
        """
        # making defense easier than attack to slightly lower combat lethality
        diff = -2  # base difficulty before mods
        self.roll_fatigue()
        penalty += self.def_penalties
        diff += penalty
        # it gets increasingly hard to defend the more times you're attacked per round
        diff += self.times_attacked * 10
        self.times_attacked += 1
        total = None
        if att.can_be_parried and self.can_parry:
            parry_roll = int(do_dice_check(self.char, stat=self.attack_stat, skill=self.attack_skill, difficulty=diff))
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
                total += block_roll
            elif block_roll > total:
                total = (total + block_roll)/2
        else:
            block_roll = -1000
        if att.can_be_dodged and self.can_dodge:
            try:
                dodge_diff = diff + self.dodge_penalty
            except (AttributeError, TypeError, ValueError):
                dodge_diff = diff
            dodge_roll = int(do_dice_check(self.char, stat="dexterity", skill="dodge", difficulty=dodge_diff))
            if dodge_roll >= 2:
                dodge_roll = (dodge_roll/2) + randint(0, (dodge_roll/2))
            if not total:
                total = dodge_roll
            elif dodge_roll > 0:
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
        self.num_actions += 1 + (0.08 * armor_penalty)
        penalty += self.num_actions + 20
        keep = self.fatigue_soak + 2
        myroll = do_dice_check(self.char, stat_list=["strength", "stamina", "dexterity", "willpower"],
                               skill="athletics", keep_override=keep, difficulty=int(penalty), divisor=2)
        myroll += randint(0, 25)
        if myroll < 0 and self.fatigue_gained_this_turn < 2:
            self.fatigue_penalty += 1
            self.fatigue_gained_this_turn += 1

    @property
    def fatigue_soak(self):
        soak = max(self.char.db.willpower or 0, self.char.db.stamina or 0)
        try:
            soak += self.char.db.skills.get("athletics", 0)
        except (AttributeError, TypeError, ValueError):
            pass
        return soak

    @property
    def fatigue_penalty(self):
        fat = self._fatigue_penalty
        soak = self.fatigue_soak
        fat -= soak
        if fat < 0:
            return 0
        return fat

    @fatigue_penalty.setter
    def fatigue_penalty(self, value):
        self._fatigue_penalty = value

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
