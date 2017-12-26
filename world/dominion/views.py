from django.views.generic import ListView, DetailView
from .models import RPEvent, AssignedTask, Crisis, Land, Domain
from .forms import RPEventCommentForm
from django.http import HttpResponseRedirect, HttpResponse
from django.http import Http404
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.db.models import Q, Min, Max
from server.utils.view_mixins import LimitPageMixin
from PIL import Image, ImageDraw

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


def map_image(request):
    GRID_SIZE = 100

    TERRAIN_COLORS = {
        Land.COAST: '#a0a002',
        Land.DESERT: '#ffff00',
        Land.GRASSLAND: '#a0ff00',
        Land.HILL: '#00ff00',
        Land.MOUNTAIN: '#afafaf',
        Land.OCEAN: '#000080',
        Land.PLAINS: '#808000',
        Land.SNOW: '#ffffff',
        Land.TUNDRA: '#cccccc',
        Land.FOREST: '#00aa00',
        Land.JUNGLE: '#008800',
        Land.MARSH: '#ff8000',
        Land.ARCHIPELAGO: '#00ff00',
        Land.FLOOD_PLAINS: '#00ff88',
        Land.ICE: '#cfcfcf',
        Land.LAKES: '#0000a0',
        Land.OASIS: '#0000ff',
    }

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

    try:
        if not request.user.is_authenticated() or not request.user.is_staff:
            return Http404
    except AttributeError:
        return Http404

    response = HttpResponse(content_type="image/png")

    min_x = 0
    min_y = 0
    max_x = 0
    max_y = 0

    lands = Land.objects.all()
    for land in lands:
        min_x = min(min_x, land.x_coord)
        min_y = min(min_y, land.y_coord)
        max_x = max(max_x, land.x_coord)
        max_y = max(max_y, land.y_coord)

    total_width = max_x - min_x
    total_height = max_y - min_y

    mapimage = Image.new("RGB", (total_width * GRID_SIZE, total_height * GRID_SIZE), "#000080")
    mapdraw = ImageDraw.Draw(mapimage)

    try:
        for land in lands:
            x1 = (land.x_coord - min_x) * GRID_SIZE
            y1 = (total_height - (land.y_coord - min_y)) * GRID_SIZE
            x2 = x1 + GRID_SIZE + 1
            y2 = y1 + GRID_SIZE + 1
            mapdraw.rectangle([(x1, y1), (x2, y2)], fill=TERRAIN_COLORS[land.terrain])

            text_color = "black"
            if (land.terrain == Land.LAKES) or (land.terrain == Land.OASIS):
                text_color = "white"

            text_x = x1 + 5
            text_y = y1 + 10
            mapdraw.text((text_x, text_y), "%s (%d,%d)\n%s" % (TERRAIN_NAMES[land.terrain], land.x_coord, land.y_coord,
                                                               land.region.name), text_color)

            domains = Domain.objects.filter(land=land)\
                .filter(ruler__house__organization_owner__members__player__player__isnull=False).distinct()
            text_x = x1 + 10
            text_y = y1 + 60
            if domains:
                result = ""
                for domain in domains:
                    result = "%s%s\n" % (result, domain.name)
                mapdraw.text((text_x, text_y), result, text_color)

    except Exception as exc:
        print str(exc)

    # Delete our drawing tool and commit the image
    del mapdraw

    mapimage.save(response, "PNG")
    return response
