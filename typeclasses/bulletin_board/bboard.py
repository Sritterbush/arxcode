"""
Default Typeclass for Bulletin Boards, based loosely on bboards.

See objects.objects for more information on Typeclassing.
"""
from typeclasses.objects import Object
from world.msgs.models import Post
from world.msgs.managers import POST_TAG, TAG_CATEGORY


class BBoard(Object):
    """
    This is the base class for all Bulletin Boards. Inherit from this to create different
    types of communication bboards.
    """
    @staticmethod
    def tag_obj(post):
        """Tags an object to show it as being a bulletin board post"""
        tagkey = POST_TAG
        category = TAG_CATEGORY
        post.tags.add(tagkey, category=category)
        return post
    
    def bb_post(self, poster_obj, msg, subject="No Subject", poster_name=None,
                event=None, announce=True):
        """
        Post the message to the board.
        """
        post = Post(db_message=msg, db_header=subject)
        post.save()
        posted_by = "Unknown"
        if poster_obj:
            post.senders = poster_obj
            post.receivers = poster_obj
            posted_by = poster_obj
        if poster_name:
            post.db_sender_external = poster_name
            post.save()
            posted_by = poster_name
        self.tag_obj(post)
        if event:
            event.tag_obj(post)
        self.receiver_object_set.add(post)
        if self.max_posts and self.posts.count() > self.max_posts:
            posts = self.posts.exclude(db_tags__db_key="sticky_post")
            if "archive_posts" in self.tags.all():
                self.archive_post(posts.first())
            else:
                posts.first().delete()
        if announce:
            post_num = self.posts.count()
            notify = "\n{{wNew post on {0} by {1}:{{n {2}".format(self.key, posted_by, subject)
            notify += "\nUse {w@bbread %s/%s {nto read this message." % (self.key, post_num)
            self.notify_subs(notify)
        return post

    @property
    def max_posts(self):
        return self.db.max_posts or 100

    def notify_subs(self, notification):
        subs = [ob for ob in self.db.subscriber_list if self.access(ob, "read")
                and "no_post_notifications" not in ob.tags.all() and (not hasattr(ob, 'is_guest') or not ob.is_guest())]
        for sub in subs:
            sub.msg(notification)

    def bb_orgstance(self, poster_obj, org, msg, postnum):
        """
        Post teeny commentary as addendum to board message.
        
        Args:
            poster_obj: Character
            org: Organization
            msg: str
            postnum: int
        """
        tagname = "%s_comment" % org
        # I love you so much <3 Do not let orange text bother you!
        # I love you too <3 Because board is calling this, board is now self.
        post = self.get_post(poster_obj, postnum)
        if not post:
            return
        if post.tags.get(tagname, category="org_comment"):
            poster_obj.msg("{w%s{n has already declared a position on this matter." % org)
            return
        if not org.access(poster_obj, "declarations"):
            poster_obj.msg("Your {w%s{n rank isn't yet high enough to make declarations on their behalf." % org)
            return
        if len(msg) > 140:
            poster_obj.msg("That message is too long for a brief declaration.")
            return
        post.db_message += "\n\n--- {w%s{n Stance ---\n%s" % (org, msg)
        post.tags.add("%s_comment" % org, category="org_comment")
        post.save()
        poster_obj.msg("{w%s{n successfully declared a stance on '%s'." % (org, post.db_header))
        self.notify_subs("{w%s has commented upon proclamation %s.{n" % (org, postnum))
        from server.utils.arx_utils import inform_staff
        inform_staff("{c%s {whas posted an org stance for %s." % (poster_obj, org))

    def has_subscriber(self, pobj):
        if pobj in self.db.subscriber_list:
            return True
        else:
            return False

    def get_unread_posts(self, pobj, old=False):
        if not old:
            return self.posts.all_unread_by(pobj)
        return self.archived_posts.all_unread_by(pobj)

    def num_of_unread_posts(self, pobj, old=False):
        return self.get_unread_posts(pobj, old).count()

    def get_post(self, pobj, postnum, old=False):
        # pobj is a player.
        postnum -= 1
        if old:
            posts = self.archived_posts
        else:
            posts = self.posts
        if (postnum < 0) or (postnum >= len(posts)):
            pobj.msg("Invalid message number specified.")
        else:
            return list(posts)[postnum]

    def get_latest_post(self):
        try:
            return self.posts.last()
        except Post.DoesNotExist:
            return None

    def get_all_posts(self, old=False):
        if not old:
            return self.posts
        return self.archived_posts
        
    def at_object_creation(self):
        """
        Run at bboard creation.
        """
        self.db.subscriber_list = []

    def subscribe_bboard(self, joiner):
        """
        Run right before a bboard is joined. If this returns a false value,
        bboard joining is aborted.
        """
        if joiner not in self.db.subscriber_list:
            self.db.subscriber_list.append(joiner)
            return True
        else:
            return False

    def unsubscribe_bboard(self, leaver):
        """
        Run right before a user leaves a bboard. If this returns a false
        value, leaving the bboard will be aborted.
        """
        if leaver in self.db.subscriber_list:
            self.db.subscriber_list.remove(leaver)
            return True
        else:
            return False

    def delete_post(self, post):
        """
        Remove post if it's inside the bulletin board.
        """
        if post in self.posts:
            post.delete()
            return True
        if post in self.archived_posts:
            post.delete()
            return True

    @staticmethod
    def sticky_post(post):
        post.tags.add("sticky_post")
        return True

    @staticmethod
    def edit_post(pobj, post, msg):
        if post.tags.get(category="org_comment"):
            pobj.msg("The post has already had org responses.")
            return
        post.db_message = msg
        post.save()
        return True
    
    @property
    def posts(self):
        return Post.objects.for_board(self).exclude(db_tags__db_key="archived")

    @property
    def archived_posts(self):
        return Post.objects.for_board(self).filter(db_tags__db_key="archived")

    def read_post(self, caller, post, old=False):
        """
        Helper function to read a single post.
        """
        if old:
            posts = self.archived_posts
        else:
            posts = self.posts
        # format post
        sender = self.get_poster(post)
        message = "\n{w" + "-"*60 + "{n\n"
        message += "{wBoard:{n %s, {wPost Number:{n %s\n" % (self.key, list(posts).index(post) + 1)
        message += "{wPoster:{n %s\n" % sender
        message += "{wSubject:{n %s\n" % post.db_header
        message += "{wDate:{n %s\n" % post.db_date_created.strftime("%x %X")
        message += "{w" + "-"*60 + "{n\n"
        message += post.db_message
        message += "\n{w" + "-" * 60 + "{n\n"
        caller.msg(message)
        if caller.is_guest():
            return
        # mark it read
        self.mark_read(caller, post)

    @staticmethod
    def archive_post(post):
        post.tags.add("archived")
        return True

    @staticmethod
    def mark_unarchived(post):
        post.tags.remove("archived")

    @staticmethod
    def mark_read(caller, post):
        post.db_receivers_accounts.add(caller)
        if caller.db.bbaltread:
            try:
                for alt in (ob.player for ob in caller.roster.alts):
                    post.db_receivers_accounts.add(alt)
            except AttributeError:
                pass

    @staticmethod
    def get_poster(post):
        sender = ""
        if post.db_sender_accounts.all():
            sender += ", ".join(str(ob).capitalize() for ob in post.db_sender_accounts.all())
        if post.db_sender_objects.all():
            if sender:
                sender += ", "
            sender += ", ".join(str(ob).capitalize() for ob in post.db_sender_objects.all())
        if post.db_sender_external:
            sender = post.db_sender_external
        if not sender:
            sender = "No One"
        return sender


def convert_tag():
    from evennia.typeclasses.tags import Tag
    tag = Tag.objects.get(db_key="Board Post")
    tag.db_key = POST_TAG
    tag.db_category = TAG_CATEGORY
    tag.db_model = "msg"
    tag.save()
