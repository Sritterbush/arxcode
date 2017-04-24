"""
This script keeps a timer that will cause an update to happen
on a weekly basis. Things we'll be updating are counting votes
for players, and processes for Dominion.
"""
import traceback
from datetime import datetime, timedelta

from django.db.models import Q, F


from evennia.players.models import PlayerDB
from evennia.objects.models import ObjectDB
from evennia.utils.evtable import EvTable

from world.dominion.models import AssetOwner, Army, AssignedTask, Member, AccountTransaction
from typeclasses.bulletin_board.bboard import BBoard
from .scripts import Script
from server.utils.arx_utils import inform_staff
from web.character.models import Investigation, RosterEntry


EVENT_SCRIPT_NAME = "Weekly Update"
# number of seconds in a week
WEEK_INTERVAL = 604800
VOTES_BOARD_NAME = 'Votes'
PRESTIGE_BOARD_NAME = 'Prestige Changes'

PLAYER_ATTRS = ("votes", 'claimed_scenelist', 'random_scenelist', 'validated_list', 'praises', 'condemns',
                'requested_validation', 'donated_ap')
CHARACTER_ATTRS = ("currently_training", "trainer", 'scene_requests', "num_trained")


class WeeklyEvents(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    XP_TYPES_FOR_RESOURCES = ("votes", "scenes")

    # noinspection PyAttributeOutsideInit
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
        self.db.run_date = datetime.now()
        # processing for each player
        self.do_events_per_player(reset)
        # awarding votes we counted
        self.award_scene_xp()
        self.award_vote_xp()
        self.post_top_rpers()
        # prestige adjustments
        self.award_prestige()
        self.post_top_prestige()
        # dominion stuff
        self.do_dominion_events()
        self.do_investigations()
        self.do_cleanup()
        self.post_inactives()
        self.db.pose_counter = (self.db.pose_counter or 0) + 1
        if self.db.pose_counter % 4 == 0:
            self.db.pose_counter = 0
            self.count_poses()
        self.db.week += 1
        self.reset_action_points()

    def do_dominion_events(self):
        for owner in AssetOwner.objects.filter(
                        Q(organization_owner__isnull=False) |
                        (Q(player__player__roster__roster__name="Active") &
                         Q(player__player__roster__frozen=False))).distinct():
            try:
                owner.do_weekly_adjustment(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in %s's weekly adjustment: %s" % (owner, err)
        # resets the weekly record of work command
        Member.objects.filter(deguilded=False).update(work_this_week=0)
        # decrement timer of limited transactions, remove transactions that are over
        AccountTransaction.objects.filter(repetitions_left__gt=0).update(repetitions_left=F('repetitions_left') - 1)
        AccountTransaction.objects.filter(repetitions_left=0).delete()
        for army in Army.objects.all():
            try:
                army.execute_orders(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in %s's army orders: %s" % (army, err)
        self.do_tasks()
        inform_staff("Dominion weekly events processed for week %s." % self.db.week)

    @staticmethod
    def reset_action_points():
        qs = RosterEntry.objects.filter(roster__name="Active")
        qs1 = qs.filter(action_points__gte=100)
        qs2 = qs.filter(action_points__lt=100)
        log_file = open("action_points_log.txt", "w")
        log_file.write("Action points before script\n\n")
        for ob in qs:
            log_file.write("%s: action points: %s\n" % (ob, ob.action_points))
        qs1.update(action_points=200)
        qs2.update(action_points=F('action_points') + 100)
        log_file.write("\n\nAction points after script\n\n")
        for ob in qs:
            log_file.write("%s: action points: %s\n" % (ob, ob.action_points))
        log_file.close()

    def do_tasks(self):
        for task in AssignedTask.objects.filter(finished=False):
            try:
                task.payout_check(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print "Error in task completion: %s" % err

    @staticmethod
    def do_investigations():
        for investigation in Investigation.objects.filter(active=True, ongoing=True,
                                                          character__roster__name="Active"):
            try:
                investigation.process_events()
            except Exception as err:
                traceback.print_exc()
                print "Error in investigation: %s" % err
        # reset all active investigations
        Investigation.objects.filter(active=True).update(active=False, silver=0, economic=0, military=0, social=0,
                                                         action_points=0, roll=Investigation.UNSET_ROLL)

    @staticmethod
    def do_cleanup():
        # cleanup old informs
        date = datetime.now()
        offset = timedelta(days=-30)
        date = date + offset
        try:
            from world.msgs.models import Inform
            qs = Inform.objects.filter(date_sent__lte=date)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print "Error in cleaning informs: %s" % err
        # cleanup old tickets
        try:
            from web.helpdesk.models import Ticket, Queue
            try:
                queue = Queue.objects.get(slug__iexact="story")
                qs = Ticket.objects.filter(status__in=(Ticket.RESOLVED_STATUS, Ticket.CLOSED_STATUS),
                                           modified__lte=date
                                           ).exclude(queue=queue)
                qs.delete()
            except Queue.DoesNotExist:
                pass
        except Exception as err:
            traceback.print_exc()
            print "Error in cleaning tickets: %s" % err
        try:
            from django.contrib.admin.models import LogEntry
            qs = LogEntry.objects.filter(action_time__lte=date)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print "Error in cleaning Django Admin Change History: %s" % err
        # cleanup soft-deleted objects
        try:
            import time
            qs = ObjectDB.objects.filter(db_tags__db_key__iexact="deleted")
            current_time = time.time()
            for ob in qs:
                # never delete a player character
                if ob.db.player_ob:
                    ob.undelete()
                    continue
                # never delete something in-game
                if ob.location:
                    ob.undelete()
                    continue
                deleted_time = ob.db.deleted_time
                # all checks passed, delete it for reals
                if (not deleted_time) or (current_time - deleted_time > WEEK_INTERVAL):
                    # if we're a unique retainer, wipe the agent object as well
                    if hasattr(ob, 'agentob'):
                        if ob.agentob.agent_class.unique:
                            ob.agentob.agent_class.delete()
                    ob.delete()
        except Exception as err:
            traceback.print_exc()
            print "Error in cleaning up deleted objects: %s" % err
        # wipe all attributes we wish to refresh this week
        from evennia.typeclasses.attributes import Attribute
        attr_names = CHARACTER_ATTRS + PLAYER_ATTRS
        qs = Attribute.objects.filter(db_key__in=attr_names)
        qs.delete()

    # noinspection PyProtectedMember
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
            self.db.scenes = {}
        self.check_freeze()
        players = [ob for ob in PlayerDB.objects.filter(Q(Q(roster__roster__name="Active") &
                                                        Q(roster__frozen=False)) |
                                                        Q(is_staff=True)) if ob.db.char_ob]
        for player in players:
            self.count_votes(player)
            self.count_praises_and_condemns(player)
            # journal XP
            self.process_journals(player)
            self.count_scenes(player)
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
            # for lazy refresh_from_db calls for queries right after the script runs, but unnecessary after a @reload
            char.ndb.stale_ap = True
            try:
                old = player.Dominion.assets.prestige
                self.db.prestige_changes[player.key] = old
            except AttributeError:
                try:
                    del self.db.prestige_changes[player.key]
                except KeyError:
                    pass
            # wipe cached attributes
            for attrname in PLAYER_ATTRS:
                try:
                    del player.attributes._cache["%s-None" % attrname]
                except KeyError:
                    continue
            for attrname in CHARACTER_ATTRS:
                try:
                    del char.attributes._cache["%s-None" % attrname]
                except KeyError:
                    continue
            for agent in player.retainers:
                try:
                    del agent.dbobj.attributes._cache["trainer-None"]
                except (KeyError, AttributeError):
                    continue

    @staticmethod
    def check_freeze():
        try:
            date = datetime.now()
            PlayerDB.objects.filter(last_login__isnull=True).update(last_login=date)
            offset = timedelta(days=-14)
            date = date + offset
            RosterEntry.objects.filter(player__last_login__lt=date).update(frozen=True)
        except Exception as err:
            import traceback
            traceback.print_exc()
            print "Error on freezing accounts: %s" % err

    def post_inactives(self):
        date = datetime.now()
        cutoffdate = date - timedelta(days=30)
        qs = PlayerDB.objects.filter(roster__roster__name="Active", last_login__isnull=False).filter(
            last_login__lte=cutoffdate)
        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable("{wName{n", "{wLast Login Date{n", border="cells", width=78)
        for ob in qs:
            table.add_row(ob.key.capitalize(), ob.last_login.strftime("%x"))
        board.bb_post(poster_obj=self, msg=str(table), subject="Inactive List", poster_name="Inactives")
        inform_staff("List of Inactive Characters posted.")

    def count_poses(self):
        qs = ObjectDB.objects.filter(roster__roster__name="Active", db_tags__db_key="rostercg")
        min_poses = 20
        low_activity = []
        for ob in qs:
            if ob.posecount < min_poses:
                low_activity.append(ob)
            ob.db.previous_posecount = ob.posecount
            ob.posecount = 0
        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable("{wName{n", "{wNum Poses{n", border="cells", width=78)
        for ob in low_activity:
            table.add_row(ob.key, ob.db.previous_posecount)
        board.bb_post(poster_obj=self, msg=str(table), subject="Inactive by Poses List")
        
    # Various 'Beats' -------------------------------------------------

    def process_journals(self, player):
        """
        In the journals here, we're processing all the XP gained for
        making journals, comments, or updating relationships.
        """
        char = player.db.char_ob
        try:
            account = player.roster.current_account
            if account.id in self.db.xptypes:
                total = self.db.xptypes[account.id].get("journals", 0)
            else:
                self.db.xptypes[account.id] = {}
                total = 0
            journal_total = char.messages.num_weekly_journals
            char.messages.reset_journal_count()
            xp = 0
            if journal_total > 0:
                xp += 4
            if journal_total > 1:
                xp += 2
            if journal_total > 2:
                xp += 1
            # XP capped at 7 for all sources
            if xp > 7:
                xp = 7
            if xp + total > 7:
                xp = 7 - total
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

    def count_scenes(self, player):
        """
        Counts the @randomscenes for each player. Each player can generate up to 3
        random scenes in a week, and each scene that they participated in gives them
        2 xp.
        """
        scenes = player.db.claimed_scenelist or []
        charob = player.db.char_ob
        for ob in scenes:
            # give credit to the character the player had a scene with
            if ob.id in self.db.scenes:
                self.db.scenes[ob.id] += 1
            else:
                self.db.scenes[ob.id] = 1
            # give credit to the player's character, once per scene
            if charob:
                if charob.id in self.db.scenes:
                    self.db.scenes[charob.id] += 1
                else:
                    self.db.scenes[charob.id] = 1
        requested_scenes = charob.db.scene_requests or {}
        if requested_scenes:
            self.db.scenes[charob.id] = self.db.scenes.get(charob.id, 0) + len(requested_scenes)

    def count_praises_and_condemns(self, player):
        # from world.dominion.models import PlayerOrNpc
        # praises/condemns are {name: [times, msg]}
        praises = player.db.praises or {}
        # condemns = player.db.condemns or {}
        # base_condemn = 0
        # try:
        #     # our base prestige is our total * .05%
        #     dompc = PlayerOrNpc.objects.get(player=player)
        #     assets = dompc.assets
        #     # base_condemn = int(assets.total_prestige * 0.0005)
        # except PlayerOrNpc.DoesNotExist:
        #     from world.dominion.setup_utils import setup_dom_for_char
        #     char = player.db.char_ob
        #     if not char or not char.db.social_rank:
        #         return
        #     try:
        #         if char.roster.roster.name == "Active":
        #             setup_dom_for_char(char)
        #     except (AttributeError, TypeError, ValueError):
        #         base_condemn = 0

        # praises are a flat value, condemns scale with the prestige of the condemner
        base_praise = 1000
        # prest = base_praise + base_condemn
        for name in praises:
            num = praises[name][0]
            msg = praises[name][1]
            existing = self.db.praises.get(name, [0, 0, []])
            existing[0] += base_praise
            existing[1] += num
            existing[2].append((player, msg))
            self.db.praises[name] = existing
        # for name in condemns:
        #    num = condemns[name][0]
        #    msg = condemns[name][1]
        #    existing = self.db.condemns.get(name, [0, 0, []])
        #    existing[0] -= prest
        #    existing[1] += num
        #    existing[2].append((player, msg))
        #    self.db.condemns[name] = existing

    def award_scene_xp(self):
        for char_id in self.db.scenes:
            try:
                char = ObjectDB.objects.get(id=char_id)
            except ObjectDB.DoesNotExist:
                continue
            player = char.db.player_ob
            if char and player:
                scenes = self.db.scenes[char_id]
                xp = self.scale_xp(scenes * 2)
                if scenes and xp:
                    msg = "You were in %s random scenes this week, earning %s xp." % (scenes, xp)
                    self.award_xp(char, xp, player, msg, xptype="scenes")

    @staticmethod
    def scale_xp(votes):
        xp = 0
        # 1 vote is 3 xp
        if votes > 0:
            xp = 3
        # 2 votes is 5 xp
        if votes > 1:
            xp += 2
        # 3 to 5 votes is 6 to 8 xp
        max_range = votes if votes <= 5 else 5
        for n in range(2, max_range):
            xp += 1

        def calc_xp(num_votes, start, stop, div):
            bonus_votes = num_votes
            if stop and (bonus_votes > stop):
                bonus_votes = stop
            bonus_xp = bonus_votes - start
            bonus_xp /= div
            if (bonus_votes - start) % div:
                bonus_xp += 1
            return bonus_xp

        # 1 more xp for each 3 between 6 to 14
        if votes > 5:
            xp += calc_xp(votes, 5, 14, 3)
        # 1 more xp for each 4 votes after 14
        if votes > 14:
            xp += calc_xp(votes, 14, 26, 4)
        # 1 more xp for each 5 votes after 26
        if votes > 26:
            xp += calc_xp(votes, 26, 41, 5)
        # 1 more xp for each 10 votes after 36
        if votes > 41:
            xp += calc_xp(votes, 41, None, 10)
        return xp

    def award_vote_xp(self):
        """
        Go through all of our votes and award xp to the corresponding character
        object of each player we've recorded votes for.
        """
        # go through each key in our votes dict, get player, award xp to their character
        for player_id in self.db.votes:
            player = PlayerDB.objects.get(id=player_id)
            # important - get their character, not the player object
            char = player.db.char_ob
            if char:
                votes = self.db.votes[player_id]
                xp = self.scale_xp(votes)

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
            self.award_resources(player, xp, xptype)

    def award_resources(self, player, xp, xptype="all"):
        if xptype not in self.XP_TYPES_FOR_RESOURCES:
            return
        resource_msg = ""
        amt = 0
        try:
            for r_type in ("military", "economic", "social"):
                amt = player.gain_resources(r_type, xp)
            if amt:
                resource_msg = "Based on your number of %s, you have gained %s resources of each type." % (xptype, amt)
        except AttributeError:
            pass
        if resource_msg:
            player.inform(resource_msg, "Resources", week=self.db.week, append=True)

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
                except (AttributeError, KeyError):
                    continue
    
    def post_top_rpers(self):
        """
        Post ourselves to a bulletin board to celebrate the highest voted RPers
        this week. We post how much xp each player earned, not how many votes
        they received.
        """
        import operator
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
                votes = tup[1]
                name = char.db.longname or char.key
                string += "{w%s){n %-35s {wXP{n: %s\n" % (num, name, votes)
            except ObjectDB.DoesNotExist:
                print "Could not find character of id %s during posting." % str(tup[0])
        board = BBoard.objects.get(db_key__iexact=VOTES_BOARD_NAME)
        board.bb_post(poster_obj=self, msg=string, subject="Weekly Votes", poster_name="Vote Results")
        inform_staff("Vote process awards complete. Posted on %s." % board)

    def post_top_prestige(self):
        import random
        board = BBoard.objects.get(db_key__iexact=PRESTIGE_BOARD_NAME)
        sorted_praises = sorted(self.db.praises.items(), key=lambda x: x[1][1], reverse=True)
        sorted_praises = sorted_praises[:20]
        table = EvTable("{wName{n", "{w#{n", "{wMsg{n", border="cells", width=78)
        for tup in sorted_praises:
            praise_messages = [msg for _, msg in tup[1][2] if msg] or [None]
            table.add_row(tup[0].capitalize()[:18], tup[1][1], "'%s'" % random.choice(praise_messages))
        table.reformat_column(0, width=18)
        table.reformat_column(1, width=5)
        table.reformat_column(2, width=55)
        prestige_msg = "{wMost Praised this week{n".center(72)
        prestige_msg = "%s\n%s" % (prestige_msg, str(table).lstrip())
        prestige_msg += "\n\n"
        # prestige_msg += "{wMost Condemned this week{n".center(72)
        # sorted_condemns = sorted(self.db.condemns.items(), key=lambda x: x[1][1], reverse=True)
        # sorted_condemns = sorted_condemns[:20]
        # table = EvTable("{wName{n", "{w#{n", "{wMsg{n", border="cells", width=78)
        # for tup in sorted_condemns:
        #     condemn_messages = [con_msg for _, con_msg in tup[1][2] if con_msg] or [None]
        #     table.add_row(tup[0].capitalize()[:18], tup[1][1], "'%s'" % random.choice(condemn_messages))
        # table.reformat_column(0, width=18)
        # table.reformat_column(1, width=5)
        # table.reformat_column(2, width=55)
        # prestige_msg = "%s\n%s" % (prestige_msg, str(table).lstrip())
        try:      
            sorted_changes = sorted(self.db.prestige_changes.items(), key=lambda x: abs(x[1][0]), reverse=True)
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
            prestige_msg += "\n\n"
            prestige_msg += "{wTop Prestige Changes{n".center(72)
            prestige_msg = "%s\n%s" % (prestige_msg, str(table).lstrip())
        except (AttributeError, ValueError, TypeError):
            import traceback
            traceback.print_exc()
        board.bb_post(poster_obj=self, msg=prestige_msg, subject="Weekly Praises/Condemns", poster_name="Prestige")
        inform_staff("Praises/condemns tally complete. Posted on %s." % board)
