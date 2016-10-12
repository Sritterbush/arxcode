"""
Template file for saving values of stats and skills.
Will add more class functionality later, with helper
functions and so on.

Stats are defined as an attribute from the name of the
stat, listed in the _valid_stats_ tuple. Skills and
abilities are held in dictionaries defined in
character.db.skills and character.db.abilities,
respectively. So while you can do
char.db.strength, you would have to access
a skill by char.db.skills.get('brawl', 0), for example.
"""
from random import randint


#tuples of allowed stats and skills

PHYSICAL_STATS = ("strength", "dexterity", "stamina")
SOCIAL_STATS = ("charm", "command", "composure")
MENTAL_STATS = ("intellect", "perception", "wits")
MAGIC_STATS = ("mana", "luck", "willpower")
_valid_stats_ = PHYSICAL_STATS + SOCIAL_STATS + MENTAL_STATS + MAGIC_STATS
_combat_skills_ = ("athletics", "brawl", "dodge", "archery", "small wpn", "medium wpn",
                   "huge wpn", "stealth", "survival")
_social_skills_ = ("intimidation", "leadership","manipulation","seduction","diplomacy",
                    "propaganda", "empathy","etiquette","performance")
_general_skills_ = ("riddles","legerdemain","ride","investigation",
                    "law", "linguistics", "medicine", "occult",  "stewardship", "theology",
                    "streetwise", "agriculture", "economics", "teaching", "war",
                    "animal ken","artwork", "sailing")
_crafting_skills_ = ('sewing', 'smithing', 'tanning', 'alchemy', 'woodworking')
_valid_skills_ = _combat_skills_ + _social_skills_ + _general_skills_ + _crafting_skills_

_crafting_abilities_ = ('tailor', 'weaponsmith', 'armorsmith', 'leatherworker', 'apothecary',
                        'carpenter', 'jeweler')
_fighting_abilities_ = ('duelist', 'berserker', 'ninja', 'blademaster', 'adept')
_magical_abilities_ = ('abyssal', 'dreamer', 'bloodmage', 'primal', 'celestial')
_cunning_abilities_ = ('assassin', 'spy', 'thief', 'mummer')
_valid_abilities_ = _crafting_abilities_ + _fighting_abilities_ + _magical_abilities_ + _cunning_abilities_
_domskills_ = ("population", "income", "farming", "productivity",
                     "upkeep", "loyalty", "warfare")
_parent_abilities_ = {'sewing': ['tailor'], 'smithing':['weaponsmith', 'armorsmith', 'jeweler'],
                      'tanning': ['leatherworker'],
                      'alchemy': ['apothecary'], 'woodworking':['apothecary']}
# Default difficulty for an 'easy' task for a person with a skill of 1
DIFF_DEFAULT = 15

# This is the number that the roll needs to be >= for an extra die
EXPLODE_VAL = 10

# The number of 'keep dice' all rolls have as a default. The higher
# this number is, the less significant the difference between a highly
# skilled and unskilled character is.
DEFAULT_KEEP = 2

# Base Costs for things:
#cost for stats are always 100, regardless of current value
NEW_STAT_COST = 100
# this multiplier is times the new rank of the skill you're going for
# so going from 2 to 3 will be 30 for non-combat, 60 for combat
NON_COMBAT_SKILL_COST_MULT = 10
COMBAT_SKILL_COST_MULT = 20
# being taught will give you a 20% discount
TEACHER_DISCOUNT = 0.8

def get_partial_match(args, type):
    # helper function for finding partial string match of stat/skills
    if type == "stat":
        word_list = _valid_stats_
    elif type == "skill":
        word_list = _valid_skills_
    else:
        return
    matches = []
    for word in word_list:
        if word.startswith(args):
            matches.append(word)
    return matches

def explode_check(num):
    """
    Recursively call itself and return the sum for exploding rolls.
    """
    if num < EXPLODE_VAL: return num
    return num + explode_check(randint(1,10))

def do_dice_check(caller, stat=None, skill=None, difficulty=DIFF_DEFAULT, stat_list=None,
                  skill_list=None, skill_keep=True, stat_keep=False,
                  keep_override=None, bonus_dice=0, divisor=1, average_lists=False):
    """
    Do a dice check and return number of successes or botches. Positive number for
    successes, negative for botches.
    Stat and skill are strings that are assumed to already be run through get_partial_match.
    We'll try to match them against the character object to get values, and 0 if there's no
    matches for them.
    """
    statval = caller.attributes.get(stat)
    # NB. attributes.get(None) returns -all- attributes by default, while trying to get
    # an attribute that doesn't exist returns None. So we need to check for type here
    if not statval or type(statval) is not int: statval = 0
    if stat_list:
        for cstat in stat_list:
            val = caller.attributes.get(cstat)
            if not val: val = 0
            statval += val
        if average_lists:
            statval /= len(stat_list)
    skillval = caller.db.skills.get(skill, 0)
    if skill_list:
        for cskill in skill_list:
            skillval += caller.db.skills.get(cskill, 0)
        if average_lists:
            skillval /= len(skill_list)
    # keep dice is either based on some combination of stats or skills, or supplied by caller
    keep_dice = DEFAULT_KEEP
    if stat_keep: keep_dice += statval
    if skill_keep: keep_dice += skillval
    if keep_override:
        keep_dice = keep_override
        
    # the number of 'dice' we roll is equal to stat + skill
    num_dice = int(statval) + int(skillval) + bonus_dice
    rolls = [randint(1, 10) for roll in range(num_dice)]
    for x in range(len(rolls)):
        rolls[x] = explode_check(rolls[x])
    # Now we sort the rolls from least to highest, and keep a number of our
    # highest rolls equal to our 'keep dice'. Those are then added as our result.
    rolls.sort()
    rolls = rolls[-keep_dice:]
    result = sum(rolls)
    if not divisor: divisor = 1
    result /= divisor
    # end result is the sum of our kept dice minus the difficulty of what we were
    # attempting. Positive number is a success, negative is a failure.
    result = result - difficulty
    return result

def get_stat_cost(caller, stat):
    "Currently all stats cost 100, but this could change."
    cost = NEW_STAT_COST
    if check_training(caller, stat, stype="stat"):
        cost = discounted_cost(caller, cost)
    total_stats = 0
    for stat in _valid_stats_:
        total_stats += caller.attributes.get(stat)
    bonus_stats = total_stats - 36
    cost *= (1 + 0.5*bonus_stats)
    return int(cost)

def cost_at_rank(caller, skill, current_rating, new_rating):
    "Returns the total cost when given a current rating and the new rating."
    cost = 0
    if new_rating > current_rating:
        while current_rating < new_rating:
            current_rating += 1
            if skill in _combat_skills_ or skill in _valid_abilities_:
                cost += current_rating * COMBAT_SKILL_COST_MULT
            else:
                cost += current_rating * NON_COMBAT_SKILL_COST_MULT
        return cost
    if new_rating < current_rating:
        while current_rating > new_rating:
            if skill in _combat_skills_ or skill in _valid_abilities_:
                cost -= current_rating * COMBAT_SKILL_COST_MULT
            else:
                cost -= current_rating * NON_COMBAT_SKILL_COST_MULT
            current_rating -= 1
        return cost
    return cost
                
def get_skill_cost_increase(caller):
    from commands.commands import guest
    skills = caller.db.skills or {}
    srank = caller.db.social_rank or 0
    total = 0
    for skill in skills:
        # get total cost of each skill
        total += cost_at_rank(caller, skill, 0, skills[skill])
    total -= guest.SKILL_POINTS * 10
    total -= guest.XP_BONUS_BY_SRANK.get(srank, 0)
    if total < 0:
        return 0.0
    return total/500.0

def get_skill_cost(caller, skill, adjust_value=None, check_teacher=True, unmodified=False):
    "Uses cost at rank and factors in teacher discounts if they are allowed."
    current_rating = caller.db.skills.get(skill, 0)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    # cost for a legendary skill
    if new_rating == 6:
        cost = 1000
    else:
        cost = cost_at_rank(caller, skill, current_rating, new_rating)
    if cost < 0:
        return cost
    if unmodified:
        return cost
    # check what discount would be    
    if check_teacher:
        if check_training(caller, skill, stype="skill"):
            cost = discounted_cost(caller, cost)
    cost += int(cost * get_skill_cost_increase(caller))
    return cost

def get_dom_cost(caller, skill, adjust_value=None, check_teacher=False):
    dompc = caller.player.Dominion
    current_rating = getattr(dompc, skill)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(caller, skill, current_rating, new_rating)
    if cost < 0:
        return cost
    cost *= 100
    return cost

def get_ability_cost(caller, ability, adjust_value=None, check_teacher=True, unmodified=False):
    "Uses cost at rank and factors in teacher discounts if they are allowed."
    current_rating = caller.db.abilities.get(ability, 0)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(caller, ability, current_rating, new_rating)
    if ability in _crafting_abilities_:
        cost /= 2
    if cost < 0:
        return cost
    if unmodified:
        return cost
    # abilities are more expensive the more we have in the same category
    if ability in _crafting_abilities_:
        for c_ability in _crafting_abilities_:
            cost += caller.db.abilities.get(c_ability, 0)
    if ability in _fighting_abilities_:
        for f_ability in _fighting_abilities_:
            cost += caller.db.abilities.get(f_ability, 0)
    if ability in _magical_abilities_:
        for m_ability in _magical_abilities_:
            cost += caller.db.abilities.get(m_ability, 0)
    if ability in _cunning_abilities_:
        for c_ability in _cunning_abilities_:
            cost += caller.db.abilities.get(c_ability, 0)
    # check what discount would be    
    if check_teacher:
        if check_training(caller, ability, stype="ability"):
            cost = discounted_cost(caller, cost)
    return cost

def discounted_cost(caller, cost):
    discount = TEACHER_DISCOUNT
    trainer = caller.db.trainer
    teaching = trainer.db.skills.get("teaching", 0)
    discount -= 0.05 * teaching
    return int(round(cost * discount))
    

def check_training(caller, field, stype):
    trainer = caller.db.trainer
    if not trainer:
        return False
    if stype == "stat":
        callerval = caller.attributes.get(field)
        trainerval = trainer.attributes.get(field)
        return trainerval > callerval + 1
    if stype == "skill":
        callerval = caller.db.skills.get(field, 0)
        trainerval = trainer.db.skills.get(field, 0)
        return trainerval > callerval + 1
    if stype == "ability":
        callerval = caller.db.abilities.get(field, 0)
        trainerval = trainer.db.abilities.get(field, 0)
        return trainerval > callerval + 1
    if stype == "dom":
        try:
            callerval = getattr(caller.db.player_ob.Dominion, field)
            trainerval = getattr(trainer.db.player_ob.Dominion, field)
            return trainerval >= callerval + 1
        except AttributeError:
            return False

def adjust_skill(caller, field, value=1):
    if field not in _valid_skills_:
        raise Exception("Error in adjust_skill: %s not found as a valid skill." % field)
    try:
        caller.db.skills[field] += value
    except KeyError:
        caller.db.skills[field] = value
    caller.db.trainer = None
    if field in _crafting_skills_:
        abilitylist = _parent_abilities_[field]
        for ability in abilitylist:
            if ability not in caller.db.abilities:
                caller.db.abilities[ability] = 1

def adjust_stat(caller, field, value=1):
    if field not in _valid_stats_:
        raise Exception("Error in adjust_stat: %s not found as a valid stat." % field)
    current = caller.attributes.get(field)
    current += value
    caller.attributes.add(field, current)
    caller.db.trainer = None

def adjust_ability(caller, field, value=1):
    if field not in _valid_abilities_:
        raise Exception("Error in adjust_ability: %s not found as a valid ability." % field)
    try:
        caller.db.abilities[field] += value
    except KeyError:
        caller.db.abilities[field] = value
    caller.db.trainer = None

def adjust_dom(caller, field, value=1):
    if field not in _domskills_:
        raise Exception("Error in adjust_dom: %s not found as a valid dominion skill." % field)
    dompc = caller.db.player_ob.Dominion
    current = getattr(dompc, field)
    setattr(dompc, field, current + value)

def get_dom_resource(field):
    if field in ("population", "loyalty"):
        return "social"
    if field in ("income", "farming", "upkeep", "productivity"):
        return "economic"
    if field in ("warfare"):
        return "military"
