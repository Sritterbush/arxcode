import json

from django.http import HttpResponse
from django.views.generic import ListView
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.http import Http404
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied

from world.msgs.models import Journal

from .forms import (JournalMarkAllReadForm, JournalWriteForm, JournalMarkOneReadForm, JournalMarkFavorite,
                    JournalRemoveFavorite)
from server.utils.view_mixins import LimitPageMixin

from django.shortcuts import render, get_object_or_404
from commands.commands.bboards import get_boards
from typeclasses.bulletin_board.bboard import BBoard, Post
from evennia.utils import ansi

# Create your views here.


class JournalListView(LimitPageMixin, ListView):
    model = Journal
    template_name = 'msgs/journal_list.html'
    paginate_by = 20

    def search_filters(self, queryset):
        get = self.request.GET
        if not get:
            return queryset
        senders = get.get('sender_name', "").split()
        if senders:
            exclude_senders = [ob[1:] for ob in senders if ob.startswith("-")]
            senders = [ob for ob in senders if not ob.startswith("-")]
            sender_filter = Q()
            for sender in senders:
                sender_filter |= Q(db_sender_objects__db_key__iexact=sender)
            queryset = queryset.filter(sender_filter)
            sender_filter = Q()
            for sender in exclude_senders:
                sender_filter |= Q(db_sender_objects__db_key__iexact=sender)
            queryset = queryset.exclude(sender_filter)
        receivers = get.get('receiver_name', "").split()
        if receivers:
            exclude_receivers = [ob[1:] for ob in receivers if ob.startswith("-")]
            receivers = [ob for ob in receivers if not ob.startswith("-")]
            receiver_filter = Q()
            for receiver in receivers:
                receiver_filter |= Q(db_receivers_objects__db_key__iexact=receiver)
            queryset = queryset.filter(receiver_filter)
            receiver_filter = Q()
            for receiver in exclude_receivers:
                receiver_filter |= Q(db_receivers_objects__db_key__iexact=receiver)
            queryset = queryset.exclude(receiver_filter)
        text = get.get('search_text', None)
        if text:
            queryset = queryset.filter(db_message__icontains=text)
        if self.request.user and self.request.user.is_authenticated():
            favtag = "pid_%s_favorite" % self.request.user.id
            favorites = get.get('favorites', None)
            if favorites:
                queryset = queryset.filter(db_tags__db_key=favtag)
        return queryset

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            qs = Journal.white_journals.order_by('-db_date_created')
        else:
            qs = Journal.objects.all_permitted_journals(user).all_unread_by(user).order_by('-db_date_created')
        return self.search_filters(qs)

    def get_context_data(self, **kwargs):
        context = super(JournalListView, self).get_context_data(**kwargs)
        # paginating our read journals as well as unread
        search_tags = ""
        sender = self.request.GET.get('sender_name', None)
        if sender:
            search_tags += "&sender_name=%s" % sender
        receiver = self.request.GET.get('receiver_name', None)
        if receiver:
            search_tags += "&receiver_name=%s" % receiver
        search_text = self.request.GET.get('search_text', None)
        if search_text:
            search_tags += "&search_text=%s" % search_text
        favorites = self.request.GET.get('favorites', None)
        if favorites:
            search_tags += "&favorites=True"
        context['search_tags'] = search_tags
        context['write_journal_form'] = JournalWriteForm()
        context['page_title'] = 'Journals'
        if self.request.user and self.request.user.is_authenticated():
            context['fav_tag'] = "pid_%s_favorite" % self.request.user.id
        else:
            context['fav_tag'] = None
        return context

    # noinspection PyUnusedLocal
    def post(self, request, *args, **kwargs):
        if "mark_all_read" in request.POST:
            form = JournalMarkAllReadForm(request.POST)
            if form.is_valid():
                for msg in form.cleaned_data['choices']:
                    msg.db_receivers_accounts.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_one_read" in request.POST:
            form = JournalMarkOneReadForm(request.POST)
            if form.is_valid():
                msg = form.cleaned_data['choice']
                msg.db_receivers_accounts.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_favorite" in request.POST:
            form = JournalMarkFavorite(request.POST)
            if form.is_valid():
                form.tag_msg(self.request.user.char_ob)
        if "remove_favorite" in request.POST:
            form = JournalRemoveFavorite(request.POST)
            if form.is_valid():
                form.untag_msg(self.request.user.char_ob)
        if "write_journal" in request.POST:
            form = JournalWriteForm(request.POST)
            if form.is_valid():
                # write journal
                form.create_journal(self.request.user.char_ob)
            else:
                raise Http404(form.errors)
        return HttpResponseRedirect(reverse('msgs:list_journals'))


class JournalListReadView(JournalListView):
    template_name = 'msgs/journal_list_read.html'

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated() or not user.db.char_ob:
            raise PermissionDenied("You must be logged in.")
        qs = Journal.objects.all_permitted_journals(user).all_read_by(user).order_by('-db_date_created')
        return self.search_filters(qs)


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
        ret = map(get_response, Journal.white_journals.filter(db_date_created__gt=timestamp
                                                              ).order_by('-db_date_created'))
        return HttpResponse(json.dumps(ret), content_type='application/json')
    if not API_CACHE:  # cache the list of all of them
        ret = map(get_response, Journal.white_journals.order_by('-db_date_created'))
        API_CACHE = json.dumps(ret)
    return HttpResponse(API_CACHE, content_type='application/json')


def board_list(request):
    def map_board(board, request):
        return {
            'id': board.id,
            'name': board.key,
            'unread': board.num_of_unread_posts(request.user, old=False)
        }

    raw_boards = get_boards(request.user)
    print ("Raw boards: " + str(raw_boards))
    boards = map(lambda board: map_board(board, request), raw_boards)
    print ("Boards: " + str(boards))
    context = {
        'boards': boards,
        'page_title': 'Boards'
    }
    return render(request, 'msgs/board_list.html', context)


def board_for_request(request, board_id):
    try:
        board = BBoard.objects.get(id=board_id)
    except BBoard.DoesNotExist, BBoard.MultipleObjectsReturned:
        raise Http404

    character = request.user.db.char_ob

    if not board.access(character, 'read'):
        raise Http404

    return board


def posts_for_request(request, board):
    return list(board.get_all_posts(old=False))[::-1]


def post_list(request, board_id):
    def post_map(post, board, read_posts):
        return {
            'id': post.id,
            'poster': board.get_poster(post),
            'subject': post.db_header,
            'date': post.db_date_created.strftime("%x"),
            'unread': post not in read_posts
        }

    board = board_for_request(request, board_id)
    raw_posts = posts_for_request(request, board)
    read_posts = Post.objects.all_read_by(request.user)
    posts = map(lambda post: post_map(post, board, read_posts), raw_posts)
    return render(request, 'msgs/post_list.html', {'board': board, 'page_title': board.key, 'posts': posts})


def post_view_all(request, board_id):
    def post_map(post, board, read_posts):
        return {
            'id': post.id,
            'poster': board.get_poster(post),
            'subject': post.db_header,
            'date': post.db_date_created.strftime("%x"),
            'unread': post not in read_posts,
            'text': ansi.strip_ansi(post.db_message)
        }

    board = board_for_request(request, board_id)
    raw_posts = posts_for_request(request, board)
    read_posts = Post.objects.all_read_by(request.user)
    posts = map(lambda post: post_map(post, board, read_posts), raw_posts)
    return render(request, 'msgs/post_view_all.html', {'board': board, 'page_title': board.key + " - Posts", 'posts': posts})


def post_view(request, board_id, post_id):
    board = board_for_request(request, board_id)
    raw_posts = posts_for_request(request, board)
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExit, Post.MultipleObjectsReturned:
        raise Http404

    # No cheating and viewing posts outside this board
    if post not in raw_posts:
        raise Http404

    print ("Got our post: " + str(post))
    board.mark_read(request.user, post)

    context = {
        'id': post.id,
        'poster': board.get_poster(post),
        'subject': post.db_header,
        'date': post.db_date_created.strftime("%x"),
        'text': ansi.strip_ansi(post.db_message),
        'page_title': board.key + " - " + post.db_header
    }
    return render(request, 'msgs/post_view.html', context)