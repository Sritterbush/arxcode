from django.views.generic import ListView, DetailView, FormView
from .models import RPEvent, AssignedTask
from .forms import RPEventCommentForm
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.db.models import Q

# Create your views here.

class RPEventListView(ListView):
    model = RPEvent
    template_name = 'dominion/cal_list.html'
    paginate_by = 20
    
    def unfinished(self):
        user = self.request.user
        try:
            if user.is_staff:
                return RPEvent.objects.filter(finished=False).order_by('-date')
        except Exception:
            pass
        if not user:
            return RPEvent.objects.filter(finished=False, public_event=True).order_by('-date')
        else:
            return RPEvent.objects.filter(Q(finished=False) &
                                          (Q(public_event=True) |
                                          (Q(participants__player_id=user.id) |
                                           Q(hosts__player_id=user.id)))).distinct().order_by('-date')
    
    def get_queryset(self):
        user = self.request.user
        try:
            if user.is_staff:
                return RPEvent.objects.filter(finished=True).order_by('-date')
        except Exception:
            pass
        if not user:
            return RPEvent.objects.filter(finished=True, public_event=True).order_by('-date')
        else:
            return RPEvent.objects.filter(Q(finished=True) &
                                          (Q(public_event=True) |
                                          (Q(participants__player_id=user.id) |
                                           Q(hosts__player_id=user.id)))).distinct().order_by('-date')


class RPEventDetailView(DetailView):
    model = RPEvent
    template_name = 'dominion/cal_view.html'
    def get_context_data(self, **kwargs):
        context = super(RPEventDetailView, self).get_context_data(**kwargs)
        context['form'] = RPEventCommentForm
        can_view = False
        user = self.request.user
        if user:
            if user.is_staff:
                can_view = True
            else:
                try:
                    ob = self.get_object()
                    dompc = user.Dominion
                    if dompc in ob.hosts.all() or dompc in ob.participants.all():
                        can_view = True
                except Exception:
                    pass
        # this will determine if we can read/write about private events, won't be used for public
        context['can_view'] = can_view
        return context

class AssignedTaskListView(ListView):
    model = AssignedTask
    template_name = 'dominion/task_list.html'
    paginate_by = 5
    def get_queryset(self):
        return AssignedTask.objects.filter(finished=True, observer_text__isnull=False).order_by('-week')

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
