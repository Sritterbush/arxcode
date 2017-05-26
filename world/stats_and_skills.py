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
from .roll import Roll


# tuples of allowed stats and skills

PHYSICAL_STATS = ("strength", "dexterity", "stamina")
SOCIAL_STATS = ("charm", "command", "composure")
MENTAL_STATS = ("intellect", "perception", "wits")
MAGIC_STATS = ("mana", "luck", "willpower")
VALID_STATS = PHYSICAL_STATS + SOCIAL_STATS + MENTAL_STATS + MAGIC_STATS
COMBAT_SKILLS = ("athletics", "brawl", "dodge", "archery", "small wpn", "medium wpn",
                 "huge wpn", "stealth", "survival")
SOCIAL_SKILLS = ("intimidation", "leadership", "manipulation", "seduction", "diplomacy",
                 "propaganda", "empathy", "etiquette", "performance")
GENERAL_SKILLS = ("riddles", "legerdemain", "ride", "investigation",
                  "law", "linguistics", "medicine", "occult",  "stewardship", "theology",
                  "streetwise", "agriculture", "economics", "teaching", "war",
                  "animal ken", "artwork", "sailing")
CRAFTING_SKILLS = ('sewing', 'smithing', 'tanning', 'alchemy', 'woodworking')
VALID_SKILLS = COMBAT_SKILLS + SOCIAL_SKILLS + GENERAL_SKILLS + CRAFTING_SKILLS

CRAFTING_ABILITIES = ('tailor', 'weaponsmith', 'armorsmith', 'leatherworker', 'apothecary',
                      'carpenter', 'jeweler')
FIGHTING_ABILITIES = ('duelist', 'berserker', 'ninja', 'blademaster', 'adept')
MAGICAL_ABILITIES = ('abyssal', 'dreamer', 'bloodmage', 'primal', 'celestial')
CUNNING_ABILITIES = ('assassin', 'spy', 'thief', 'mummer')
VALID_ABILITIES = CRAFTING_ABILITIES + FIGHTING_ABILITIES + MAGICAL_ABILITIES + CUNNING_ABILITIES
DOM_SKILLS = ("population", "income", "farming", "productivity",
              "upkeep", "loyalty", "warfare")
_parent_abilities_ = {'sewing': ['tailor'], 'smithing': ['weaponsmith', 'armorsmith', 'jeweler'],
                      'tanning': ['leatherworker'],
                      'alchemy': ['apothecary'], 'woodworking': ['carpenter']}
# Default difficulty for an 'easy' task for a person with a skill of 1
DIFF_DEFAULT = 15


# Base Costs for things:
# cost for stats are always 100, regardless of current value
NEW_STAT_COST = 100
# this multiplier is times the new rank of the skill you're going for
# so going from 2 to 3 will be 30 for non-combat, 60 for combat
NON_COMBAT_SKILL_COST_MULT = 10
COMBAT_SKILL_COST_MULT = 20
# being taught will give you a 20% discount
TEACHER_DISCOUNT = 0.8


def get_partial_match(args, s_type):
    # helper function for finding partial string match of stat/skills
    if s_type == "stat":
        word_list = VALID_STATS
    elif s_type == "skill":
        word_list = VALID_SKILLS
    else:
        return
    matches = []
    for word in word_list:
        if word.startswith(args):
            matches.append(word)
    return matches


def do_dice_check(caller, stat=None, skill=None, difficulty=DIFF_DEFAULT, stat_list=None,
                  skill_list=None, skill_keep=True, stat_keep=False, quiet=True, announce_room=None,
                  keep_override=None, bonus_dice=0, divisor=1, average_lists=False, can_crit=True,
                  average_stat_list=False, average_skill_list=False, use_real_name=False):
    """
    Sending stuff to Roll class for dice checks; assumed to already be run through get_partial_match.
    """
    roll = Roll(caller=caller, stat=stat, skill=skill, difficulty=difficulty, stat_list=stat_list,
                skill_list=skill_list, skill_keep=skill_keep, stat_keep=stat_keep, quiet=quiet,
                announce_room=announce_room, keep_override=keep_override, bonus_dice=bonus_dice,
                divisor=divisor, average_lists=average_lists, can_crit=can_crit,
                average_stat_list=average_stat_list, average_skill_list=average_skill_list, use_real_name=use_real_name)
    caller.ndb.last_roll = roll
    roll.roll()
    return roll.result


def get_stat_cost(caller, stat):
    """Currently all stats cost 100, but this could change."""
    cost = NEW_STAT_COST
    if check_training(caller, stat, stype="stat"):
        cost = discounted_cost(caller, cost)
    total_stats = 0
    for stat in VALID_STATS:
        total_stats += caller.attributes.get(stat)
    bonus_stats = total_stats - 36
    if bonus_stats > 0:
        cost *= (1 + 0.5*bonus_stats)
    return int(cost)


def cost_at_rank(skill, current_rating, new_rating):
    """Returns the total cost when given a current rating and the new rating."""
    cost = 0
    if new_rating > current_rating:
        while current_rating < new_rating:
            current_rating += 1
            if skill in COMBAT_SKILLS or skill in VALID_ABILITIES:
                cost += current_rating * COMBAT_SKILL_COST_MULT
            else:
                cost += current_rating * NON_COMBAT_SKILL_COST_MULT
        return cost
    if new_rating < current_rating:
        while current_rating > new_rating:
            if skill in COMBAT_SKILLS or skill in VALID_ABILITIES:
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
    age = caller.db.age or 0
    total = 0
    for skill in skills:
        # get total cost of each skill
        total += cost_at_rank(skill, 0, skills[skill])
    total -= guest.SKILL_POINTS * 10
    total -= guest.XP_BONUS_BY_SRANK.get(srank, 0)
    total -= guest.award_bonus_by_age(age)
    if total < 0:
        return 0.0
    return total/500.0


def get_skill_cost(caller, skill, adjust_value=None, check_teacher=True, unmodified=False):
    """Uses cost at rank and factors in teacher discounts if they are allowed."""
    current_rating = caller.db.skills.get(skill, 0)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    # cost for a legendary skill
    if new_rating == 6:
        cost = 1000
    else:
        cost = cost_at_rank(skill, current_rating, new_rating)
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


def get_dom_cost(caller, skill, adjust_value=None):
    dompc = caller.player.Dominion
    current_rating = getattr(dompc, skill)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(skill, current_rating, new_rating)
    if cost < 0:
        return cost
    cost *= 100
    return cost


def get_ability_cost(caller, ability, adjust_value=None, check_teacher=True, unmodified=False):
    """Uses cost at rank and factors in teacher discounts if they are allowed."""
    current_rating = caller.db.abilities.get(ability, 0)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(ability, current_rating, new_rating)
    if ability in CRAFTING_ABILITIES:
        cost /= 2
    if cost < 0:
        return cost
    if unmodified:
        return cost
    # abilities are more expensive the more we have in the same category
    if ability in CRAFTING_ABILITIES:
        for c_ability in CRAFTING_ABILITIES:
            cost += caller.db.abilities.get(c_ability, 0)
    if ability in FIGHTING_ABILITIES:
        for f_ability in FIGHTING_ABILITIES:
            cost += caller.db.abilities.get(f_ability, 0)
    if ability in MAGICAL_ABILITIES:
        for m_ability in MAGICAL_ABILITIES:
            cost += caller.db.abilities.get(m_ability, 0)
    if ability in CUNNING_ABILITIES:
        for c_ability in CUNNING_ABILITIES:
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
    if 0 > discount > 1:
        raise ValueError("Error: Training Discount outside valid ranges")
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
    if field not in VALID_SKILLS:
        raise Exception("Error in adjust_skill: %s not found as a valid skill." % field)
    try:
        caller.db.skills[field] += value
    except KeyError:
        caller.db.skills[field] = value
    caller.db.trainer = None
    if field in CRAFTING_SKILLS:
        abilitylist = _parent_abilities_[field]
        if caller.db.abilities is None:
            caller.db.abilities = {}
        for ability in abilitylist:
            if ability not in caller.db.abilities:
                caller.db.abilities[ability] = 1


def adjust_stat(caller, field, value=1):
    if field not in VALID_STATS:
        raise Exception("Error in adjust_stat: %s not found as a valid stat." % field)
    current = caller.attributes.get(field)
    current += value
    caller.attributes.add(field, current)
    caller.db.trainer = None


def adjust_ability(caller, field, value=1):
    if field not in VALID_ABILITIES:
        raise Exception("Error in adjust_ability: %s not found as a valid ability." % field)
    try:
        caller.db.abilities[field] += value
    except KeyError:
        caller.db.abilities[field] = value
    caller.db.trainer = None


def adjust_dom(caller, field, value=1):
    if field not in DOM_SKILLS:
        raise Exception("Error in adjust_dom: %s not found as a valid dominion skill." % field)
    dompc = caller.db.player_ob.Dominion
    current = getattr(dompc, field)
    setattr(dompc, field, current + value)


def get_dom_resource(field):
    if field in ("population", "loyalty"):
        return "social"
    if field in ("income", "farming", "upkeep", "productivity"):
        return "economic"
    if field in ("warfare",):
        return "military"
