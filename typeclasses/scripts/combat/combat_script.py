"""
Combat Manager. This is where the magic happens. And by magic,
we mean characters dying, most likely due to vile sorcery.

The Combat Manager is invoked by a character starting combat
with the +fight command. Anyone set up as a defender of either
of those two characters is pulled into combat automatically.
Otherwise, players can enter into combat that is in progress
with the appropriate defend command, or by a +fight command
to attack one of the belligerent parties.

Turn based combat has the obvious drawback that someone who
is AFK or deliberately not taking their turn completely halts
the action. There isn't an easy solution to this. GMs will
have tools to skip someone's turn or remove them from combat,
and a majority vote by all parties can cause a turn to proceed
even when someone has not taken their turn.

Phase 1 is the setup phase. This phase is designed to have a
pause before deciding actions so that other people can join
combat. Characters who join in later phases will not receive
a combat turn, and will be added to the fight in the following
turn. Phase 1 is also when players can vote to end the combat.
Every player MUST enter a command to continue for combat to
proceed. There will never be a case where a character can be
AFK and in combat. It is possible to vote a character out of
combat due to AFK in order for things to proceed. Immediately
after every current combatant selects to continue, the participants
are locked in and we go to phase 2.

Phase 2 is the action phase. Initiative is rolled, and then
each player must take an action when it is their turn. 'pass'
is a valid action. Each combat action is resolved during the
character's turn. Characters who are incapacitated lose their
action. Characters who join combat during Phase 2 must wait
for the following turn to be allowed a legal action.
"""

from typeclasses.scripts.scripts import Script as BaseScript
from evennia.utils.utils import fill, dedent, list_to_string
from server.utils.prettytable import PrettyTable
from commands.cmdsets.combat import CombatCmdSet
from world.stats_and_skills import do_dice_check
from twisted.internet import reactor

from operator import attrgetter
import time
import combat_settings
from combatant import CharacterCombatData
from world.dominion.battle import Formation


COMBAT_INTRO = combat_settings.COMBAT_INTRO
PHASE1_INTRO = combat_settings.PHASE1_INTRO
PHASE2_INTRO = combat_settings.PHASE2_INTRO
MAX_AFK = combat_settings.MAX_AFK
ROUND_DELAY = combat_settings.ROUND_DELAY


class CharFormation(Formation):
    pass
        

class CombatManager(BaseScript):
    """
    Players are added via add_combatant or add_observer. These are invoked
    by commands in normal commandsets. Characters added receive the combat
    commandset, which give commands that invoke the other methods.
    
    Turns proceed based on every combatant submitting an action, which is a
    dictionary of combatant IDs to their actions. Dead characters are moved
    to observer status, incapacitated characters are moved to a special
    list to denote that they're still in combat but can take no action.
    Attribute references to the combat manager script are stored in the room
    location under room.ndb.combat_manager, and inside each character in the
    combat under character.ndb.combat_manager.
    Note that all the data for the combat manager is stored inside non-database
    attributes, since it is designed to be non-persistent. If there's a server
    reset, combat will end.
    Non-database attributes:
    self.ndb.combatants - list of everyone active in the fight. If it's empty, combat ends
    self.ndb.observers - People passively watching the fight
    self.ndb.incapacitated - People who are too injured to act, but still can be attacked
    self.ndb.fighter_data - CharacterCombatData for each combatant. dict with character.id as keys
    self.ndb.combat_location - room where script happens
    self.ndb.initiative_list - CharacterCombatData for each fighter. incapacitated chars aren't in it
    self.ndb.active_character - Current turn of player in phase 2. Not used in phase 1
    self.ndb.phase - Phase 1 or 2. 1 is setup, 2 is resolution
    self.ndb.afk_check - anyone we're checking to see if they're afk
    self.ndb.votes_to_end - anyone voting to end combat
    self.ndb.flee_success - Those who can run this turn
    self.ndb.fleeing - Those intending to try to run

    Admin Methods:
    self.msg() - Message to all combatants/observers.
    self.end_combat() - shut down the fight
    self.next_character_turn() - move to next character in initiative list in phase 2
    self.add_observer(character)
    self.add_combatant(character)
    self.remove_combatant(character)
    self.move_to_observer(character)
    """

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "CombatManager"
        self.desc = "Manages the combat state for a group of combatants"
        # Not persistent because if someone goes LD, we don't want them reconnecting
        # in combat a week later with no way to leave it. Intentionally quitting out
        # to avoid combat will just need to be corrected with rules enforcement.
        self.persistent = False
        self.interval = ROUND_DELAY
        self.start_delay = True
        self.ndb.combatants = []  # those actively involved in fight
        self.ndb.observers = []  # sent combat data, but cannot act
        self.ndb.combat_location = self.obj  # room of the fight
        self.ndb.initiative_list = []  # CharacterCombatData of characters in order of initiative
        self.ndb.active_character = None  # who is currently acting during phase 2
        self.ndb.phase = 1
        self.ndb.afk_check = []  # characters who are flagged afk until they take an action
        self.ndb.votes_to_end = []  # if all characters vote yes, combat ends
        self.ndb.flee_success = []  # if we're here, the character is allowed to flee on their turn
        self.ndb.fleeing = []  # if we're here, they're attempting to flee but haven't rolled yet
        self.ndb.lethal = not self.obj.tags.get("nonlethal_combat")
        self.ndb.max_rounds = 250
        self.ndb.rounds = 0
        # to ensure proper shutdown, prevent some timing errors
        self.ndb.shutting_down = False
        self.ndb.status_table = None

    def at_start(self):
        pass

    def at_repeat(self):
        # reset the script timers
        if self.ndb.shutting_down:
            return
        # proceed to combat
        if self.ndb.phase == 1:
            self.ready_check()
        self.display_phase_status_to_all()

    def is_valid(self):
        """
        Check if still has combatants. Incapacitated characters are still
        combatants, just with very limited options - they can either pass
        turn or vote to end the fight. The fight ends when all combatants
        either pass they turn or choose to end. Players can be forced out
        of active combat if they are AFK, moved to observer status.
        """
        if self.ndb.shutting_down:
            return False
        if self.ndb.combatants:
            return True
        return False

    # ----Methods for passing messages to characters-------------
    @staticmethod
    def send_intro_message(character, combatant=True):
        """
        Displays intro message of combat to character
        """
        if not combatant:
            msg = fill("{mYou are now in observer mode for a fight. {n" +
                       "Most combat commands will not function. To " +
                       "join the fight, use the {w+fight{n command.")
        else:
            msg = "{rEntering combat mode.{n\n"
            msg += "\n\n" + fill(COMBAT_INTRO)
        character.msg(msg)
        return

    @staticmethod
    def phase_1_intro(character):
        """
        Displays info about phase 1 to character
        """
        character.msg(PHASE1_INTRO)

    @staticmethod
    def phase_2_intro(character):
        """
        Displays info about phase 2 to character
        """
        character.msg(PHASE2_INTRO)

    def display_phase_status(self, character, disp_intro=True):
        """
        Gives message based on the current combat phase to character.cmdset
        In phase 1, just list combatants and observers, anyone marked AFK,
        dead, whatever, and any votes to end.
        In phase 2, list initiative order and who has the current action.
        """
        if self.ndb.phase == 1:
            if disp_intro:
                self.phase_1_intro(character)
            character.msg("{wCurrent combatants:{n %s" % list_to_string(self.ndb.combatants))
            character.msg(str(self.ndb.status_table))
            return
        if self.ndb.phase == 2:
            if disp_intro:
                self.phase_2_intro(character)
            if self.ndb.active_character:
                character.msg("{wIt is {c%s's {wturn to act.{n" % self.ndb.active_character.name)
                character.msg(str(self.ndb.status_table))
            return

    def build_status_table(self):
        table = PrettyTable(["{wName{n", "{wDamage{n", "{wFatigue{n", "{wAction{n", "{wReady?{n"])
        for char in self.ndb.combatants:
            com = char.combat
            if not com:
                continue
            name = com.name
            dmg = str(char.db.damage)
            fatigue = str(com.fatigue_penalty)
            action = str(com.queued_action)
            rdy = str(com.ready)
            table.add_row([name, dmg, fatigue, action, rdy])
        self.ndb.status_table = table

    def display_phase_status_to_all(self, intro=False):
        msglist = self.ndb.combatants + self.ndb.observers
        self.build_status_table()
        for ob in msglist:
            self.display_phase_status(ob, disp_intro=intro)
    
    def msg(self, message, exclude=None, options=None):
        """
        Sends a message to all objects in combat/observers except for
        individuals in the exclude list.
        """
        # those in incapacitated list should still be in combatants also
        msglist = self.ndb.combatants + self.ndb.observers
        if not exclude:
            exclude = []
        msglist = [ob for ob in msglist if ob not in exclude]
        for ob in msglist:
            mymsg = message
            ob.msg(mymsg, options)

    # ---------------------------------------------------------------------
    # -----Admin Methods for OOC character status: adding, removing, etc----
    def add_combatant(self, character, adder=None):
        """
        Adds a character to combat. The adder is the character that started
        the process, and the return message is sent to them. We return None
        if they're already fighting, since then it's likely a state change
        in defending or so on, and messages will be sent from elsewhere.
        """
        # if we're already fighting, nothing happens
        if character in self.ndb.combatants:
            if character == adder:
                return "You are already in the fight."
            cdata = character.combat
            if cdata and adder:
                cdata.add_foe(adder)
                adata = adder.combat
                if adata:
                    adata.add_foe(character)
            return "%s is already fighting." % character.key
        # check if attackable
        if not character.db.attackable:
            return "%s is not attackable." % character.key
        if character.location != self.obj:
            return "%s is not in the same room as the fight." % character.key
        # if we were in observer list, we stop since we're participant now
        self.remove_observer(character)
        self.send_intro_message(character, combatant=True)
        self.ndb.combatants.append(character)
        character.cmdset.add(CombatCmdSet, permanent=False)
        if character.db.defenders:
            for ob in character.db.defenders:
                self.add_defender(character, ob)
        if character.db.assigned_guards:
            for ob in character.db.assigned_guards:
                self.add_defender(character, ob)
        reactor.callLater(1, cdata.reset)
        if character == adder:
            return "{rYou have entered combat.{n"
        # if we have an adder, they're fighting one another. set targets
        elif adder in self.ndb.combatants:
            # make sure adder is a combatant, not a GM
            adata = adder.combat
            if adata:
                cdata.add_foe(adder)
                cdata.prev_targ = adder
                adata.add_foe(character)
                adata.prev_targ = character
        return "You have added %s to a fight." % character.name

    def ready_check(self, checker=None):
        """
        Check all combatants. If all ready, move to phase 2. If checker is
        set, it's a character who is already ready but is using the command
        to see a list of who might not be, so the message is only sent to them.
        """
        ready = []
        not_ready = []
        if not self.ndb.combatants:
            self.msg("No combatants found. Exiting.")
            self.end_combat()
            return
        if not self or not self.pk or self.ndb.shutting_down:
            self.end_combat()
            return
        active_combatants = [ob for ob in self.ndb.combatants if ob.conscious]
        active_fighters = [ob.combat for ob in active_combatants]
        active_fighters = [ob for ob in active_fighters if not (ob.automated and ob.queued_action.qtype == "Pass")]
        if not active_fighters:
            self.msg("All combatants are incapacitated or automated npcs who are passing their turn. Exiting.")
            self.end_combat()
            return
        for char in self.ndb.combatants:
            if char.combat.ready:
                ready.append(char)
            elif not char.conscious:
                ready.append(char)
            else:
                not_ready.append(char)
        if not_ready:  # not ready for phase 2, tell them why
            if checker:
                checker.msg("{wCharacters who are ready:{n " + list_to_string(ready))
                checker.msg("{wCharacter who have not yet hit 'continue' or queued an action:{n " +
                            list_to_string(not_ready))
            else:
                self.msg("{wCharacters who are ready:{n " + list_to_string(ready))
                self.msg("{wCharacter who have not yet hit 'continue':{n " + list_to_string(not_ready))
        else:
            try:
                self.start_phase_2()
            except ValueError:
                self.end_combat()

    def afk_check(self, checking_char, char_to_check):
        """
        Prods a character to make a response. If the character is not in the
        afk_check list, we add them and send them a warning message, then update
        their combat data with the AFK timer. Subsequent checks are votes to
        kick the player if they have been AFK longer than a given idle timer.
        Any action removes them from AFK timer and resets the AFK timer in their
        combat data as well as removes all votes there.
        """
        # No, they can't vote themselves AFK as a way to escape combat
        if checking_char == char_to_check:
            checking_char.msg("You cannot vote yourself AFK to leave combat.")
            return
        if char_to_check not in self.ndb.combatants:
            checking_char.msg("Can only check AFK on someone in the fight.")
            return
        if self.ndb.phase == 1 and char_to_check.combat.ready:
            checking_char.msg("That character is already ready to proceed " +
                              "with combat. They are not holding up the fight.")
            return
        if self.ndb.phase == 2 and not self.ndb.active_character == char_to_check:
            checking_char.msg("It is not their turn to act. You may only " +
                              "vote them AFK if they are holding up the fight.")
            return
        if char_to_check not in self.ndb.afk_check:
            msg = "{w%s is checking if you are AFK. Please take" % checking_char.name
            msg += " an action within a few minutes.{n"
            char_to_check.msg(msg)
            checking_char.msg("You have nudged %s to take an action." % char_to_check.name)
            self.ndb.afk_check.append(char_to_check)
            char_to_check.combat.afk_timer = time.time()  # current time
            return
        # character is in the AFK list. Check if they've been gone long enough to vote against
        elapsed_time = time.time() - char_to_check.combat.afk_timer
        if elapsed_time < MAX_AFK:
            msg = "It has been %s since %s was first checked for " % (elapsed_time, char_to_check.name)
            msg += "AFK. They have %s seconds to respond before " % (MAX_AFK - elapsed_time)
            msg += "votes can be lodged against them to remove them from combat."
            checking_char.msg(msg)
            return
        # record votes. if we have enough votes, boot 'em.
        votes = char_to_check.combat.votes_to_kick
        if checking_char in votes:
            checking_char.msg("You have already voted for their removal. Every other player " +
                              "except for %s must vote for their removal." % char_to_check.name)
            return
        votes.append(checking_char)
        if votes >= len(self.ndb.combatants) - 1:
            self.msg("Removing %s from combat due to inactivity." % char_to_check.name)
            self.move_to_observer(char_to_check)
            return
        char_to_check.msg("A vote has been lodged for your removal from combat due to inactivity.")
        pass
    
    def remove_afk(self, character):
        """
        Removes a character from the afk_check list after taking a combat
        action. Resets relevant fields in combat data
        """
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
            character.combat.afk_timer = None
            character.combat.votes_to_kick = []
            character.msg("You are no longer being checked for AFK.")
            return

    def move_to_observer(self, character):
        """
        If a character is marked AFK or dies, they are moved from the
        combatant list to the observer list.
        """
        self.remove_combatant(character)
        self.add_observer(character)

    def remove_combatant(self, character, in_shutdown=False):
        """
        Remove a character from combat altogether. Do a ready check if
        we're in phase one.
        """
        self.stop_covering(character)
        c_fite = character.combat
        if character in self.ndb.combatants:
            self.ndb.combatants.remove(character)
        if character in self.ndb.fleeing:
            self.ndb.fleeing.remove(character)
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
        self.clear_blocked_by_list(character)
        self.clear_covered_by_list(character)
        guarding = c_fite.guarding
        if guarding:
            self.remove_defender(guarding, character)
        self.msg("%s has left the fight." % character.name)
        character.cmdset.delete(CombatCmdSet)
        character.ndb.combat_manager = None
        character.ndb.charcombatdata = []
        # nonlethal combat leaves no lasting harm
        if not self.ndb.lethal:
            # set them to what they were before the fight and wake them up
            character.dmg = c_fite.prefight_damage
            try:
                character.wake_up(quiet=True)
            except AttributeError:
                pass
        # if we're already shutting down, avoid redundant messages
        if len(self.ndb.combatants) < 2 and not in_shutdown:
            # We weren't shutting down and don't have enough fighters to continue. end the fight.
            self.end_combat()
            return
        if self.ndb.phase == 1 and not in_shutdown:
            self.ready_check()
            return
        if self.ndb.phase == 2 and not in_shutdown:
            if character in self.ndb.initiative_list:
                self.ndb.initiative_list.remove(character)
                return
            if self.ndb.active_character == character:
                self.next_character_turn()

    def add_observer(self, character):
        """
        Character becomes a non-participating observer. This is usually
        for GMs who are watching combat, but other players may be moved
        to this - dead characters are no longer combatants, nor are
        characters who have been marked as AFK.
        """
        self.send_intro_message(character, combatant=False)
        self.display_phase_status(character, disp_intro=False)
        if character not in self.ndb.observers:
            character.ndb.combat_manager = self
            self.ndb.observers.append(character)
            return
        
    def remove_observer(self, character, quiet=True):
        """
        Leave observer list, either due to stop observing or due to
        joining the fight
        """
        if character in self.ndb.observers:
            character.msg("You stop spectating the fight.")
            self.ndb.observers.remove(character)
            return
        if not quiet:
            character.msg("You were not an observer, but stop anyway.")

    def build_initiative_list(self):
        """
        Rolls initiative for each combatant, resolves ties, adds them
        to list in order from first to last. Sets current character
        to first character in list.
        """
        fighters = [ob.combat for ob in self.ndb.combatants]
        for fighter in fighters:
            fighter.roll_initiative()
        self.ndb.initiative_list = sorted([data for data in fighters
                                           if data.can_fight],
                                          key=attrgetter('initiative', 'tiebreaker'),
                                          reverse=True)

    def next_character_turn(self):
        """
        It is now a character's turn in the iniative list. They will
        be prompted to take an action. If there is no more characters,
        end the turn when this is called and start over at Phase 1.
        """
        if self.ndb.shutting_down:
            return
        if not self.ndb.initiative_list:
            self.start_phase_1()
            return
        char_data = self.ndb.initiative_list.pop(0)
        acting_char = char_data.char
        acting_char.refresh_from_db()
        self.ndb.active_character = acting_char
        # check if they went LD, teleported, or something
        if acting_char.location != self.ndb.combat_location:
            self.msg("%s is no longer here. Removing them from combat." % acting_char.name)
            self.remove_combatant(acting_char)
            return self.next_character_turn()
        # For when we put in subdue/hostage code
        if char_data.status != "active":
            acting_char.msg("It would be your turn, but you cannot act. Passing your turn.")
            self.msg("%s cannot act." % acting_char.name, exclude=[acting_char])
            return self.next_character_turn()
        # turns lost from botches or other effects
        if char_data.lost_turn_counter > 0:
            char_data.remaining_attacks -= 1
            char_data.lost_turn_counter -= 1    
            if char_data.remaining_attacks == 0:
                acting_char.msg("It would be your turn, but you are recovering from a botch. Passing.")
                self.msg("%s is recovering from a botch and loses their turn." % acting_char.name,
                         exclude=[acting_char])
                return self.next_character_turn()                 
        self.msg("{wIt is now{n {c%s's{n {wturn.{n" % acting_char.name, exclude=[acting_char])
        if self.ndb.initiative_list:
            self.msg("{wTurn order for remaining characters:{n %s" % list_to_string(self.ndb.initiative_list))
        result = char_data.do_turn_actions()
        if not result and self.ndb.phase == 2:
            mssg = dedent("""
            It is now {wyour turn{n to act in combat. Please give a little time to make
            sure other players have finished their poses or emits before you select
            an action. For your character's action, you may either pass your turn
            with the {wpass{n command, or execute a command like {wattack{n. Once you
            have executed your command, control will pass to the next character, but
            please describe the results of your action with appropriate poses.
            """)
            acting_char.msg(mssg)

    def start_phase_1(self):
        """
        Setup for phase 1, the 'setup' phase. We'll mark all current
        combatants as being non-ready. Characters will need to hit the
        'continue' command to be marked as ready. Once all combatants
        have done so, we move to phase 2. Alternately, everyone can
        vote to end the fight, and then we're done.
        """
        if self.ndb.shutting_down:
            return
        self.ndb.phase = 1
        self.ndb.active_character = None
        self.ndb.votes_to_end = []
        allchars = self.ndb.combatants + self.ndb.observers
        if not allchars:
            return
        for char in self.ndb.combatants:
            char.combat.reset()
        self.force_repeat()
        self.ndb.rounds += 1
        if self.ndb.rounds >= self.ndb.max_rounds:
            self.end_combat()
    
    def start_phase_2(self):
        """
        Setup for phase 2, the 'resolution' phase. We build the list
        for initiative, which will be a list of CombatCharacterData
        objects from self.ndb.fighter_data.values(). Whenever it comes
        to a character's turn, they're popped from the front of the
        list, and it remains their turn until they take an action.
        Any action they take will call the next_character_turn() to
        proceed, and when there are no more characters, we go back
        to phase 1.
        """
        if self.ndb.shutting_down:
            return
        self.ndb.phase = 2
        # determine who can flee this turn
        self.ndb.flee_success = []
        # if they were attempting to flee last turn, roll for them
        for char in self.ndb.fleeing:
            c_fite = char.combat
            if c_fite.roll_flee_success():  # they can now flee
                self.ndb.flee_success.append(char)
        for char in self.ndb.combatants[:]:
            if char.location != self.ndb.combat_location:
                self.remove_combatant(char)
                continue
        self.build_initiative_list()
        self.force_repeat()
        self.next_character_turn()

    def vote_to_end(self, character):
        """
        Allows characters to vote to bring the fight to a conclusion.
        """
        if character in self.ndb.votes_to_end:
            character.msg("You have already voted to end the fight.")
            mess = ""
        else:
            mess = "%s has voted to end the fight.\n" % character.name
            self.ndb.votes_to_end.append(character)
        not_voted = [ob for ob in self.ndb.combatants if ob and ob not in self.ndb.votes_to_end]
        # only let conscious people vote
        not_voted = [ob for ob in not_voted if ob.combat
                     and ob.combat.can_fight
                     and not ob.combat.wants_to_end]
        if not not_voted:
            self.msg("All parties have voted to end combat.")
            self.end_combat()
            return
        if character not in self.ndb.combatants:
            character.msg("Only participants in the fight may vote to end it.")
            return
        if self.ndb.votes_to_end:
            mess += "{wThe following characters have also voted to end:{n %s\n" % list_to_string(self.ndb.votes_to_end)
        mess += "{wFor the fight to end, the following characters must vote to end:{n "
        mess += "%s" % list_to_string(not_voted)
        self.msg(mess)
    
    def end_combat(self):
        """
        Shut down combat.
        """
        self.msg("Ending combat.")
        self.ndb.shutting_down = True
        for char in self.ndb.combatants[:]:
            self.remove_combatant(char, in_shutdown=True)
        for char in self.ndb.observers[:]:
            self.remove_observer(char)
        self.obj.ndb.combat_manager = None
        self.stop()  # delete script
