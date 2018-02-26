from django.views.generic import ListView, DetailView
from .models import RPEvent, AssignedTask, Crisis, Land, Domain
from .forms import RPEventCommentForm
from django.http import HttpResponseRedirect, HttpResponse
from django.http import Http404
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, render
from django.db.models import Q, Min, Max
from django.template.loader import render_to_string
from server.utils.view_mixins import LimitPageMixin
from PIL import Image, ImageDraw, ImageFont
from math import trunc
import os.path

# Create your views here.


class RPEventListView(LimitPageMixin, ListView):
    model = RPEvent
    template_name = 'dominion/cal_list.html'
    paginate_by = 20

    def search_filter(self, qs):
        event_type = self.request.GET.get("event_type")
        if event_type == "gm_only":
            qs = qs.filter(gm_event=True)
        elif event_type == "prp_only":
            qs = qs.filter(gm_event=False, gms__isnull=False)
        text = self.request.GET.get("search_text")
        if text:
            qs = qs.filter(Q(name__icontains=text) | Q(hosts__player__username__iexact=text) | Q(desc__icontains=text) |
                           Q(gms__player__username__iexact=text) | Q(participants__player__username__iexact=text))
        return qs

    def unfinished(self):
        user = self.request.user
        try:
            if user.is_staff:
                return self.search_filter(RPEvent.objects.filter(finished=False).distinct().order_by('-date'))
        except AttributeError:
            pass
        if not user.is_authenticated():
            return self.search_filter(
                RPEvent.objects.filter(finished=False, public_event=True).distinct().order_by('-date'))
        else:
            return self.search_filter(RPEvent.objects.filter(Q(finished=False) &
                                                             (Q(public_event=True) |
                                                              (Q(participants__player_id=user.id) |
                                                               Q(hosts__player_id=user.id)))).distinct().order_by(
                '-date'))

    def get_queryset(self):
        user = self.request.user
        try:
            if user.is_staff:
                return self.search_filter(
                    RPEvent.objects.filter(finished=True, participants__isnull=False).distinct().order_by('-date'))
        except AttributeError:
            pass
        if not user.is_authenticated():
            return self.search_filter(RPEvent.objects.filter(finished=True, participants__isnull=False,
                                                             public_event=True).distinct().order_by('-date'))
        else:
            return self.search_filter(RPEvent.objects.filter(Q(finished=True) &
                                                             (Q(public_event=True) |
                                                              (Q(participants__player_id=user.id) |
                                                               Q(hosts__player_id=user.id)))).distinct().order_by(
                '-date'))

    def get_context_data(self, **kwargs):
        context = super(RPEventListView, self).get_context_data(**kwargs)
        context['page_title'] = 'Events'
        search_tags = ""
        text = self.request.GET.get("search_text")
        if text:
            search_tags += "&search_text=%s" % text
        event_type = self.request.GET.get("event_type")
        if event_type:
            search_tags += "&event_type=%s" % event_type
        context['search_tags'] = search_tags
        return context


class RPEventDetailView(DetailView):
    model = RPEvent
    template_name = 'dominion/cal_view.html'

    def get_context_data(self, **kwargs):
        context = super(RPEventDetailView, self).get_context_data(**kwargs)
        context['form'] = RPEventCommentForm
        can_view = False
        user = self.request.user
        private = not self.get_object().public_event
        if user.is_authenticated():
            if user.is_staff:
                can_view = True
            else:
                try:
                    ob = self.get_object()
                    dompc = user.Dominion
                    if dompc in ob.hosts.all() or dompc in ob.participants.all():
                        can_view = True
                except AttributeError:
                    pass
        # this will determine if we can read/write about private events, won't be used for public
        if private and not can_view:
            raise Http404
        context['can_view'] = can_view
        context['page_title'] = str(self.get_object())
        return context


class CrisisDetailView(DetailView):
    model = Crisis
    template_name = 'dominion/crisis_view.html'

    def get_context_data(self, **kwargs):
        context = super(CrisisDetailView, self).get_context_data(**kwargs)
        if not self.get_object().check_can_view(self.request.user):
            raise Http404
        context['page_title'] = str(self.get_object())
        context['viewable_actions'] = self.get_object().get_viewable_actions(self.request.user)
        context['updates_with_actions'] = [ob.update for ob in context['viewable_actions']]
        return context


class AssignedTaskListView(LimitPageMixin, ListView):
    model = AssignedTask
    template_name = 'dominion/task_list.html'
    paginate_by = 5

    def get_queryset(self):
        return AssignedTask.objects.filter(finished=True, observer_text__isnull=False).distinct().order_by('-week')

    def get_context_data(self, **kwargs):
        context = super(AssignedTaskListView, self).get_context_data(**kwargs)
        context['page_title'] = 'Rumors'
        return context


def event_comment(request, pk):
    """
    Makes an in-game comment on an event
    """
    char = request.user.db.char_ob
    if not char:
        raise Http404
    event = get_object_or_404(RPEvent, id=pk)
    if request.method == 'POST':
        form = RPEventCommentForm(request.POST)
        if form.is_valid():
            form.post_comment(char, event)
            return HttpResponseRedirect(reverse('dominion:display_event', args=(pk,)))
    return HttpResponseRedirect(reverse('dominion:display_event', args=(pk,)))

GRID_SIZE = 100
SUBGRID = 10


def map_image(request):
    """
    Generates a graphical map from the Land and Domain entries, omitting all NPC domains for now.
    You can pass a 'bw_grid=1' option to generate a black and white printable grid, and 'subgrid=1'
    to generate a gray 10x10 grid within each of the grid squares. Presently only available to
    logged-in staff.

    :param request: The HTTP request
    :return: The Django view response, in this case an image/png blob.
    """

    def draw_font_outline(draw, x, y, font, text):
        # This is awful
        draw.text((x - 1, y), text, font=font, fill='white')
        draw.text((x + 1, y), text, font=font, fill='white')
        draw.text((x, y - 1), text, font=font, fill='white')
        draw.text((x, y + 1), text, font=font, fill='white')
        draw.text((x, y), text, font=font, fill='black')

    TERRAIN_NAMES = {
        Land.COAST: 'Coastal',
        Land.DESERT: 'Deset',
        Land.GRASSLAND: 'Grassland',
        Land.HILL: 'Hills',
        Land.MOUNTAIN: 'Mountains',
        Land.OCEAN: 'Ocean',
        Land.PLAINS: 'Plains',
        Land.SNOW: 'Snow',
        Land.TUNDRA: 'Tundra',
        Land.FOREST: 'Forest',
        Land.JUNGLE: 'Jungle',
        Land.MARSH: 'Marsh',
        Land.ARCHIPELAGO: 'Archipelago',
        Land.FLOOD_PLAINS: 'Flood Plains',
        Land.ICE: 'Ice',
        Land.LAKES: 'Lakes',
        Land.OASIS: 'Oasis',
    }

    regen = False

    if request.user.is_authenticated():
        overlay = request.GET.get("overlay")
        regen = request.GET.get("regenerate")

    response = HttpResponse(content_type="image/png")

    if not os.path.exists("world/dominion/map/arxmap_generated.png"):
        regen = True

    if not regen and not overlay:
        mapimage = Image.open("world/dominion/map/arxmap_generated.png")
        mapimage.save(response, "PNG")
        return response

    min_x = 0
    min_y = 0
    max_x = 0
    max_y = 0

    lands = Land.objects.all()

    # This might be better done with annotations?
    for land in lands:
        min_x = min(min_x, land.x_coord)
        min_y = min(min_y, land.y_coord)
        max_x = max(max_x, land.x_coord)
        max_y = max(max_y, land.y_coord)

    total_width = max_x - min_x
    total_height = max_y - min_y

    mapimage = Image.open("world/dominion/map/arxmap_resized.jpg")
    mapdraw = ImageDraw.Draw(mapimage)

    font = ImageFont.truetype("world/dominion/map/Amaranth-Regular.otf", 14)
    domain_font = ImageFont.truetype("world/dominion/map/Amaranth-Regular.otf", 24)

    if overlay:
        for xloop in range(0, mapimage.size[0] / GRID_SIZE):
            for yloop in range(0, mapimage.size[1] / GRID_SIZE):
                x1 = (xloop * GRID_SIZE)
                y1 = (yloop * GRID_SIZE)
                x2 = x1 + GRID_SIZE
                y2 = y1 + GRID_SIZE

                for x in range(0, GRID_SIZE / SUBGRID):
                    for y in range(0, GRID_SIZE / SUBGRID):
                        subx = x1 + (SUBGRID * x)
                        suby = y1 + (SUBGRID * y)
                        mapdraw.rectangle([(subx, suby), (subx + SUBGRID, suby + SUBGRID)], outline="#8a8a8a")

                mapdraw.rectangle([(x1, y1), (x2, y2)], outline="#ffffff")

    try:
        for land in lands:
            x1 = ((land.x_coord - min_x) * GRID_SIZE)
            y1 = ((total_height - (land.y_coord - min_y)) * GRID_SIZE)

            if overlay:
                text_x = x1 + 10
                text_y = y1 + 60

                maptext = "%s (%d,%d)\n%s" % (TERRAIN_NAMES[land.terrain], land.x_coord, land.y_coord, land.region.name)
                draw_font_outline(mapdraw, text_x, text_y, font, maptext)

            domains = Domain.objects.filter(location__land=land)\
                .filter(ruler__house__organization_owner__members__player__player__isnull=False).distinct()

            if domains:
                for domain in domains:
                    circle_x = x1 + (SUBGRID * domain.location.x_coord)
                    circle_y = y1 + (SUBGRID * domain.location.y_coord)

                    mapdraw.ellipse([(circle_x, circle_y),
                                     (circle_x + SUBGRID, circle_y + SUBGRID)], '#000000')

                    label_x = circle_x + SUBGRID + 6
                    label_y = circle_y - 4
                    draw_font_outline(mapdraw, label_x, label_y, domain_font, domain.name)

    except Exception as exc:
        print str(exc)

    # Delete our drawing tool and commit the image
    del mapdraw

    if not overlay:
        mapimage.save("world/dominion/map/arxmap_generated.png", "PNG")
    mapimage.save(response, "PNG")
    return response


def map_wrapper(request):

    regen = False

    if request.user.is_authenticated():
        regen = request.GET.get("regenerate")

    if not os.path.exists("world/dominion/templates/dominion/_map_pregen_include.html"):
        regen = True

    if not regen:
        context = {
            'page_title': 'Map of Arvum',
        }
        return render(request, "dominion/map_pregen.html", context)

    map_links = []
    mapimage = Image.open("world/dominion/map/arxmap_resized.jpg")

    try:
        lands = Land.objects.all()

        min_x = 0
        min_y = 0
        max_x = 0
        max_y = 0

        # This might be better done with annotations?
        for land in lands:
            min_x = min(min_x, land.x_coord)
            min_y = min(min_y, land.y_coord)
            max_x = max(max_x, land.x_coord)
            max_y = max(max_y, land.y_coord)

        total_width = max_x - min_x
        total_height = max_y - min_y

        ratio = 1280.0 / mapimage.size[0]
        img_width = trunc(mapimage.size[0] * ratio)
        img_height = trunc(mapimage.size[1] * ratio)

        domain_font = ImageFont.truetype("world/dominion/map/Amaranth-Regular.otf", 24)

        for land in lands:
            x1 = (land.x_coord - min_x) * GRID_SIZE
            y1 = (total_height - (land.y_coord - min_y)) * GRID_SIZE

            domains = Domain.objects.filter(location__land=land)\
                .filter(ruler__house__organization_owner__members__player__player__isnull=False).distinct()

            if domains:
                for domain in domains:
                    domain_x = x1 + (SUBGRID * domain.location.x_coord)
                    domain_y = y1 + ((SUBGRID * domain.location.y_coord) - 4)

                    font_size = domain_font.getsize(domain.name)
                    domain_x2 = domain_x + font_size[0] + 10
                    domain_y2 = domain_y + font_size[1]

                    org = domain.ruler.house.organization_owner
                    org_url = reverse("help_topics:display_org", kwargs={'object_id': org.id})

                    map_data = {"x1": trunc(domain_x * ratio), "y1": trunc(domain_y * ratio),
                                "x2": trunc(domain_x2 * ratio), "y2": trunc(domain_y2 * ratio),
                                "url": org_url}
                    map_links.append(map_data)

    except Exception as exc:
        print str(exc)
        raise Http404

    context = {
        'imagemap_links': map_links,
        'img_width': img_width,
        'img_height': img_height,
        'page_title': 'Map of Arvum'
    }
    result = render_to_string("dominion/map_wrapper.html", context)

    pregen_file = open("world/dominion/templates/dominion/_map_pregen_include.html", "w")
    pregen_file.write(result)
    pregen_file.close()

    return render(request, "dominion/map_pregen.html", context)



