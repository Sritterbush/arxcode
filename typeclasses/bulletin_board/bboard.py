"""
Default Typeclass for Bulletin Boards, based loosely on bboards.

See objects.objects for more information on Typeclassing.
"""
from typeclasses.objects import Object
from evennia.comms.models import Msg


class BBoard(Object):
    """
    This is the base class for all Bulletin Boards. Inherit from this to create different
    types of communication bboards.
    """
    @staticmethod
    def tag_obj(post):
        """Tags an object to show it as being a bulletin board post"""
        tagkey = "Board Post"
        category = "board"
        from evennia.typeclasses.tags import Tag
        try:
            tag = Tag.objects.get(db_key=tagkey, db_category=category,
                                  db_model="msg")
        except Tag.DoesNotExist:
            tag = Tag.objects.create(db_key=tagkey, db_category=category,
                                     db_model="msg")
        post.db_tags.add(tag)
        return post
    
    def bb_post(self, poster_obj, msg, subject="No Subject", poster_name=None,
                event=None, announce=True):
        """
        Post the message to the board.
        """
        post = Msg(db_message=msg, db_header=subject)
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
        if announce:
            for sub in self.db.subscriber_list:
                notify = "\n{{wNew post on {0} by {1}:{{n {2}".format(self.key, posted_by, subject)
                sub.msg(notify)
        if self.db.max_posts and self.posts.count() > self.db.max_posts:
            self.posts.first().delete()
        return post

    def has_subscriber(self, pobj):
        if pobj in self.db.subscriber_list:
            return True
        else:
            return False

    def get_unread_posts(self, pobj):
        return self.posts.exclude(db_receivers_players=pobj)

    def num_of_unread_posts(self, pobj):
        return self.get_unread_posts(pobj).count()

    def get_post(self, pobj, postnum):
        postnum -= 1
        if (postnum < 0) or (postnum >= len(self.posts)):
            pobj.msg("Invalid message number specified.")
        else:
            return list(self.posts)[postnum]

    def get_latest_post(self):
        try:
            return self.posts.last()
        except Msg.DoesNotExist:
            return None

    def get_all_posts(self):
        return self.posts
        
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

    def delete_post(self, post_num):
        """
        Remove post if it's inside the bulletin board.
        """
        post_num -= 1
        if post_num < 0 or post_num >= len(self.posts):
            return False
        self.posts[post_num].delete()
        return True

    @staticmethod
    def edit_post(post, msg):
        post.db_message = msg
        post.save()
        return True
    
    @property
    def posts(self):
        return self.receiver_object_set.filter(db_tags__db_key="Board Post")

    def read_post(self, caller, post, board_num=None):
        """
        Helper function to read a single post.
        """
        # format post
        sender = self.get_poster(post)
        message = "\n{w" + "-"*60 + "{n\n"
        message += "{wBoard:{n %s, {wPost Number:{n %s\n" % (self.key, list(self.posts).index(post) + 1)
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
    def mark_read(caller, post):
        post.db_receivers_players.add(caller)
        if caller.db.bbaltread:
            try:
                for alt in (ob.player for ob in caller.roster.alts):
                    post.db_receivers_players.add(alt)
            except AttributeError:
                pass

    @staticmethod
    def get_poster(post):
        sender = ""
        if post.db_sender_players.all():
            sender += ", ".join(str(ob).capitalize() for ob in post.db_sender_players.all())
        if post.db_sender_objects.all():
            if sender:
                sender += ", "
            sender += ", ".join(str(ob).capitalize() for ob in post.db_sender_objects.all())
        if post.db_sender_external:
            sender = post.db_sender_external
        if not sender:
            sender = "No One"
        return sender

    # def convert_posts(self):
    #     """
    #     Helper function to convert old-style posts stored in attribute to new posts
    #     """
    #     try:
    #         from server.utils.utils import broadcast
    #         broadcast("Converting posts of board %s." % self.key)
    #     except Exception:
    #         pass
    #     for post in self.db.posts:
    #         posted_by = post['Poster']
    #         subject = post['Subject']
    #         msg = post['Msg']
    #         date = post['Date']
    #         time = post['Time']
    #         list_of_readers = post['Readers']
    #         from typeclasses.players import Player
    #         try:
    #             pobj = Player.objects.get(username__iexact=posted_by)
    #             poster_name=None
    #         except Player.DoesNotExist:
    #             pobj = None
    #             poster_name=posted_by
    #         post_obj = self.bb_post(poster_obj=pobj, msg=msg, subject=subject,
    #                                 poster_name=poster_name, announce=False)
    #         for reader in list_of_readers:
    #             try:
    #                 post_obj.db_receivers_players.add(reader)
    #             except Exception:
    #                 import traceback
    #                 traceback.print_exc()
    #     self.attributes.remove("posts")
