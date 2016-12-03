import json

from django.http import HttpResponse
from django.views.generic import ListView
from evennia.comms.models import Msg
from .forms import JournalMarkAllReadForm, JournalWriteForm, JournalMarkOneReadForm
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
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
            return Msg.objects.filter((Q(db_header__icontains='white_journal') |
                                       Q(db_header__icontains='black_journal')) &
                                      Q(db_receivers_players=user)).order_by('-db_date_created')
        return Msg.objects.filter((Q(db_header__icontains='white_journal') |
                                    (Q(db_header__icontains='black_journal') &
                                     Q(db_sender_objects=user.db.char_ob))) &
                                  Q(db_receivers_players=user)).order_by('-db_date_created')

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            return Msg.objects.filter(db_header__icontains="white_journal").order_by('-db_date_created')
        if user.is_staff:
            return Msg.objects.filter((Q(db_header__icontains='white_journal') |
                                       Q(db_header__icontains='black_journal')) &
                                      ~Q(db_receivers_players=user)).order_by('-db_date_created')
        return Msg.objects.filter((Q(db_header__icontains='white_journal') |
                                    (Q(db_header__icontains='black_journal') &
                                     Q(db_sender_objects=user.db.char_ob))) &
                                  ~Q(db_receivers_players=user)).order_by('-db_date_created')

    def get_context_data(self, **kwargs):
        context = super(JournalListView, self).get_context_data(**kwargs)
        # paginating our read journals as well as unread
        read_page = self.request.GET.get('read_page')
        if read_page:
            context['read_is_active'] = True
        else:
            context['read_is_active'] = False
        context['write_journal_form'] = JournalWriteForm()
        return context

    # noinspection PyUnusedLocal
    def post(self, request, *args, **kwargs):
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
                # write journal
                form.create_journal(self.request.user.db.char_ob)
            else:
                raise Http404(form.errors)
        return HttpResponseRedirect(reverse('msgs:list_journals'))

API_CACHE = None


def journal_list_json(request):
    def get_fullname(char):
        commoner_names = {
            'Velenosa': 'Masque',
            'Valardin': 'Honor',
            'Crownsworn': 'Crown',
            'Redrain': 'Frost',
            'Grayson': 'Crucible',
            'Thrax': 'Waters'
        }
        last = commoner_names.get(char.db.fealty, "") if char.db.family == "None" else char.db.family
        return "{0} {1}".format(char.key, last)

    def get_response(entry):
        try:
            sender = entry.senders[0]
        except IndexError:
            sender = None
        try:
            target = entry.db_receivers_objects.all()[0]
        except IndexError:
            target = None
        from world.msgs.messagehandler import MessageHandler
        ic_date = MessageHandler.get_date_from_header(entry)
        return {
            'id': entry.id,
            'sender': get_fullname(sender) if sender else "",
            'target': get_fullname(target) if target else "",
            'message': entry.db_message,
            'ic_date': ic_date
        }

    try:
        timestamp = request.GET.get('timestamp', 0)
        import datetime
        timestamp = datetime.datetime.fromtimestamp(float(timestamp))
    except (AttributeError, ValueError, TypeError):
        timestamp = None
    global API_CACHE
    if timestamp:
        ret = map(get_response, Msg.objects.filter(Q(db_date_created__gt=timestamp) &
                                                   Q(db_header__icontains="white_journal")
                                                   ).order_by('-db_date_created'))
        return HttpResponse(json.dumps(ret), content_type='application/json')
    if not API_CACHE:  # cache the list of all of them
        ret = map(get_response, Msg.objects.filter(db_header__icontains="white_journal"
                                                   ).order_by('-db_date_created'))
        API_CACHE = json.dumps(ret)
    return HttpResponse(API_CACHE, content_type='application/json')
