"""
Default Typeclass for Bulletin Boards, based loosely on bboards.

See objects.objects for more information on Typeclassing.
"""
#from src.comms import Msg, TempMsg, bboardDB
from typeclasses.objects import Object
from datetime import datetime
from evennia.utils.utils import datetime_format


class BBoard(Object):
    """
    This is the base class for all Bulletin Boards. Inherit from this to create different
    types of communication bboards.
    """
       

    def bb_post(self, poster_obj, msg, subject="No Subject", poster_name=None):
        """
        Post the message to the board.
        """
        posted_by = "No One"
        list_of_readers = []
        if poster_name: #some form of system or script event
            posted_by = poster_name
        elif poster_obj:
            posted_by = poster_obj.key.capitalize()
            list_of_readers.append(poster_obj)
        date = datetime.today().strftime("%m-%d-%y")
        time = datetime_format(datetime.now())
        post = {'Poster': posted_by,
                'Subject': subject,
                'Msg': msg,
                'Date': date,
                'Time': time,
                'Readers': list_of_readers}
        self.db.posts.append(post)
        for sub in self.db.subscriber_list:
            notify = "\n{{wNew post on {0} by {1}:{{n {2}".format(self.key, posted_by, subject)
            sub.msg(notify)

    def has_subscriber(self, pobj):
        if pobj in self.db.subscriber_list:
            return True
        else:
            return False

    def num_of_unread_posts(self, pobj):
        num_posts = 0
        for post in self.db.posts:
            if pobj not in post['Readers']:
                num_posts += 1
        return num_posts

    def get_post(self, pobj, postnum):
        postnum -= 1
        if (postnum < 0) or (postnum >= len(self.db.posts)):
            pobj.msg("Invalid message number specified.")
        else:
            return self.db.posts[postnum]

    def get_latest_post(self):
        if self.db.posts:
            return self.db.posts[-1]

    def get_all_posts(self):
        return self.db.posts
        

    def at_object_creation(self):
        """
        Run at bboard creation.
        """
        self.db.subscriber_list = []
        self.db.posts = []
        self.db.bboard = True

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

    def is_bboard(self):
        """
        Identifier method. All typeclasses will have some variant
        of this going forward for doublechecking in searches.
        """
        return True

    def delete_post(self, post_num, pobj):
        """
        Remove post if it's inside the bulletin board.
        """
        post_num -= 1
        if post_num < 0 or post_num >= len(self.db.posts):
            return False
        del self.db.posts[post_num]
        return True

        pass

