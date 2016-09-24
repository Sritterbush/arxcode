# Views for our character app
# __init__.py for character configures cloudinary

from django.http import Http404
from django.shortcuts import render, render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect, HttpResponse
from django.core.urlresolvers import reverse
from django.conf import settings

from evennia.utils.search import object_search
from evennia.utils.utils import inherits_from
from evennia.objects.models import ObjectDB
from world.dominion.models import Organization
from commands.commands import roster
import cloudinary, cloudinary.uploader, cloudinary.forms
from cloudinary import api
from .forms import (PhotoForm, PhotoDirectForm, PhotoUnsignedDirectForm, PortraitSelectForm,
                   PhotoDeleteForm, PhotoEditForm)
from .models import Photo, Story, Chapter, Episode
from cloudinary.forms import cl_init_js_callbacks
import json
from django.views.decorators.csrf import csrf_exempt
from django import forms
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from server.utils.name_paginator import NamePaginator
from django.views.generic import ListView

def get_character_from_ob(object_id):
    "Helper function to get a character, run checks, return character + error messages"
    object_id = '#' + object_id
    character = None
    err_message = None
    try:
        character = object_search(object_id)[0]
    except IndexError:
        err_message = "I couldn't find a character with that ID."
    if not inherits_from(character, settings.BASE_CHARACTER_TYPECLASS):
        err_message = "No character with that ID. Found something else instead."
    return character, err_message

def comment(request, object_id):
    """
    Makes an in-game comment on a character sheet.
    """
    send_charob = request.user.db.char_ob
    rec_charob, err = get_character_from_ob(object_id)
    if not rec_charob:
        raise Http404(err)
    comment_txt = request.POST['comment']
    roster.create_comment(send_charob, rec_charob, comment_txt)
    return HttpResponseRedirect(reverse('character:sheet', args=(object_id,)))

def sheet(request, object_id):
    """
    Displays a character sheet, and is used as the primary
    'wiki' page for a character. 
    """
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    user = request.user
    show_hidden = False
    can_comment = False
    # we allow only staff or the player to see secret information
    # but only other characters can leave IC comments.
    if user.is_authenticated():
        try:
            if user.db.char_ob.id == character.id or user.check_permstring("builders"):
                show_hidden = True
            if user.db.char_ob.id != character.id:
                can_comment = True
        # if we're logged in as a player without a character assigned somehow
        except Exception:
            pass
    if not show_hidden and (hasattr(character, 'roster') and
                            character.roster.roster.name == "Unavailable"):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    pheight = character.db.portrait_height or 480
    pwidth = character.db.portrait_width or 320
    try:
        fealty_org_id = Organization.objects.get(name__iexact=character.db.fealty)
    except Organization.DoesNotExist:
        fealty_org_id = None
    try:
        family_org_id = Organization.objects.get(name__iexact=character.db.family)
    except Organization.DoesNotExist:
        family_org_id = None
    return render(request, 'character/sheet.html', { 'character': character,
                                                     'show_hidden': show_hidden,
                                                     'can_comment': can_comment,
                                                     'pheight': pheight,
                                                     'pwidth': pwidth,
                                                     'fealty_org_id': fealty_org_id,
                                                     'family_org_id': family_org_id,})

def journals(request, object_id):
    """
    Displays a character's journals
    """
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    user = request.user
    show_hidden = False

    if user.is_authenticated():
        if user.db.char_ob.id == character.id or user.check_permstring("builders"):
            show_hidden = True

    if not show_hidden and (hasattr(character, 'roster') and
                            character.roster.roster.name == "Unavailable"):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    white_journal = character.messages.white_journal
    black_journal = character.messages.black_journal

    return render(request, 'character/journals.html', { 'character': character,
                                                     'show_hidden': show_hidden,
                                                     'white_journal': white_journal,
                                                     'black_journal': black_journal,
                                                     })


class RosterListView(ListView):
    model = ObjectDB
    template_name = 'character/list.html'
    paginator_class = NamePaginator
    paginate_by = 20
    roster_name = "Active"
    def get_queryset(self):
        return ObjectDB.objects.filter(roster__roster__name=self.roster_name).order_by('db_key')
    def get_context_data(self, **kwargs):
        context = super(RosterListView, self).get_context_data(**kwargs)
        user = self.request.user
        show_hidden = False
        if user.is_authenticated() and user.check_permstring("builders"):
            show_hidden = True
        context['show_hidden'] = show_hidden
        context['roster_name'] = self.roster_name
        return context

class ActiveRosterListView(RosterListView):
    pass

class AvailableRosterListView(RosterListView):
    roster_name = "Available"

class IncompleteRosterListView(RosterListView):
    roster_name = "Incomplete"
    def get_queryset(self):
        user = self.request.user
        if not (user.is_authenticated() and user.check_permstring("builders")):
            raise Http404("Not staff")
        return super(IncompleteRosterListView, self).get_queryset()

class UnavailableRosterListView(IncompleteRosterListView):
    roster_name = "Unavailable"


def gallery(request, object_id):
    "List photos that belong to object_id"
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    user = request.user
    can_upload = False
    if user.is_authenticated() and (user.db.char_ob == character or user.is_staff):
        can_upload = True
    photos = Photo.objects.filter(owner__id = object_id)
    portrait_form = PortraitSelectForm(object_id)
    edit_form = PhotoEditForm(object_id)
    delete_form = PhotoDeleteForm(object_id)
    pheight = character.db.portrait_height or 480
    pwidth = character.db.portrait_width or 320
    return render(request, 'character/gallery.html', {'character': character, 'photos': photos,
                                                      'can_upload': can_upload, 'portrait_form': portrait_form,
                                                      'edit_form': edit_form, 'delete_form': delete_form,
                                                      'pheight': pheight, 'pwidth': pwidth,
                                                      })

def edit_photo(request, object_id):
    character, err = get_character_from_ob(object_id)
    user = request.user
    if not character:
        raise Http404(err)
    if not (user == character.db.player_ob or user.is_staff):
        raise Http404("Only owners or staff may edit photos.")
    try:
        photo = Photo.objects.get(pk=request.POST['select_photo'])
        title = request.POST['title']
        alt_text = request.POST['alt_text']
    except Exception as err:
        raise Http404(err)
    photo.title = title
    photo.alt_text = alt_text
    photo.save()
    if character.db.portrait and character.db.portrait.id == photo.id:
        character.db.portrait = photo
    return HttpResponseRedirect(reverse('character:gallery', args=(object_id,)))

def delete_photo(request, object_id):
    character, err = get_character_from_ob(object_id)
    user = request.user
    if not character:
        raise Http404(err)
    if not (user == character.db.player_ob or user.is_staff):
        raise Http404("Only owners or staff may delete photos.")
    try:
        photo = Photo.objects.get(pk=request.POST['select_photo'])
    except Exception as err:
        raise Http404(err)
    cloudinary.api.delete_resources([photo.image.public_id])
    if character.db.portrait and character.db.portrait.id == photo.id:
        character.db.portrait = None
    photo.delete()
    return HttpResponseRedirect(reverse('character:gallery', args=(object_id,)))

def select_portrait(request, object_id):
    """
    Chooses a photo as character portrait
    """
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    try:
        portrait = Photo.objects.get(pk=request.POST['select_portrait'])
        height = request.POST['portrait_height']
        width = request.POST['portrait_width']
    except Exception:
        portrait = None
        height = None
        width = None
    character.db.portrait_height = height or 480
    character.db.portrait_width = width or 320
    try:
        character.roster.profile_picture = portrait
        character.roster.save()
    except Exception:
        pass
    return HttpResponseRedirect(reverse('character:gallery', args=(object_id,)))
                                                       

def upload(request, object_id):
    user = request.user
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    if not user.is_authenticated() or (user.db.char_ob != character and not user.is_staff):
        raise Http404("You are not permitted to upload to this gallery.")
    unsigned = request.GET.get("unsigned") == "true"
    
    if (unsigned):
        # For the sake of simplicity of the sample site, we generate the preset on the fly. It only needs to be created once, in advance.
        try:
            api.upload_preset(PhotoUnsignedDirectForm.upload_preset_name)
        except api.NotFound:
            api.create_upload_preset(name=PhotoUnsignedDirectForm.upload_preset_name, unsigned=True, folder="preset_folder")
            
    direct_form = PhotoUnsignedDirectForm() if unsigned else PhotoDirectForm()
    context = dict(
        # Form demonstrating backend upload
        backend_form = PhotoForm(),
        # Form demonstrating direct upload
        direct_form = direct_form,
        # Should the upload form be unsigned
        unsigned = unsigned,
    )
    # When using direct upload - the following call in necessary to update the
    # form's callback url
    cl_init_js_callbacks(context['direct_form'], request)
    context['character'] = character
    if request.method == 'POST':
        # Only backend upload should be posting here
        owner_char = Photo(owner=character)
        form = PhotoForm(request.POST, request.FILES, instance=owner_char)
        context['posted'] = False
        if form.is_valid():
            # Uploads image and creates a model instance for it
            if user.is_authenticated() and user.check_permstring("builders"):
                context['show_hidden'] = True
            context['posted'] = form.instance
            form.save()

    return render(request, 'character/upload.html', context)

@csrf_exempt
def direct_upload_complete(request, object_id):
    character, err = get_character_from_ob(object_id)
    if not character:
        raise Http404(err)
    owner_char = Photo(owner = character)
    form = PhotoDirectForm(request.POST, instance=owner_char)
    if form.is_valid():
        # Create a model instance for uploaded image using the provided data
        form.save()
        ret = dict(photo_id = form.instance.id)
    else:
        ret = dict(errors = form.errors)

    return HttpResponse(json.dumps(ret), content_type='application/json')

def current_story(request):
    story = Story.objects.latest('start_date')
    chapters = story.previous_chapters.order_by('-start_date')
    return render(request, 'character/story.html', { 'story': story, 'chapters': chapters})

def episode(request, ep_id):
    try:
        episode = Episode.objects.get(id=ep_id)
    except Episode.DoesNotExist:
        raise Http404
    return render(request, 'character/episode.html', {'episode': episode})
