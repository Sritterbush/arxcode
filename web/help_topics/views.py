# Views for our help topics app

from django.http import Http404
from django.shortcuts import render
from django.conf import settings

from evennia.utils.search import object_search
from evennia.utils.utils import inherits_from
from evennia.objects.models import ObjectDB

from evennia.help.models import HelpEntry
from world.dominion.models import (CraftingRecipe, CraftingMaterialType,
                                  Organization, Member)
from commands.default_cmdsets import PlayerCmdSet, CharacterCmdSet
from commands.cmdsets.situational import SituationalCmdSet

def topic(request, object_key):
    object_key = object_key.lower()
    try:
        topic = list(HelpEntry.objects.find_topicmatch(object_key, exact=True))[0]
    except IndexError:
        raise Http404("I couldn't find a character with that ID.")
    
    return render(request, 'help_topics/topic.html', {'topic': topic})

def command_help(request, cmd_key):
    user = request.user
    char = None
    try:
        char = user.db.char_ob
    except AttributeError:
        pass
    cmd_key = cmd_key.lower()
    matches = [ob for ob in PlayerCmdSet() if ob.key.lower() == cmd_key and ob.access(user, 'cmd')]
    matches += [ob for ob in CharCmdSet() if ob.key.lower() == cmd_key and ob.access(char, 'cmd')]
    matches += [ob for ob in SituationalCmdSet() if ob.key.lower() == cmd_key and ob.access(user, 'cmd')]
    return render(request, 'help_topics/command_help.html', {'matches': matches})

def list_topics(request):
    user = request.user
    try:
        all_topics = [topic for topic in HelpEntry.objects.all() if topic.access(user, 'view', default=True)]
        all_topics = sorted(all_topics, key = lambda entry: entry.key.lower())
        all_categories = list(set([topic.help_category.capitalize() for topic in all_topics]))
        all_categories = sorted(all_categories)
    except IndexError:
        raise Http404("Error in compiling topic list.")
    # organizations also
    from django.db.models import Q
    all_orgs = Organization.objects.filter(Q(secret=False) & Q(members__deguilded=False) &
                                           Q(members__player__player__isnull=False)).distinct().order_by('name')
    secret_orgs = []
    try:
        if user.is_staff:
            secret_orgs = Organization.objects.filter(secret=True)
        else:
            secret_orgs = Organization.objects.filter(Q(members__deguilded=False) & Q(secret=True)
                                                      & Q(members__player__player=user))
    except Exception:
        pass
    return render(request, 'help_topics/list.html', {'all_topics': all_topics,
                                                     'all_categories': all_categories,
                                                     'all_orgs': all_orgs,
                                                     'secret_orgs':secret_orgs,})

def list_recipes(request):
    user = request.user
    all_recipes = CraftingRecipe.objects.all().order_by('ability', 'difficulty')
    known_recipes = []
    materials = CraftingMaterialType.objects.all().order_by('value')
    try:
        known_recipes = user.Dominion.assets.recipes.all()
    except Exception:
        pass
    return render(request, 'help_topics/recipes.html', {'all_recipes': all_recipes,
                                                        'materials': materials,
                                                     'known_recipes': known_recipes})

def display_org(request, object_id):
    user = request.user
    rank_display = 0
    try:
        org = Organization.objects.get(id=object_id)
    except IndexError:
        raise Http404("I couldn't find an Org by that name.")
    if org.secret:
        try:
            if not (org.members.filter(deguilded=False, player__player__id=user.id)
                    or user.is_staff):
                raise Exception()
            if not user.is_staff:
                try:
                    rank_display = user.Dominion.memberships.get(organization=org).rank
                except Exception:
                    rank_display = 11
        except Exception:
            raise Http404("You cannot view this page.")
    try:
        holdings = org.assets.estate.holdings.all()
    except Exception:
        holdings = []
    
    return render(request, 'help_topics/org.html', {'org': org,
                                                    'holdings': holdings,
                                                    'rank_display': rank_display,
                                                    })

def list_commands(request):
    user = request.user
    char = None
    try:
        char = user.db.char_ob
    except AttributeError:
        pass
    player_cmds = [ob for ob in PlayerCmdSet() if ob.access(user, 'cmd')]
    char_cmds = [ob for ob in CharacterCmdSet() if ob.access(char, 'cmd')]
    situational_cmds = [ob for ob in SituationalCmdSet() if ob.access(user, 'cmd')]
    return render(request, 'help_topics/list_commands.html', {'player_cmds': player_cmds,
                                                    'char_cmds': char_cmds,
                                                    'situational_cmds': situational_cmds})
