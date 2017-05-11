"""
Npc guards, which are connected to an AgentOb instance,
which is itself connected to an Agent instance. The Agent
instance determines the type of agents (guards, spies, etc),
and how many are currently unassigned. AgentOb is for assigned
agents, and stores how many, and this object which acts as its
in-game representation on the grid.

For this object, our values are populated by setup_agent, while
we already have the 'agentob' property given by the related
OneToOne field from our associated AgentOb.

We come into being in one of two ways:
1) We're assigned to an individual player as that player-character's
agents, who can them summon them.
2) A player is in a square that is marked as having the attribute
'unassigned_guards' which points to an Agent instance, and then
should have the cmdset in that room that allows them to draw upon
those guards if they meet certain criteria. If they execute that
command, it then summons guards for that player character.

"""
from typeclasses.characters import Character
from .npc_types import (get_npc_stats, get_npc_desc, get_npc_skills,
                        get_npc_singular_name, get_npc_plural_name, get_npc_weapon,
                        get_armor_bonus, get_hp_bonus, primary_stats,
                        assistant_skills, spy_skills, get_npc_stat_cap, check_passive_guard,
                        COMBAT_TYPES, get_innate_abilities, ABILITY_COSTS)
from world.stats_and_skills import (do_dice_check, get_stat_cost, get_skill_cost,
                                    PHYSICAL_STATS, MENTAL_STATS, SOCIAL_STATS)
import time


class Npc(Character):
    """
    NPC objects

    """    
    # ------------------------------------------------
    # PC command methods
    # ------------------------------------------------
    def attack(self, targ, lethal=False):
        """
        Attack a given target. If lethal is False, we will not kill any
        characters in combat.
        """
        self.execute_cmd("+fight %s" % targ)
        if lethal:
            self.execute_cmd("kill %s" % targ)
        else:
            self.execute_cmd("attack %s" % targ)
        # if we're ordered to attack, don't vote to end
        self.combat.wants_to_end = False
    
    def stop(self):
        """
        Stop attacking/exit combat.
        """
        self.combat.wants_to_end = True
        if self.combat.combat:
            self.combat.reset()
            self.combat.setup_phase_prep()

    def _get_passive(self):
        return self.db.passive_guard or False

    def _set_passive(self, val):
        if val:
            self.db.passive_guard = True
            self.stop()
        else:
            self.db.passive_guard = False
            self.combat.wants_to_end = False
    passive = property(_get_passive, _set_passive)

    @property
    def discreet(self):
        return self.db.discreet_guard or False

    @discreet.setter
    def discreet(self, val):
        if val:
            self.db.discreet_guard = True
        else:
            self.db.discreet_guard = False

    # ------------------------------------------------
    # Inherited Character methods
    # ------------------------------------------------
    def at_object_creation(self):
        """
        Called once, when this object is first created.
        """
        # BriefMode is for toggling brief descriptions from rooms
        self.db.briefmode = False
        # identification attributes about our player
        self.db.player_ob = None
        self.db.dice_string = "Default Dicestring"
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.db.automate_combat = True
        self.db.damage = 0
        self.at_init()
    
    def resurrect(self, *args, **kwargs):
        """
        Cue 'Bring Me Back to Life' by Evanessence.
        """
        self.db.health_status = "alive"
        if self.location:
            self.location.msg_contents("{w%s has returned to life.{n" % self.name)

    def fall_asleep(self, uncon=False, quiet=False, **kwargs):
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

    def wake_up(self, quiet=False):
        """
        Wakes up.
        """
        self.db.sleep_status = "awake"
        if self.location:
            self.location.msg_contents("%s wakes up." % self.name)
            combat = self.location.ndb.combat_manager
            if combat and self in combat.ndb.combatants:
                combat.wake_up(self)
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
        applied_damage = self.dmg - roll  # how much dmg character has after the roll
        if applied_damage < 0:
            applied_damage = 0  # no remaining damage
        self.db.damage = applied_damage
        if not free:
            self.db.last_recovery_test = time.time()
        return roll
    
    def sensing_check(self, difficulty=15, invis=False, allow_wake=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        roll = do_dice_check(self, stat="perception", stat_keep=True, difficulty=difficulty)
        return roll

    def get_fakeweapon(self, force_update=False):
        if not self.db.fakeweapon or force_update:
            npctype = self._get_npc_type()
            quality = self._get_quality()
            self.db.fakeweapon = get_npc_weapon(npctype, quality)
        return self.db.fakeweapon

    def _set_fakeweapon(self, val):
        self.db.fakeweapon = val

    fakeweapon = property(get_fakeweapon, _set_fakeweapon)

    @property
    def is_npc(self):
        return True

    # npcs are easier to hit than players, and have an easier time hitting
    @property
    def defense_modifier(self):
        return super(Npc, self).defense_modifier - 30

    @property
    def attack_modifier(self):
        return super(Npc, self).attack_modifier + 30

    # ------------------------------------------------
    # New npc methods
    # ------------------------------------------------
    def _get_npc_type(self):
        return self.db.npc_type or 0
    npc_type = property(_get_npc_type)

    def _get_quality(self):
        return self.db.npc_quality or 0
    quality = property(_get_quality)

    @property
    def quantity(self):
        return 1 if self.conscious else 0

    @property
    def weaponized(self):
        return True

    def setup_stats(self, ntype, threat):
        self.db.npc_quality = threat
        for stat, value in get_npc_stats(ntype).items():
            self.attributes.add(stat, value)
        skills = get_npc_skills(ntype)
        for skill in skills:
            skills[skill] += threat
        self.db.skills = skills
        self.db.fakeweapon = get_npc_weapon(ntype, threat)
        self.db.armor_class = get_armor_bonus(self._get_npc_type(), self._get_quality())
        self.db.bonus_max_hp = get_hp_bonus(self._get_npc_type(), self._get_quality())

    @property
    def num_armed_guards(self):
        if self.weaponized:
            return self.quantity
        return 0

    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        # if we don't
        if not keepold:
            self.db.npc_type = ntype
            self.name = sing_name or plural_name or "#%s" % self.id
            self.desc = desc or get_npc_desc(ntype)
        self.setup_stats(ntype, threat)


class MultiNpc(Npc):
    def multideath(self, num, death=False):
        living = self.db.num_living or 0       
        if num > living:
            num = living
        self.db.num_living = living - num
        if death:
            dead = self.db.num_dead or 0            
            self.db.num_dead = dead + num
        else:
            incap = self.db.num_incap or 0
            self.db.num_incap = incap + num

    def get_singular_name(self):
        return self.db.singular_name or get_npc_singular_name(self._get_npc_type())

    def get_plural_name(self):
        return self.db.plural_name or get_npc_plural_name(self._get_npc_type())

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.
        """
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % get_npc_singular_name(self._get_npc_type()))
        if kwargs.get('lethal', True):
            self.multideath(num=1, death=True)
        else:
            self.temp_losses += 1
        self.db.damage = 0

    def fall_asleep(self, uncon=False, quiet=False, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if self.location:
            self.location.msg_contents("{w%s falls %s.{n" % (get_npc_singular_name(self._get_npc_type()),
                                                             "unconscious" if uncon else "asleep"))
        if kwargs.get('lethal', True):
            self.multideath(num=1, death=False)
        else:
            self.temp_losses += 1
        # don't reset damage here since it's used for death check. Reset in combat process

    # noinspection PyAttributeOutsideInit
    def setup_name(self):
        npc_type = self.db.npc_type
        if self.db.num_living == 1 and not self.db.num_dead:
            self.key = self.db.singular_name or get_npc_singular_name(npc_type)
        else:
            if self.db.num_living == 1:
                noun = self.db.singular_name or get_npc_singular_name(npc_type)
            else:
                noun = self.db.plural_name or get_npc_plural_name(npc_type)
            if not self.db.num_living and self.db.num_dead:
                noun = "dead %s" % noun
                self.key = "%s %s" % (self.db.num_dead, noun)
            else:
                self.key = "%s %s" % (self.db.num_living, noun)
        self.save()

    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.num_living = num
        self.db.num_dead = 0
        self.db.num_incap = 0
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        # if we don't 
        if not keepold:
            self.db.npc_type = ntype
            self.db.singular_name = sing_name
            self.db.plural_name = plural_name
            self.desc = desc or get_npc_desc(ntype)
        self.setup_stats(ntype, threat)     
        self.setup_name()

    # noinspection PyAttributeOutsideInit
    def dismiss(self):
        self.location = None
        self.save()

    @property
    def quantity(self):
        num = self.db.num_living or 0
        return num - self.temp_losses

    @property
    def conscious(self):
        return self.quantity > 0

    @property
    def temp_losses(self):
        if self.ndb.temp_losses is None:
            self.ndb.temp_losses = 0
        return self.ndb.temp_losses

    @temp_losses.setter
    def temp_losses(self, val):
        self.ndb.temp_losses = val


class AgentMixin(object):

    @property
    def desc(self):
        self.agent.refresh_from_db(fields=('desc',))
        return self.agent.desc

    @desc.setter
    def desc(self, val):
        self.agent.desc = val
        self.agent.save()

    def setup_agent(self  # type: Retainer or Agent
                    ):
        """
        We'll set up our stats based on the type given by our agent class.
        """
        agent = self.agentob
        agent_class = agent.agent_class
        quality = agent_class.quality or 0
        # set up our stats based on our type
        desc = agent_class.desc
        atype = agent_class.type
        self.setup_npc(ntype=atype, threat=quality, num=agent.quantity, desc=desc)
        self.db.passive_guard = check_passive_guard(atype)
        
    def setup_locks(self  # type: Retainer or Agent
                    ):
        # base lock - the 'command' lock string
        lockfunc = ["command: %s", "desc: %s"]
        player_owner = None
        assigned_char = self.db.guarding
        owner = self.agentob.agent_class.owner
        if owner.player:
            player_owner = owner.player.player
        if not player_owner:
            org_owner = owner.organization_owner
            if assigned_char:
                perm = "rank(2, %s) or id(%s)" % (org_owner.name, assigned_char.id)
            else:
                perm = "rank(2, %s)" % org_owner.name
        else:
            if assigned_char:
                perm = "pid(%s) or id(%s)" % (player_owner.id, assigned_char.id)
            else:
                perm = "pid(%s)" % player_owner.id
        for lock in lockfunc:
            # add the permission to the lock function from above
            # noinspection PyAugmentAssignment
            lock = lock % perm
            # note that this will replace any currently defined 'command' lock
            self.locks.add(lock)

    def assign(self,  # type: Retainer or Agent
               targ):
        """
        When given a Character as targ, we add ourselves to their list of
        guards, saved as an Attribute in the character object.
        """
        guards = targ.db.assigned_guards or []
        if self not in guards:
            guards.append(self)
        targ.db.assigned_guards = guards
        self.db.guarding = targ
        self.setup_locks()
        self.setup_name()
        if self.agentob.quantity < 1:
            self.agentob.quantity = 1
            self.agentob.save()

    def lose_agents(self, num, death=False):
        if num < 1:
            return 0
        self.unassign()

    def gain_agents(self, num):
        self.setup_name()

    # noinspection PyAttributeOutsideInit
    def setup_name(self):
        self.name = self.agent.name

    def unassign(self  # type: Retainer or Agent
                 ):
        """
        When unassigned from the Character we were guarding, we remove
        ourselves from their guards list and then call unassign in our
        associated AgentOb.
        """
        targ = self.db.guarding
        if targ:
            guards = targ.db.assigned_guards or []
            if self in guards:
                guards.remove(self)
        self.stop_follow(unassigning=True)
        self.agentob.unassign()
        self.locks.add("command: false()")
        self.db.guarding = None

    def _get_npc_type(self):
        return self.agent.type

    def _get_quality(self):
        return self.agent.quality or 0
    npc_type = property(_get_npc_type)
    quality = property(_get_quality)
    
    def stop_follow(self,  # type: Retainer or Agent
                    dismiss=True, unassigning=False):
        super(AgentMixin, self).stop_follow()
        # if we're not being unassigned, we dock them. otherwise, they're gone
        if dismiss:
            self.dismiss(dock=not unassigning)
    
    def summon(self,  # type: Retainer or Agent
               summoner=None):
        """
        Have these guards appear to defend the character. This should generally only be
        called in a location that permits it, such as their house barracks, or in a
        square close to where the guards were docked.
        """
        if not summoner:
            summoner = self.db.guarding
        loc = summoner.location
        self.move_to(loc)
        self.follow(self.db.guarding)
        docked_loc = self.db.docked
        if docked_loc and docked_loc.db.docked_guards and self in docked_loc.db.docked_guards:
            docked_loc.db.docked_guards.remove(self)
        self.db.docked = None

    def dismiss(self,  # type: Retainer or Agent
                dock=True):
        """
        Dismisses our guards. If they're not being dismissed permanently, then
        we dock them at the location they last occupied, saving it as an attribute.
        """
        loc = self.location
        # being dismissed permanently while gone
        if not loc:
            docked = self.db.docked
            if docked and docked.db.docked_guards and self in docked.db.docked_guards:
                docked.db.docked_guards.remove(self)
            return       
        self.db.prelogout_location = loc
        if dock:
            self.db.docked = loc
            docked = loc.db.docked_guards or []
            if self not in docked:
                docked.append(self)
            loc.db.docked_guards = docked
        loc.msg_contents("%s have been dismissed." % self.name)
        # noinspection PyAttributeOutsideInit
        self.location = None
        if self.ndb.combat_manager:
            self.ndb.combat_manager.remove_combatant(self)

    def at_init(self  # type: Retainer or Agent
                ):
        try:
            if self.location and self.db.guarding and self.db.guarding.location == self.location:
                self.follow(self.db.guarding)
        except AttributeError:
            import traceback
            traceback.print_exc()

    def get_stat_cost(self,  # type: Retainer or Agent
                      attr):
        """
        Get the cost of a stat based on our current
        rating and the type of agent we are.
        """
        atype = self.agent.type
        stats = primary_stats.get(atype, [])
        base = get_stat_cost(self, attr)
        if attr not in stats:
            base *= 2
        xpcost = base
        rescost = base
        if attr in MENTAL_STATS:
            restype = "economic"
        elif attr in SOCIAL_STATS:
            restype = "social"
        elif attr in PHYSICAL_STATS:
            restype = "military"
        else:  # special stats
            restype = "military"
        return xpcost, rescost, restype
    
    def get_skill_cost(self, attr):
        """
        Get the cost of a skill based on our current rating and the
        type of agent that we are.
        """
        restype = "military"
        atype = self.agent.type
        primary_skills = get_npc_skills(atype)
        base = get_skill_cost(self, attr)
        if attr not in primary_skills:
            base *= 2
        xpcost = base
        rescost = base
        if attr in spy_skills:
            restype = "social"
        elif attr in assistant_skills:
            restype = "economic"
        return xpcost, rescost, restype

    def get_stat_maximum(self, attr):
        """
        Get the current max for a stat based on the type
        of agent we are. If it's primary stats, == to our
        quality level. Otherwise, quality - 1.
        """
        atype = self.agent.type
        pstats = primary_stats.get(atype, [])
        if attr in pstats:
            cap = self.agent.quality
        else:
            cap = self.agent.quality - 1
        typecap = get_npc_stat_cap(atype, attr)
        if cap > typecap:
            cap = typecap
        return cap
    
    def get_skill_maximum(self, attr):
        """
        Get the current max for a skill based on the type
        of agent we are
        """
        atype = self.agent.type
        primary_skills = get_npc_skills(atype)
        if attr in primary_skills:
            return self.agent.quality
        return self.agent.quality - 1

    @property
    def agent(self  # type: Retainer or Agent
              ):
        """
        Returns the agent type that this object belongs to.
        """
        return self.agentob.agent_class

    def train_agent(self, trainer):
        trainer.msg("This type of agent cannot be trained.")
        return False
    
    @property
    def training_skill(self):
        if "animal" in self.agent.type_str:
            return "animal ken"
        return "teaching"

    @property
    def species(self  # type: Retainer or Agent
                ):
        if "animal" in self.agent.type_str:
            default = "animal"
        else:
            default = "human"
        return self.db.species or default
    
    @property
    def owner(self):
        return self.agent.owner
    
    def inform_owner(self, text):
        """Passes along an inform to our owner."""
        self.owner.inform_owner(text, category="Agents")

    @property
    def weaponized(self  # type: Retainer or Agent
                   ):
        if self.npc_type in COMBAT_TYPES:
            return True
        if self.weapons_hidden:
            return False
        try:
            if self.weapondata.get('weapon_damage', 1) > 2:
                return True
        except (AttributeError, KeyError):
            return False


class Retainer(AgentMixin, Npc):

    def display(self):
        if self.db.guarding:
            guarding_name = self.db.guarding.key
        else:
            guarding_name = "None"
        msg = "{wAssigned to:{n %s " % guarding_name
        msg += "{wLocation:{n %s\n" % (self.location or self.db.docked or "Home Barracks")
        return msg

    # noinspection PyUnusedLocal
    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.setup_stats(ntype, threat)
        self.name = self.agentob.agent_class.name

    @property
    def buyable_abilities(self):
        """
        Returns a list of ability names that are valid to buy for this agent
        """
        abilities = ()
        innate = get_innate_abilities(self.agent.type)
        abilities += innate
        # to do - get abilities based on level and add em to the ones they get innately
        return abilities

    # noinspection PyUnusedLocal
    def get_ability_maximum(self, attr):
        """Returns max for an ability that we can buy"""
        # to do - make it different based on off-classes
        return self.agent.quality + 1

    # noinspection PyMethodMayBeStatic
    def get_ability_cost(self, attr):
        cost, res_type = ABILITY_COSTS.get(attr)
        return cost, cost, res_type

    def can_train(self, trainer):
        skill = trainer.db.skills.get(self.training_skill, 0)
        if not skill:
            trainer.msg("You must have %s skill to train them." % self.training_skill)
            return False
        currently_training = trainer.db.currently_training or []
        if self.db.trainer == trainer:
            trainer.msg("They have already been trained by %s this week." % self.db.trainer)
            return False
        # because of possible cache errors we'll check by ID rather than by self
        currently_training_ids = [ob.id for ob in currently_training]
        if self.id in currently_training_ids:
            trainer.msg("They have already been trained by you this week.")
            return False
        return True

    def train_agent(self, trainer):
        """
        Gives xp to this agent if they haven't been trained yet this week.
        The skill used to train them is based on our type - animal ken for
        animals, teaching for non-animals.
        """
        self.db.trainer = trainer
        currently_training = trainer.db.currently_training or []
        if self in currently_training:
            # this should not be possible. Nonetheless, it has happened.
            trainer.msg("Error: You have already trained this agent despite the check saying you hadn't.")
            return
        # do training roll
        roll = do_dice_check(trainer, stat="command", skill=self.training_skill, difficulty=0, quiet=False)
        self.agent.xp += roll
        self.agent.save()
        # redundant attribute to try to combat cache errors
        num_trained = trainer.db.num_trained or len(currently_training)
        num_trained += 1
        trainer.db.num_trained = num_trained
        currently_training.append(self)
        trainer.db.currently_training = currently_training
        trainer.msg("You have trained %s, giving them %s xp." % (self, roll))
        msg = "%s has trained %s, giving them %s xp." % (trainer, self, roll)
        self.inform_owner(msg)
    

class Agent(AgentMixin, MultiNpc):
    # -----------------------------------------------
    # AgentHandler Admin client methods
    # -----------------------------------------------

    # noinspection PyAttributeOutsideInit
    def setup_name(self):
        a_type = self.agentob.agent_class.type
        noun = self.agentob.agent_class.name
        if not noun:
            if self.db.num_living == 1:
                noun = get_npc_singular_name(a_type)
            else:
                noun = get_npc_plural_name(a_type)
        if self.db.num_living:
            self.key = "%s %s" % (self.db.num_living, noun)
        else:
            self.key = noun
        self.save()     

    def lose_agents(self, num, death=False):
        """
        Called whenever we lose one of our agents, due to them being recalled
        or dying.
        """
        if num < 0:
            raise ValueError("Must pass a positive integer to lose_agents.")
        if num > self.db.num_living:
            num = self.db.num_living
        self.multideath(num, death)
        self.agentob.lose_agents(num)
        self.setup_name()       
        if self.db.num_living <= 0:
            self.unassign()
        return num
    
    def gain_agents(self, num):
        self.db.num_living += num
        self.setup_name()
        
    def display(self):
        msg = "\n{wGuards:{n %s\n" % self.name
        if self.db.guarding:
            msg += "{wAssigned to:{n %s {wOwner{n:%s\n" % (self.db.guarding.key, self.agent.owner)
        msg += "{wLocation:{n %s\n" % (self.location or self.db.docked or "Home Barracks")
        return msg

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location.
        """
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % get_npc_singular_name(self._get_npc_type()))
        self.lose_agents(num=1, death=True)
        self.db.damage = 0
