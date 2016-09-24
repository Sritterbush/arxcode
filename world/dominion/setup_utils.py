"""
Utilities to setup the different aspects of Dominion, such
as creating Land squares of random terrain based on a regional
climate, and setup a character's initial domain based on their
social rank.
"""
from .models import (Land, PlayerOrNpc, Ruler, Domain, Army, AssetOwner,
                                  Organization)
from . import unit_types
import random

CAPITALS = [(0,1), # Sanctum
            (3, -5), # Lenosia
            (9, 2), # Arx
            (3,7), # Farhaven
            (12,2), # Maelstrom
            ]

org_lockstring = ("edit:rank(2);boot:rank(2);guards:rank(2);withdraw:rank(2)" +
                  ";setrank:rank(2);invite:rank(2);setruler:rank(2);view:rank(10)" +
                  ";command:rank(2);build:rank(2);agents:rank(2)")

def setup_dom_for_player(player):
    if hasattr(player, 'Dominion'):
        # they already have one
        return player.Dominion
    return PlayerOrNpc.objects.create(player=player)

def setup_assets(dompc, amt):
    if hasattr(dompc, 'assets'):
        return
    AssetOwner.objects.create(player=dompc, vault=amt)

def starting_money(srank):
    try:
        srank = int(srank)
        if srank > 10 or srank < 1:
            raise TypeError
    except TypeError:
        print "Invalid Social rank. Using rank 10 as a default."
        srank = 10
    val = 11 - srank
    return val * val * val

def get_domain_resources(area):
    """
    Given the size of a domain, returns a dictionary of
    the keys 'mills', 'mines', 'lumber', 'farms', 'housing'
    with appropriate values to be assigned to a domain. We just
    go round robin incrementing the values.
    """

    res_order = ['farms', 'housing', 'mills', 'mines', 'lumber']
    initial = area/5
    area %= 5
    resources = { resource: initial for resource in res_order }
    counter = 0
    while area > 0:
        resource = res_order[counter]
        resources[resource] += 1
        area -= 1
        counter += 1
        if counter >= len(res_order):
            counter = 0
    return resources

def srank_dom_stats(srank, region, name, male=True):
    if srank < 1 or srank > 6:
        raise ValueError("Invalid social rank of %s. Aborting." % srank)
    if srank == 6:
        if male:
            title = "Baron of %s" % region.name
        else:
            title = "Baroness of %s" % region.name
        name = "%s's Barony" % name
        dom_size = 200
        castle_level = 1
    if srank == 5:
        if male:
            title = "Count of %s" % region.name
        else:
            title = "Countess of %s" % region.name
        name = "%s's Countship" % name
        dom_size = 400
        castle_level = 2
    elif srank == 4:
        if male:
            title = "Marquis of %s" % region.name
        else:
            title = "Marquessa of %s" % region.name
        name = "%s's March" % name
        dom_size = 700
        castle_level = 3
    elif srank == 3:
        if male:
            title = "Duke of %s" % region.name
        else:
            title = "Duchess of %s" % region.name
        name = "%s's Duchy" % name
        dom_size = 1200
        castle_level = 4
    elif srank == 2:
        if male:
            title = "Prince of %s" % region.name
        else:
            title = "Princess of %s" % region.name
        name = "%s's Principality" % name
        dom_size = 2000
        castle_level = 5
    elif srank == 1:
        if male:
            title = "King of %s" % region.name
        else:
            title = "Queen of %s" % region.name
        name = "%s's Kingdom" % name
        dom_size = 5000
        castle_level = 6
    return (title, name, dom_size, castle_level)

def setup_domain(dompc, region, srank, male=True, ruler=None):
    """
    Sets up the domain for a given PlayerOrNpc object passed by
    'dompc'. region must be a Region instance, and srank must be
    an integer between 1 and 6. Ruler should be a defined Ruler
    object with vassals/lieges already set.
    """
    name = str(dompc)
    if not ruler:
        if hasattr(dompc, 'assets'):
            assetowner = dompc.assets
        else:
            assetowner = AssetOwner.objects.create(player=dompc)
        ruler = Ruler.objects.create(castellan=dompc, house=assetowner)
    else:
        assetowner = ruler.house
    title, name, dom_size, castle_level = srank_dom_stats(srank, region, name, male)
    squares = Land.objects.filter(region_id=region.id)
    squares = [land for land in squares if land.free_area >= dom_size and (land.x_coord, land.y_coord) not in CAPITALS]
    if not squares:
        raise ValueError("No squares that match our minimum land requirement in region.")
    land = random.choice(squares)
    # get a dict of the domain's resources
    resources = get_domain_resources(dom_size)
    domain = Domain.objects.create(land=land, ruler=ruler,
                                   name=name, area=dom_size, title=title)
    set_domain_resources(domain, resources)
    armyname = "%s's army" % str(dompc)
    setup_army(domain, srank, armyname, assetowner)
    castle_name = "%s's castle" % str(dompc)
    domain.castles.create(level=castle_level, name=castle_name)
    return domain

def set_domain_resources(domain, resources):
    # resources
   domain.num_farms=resources['farms']
   domain.num_housing=resources['housing']
   domain.num_mills=resources['mills']
   domain.num_mines=resources['mines']
   domain.num_lumber_yards=resources['lumber']
   domain.stored_food=resources['farms'] * 100
   # serfs
   domain.mining_serfs=resources['farms'] * 10
   domain.lumber_serfs=resources['lumber'] * 10
   domain.farming_serfs=resources['farms'] * 10
   domain.mill_serfs=resources['mills'] * 10
   domain.save()

def convert_domain(domain, srank=None, male=None):
    region = domain.land.region
    if not male or not srank:
        char = domain.ruler.castellan.player.db.char_ob
        if not male:
            male = char.db.gender.lower() == "male"
        if not srank:
            srank = char.db.social_rank
        name = char.key
    else:
        name = str(domain.ruler.castellan)
    title, name, dom_size, castle_level = srank_dom_stats(srank, region, name, male)
    resources = get_domain_resources(dom_size)
    domain.area = dom_size
    set_domain_resources(domain, resources)
    if domain.armies.all():
        aname = domain.armies.all()[0].name
    else:
        aname = "Army of %s." % domain
    setup_army(domain, srank, aname, domain.ruler.house)
    if domain.castles.all():
        castle = domain.castles.all()[0]
        castle.level = castle_level
        castle.save()
            
def setup_army(domain, srank, name, owner):
    # create new army in domain
    try:
        army = domain.armies.all()[0]
        if name:
            army.name = name
        army.save()
    except Exception:
        army = domain.armies.create(name=name, land=domain.land, owner=owner)
    setup_units(army, srank)

def setup_units(army, srank):
    INF = unit_types.INFANTRY
    PIK = unit_types.PIKE
    CAV = unit_types.CAVALRY
    ARC = unit_types.ARCHERS
    units = {}
    # add more units based on srank
    if srank == 6:
        units[INF] = 200
        units[PIK] = 70
        units[CAV] = 40
        units[ARC] = 70
    if srank == 5:
        units[INF] = 375
        units[PIK] = 125
        units[CAV] = 70
        units[ARC] = 125
    if srank == 4:
        units[INF] = 750
        units[PIK] = 250
        units[CAV] = 125
        units[ARC] = 250
    if srank == 3:
        units[INF] = 1500
        units[PIK] = 500
        units[CAV] = 250
        units[ARC] = 500
    if srank == 2:
        units[INF] = 3000
        units[PIK] = 1000
        units[CAV] = 500
        units[ARC] = 1000
    if srank == 1:
        units[INF] = 5000
        units[PIK] = 1500
        units[CAV] = 1000
        units[ARC] = 1500
    # populate the army with units
    for unit in units:
        try:
            squad = army.units.get(unit_type=unit)
            squad.quantity = units[unit]
            squad.save()
        except Exception:
            army.units.create(unit_type=unit, quantity=units[unit])
    
def setup_family(dompc, family, create_liege=True, create_vassals=True,
                 character=None, srank=None, region=None, liege=None,
                 num_vassals=2):
    """
    Creates a ruler object and either retrieves a house
    organization or creates it. Then we also create similar
    ruler objects for an npc liege (if we should have one),
    and npc vassals (if we should have any). We return a tuple of
    our ruler object, our liege's ruler object or None, and a list
    of vassals' ruler objects.
    """
    ruler = None
    vassals = []
    # create a liege only if we don't have one already
    if create_liege and not liege:
        name = "Liege of %s" % family
        liege = setup_ruler(name)
    ruler = setup_ruler(family, dompc, liege)
    if create_vassals:
        vassals = setup_vassals(family, ruler, region, character, srank, num=num_vassals) 
    return (ruler, liege, vassals)

def setup_vassals(family, ruler, region, character, srank, num=2):
    vassals = []
    for x in range(num):
        name = "Vassal of %s (#%s)" % (family, x + 1)
        vassals.append(setup_ruler(name, liege=ruler))
    for y in range(len(vassals)):
        name = "Vassal #%s of %s" % (y + 1, character)
        setup_dom_for_npc(name, srank=srank + 1, region=region, ruler=vassals[y])
    return vassals

def setup_vassals_for_player(player, num=5):
    dompc = player.Dominion
    char = player.db.char_ob
    family = char.db.family
    ruler = dompc.ruler
    srank = char.db.social_rank
    region = ruler.holdings.all()[0].land.region
    setup_vassals(family, ruler, region, char, srank, num)

def setup_ruler(name, castellan=None, liege=None):
    """
    We may have to create up to three separate models to fully create
    our ruler object. First is the House as an Organization, then the
    economic holdings of that house (its AssetOwner instance), then the
    ruler object that sets it up as a ruler of a domain, with the liege/vassal
    relationships
    """
    try:
        house_org = Organization.objects.get(name__iexact=name)
    except Organization.DoesNotExist:
        house_org = Organization.objects.create(name=name)
        house_org.locks.add(org_lockstring)
    if not hasattr(house_org, 'assets'):
        house = AssetOwner.objects.create(organization_owner = house_org)
    else:
        house = house_org.assets
    try:
        ruler = Ruler.objects.get(house_id=house.id)
    except Ruler.DoesNotExist:
        ruler = Ruler.objects.create(house=house)
    if castellan:
        ruler.castellan = castellan
        if not castellan.memberships.filter(organization_id=house_org.id):
            castellan.memberships.create(organization=house_org, rank=1)
    if liege:
        ruler.liege = liege
    ruler.save()
    return ruler

def setup_dom_for_char(character, create_dompc=True, create_assets=True,
                       region=None, srank=None, family=None, liege_domain=None,
                       create_domain=True, create_liege=True, create_vassals=True,
                       num_vassals=2):
    """
    Creates both a PlayerOrNpc instance and an AssetOwner instance for
    a given character. If region is defined and create_domain is True,
    we create a domain for the character. Family is the House that will
    be created (or retrieved, if it already exists) as an owner of the
    domain, while 'fealty' will be the Organization that is set as their
    liege.
    """
    pc = character.db.player_ob
    if not pc:
        raise TypeError("No player object found for character %s." % character)
    if create_dompc:
        dompc = setup_dom_for_player(pc)
    else:
        dompc = pc.Dominion
    if not srank:
        srank = character.db.social_rank
    if create_assets:
        amt = starting_money(srank)
        setup_assets(dompc, amt)
    # if region is provided, we will setup a domain unless explicitly told not to
    if create_domain and region:       
        if character.db.gender and character.db.gender.lower() == 'male':
            male = True
        else:
            male = False
        if not family:
            family = character.db.family or "%s Family" % character
        # We make vassals if our social rank permits it
        if create_vassals:
            create_vassals = srank < 6
        # if we're setting them as vassals to a house, then we don't create a liege
        liege = None
        if liege_domain:
            create_liege = False
            liege = liege_domain.ruler
        ruler, liege, vassals = setup_family(dompc, family, create_liege=create_liege, create_vassals=create_vassals,
                                             character=character, srank=srank, region=region, liege=liege,
                                             num_vassals=num_vassals)
        # if we created a liege, finish setting them up
        if create_liege:
            name = "%s's Liege" % character
            setup_dom_for_npc(name, srank=srank - 1, region=region, ruler=liege)
        # return the new domain if we were supposed to create one
        return setup_domain(dompc, region, srank, male, ruler)
    else: # if we're not setting up a new domain, return Dominion object
        return dompc

def setup_dom_for_npc(name, srank, gender='male', region=None, ruler=None,
                      create_domain=True):
    """
    If create_domain is True and region is defined, we also create a domain for
    this npc. Otherwise we just setup their PlayerOrNpc model and AssetOwner
    model.
    """
    if gender.strip().lower() != 'male':
        male = False
    else:
        male = True
    if PlayerOrNpc.objects.filter(npc_name__iexact=name):
        raise ValueError("An npc of that name already exists.")
    domnpc = PlayerOrNpc.objects.create(npc_name=name)
    setup_assets(domnpc, starting_money(srank))
    if create_domain and region:
        setup_domain(domnpc, region, srank, male, ruler)

def replace_vassal(domain, player, num_vassals=2):
    """
    Replaces the npc ruler of a domain that is someone's vassal, and then
    creates vassals of their own.
    """
    char = player.db.char_ob
    if not char:
        raise ValueError("Character not found.")
    family = char.db.family
    if not family:
        raise ValueError("Family not defined on character.")
    srank = char.db.social_rank
    if not srank:
        raise ValueError("Social rank undefined")
    ruler = domain.ruler
    assets = domain.ruler.house
    org = assets.organization_owner
    npc = ruler.castellan
    if npc:
        if npc.player:
            raise ValueError("This domain already has a player ruler.")
        npc.npc_name = None
        npc.player = player
        npc.save()
    org.name = family
    org.save()
    # create their vassals
    setup_vassals(family, ruler, domain.land.region, char, srank, num=num_vassals)

REGION_TYPES = ("coast", "temperate", "continental", "tropical")
def get_terrain(type):
    terrain = Land.PLAINS
    landlocked = False
    if type == "coast":
        types = [Land.COAST, Land.PLAINS, Land.ARCHIPELAGO, Land.LAKES, Land.FOREST, Land.FLOOD_PLAINS, Land.MARSH]   
    elif type == "temperate":
        types = [Land.PLAINS, Land.FOREST, Land.GRASSLAND, Land.HILL, Land.MARSH, Land.LAKES, Land.MOUNTAIN ]
        landlocked = random.choice((True, False, False))
    elif type == "continental":
        types = [Land.TUNDRA, Land.HILL, Land.MOUNTAIN, Land.PLAINS, Land.LAKES, Land.FOREST, Land.GRASSLAND]
        landlocked = random.choice((True, False, False))
    elif type == "tropical":
        types = [Land.JUNGLE, Land.OASIS, Land.PLAINS, Land.GRASSLAND, Land.HILL, Land.LAKES, Land.MARSH]
        landlocked = random.choice((True, False, False))
    terrain = random.choice(types)
    return terrain, landlocked

def populate(region, end_x, end_y, type):
    type = type.lower()
    if type not in REGION_TYPES:
        raise TypeError("Region-type %s not in %s." % (type, str(REGION_TYPES)))
    try:
        start_x = region.origin_x_coord
        start_y = region.origin_y_coord
    except:
        print "Invalid object %s passed as region. Cannot populate." % str(region)
    for x in range(start_x, end_x + 1):
        for y in range(start_y, end_y + 1):
            name = "%s (%s, %s)" % (region.name, x, y)
            terrain, landlocked = get_terrain(type)
            try:
                land = Land.objects.get(x_coord=x, y_coord=y)
                # already exists at this x,y, so pass
            except Land.DoesNotExist:
                region.land_set.create(name=name, terrain=terrain, landlocked=landlocked, x_coord=x, y_coord=y)
    
    
