from django.views.generic import ListView, DetailView, FormView
from evennia.comms.models import Msg
from .forms import JournalMarkAllReadForm, JournalWriteForm, JournalMarkOneReadForm
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from server.utils.view_mixins import LimitPageMixin

# Create your views here.

class JournalListView(LimitPageMixin, ListView):
    model = Msg
    template_name = 'msgs/journal_list.html'
    paginate_by = 20
    additional_pages = {'read_journals': ('get_read_journals', 'read_page')}
    def get_read_journals(self):
        user = self.request.user
        if not user or not user.is_authenticated():
            return []
        if user.is_staff:
            return Msg.objects.filter( (Q(db_header__icontains='white_journal') |
                                    Q(db_header__icontains='black_journal')) &
                                    Q(db_receivers_players=user)).order_by('-db_date_created')
        return Msg.objects.filter(( Q(db_header__icontains='white_journal') |
                                    (Q(db_header__icontains='black_journal') &
                                    Q(db_sender_objects=user.db.char_ob))) &
                                  Q(db_receivers_players=user)).order_by('-db_date_created')
    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            return Msg.objects.filter(db_header__icontains="white_journal").order_by('-db_date_created')
        if user.is_staff:
            return Msg.objects.filter( (Q(db_header__icontains='white_journal') |
                                     Q(db_header__icontains='black_journal')) &
                                    ~Q(db_receivers_players=user)).order_by('-db_date_created')
        return Msg.objects.filter( (Q(db_header__icontains='white_journal') |
                                    (Q(db_header__icontains='black_journal') &
                                    Q(db_sender_objects=user.db.char_ob))) &
                                  ~Q(db_receivers_players=user)).order_by('-db_date_created')
    def get_context_data(self, **kwargs):
        context = super(JournalListView, self).get_context_data(**kwargs)
        # paginating our read journals as well as unread
##        read_journals = self.get_read_journals()
##        paged_read = Paginator(read_journals, 20)
        read_page = self.request.GET.get('read_page')
        if read_page:
            context['read_is_active'] = True
        else:
            context['read_is_active'] = False
##        try:
##            read_journals = paged_read.page(read_page)
##        except PageNotAnInteger:
##            read_journals = paged_read.page(1)
##        except EmptyPage:
##            read_journals = paged_read.page(paged_read.num_pages)
##        context['read_journals'] = read_journals
        context['write_journal_form'] = JournalWriteForm()
        return context

    def post(self, request, *args, **kwargs):
        #context = self.get_context_data(**kwargs)
        if "mark_all_read" in request.POST:
            form = JournalMarkAllReadForm(request.POST)
            if form.is_valid():
                for msg in form.cleaned_data['choices']:
                    msg.db_receivers_players.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_one_read" in request.POST:
            form = JournalMarkOneReadForm(request.POST)
            if form.is_valid():
                msg = form.cleaned_data['choice']
                msg.db_receivers_players.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "write_journal" in request.POST:
            form = JournalWriteForm(request.POST)
            if form.is_valid():
                #write journal
                form.create_journal(self.request.user.db.char_ob)
                #context['read_is_active'] = True
                #return render(request, self.template_name, context)
            else:
                raise Http404(form.errors)
        return HttpResponseRedirect(reverse('msgs:list_journals'))

API_CACHE = None

def journal_list_json(request):
    def get_response(entry):
        sender = entry.senders.0
        target = entry.db_receivers_objects.all.0
        return {
            'id': entry.db.id,
            'sender': "{0} {1}".format(sender.key, sender.db.family),
            'target': "{0} {1}".format(target.key, target.db.family),
            'message': entry.db_message
        }

    global API_CACHE
    if not API_CACHE:
        timestamp = request.timestamp if request.timestamp else 0
        ret = map(get_response, Msg.objects.filter(Q(db_date_created__gt=timestamp) &
                                                   Q(db_header__icontains="white_journal")).order_by('-db_date_created'))
        API_CACHE = json.dumps(ret)
    return HttpResponse(API_CACHE, content_type='application/json')
