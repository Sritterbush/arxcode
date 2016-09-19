"""
This script keeps a timer that will cause an update to happen
on a weekly basis. Things we'll be updating are counting votes
for players, and processes for Dominion.
"""

from time import time
from django.conf import settings
from .scripts import Script
from evennia.utils.create import create_script
from server.utils.utils import inform_staff
from evennia.players.models import PlayerDB
from evennia.objects.models import ObjectDB
from world.dominion.models import PlayerOrNpc, AssetOwner, Army, AssignedTask
import traceback
from django.db.models import Q
from datetime import datetime, timedelta

EVENT_SCRIPT_NAME = "Weekly Update"
# number of seconds in a week
WEEK_INTERVAL = 604800
BOARD_NAME = 'News'


class WeeklyEvents(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = EVENT_SCRIPT_NAME
        self.desc = "Triggers weekly events"
        self.interval = 3600
        self.persistent = True
        self.start_delay = True
        self.attributes.add("run_time", 0.0)  # OOC time

    def at_repeat(self):
        """
        Called every minute to update the timers.
        """
        time = self.db.run_time or 0
        time += 3600
        self.db.run_time = time
        if self.check_event():
            self.do_weekly_events()

    def check_event(self):
        """
        Determine if a week has passed. Return true if so.
        """
        if self.db.run_time >= WEEK_INTERVAL:
            return True
        else:
            return False

    def do_weekly_events(self, reset=True):
        """
        It's time for us to do events, like count votes, update dominion, etc.
        """
        self.db.run_time = 0
        # processing for each player
        self.do_events_per_player(reset)
        # awarding votes we counted
        self.award_vote_xp()
        self.post_top_rpers()
        # prestige adjustments
        self.award_prestige()
        self.post_top_prestige()
        # dominion stuff
        self.do_dominion_events()
        self.do_investigations()
        self.do_cleanup()
        self.db.week += 1

    def do_dominion_events(self):
        from django.db.models import Q
        for owner in AssetOwner.objects.filter((Q(organization_owner__isnull=False) &
                                                Q(organization_owner__members__player__player__isnull=False) &
                                                Q(organization_owner__members__player__player__roster__frozen=False))|
                                               Q(player__player__roster__roster__name="Active")).distinct():
            try:
                owner.do_weekly_adjustment(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in %s's weekly adjustment: %s" % (owner, err)
        for army in Army.objects.all():
            try:
                army.execute_orders(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in %s's army orders: %s" % (army, err)
        self.do_tasks()
        inform_staff("Dominion weekly events processed for week %s." % self.db.week)

    def do_tasks(self):
        for task in AssignedTask.objects.filter(finished=False):
            try:
                task.payout_check(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in task completion: %s" % err

    def do_investigations(self):
        from web.character.models import Investigation
        for investigation in Investigation.objects.filter(active=True, ongoing=True):
            try:
                investigation.process_events()
            except Exception as err:
                traceback.print_exc()
                print "Error in investigation: %s" % err

    def do_cleanup(self):
        try:
            from world.msgs.models import Inform
            date = datetime.now()
            offset = timedelta(days=-30)
            date = date + offset
            qs = Inform.objects.filter(date_sent__lte=date)
            for ob in qs:
                ob.delete()
        except Exception as err:
            traceback.print_exc()
            print "Error in cleanup: %s" % err
            

    def do_events_per_player(self, reset=True):
        """
        All the different processes that need to occur per player.
        These should be able to occur in any particular order. Because
        votes and prestige gains are tallied we don't do the awards here,
        but handle them separately for efficiency. Things that don't need
        to be recorded will just be processed in their methods.
        """
        if reset:
            # our votes are a dict of player to their number of votes
            self.db.votes = {}
            self.db.vote_history = {}
            # storing how much xp each player gets to post after
            self.db.xp = {}
            # our praises/condemns are {name: [total adjustment, times, [msgs]]}
            self.db.praises = {}
            self.db.condemns = {}
            self.db.prestige_changes = {}
            self.db.xptypes = {}
            self.db.requested_support = {}
        players = [ob for ob in PlayerDB.objects.filter(Q(roster__roster__name="Active") &
                                                        Q(roster__frozen=False)) if ob.db.char_ob]
        for player in players:
            self.check_freeze(player)
            self.count_votes(player)
            self.count_praises_and_condemns(player)
            # journal XP
            self.process_journals(player)
            # niche XP?
            # first-time RP XP?
            # losing gracefully
            # taking damage
            # conditions/social imperative
            # aspirations/progress toward goals
            char = player.db.char_ob
            # task resets
            cooldown = char.db.support_cooldown or {}
            for cid in cooldown:
                if cooldown[cid] > 0:
                    cooldown[cid] -= 1
            char.db.support_cooldown = cooldown
            char.db.support_points_spent = 0
            # reset list of people we were training
            char.db.currently_training = []
            char.db.trainer = None
            try:
                old = player.Dominion.assets.prestige
                self.db.prestige_changes[player.key] = old
            except AttributeError:
                try:
                    del self.db.prestige_changes[player.key]
                except KeyError:
                    pass
        pass
    def check_freeze(self, player):
        try:
            date = datetime.now()
            if not player.last_login:
                player.last_login = date
                player.save()
            offset = timedelta(days=-14)
            date = date + offset
            if player.last_login < date:
                player.roster.frozen = True
                player.roster.save()
        except Exception as err:
            import traceback
            traceback.print_exc()
            print "Error on freezing account: ID:%s, Error: %s" % (player.id, err)
    # Various 'Beats' -------------------------------------------------

    def process_journals(self, player):
        """
        In the journals here, we're processing all the XP gained for
        making journals, comments, or updating relationships.
        """
        char = player.db.char_ob
        num_journals = char.db.num_journals or 0
        char.db.num_journals = 0
        num_comments = char.db.num_comments or 0
        char.db.num_comments = 0
        num_rels = char.db.num_rel_updates or 0
        char.db.num_rel_updates = 0
        try:
            account = player.roster.current_account
            if account.id in self.db.xptypes:
                total = self.db.xptypes[account.id].get("journals", 0)
            else:
                self.db.xptypes[account.id] = {}
                total = 0
            jtotal = num_journals + int(num_comments) + int(num_rels)
            xp = 0
            if jtotal > 0:
                xp += 4
            if jtotal > 1:
                xp += 2
            if jtotal > 2:
                xp += 1
            # XP capped at 7 for all sources
            if xp > 7:
                xp = 7
            if xp + total > 7:
                if total > xp:
                    xp = 7 - total
                else:
                    xp = 7 - xp
            if xp <= 0:
                return
        except (ValueError, TypeError):
            return
        except AttributeError:
            return
        except Exception as err:
            print "ERROR in process journals: %s" % err
            traceback.print_exc()
            return
        if xp:
            msg = "You received %s xp this week for journals/comments/relationship updates." % xp
            self.award_xp(char, xp, player, msg, xptype="journals")

    # -----------------------------------------------------------------

    def count_votes(self, player):
        """
        Counts the votes for each player. We may log voting patterns later if
        we need to track against abuse, but since voting is stored in each
        player it's fairly trivial to check each week on an individual basis
        anyway.
        """       
        votes = player.db.votes or []
        for ob in votes:
            if ob.id in self.db.votes:
                self.db.votes[ob.id] += 1
            else:
                self.db.votes[ob.id] = 1
        if votes:
            self.db.vote_history[player.id] = votes
        player.db.votes = []

    def count_praises_and_condemns(self, player):
        # praises/condemns are {name: [times, msg]}
        praises = player.db.praises or {}
        condemns = player.db.condemns or {}
        BASE_CONDEMN = 0
        try:
            # our base prestige is our total * .05%
            dompc = PlayerOrNpc.objects.get(player=player)
            assets = dompc.assets
            BASE_CONDEMN = int(assets.total_prestige * 0.0005)
        except PlayerOrNpc.DoesNotExist:
            from game.dominion.setup_utils import setup_dom_for_char
            char = player.db.char_ob
            if not char or not char.db.social_rank:
                return
            try:
                if char.roster.roster.name == "Active":
                    dompc = setup_dom_for_char(char)
            except Exception:
                BASE_CONDEMN = 0
            prest = 0
        # praises are a flat value, condemns scale with the prestige of the condemner
        BASE_PRAISE = 1000
        prest = BASE_PRAISE + BASE_CONDEMN
        for name in praises:
            num = praises[name][0]
            msg = praises[name][1]
            existing = self.db.praises.get(name, [0, 0, []])
            existing[0] += BASE_PRAISE
            existing[1] += num
            existing[2].append(msg)
            self.db.praises[name] = existing
        for name in condemns:
            num = condemns[name][0]
            msg = condemns[name][1]
            existing = self.db.condemns.get(name, [0, 0, []])
            existing[0] -= prest
            existing[1] += num
            existing[2].append(msg)
            self.db.condemns[name] = existing
        # reset their praises/condemns for next week after recording
        player.db.praises = {}
        player.db.condemns = {}
  
    def award_vote_xp(self):
        """
        Go through all of our votes and award xp to the corresponding character
        object of each player we've recorded votes for.
        """
        # go through each key in our votes dict, get player, award xp to their character
        for id in self.db.votes:
            player = PlayerDB.objects.get(id=id)
            # important - get their character, not the player object
            char = player.db.char_ob
            if char:
                votes = self.db.votes[id]
                xp = 0
                # 1 vote is 3 xp
                if votes > 0:
                    xp = 3
                # 2 votes is 5 xp
                if votes > 1:
                    xp += 2
                # 3 to 8 votes is 6 to 11 xp
                max_range = votes if votes <= 8 else 8
                for n in range(2,max_range):
                    xp += 1
                # 1 more xp for each 2 between 9 to 12
                if votes > 8:
                    bonusvotes = votes
                    if bonusvotes > 12:
                        bonusvotes = 12
                    bonus = bonusvotes - 8
                    bonus /= 2
                    if not bonus: bonus = 1
                    xp += bonus
                # 1 more xp for each 3 votes after 12
                if votes > 12:
                    bonus = votes - 12
                    bonus /= 3
                    if not bonus: bonus = 1
                    xp += bonus               
                if votes and xp:
                    msg = "You received %s votes this week, earning %s xp." % (votes, xp)
                    self.award_xp(char, xp, player, msg, xptype="votes")
                    
                    

    def award_xp(self, char, xp, player=None, msg=None, xptype="all"):
        try:
            try:
                account = char.roster.current_account
                if account.id not in self.db.xptypes:
                    self.db.xptypes[account.id] = {}
                self.db.xptypes[account.id][xptype] = xp + self.db.xptypes[account.id].get(xptype, 0)
            except AttributeError:
                pass
            xp = int(xp)
            char.adjust_xp(xp)
            self.db.xp[char.id] = xp + self.db.xp.get(char.id, 0)
        except Exception as err:
            traceback.print_exc()
            print "Award XP encountered ERROR: %s" % err
        if player and msg:
            player.inform(msg, "XP", week=self.db.week, append=True)


    def award_prestige(self):
        for name in self.db.praises:
            try:
                player = PlayerDB.objects.select_related('Dominion__assets').get(username__iexact=name)
                assets = player.Dominion.assets
            except AttributeError:
                continue
            val = self.db.praises[name][0]
            assets.adjust_prestige(val)
        for name in self.db.condemns:
            try:
                player = PlayerDB.objects.select_related('Dominion__assets').get(username__iexact=name)
                assets = player.Dominion.assets
            except AttributeError:
                continue
            val = self.db.condemns[name][0]
            assets.adjust_prestige(val)
        for name in self.db.prestige_changes:
            try:
                player = PlayerDB.objects.select_related('Dominion__assets').get(username__iexact=name)
                prestige = player.Dominion.assets.prestige
                old = self.db.prestige_changes[name]
                self.db.prestige_changes[name] = (prestige - old, prestige)
            except AttributeError:
                try:
                    self.db.prestige_changes[name] = (0, 0)
                except Exception:
                    continue
    
    def post_top_rpers(self):
        """
        Post ourselves to a bulletin board to celebrate the highest voted RPers
        this week. We post how much xp each player earned, not how many votes
        they received.
        """
        import operator
        from commands.commands.bboards import get_boards
        # this will create a sorted list of tuples of (id, votes), sorted by xp, highest to lowest
        sorted_xp = sorted(self.db.xp.items(), key=operator.itemgetter(1), reverse=True)
        string = "{wTop RPers this week by XP earned{n".center(60)
        string += "\n{w" + "-"*60 + "{n\n"
        sorted_xp = sorted_xp[:20]
        num = 0
        for tup in sorted_xp:
            num += 1
            try:
                char = ObjectDB.objects.get(id=tup[0])
                player = char.db.player_ob
                votes = tup[1]
                name = char.db.longname or char.key
                string += "{w%s){n %-35s {wXP{n: %s\n" % (num, name, votes)
            except ObjectDB.DoesNotExist:
                print "Could not find character of id %s during posting." % str(tup[0])
        boards = get_boards(self)
        boards = [ob for ob in boards if ob.key == BOARD_NAME]
        board = boards[0]
        board.bb_post(poster_obj=self, msg=string, subject="Weekly Votes", poster_name="Vote Results")
        inform_staff("Vote process awards complete. Posted on News.")

    def post_top_prestige(self):
        from commands.commands.bboards import get_boards
        from evennia.utils.evtable import EvTable
        import random
        boards = get_boards(self)
        boards = [ob for ob in boards if ob.key == BOARD_NAME]
        board = boards[0]
        sorted_praises = sorted(self.db.praises.items(), key=lambda x:x[1][1], reverse=True)
        sorted_praises = sorted_praises[:20]
        table = EvTable("{wName{n", "{w#{n", "{wMsg{n", border="cells", width=78)
        for tup in sorted_praises:
            praise_messages = [msg for msg in tup[1][2] if msg] or [None]
            table.add_row(tup[0].capitalize()[:18], tup[1][1], "'%s'" % random.choice(praise_messages))
        table.reformat_column(0, width=18)
        table.reformat_column(1, width=5)
        table.reformat_column(2, width=55)
        pmsg = "{wMost Praised this week{n".center(72)
        pmsg = "%s\n%s" % (pmsg, str(table).lstrip())
        pmsg +="\n\n"
        pmsg += "{wMost Condemned this week{n".center(72)
        sorted_condemns = sorted(self.db.condemns.items(), key=lambda x:x[1][1], reverse=True)
        sorted_condemns = sorted_condemns[:20]
        table = EvTable("{wName{n", "{w#{n", "{wMsg{n", border="cells", width=78)
        for tup in sorted_condemns:
            condemn_messages = [cmsg for cmsg in tup[1][2] if cmsg] or [None]
            table.add_row(tup[0].capitalize()[:18], tup[1][1], "'%s'" % random.choice(condemn_messages))
        table.reformat_column(0, width=18)
        table.reformat_column(1, width=5)
        table.reformat_column(2, width=55)
        pmsg = "%s\n%s" % (pmsg, str(table).lstrip())
        try:      
            sorted_changes = sorted(self.db.prestige_changes.items(), key=lambda x:abs(x[1][0]), reverse=True)
            sorted_changes = sorted_changes[:20]
            table = EvTable("{wName{n", "{wPrestige Change Amount{n", "{wPrestige Rank{n", border="cells", width=78)
            qs = AssetOwner.objects.filter(player__player__isnull=False)
            for tup in sorted_changes:
                # get our prestige ranking compared to others
                rank = qs.filter(prestige__gt=tup[1][1]).count()
                # get the amount that our prestige has changed. add + for positive
                amt = tup[1][0]
                if amt > 0:
                    amt = "+%s" % amt
                table.add_row(tup[0].capitalize(), amt, rank)
            pmsg += "\n\n"
            pmsg += "{wTop Prestige Changes{n".center(72)
            pmsg = "%s\n%s" % (pmsg, str(table).lstrip())
        except Exception:
            import traceback
            traceback.print_exc()
        board.bb_post(poster_obj=self, msg=pmsg, subject="Weekly Praises/Condemns", poster_name="Prestige")
        inform_staff("Praises/condemns tally complete. Posted on News.")
        
