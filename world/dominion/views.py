from django.views.generic import ListView, DetailView
from .models import RPEvent, AssignedTask, Crisis
from .forms import RPEventCommentForm
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.db.models import Q
from server.utils.view_mixins import LimitPageMixin

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
