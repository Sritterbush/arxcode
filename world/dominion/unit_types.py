"""
Unit types:

All the stats for different kinds of military units are defined here and
will be used at runtime.
"""
import traceback
from game.dominion.combat_grid import PositionActor
from random import randint

# The corresponding database model will save type as an integer value
INFANTRY = 0
PIKE = 1
CAVALRY = 2
ARCHERS = 3
WARSHIP = 4
SIEGE_WEAPON = 5

#silver upkeep costs for 1 of a given unit
upkeep = {
    INFANTRY: 10,
    PIKE: 15,
    CAVALRY: 30,
    ARCHERS: 20,
    WARSHIP: 1000,
    SIEGE_WEAPON: 1000,
    }

food = {
    INFANTRY: 1,
    PIKE: 1,
    CAVALRY: 1,
    ARCHERS: 1,
    WARSHIP: 20,
    SIEGE_WEAPON: 20,
    }

def get_type_str(utype):
    if utype == INFANTRY:
        return "infantry"
    if utype == PIKE:
        return "pike"
    if utype == CAVALRY:
        return "cavalry"
    if utype == ARCHERS:
        return "archers"
    if utype == WARSHIP:
        return "warships"
    if utype == SIEGE_WEAPON:
        return "siege weapons"

def type_from_str(ustr):
    ustr = ustr.lower()
    if ustr == "infantry":
        return INFANTRY
    if ustr == "pike":
        return PIKE
    if ustr == "cavalry":
        return CAVALRY
    if ustr == "archers":
        return ARCHERS
    if ustr == "warships":
        return WARSHIP
    if ustr == "siege weapons":
        return SIEGE_WEAPON

def get_combat(unit_model, grid=None):
    """
    Returns the type of unit class for combat that corresponds
    to a unit's database model instance. Because we don't want to have
    the entire weekly maintenance process that handles all dominion
    commands stop for an exception, we do a lot of handling with default
    values.
    """
    try:
        u_type = types[unit_model.unit_type]
    except AttributeError:
        print "ERROR: No dbobj passed to get_combat! Using default."
        u_type = UnitStats
    except KeyError:
        print "ERROR: Unit type not found for unit %s with type %s! Defaulting to infantry." % (unit_model.id, unit_model.unit_type)
        traceback.print_exc()
        u_type = Infantry
    unit = u_type(unit_model, grid)
    return unit
    
class UnitStats(PositionActor):
    """
    Contains all the stats for a military unit.
    """
    def __init__(self, dbobj, grid):
        super(UnitStats, self).__init__(grid)
        self.formation = None
        self.log = None
        self.name = "Default"
        # how powerful we are in melee combat
        self.melee_damage = 1
        # how powerful we are at range
        self.range_damage = 0
        # our defense against attacks
        self.defense = 0
        # defense against ANY number of attackers. Super powerful
        self.multi_defense = 0
        self.storm_damage = 0
        # how much damage each individual in unit can take
        self.hp = 1
        # if we are a ranged unit, this value is not 0. Otherwise it is 0.
        self.range = 0
        # the minimum range an enemy must be for us to use our ranged attack
        self.min_for_range = 1
        # our value in siege
        self.siege = 0
        self.movement = 0
        # how much damage we've taken
        self.damage = 0
        # how many troops from unit have died
        self.losses = 0
        self.routed = False
        self.destroyed = False
        # the target we are currently trying to engage
        self.target = None
        # whether we are currently storming a castle
        self.storming = False
        # if we know a castle position to storm
        self.storm_targ_pos = None
        # A castle object if we're in it
        self.castle = None
        self.flanking = None
        self.flanked_by = None
        try:
            self.commander = dbobj.commander
            if dbobj.army:
                self.morale = dbobj.army.morale
                self.commander = self.commander or dbobj.army.commander
            else:
                self.morale = 80
            self.level = dbobj.level
            self.equipment = dbobj.equipment
            self.type = dbobj.unit_type
            self.quantity = dbobj.quantity
            self.starting_quantity = dbobj.quantity
            self.dbobj = dbobj
        except AttributeError:
            print "ERROR: No dbobj for UnitStats found! Using default values."
            traceback.print_exc()
            self.morale = 0
            self.level = 0
            self.equipment = 0
            self.type = INFANTRY
            self.quantity = 1
            self.starting_quantity = 1
            self.dbobj = None
            self.commander = None
            
    def _targ_in_range(self):
        if not self.target:
            return False
        return (self.check_distance_to_actor(self.target) <= self.range)
    targ_in_range = property(_targ_in_range)
    
    def _unit_active(self):
        return not self.routed and not self.destroyed
    active = property(_unit_active)
    
    def _unit_value(self):
        try:
            value = upkeep[self.type]
        except KeyError:
            print "ERROR: Type %s not found for unit." % self.type
            value = 20
        return self.quantity * value
    value = property(_unit_value)
    def __str__(self):
        name = "%s's %s(%s)" % (str(self.formation), self.name, self.quantity)
   
    def swing(self, target, atk):
        """
        One unit trying to do damage to another. Defense is a representation
        of how much resistance to damage each individual unit has against
        attacks. For that reason, it's limited by the number of attacks the
        unit is actually receiving. multi_defense, however, is an additional
        defense that scales with the number of attackers, representing some
        incredible durability that can ignore small units. Essentially this
        is for dragons, archmages, etc, who are effectively war machines.
        """
        defense = target.defense
        defense += target.defense * target.level
        defense += target.defense * target.equipment
        def_mult = target.quantity
        if self.quantity < def_mult:
            def_mult = self.quantity
        defense *= def_mult
        # usually this will be 0. multi_defense is for dragons, mages, etc
        defense += target.multi_defense * self.quantity
        def_roll = randint(0, defense)
        if target.commander:
            def_roll += def_roll * target.commander.warfare
        if target.castle:
            def_roll += def_roll * target.castle.level
        attack = atk * self.quantity
        attack += atk * self.level
        attack += atk * self.equipment
        # have a floor of half our attack
        atk_roll = randint(attack/2, attack)
        if self.commander:
            atk_roll += atk_roll * self.commander.warfare
        damage = atk_roll - def_roll
        if damage < 0: damage = 0
        target.damage += damage
        self.log.info("%s attacked %s. Atk roll: %s Def roll: %s\nDamage:%s" % (str(self), str(target), atk_roll, def_roll))
    
    def ranged_attack(self):
        if not self.range:
            return
        if not self.target:
            return
        if not self.targ_in_range:
            return
        self.swing(target, self.range_damage)
        
    def melee_attack(self):
        if not self.target:
            return
        if not self.targ_in_range:
            return
        if self.storming:
            self.swing(target, self.storm_damage)
        else:
            self.swing(target, self.melee_damage)
        target.swing(self, target.melee_damage)
   
    def advance(self):
        if self.target and not self.targ_in_range:
            self.move_toward_actor(self.target, self.movement)
        elif self.storm_targ_pos:
            try:
                x,y,z = self.storm_targ_pos
                self.move_toward_position(x, y, z, self.movement)
            except:
                print "ERROR when attempting to move toward castle. storm_targ_pos: %s" % str(self.storm_targ_pos)
        self.log.info("%s has moved. Now at pos: %s" % (self(str), str(self.position)))
    
    def cleanup(self):
        """
        Apply damage, destroy units/remove them, make units check for rout, check
        for rally.
        """
        if not self.damage:
            return
        hp = self.hp
        hp += self.hp * self.level
        hp += self.hp * self.equipment
        if self.damage >= hp:
            losses = self.damage/hp
            # save remainder
            self.losses += losses
            self.quantity -= losses
            if self.quantity <= 0:
                self.quantity = 0
                self.destroyed = True
                self.info.log("%s has been destroyed." % (str(self)))
                return
            self.damage %= hp
            self.rout_check()
        if self.routed:
            self.rally_check()
        
    def rout_check(self):
        """
        Chance for the unit to rout. Roll 1-100 to beat a difficulty number
        to avoid routing. Difficulty is based on our percentage of losses +
        any morale rating we have below 100. Reduced by 5 per troop level
        and commander level.
        """
        percent_losses = float(self.losses)/float(self.starting_quantity)
        percent_losses = int(percent_losses * 100)
        morale_penalty = 100 - self.morale
        difficulty = percent_losses + morale_penalty
        difficulty -= 5 * self.level
        if self.commander:
            difficulty -= 5 * self.commander.warfare
        if randint(1, 100) < difficulty:
            self.routed = True
    
    def rally_check(self):
        """
        Rallying is based almost entirely on the skill of the commander. It's
        a 1-100 roll trying to reach 100, with the roll being multiplied by
        our commander's level(+1). We add +10 for each level of troop training
        of the unit, as elite units will automatically rally. Yes, this means
        that it is impossible for level 10 or higher units to rout.
        """
        level = 0
        if self.commander:
            level = self.commander.warfare
        # a level 0 or no commander just means roll is unmodified
        level += 1
        roll = randint(1, 100)
        roll *= level
        roll += 10 * self.level
        self.log.info("%s has routed and rolled %s to rally." % (str(self), roll))
        if roll >= 100:
            self.routed = False
    
    def check_target(self):
        if not self.target:
            return
        if self.target.active:
            return self.target
    
    def acquire_target(self, enemy_formation):
        """
        Retrieve a target from the enemy formation based on various
        targeting criteria.
        """
        self.target = enemy_formation.get_target_from_formation_for_attacker(self)       

class Infantry(UnitStats):
    def __init__(self, dbobj, grid):
        super(Infantry, self).__init__(dbobj, grid)
        self.name = "Infantry"
        self.melee_damage = 3
        self.storm_damage = 3
        self.defense = 1
        self.hp = 30
        self.movement = 2

class Pike(UnitStats):
    def __init__(self, dbobj, grid):
        super(Pike, self).__init__(dbobj, grid)
        self.name = "Pike"
        self.melee_damage = 5
        self.storm_damage = 3
        self.defense = 1
        self.hp = 30
        self.movement = 2

class Cavalry(UnitStats):
    def __init__(self, dbobj, grid):
        super(Cavalry, self).__init__(dbobj, grid)
        self.name = "Cavalry"
        self.melee_damage = 10
        self.storm_damage = 3
        self.defense = 3
        self.hp = 60
        self.movement = 6


class Archers(UnitStats):
    def __init__(self, dbobj, grid):
        super(Archers, self).__init__(dbobj, grid)
        self.name = "Archers"
        self.melee_damage = 1
        self.range_damage = 5
        self.storm_damage = 3
        self.defense = 1
        self.hp = 20
        self.range = 6
        self.siege = 5
        self.movement = 2

class Warship(UnitStats):
    def __init__(self, dbobj, grid):
        super(Warship, self).__init__(dbobj, grid)
        self.name = "Warship"
        self.movement = 5

class SiegeWeapon(UnitStats):
    def __init__(self, dbobj, grid):
        super(SiegeWeapon, self).__init__(dbobj, grid)
        self.name = "SiegeWeapon"
        self.movement = 1
        self.melee_damage = 20
        self.range_damage = 300
        self.defense = 10
        self.hp = 400
        self.storm_damage = 600


types = {
    INFANTRY: Infantry,
    PIKE: Pike,
    CAVALRY: Cavalry,
    ARCHERS: Archers,
    WARSHIP: Warship,
    SIEGE_WEAPON: SiegeWeapon,
    }
