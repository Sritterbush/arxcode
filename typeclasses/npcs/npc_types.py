import copy

GUARD = 0
THUG = 1
SPY = 2
ASSISTANT = 3
CHAMPION = 4

npc_templates = {
    "guard": GUARD,
    "thug": THUG,
    "spy": SPY,
    "champion": CHAMPION,
    "assistant": ASSISTANT,
    }

guard_stats = {
    'strength': 3, 'stamina': 3, 'dexterity':3,
    'charm':1, 'command':1, 'composure':1,
    'intellect':2, 'perception':2, 'wits':2,
    'mana':1, 'luck':1, 'willpower':1,   
    }
spy_stats = {
    'strength': 1, 'stamina': 1, 'dexterity':1,
    'charm':3, 'command':3, 'composure':3,
    'intellect':2, 'perception':2, 'wits':2,
    'mana':1, 'luck':1, 'willpower':1, 
    }
assistant_stats = {
    'strength': 1, 'stamina': 1, 'dexterity':1,
    'charm':2, 'command':2, 'composure':2,
    'intellect':3, 'perception':3, 'wits':3,
    'mana':1, 'luck':1, 'willpower':1, 
    }
unknown_stats = {
    'strength': 2, 'stamina': 2, 'dexterity':2,
    'charm':1, 'command':1, 'composure':1,
    'intellect':2, 'perception':2, 'wits':2,
    'mana':1, 'luck':1, 'willpower':1, 
    }

npc_stats = {
    GUARD: guard_stats,
    THUG: guard_stats,
    SPY: spy_stats,
    ASSISTANT: assistant_stats,
    CHAMPION: guard_stats,
    }

guard_skills = {
    "crushing melee": 0, "piercing melee": 0, "slashing melee": 0,
    "brawl":  0, "dodge": 0
    }
spy_skills = {
    "streetwise": 0, "seduction":0, "investigation":0,
    "intimidation":0, "empathy":0, "manipulation":0
    }
npc_skills = {
    GUARD: guard_skills,
    THUG: guard_skills,
    SPY: spy_skills,
    ASSISTANT: spy_skills,
    CHAMPION: guard_skills,
    }

guard_weapon = {
    'attack_skill': 'medium wpn',
    'attack_stat': 'dexterity',
    'damage_stat': 'strength',
    'weapon_damage': 1,
    'attack_type': 'melee',
    'can_be_parried': True,
    'can_be_blocked': True,
    'can_be_dodged': True,
    'can_parry': True,
    'can_riposte': True,
    'reach': 1,
    'minimum_range': 0,
    }

npc_weapons = {
    GUARD: guard_weapon,
    THUG: guard_weapon,
    SPY: guard_weapon,
    ASSISTANT: guard_weapon,
    CHAMPION: guard_weapon,
    }

# all armor values are (base, scaling)
guard_armor = (0, 10)
npc_armor = {
    GUARD: guard_armor,
    THUG: guard_armor,
    }
guard_hp = (0, 10)
npc_hp = {
    GUARD: guard_hp,
    THUG: guard_hp,
    }


npc_descs = {
    GUARD: "A group of guards.",
    THUG: "A group of thugs.",
    SPY: "A group of spies.",
    ASSISTANT: "A loyal assistant.",
    CHAMPION: "A loyal champion.",
    }

npc_plural_names = {
    GUARD: "guards",
    THUG: "thugs",
    SPY: "spies",
    }

npc_singular_names = {
    GUARD: "guard",
    THUG: "thug",
    SPY: "spy",
    CHAMPION: "champion",
    ASSISTANT: "assistant",
    }

def get_npc_stats(type):
    return copy.deepcopy(npc_stats.get(type, unknown_stats))

def get_npc_skills(type):
    return copy.deepcopy(npc_skills.get(type, {}))

def get_npc_desc(type):
    return npc_descs.get(type, "Unknown description")

def get_npc_plural_name(type):
    return npc_plural_names.get(type, "unknown agents")

def get_npc_singular_name(type):
    return npc_singular_names.get(type, "unknown agent")

def get_npc_type(name):
    name = name.lower()
    for key,val in npc_plural_names.items():
        if val == name:
            return key
    for key,val in npc_singular_names.items():
        if val == name:
            return key
    return npc_templates[name]

def get_npc_weapon(type, quality):
    weapon = copy.deepcopy(npc_weapons.get(type, guard_weapon))
    weapon['weapon_damage'] += quality
    return weapon

def get_armor_bonus(type, quality):
    base, scale = npc_armor.get(type, guard_armor)
    return base + (scale * quality)

def get_hp_bonus(type, quality):
    base, scale = npc_hp.get(type, guard_hp)
    return base + (scale * quality)

def generate_default_name_and_desc(type, quality, org):
    """
    Returns a two-tuple of name, desc based on the
    org name, the quality level of the agent, and
    the type.
    """
    name = org.name
    if type == GUARD:
        tname = "guards"
    if type == THUG:
        tname = "thugs"
    if quality == 0:
        name += " untrained %s" % tname
        desc = "Completely untrained %s. Farmers and the like." % tname
    if quality == 1:
        name += " novice %s" % tname
        desc = "Untested and barely trained %s." % tname
    if quality == 2:
        name += " trained %s" % tname
        desc = "%s who have at least received some training." % tname.capitalize()
    if quality == 3:
        name += " veteran %s" % tname
        desc = "%s who have seen combat before." % tname.capitalize()
    if quality == 4:
        name += " skilled veteran %s" % tname
        desc = "%s who have seen combat, and proven to be very good at it." % tname.capitalize()
    if quality == 5:
        name += " elite %s" % tname
        desc = "Highly skilled %s. Most probably would have name-recognition for their skill." % tname
    return (name, desc)

    