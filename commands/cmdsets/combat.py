"""
This commandset attempts to define the combat state.
Combat in Arx isn't designed to mimic the real-time
nature of MMOs, or even a lot of MUDs. Our model is
closer to tabletop RPGs - a turn based system that
can only proceed when everyone is ready. The reason
for this is that having 'forced' events based on a
time limit, while perfectly appropriate for a video
game, is unacceptable when attempting to have a game
that is largely an exercise in collaborative story-
telling. It's simply too disruptive, and often creates
situations that are damaging to immersion and the
creative process.
"""
from django.db.models import Q
from evennia import CmdSet
from server.utils.arx_utils import ArxCommand
from evennia.utils import create, evtable
from server.utils.arx_utils import inform_staff
from typeclasses.scripts.combat import combat_settings
from evennia.objects.models import ObjectDB
import random
from typeclasses.npcs import npc_types
from world.stats_and_skills import do_dice_check

CSCRIPT = "typeclasses.scripts.combat.combat_script.CombatManager"


class CombatCmdSet(CmdSet):
    """CmdSet for players who are currently engaging in combat."""
    key = "CombatCmdSet"
    priority = 20
    duplicates = False
    no_exits = True
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdEndCombat())
        self.add(CmdAttack())
        self.add(CmdSlay())
        self.add(CmdReadyTurn())
        self.add(CmdPassTurn())
        self.add(CmdFlee())
        self.add(CmdFlank())
        self.add(CmdCombatStance())
        self.add(CmdCatch())
        self.add(CmdCoverRetreat())
        self.add(CmdVoteAFK())
        self.add(CmdCancelAction())
        

"""
-------------------------------------------------------------------
+fight will start combat, and will probably be a part of
the mobile commandset. It won't be a part of the combat command set,
because those are only commands that are added once you're placed
in combat mode.
+defend/+protect will also be a part of mobile, marking a character
as automatically entering combat whenever the character they are
protecting does.
-------------------------------------------------------------------
"""


class CmdStartCombat(ArxCommand):
    """
    Starts combat.
    Usage:
        +fight <character to attack>[,<another character to attack>, etc]
        +fight

    +fight will cause you to enter combat with the list of characters
    you supply, or with no arguments will enter a fight that is already
    present in the room if one exists. While in combat, a number of combat-
    specific commands will be made available to you. Combat continues
    while two or more characters are active combatants.

    To end combat, use +end_combat.
    """
    key = "+fight"
    aliases = ["fight"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        room = caller.location
        lhslist = self.lhslist
        # find out if we have a combat script already active for this room
        cscript = room.ndb.combat_manager
        if not self.args:
            if not cscript or not cscript.ndb.combatants:
                caller.msg("No one else is fighting here. To start a new " +
                           "fight, {w+fight <character>{n")
                return
            caller.msg(cscript.add_combatant(caller, caller))
            return
        if not lhslist:
            caller.msg("Usage: +fight <character to attack>")
            return
        # search for each name listed in arguments, match them to objects
        oblist = [caller.search(name) for name in lhslist if caller.search(name)]
        if not oblist:
            caller.msg("No one found by the names you provided.")
            return
        if not cscript:
            cscript = create.create_script(CSCRIPT, obj=room)
            room.ndb.combat_manager = cscript
            cscript.ndb.combat_location = room
            inform_staff("{wCombat:{n {c%s{n started a fight in room {w%s{n." % (caller.key, room.id))
            announce_exclude = oblist + [caller]
            room.msg_contents("{rA fight has broken out here. Use @spectate_combat to watch, or +fight to join.",
                              exclude=announce_exclude)
        cscript.add_combatant(caller, caller)
        caller.msg("You have started a fight.")
        for ob in oblist:
            # Try to add them, cscript returns a string of success or error
            retmsg = cscript.add_combatant(ob, caller)
            if retmsg:
                caller.msg(retmsg)
        # mark the script as no longer initializing
        cscript.finish_initialization()


class CmdAutoattack(ArxCommand):
    """
    Turns autoattack on or off
    Usage:
        +autoattack
        +autoattack/stop

    +autoattack toggles whether or not you will automatically issue
    attack commands on people fighting you in combat. It has a number
    of intended limitations: first, you won't attempt to finish off
    an incapcitated enemy. This doesn't mean you can't kill someone,
    but you won't keep hitting someone after they're down. Second,
    you will still need to hit 'ready' at the start of each round
    for it to proceed, as a check against AFK, and so that combat
    doesn't instantly resolve when all characters are autoattacking.
    """
    key = "+autoattack"
    aliases = ["autoattack", "auto"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        autoattack_on = False
        if not self.switches:
            if not caller.db.autoattack:
                caller.db.autoattack = True
                caller.msg("Autoattack is now set to be on.")
                autoattack_on = True
            else:
                self.switches.append("stop")
        if "stop" in self.switches:
            caller.db.autoattack = False
            caller.msg("Autoattack is now set to be off.")
            autoattack_on = False
        caller.combat.autoattack = autoattack_on


class CmdProtect(ArxCommand):
    """
    Defends a character
    Usage:
        +protect <character>
        +defend <character>
        +defend/stop
        +protect/stop

    Marks yourself as defending a character. While with them, this will
    mean you will always enter combat whenever they do, on their side. If
    the character is already in combat, you'll join in. While in combat,
    you will attempt to protect the character by intercepting attackers for
    them and guarding them against attempts to flank them. This captures
    the situation of loyal guards who would place themselves in harm's way
    for the person they're protecting.
    If two characters are attempting to protect each other, it simulates
    the situation of two characters fighting back-to-back or otherwise in
    some formation where they try to guard one another against threats, or
    an individual who stubbornly resists being kept out of harm's way.
    You may only focus on defending one character at a time. To stop
    guarding a character, use the /stop switch.
    """
    key = "+protect"
    aliases = ["+defend"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """
        +protect adds people to character.db.defenders list if they're not
        already there, and sets caller.db.guarding to be that character.db
        Only one guarded target allowed at a time. Additionally, we'll
        add them to combat if their guarded character is involved in a
        fight.
        """
        caller = self.caller
        current = caller.db.guarding
        if "stop" in self.switches:
            caller.db.guarding = None
            if current:
                caller.msg("You stop guarding %s." % current.name)
                deflist = current.db.defenders
                if caller in deflist:
                    # have to do it this way due to removal in place failing for attributes that
                    #  are python lists/dicts/etc
                    deflist.remove(caller)
                    current.db.defenders = deflist
                    current.combat.remove_defender(caller)
                return
            caller.msg("You weren't guarding anyone.")
            return
        if current:
            caller.msg("You are currently guarding %s." % current.name)
            caller.msg("To guard someone else, first use {w+protect/stop{n.")
            return
        if not self.args:
            caller.msg("Protect who?")
            return
        to_guard = caller.search(self.args)
        if not to_guard:
            caller.msg("Couldn't find anyone to guard.")
            return
        if not to_guard.attackable:
            caller.msg("Your target is currently not attackable and " +
                       "does not need a guard.")
            return
        # all checks succeeded. Start guarding
        caller.db.guarding = to_guard
        # doing it this way since list/dict methods tend to fail when called directly on attribute object.
        #  assignment works tho
        dlist = to_guard.db.defenders or []
        dlist.append(caller)
        to_guard.db.defenders = dlist
        caller.msg("You start guarding %s." % to_guard.name)
        # now check if they're in combat. if so, we join in heroically.
        to_guard.combat.add_defender(caller)
        return


"""
----------------------------------------------------
These commands will all be a part of the combat
commandset.

CmdEndCombat - character votes for fight to end
CmdAttack - attack a character
CmdSlay - attempt to kill a player character
CmdPassTurn - mark ready in phase 1 or pass in phase 2
CmdFlee - attempt to flee combat
CmdFlank - attempt an ambush attack
CmdCombatStance - ex: from defensive style to aggressive
CmdCatch - attempt to prevent a character from fleeing
CmdCoverRetreat - Try to remain behind to cover others to flee
CmdVoteAFK - vote a character as AFK
----------------------------------------------------
"""


# ----Helper Functions--------------------------------------
def check_combat(caller, quiet=False):
    """Checks for and returns the combat object for a room."""
    if not caller.location:
        return
    combat = caller.location.ndb.combat_manager
    if not combat and not quiet:
        caller.msg("No combat found at your location.")
    return combat


def check_targ(caller, target, verb="Attack"):
    """
    Checks validity of target, sends error messages to caller, returns
    True or False.
    """
    if not target:
        caller.msg("%s who?" % verb)
        return False
    if not target.attackable:
        caller.msg("%s is not attackable and cannot enter combat." % target.name)
        return False
    if target.combat.combat != caller.combat.combat:
        caller.msg("%s is not in combat with you." % target.name)
        return False
    return True
# --------------------------------------------------------


class CmdEndCombat(ArxCommand):
    """
    Votes to end combat.

    Usage:
         +end_combat

    Votes to have the combat come to an end. If every other combatant
    agrees, combat will end. If other players don't vote to end combat,
    the only other choice is to {wcontinue{n to begin the combat round,
    or mark non-participating characters as afk.
    """
    key = "+end_combat"
    locks = "cmd:all()"
    help_category = "Combat"
    aliases = ["+end_fight"]

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        combat.vote_to_end(caller)


class CmdAttack(ArxCommand):
    """
    Attack a character
    Usage:
          attack <character>
          attack/only <character>
          attack/critical <character>[=difficulty]
          
    An attempt to attack a given character that is in combat with you. If
    the character has defenders, you will be forced to attack one of them
    instead. The /only switch has you attempt to bypass defenders and only
    attack their protected target, but at a difficulty penalty based on
    the number of defenders. Attempting to bypass a large number of guards
    with brute force is extremely difficult and is likely to result in a
    botch. Attempting to launch a sneak attack around them is represented
    by the {wflank{n command.
    The /critical switch allows you to raise the difficulty of your attack
    in order to attempt to do more damage. The default value is 15.
    """
    key = "attack"
    locks = "cmd:all()"
    help_category = "Combat"
    can_kill = False
    can_bypass = True

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        create_queued = False
        if not combat:
            return
        targ = caller.search(self.lhs)
        if not check_targ(caller, targ):
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        if not caller.conscious:
            self.msg("You are not conscious.")
            return
        if combat.ndb.phase != 2 or combat.ndb.active_character != caller:
            create_queued = True
        # we only allow +coupdegrace to kill unless they're an npc
        can_kill = self.can_kill
        if targ.db.npc:
            can_kill = True
        if not targ.conscious and not can_kill:
            message = "%s is incapacitated. " % targ.name
            message += "To kill an incapacitated character, "
            message += "you must use the {w+coupdegrace{n command."
            caller.msg(message)
            return
        defenders = targ.combat.get_defenders()
        diff = 0
        mod = 0
        mssg = "{rAttacking{n %s: " % targ.name
        if defenders:
            if "only" not in self.switches:
                if not self.can_bypass:
                    caller.msg("You cannot bypass defenders with the 'only' switch when trying to kill.")
                    return
                targ = random.choice(defenders)
                mssg += "%s gets in your way - attacking them instead. " % targ.name
            else:  # we're doing a called shot at a protected target
                diff += 15 * len(defenders)
        if "critical" in self.switches:
            mod = 15
            if self.rhs:
                if not self.rhs.isdigit():
                    caller.msg("Difficulty must be a number between 1 and 50.")
                    return
                mod = int(self.rhs)
                if mod < 1 or mod > 50:
                    caller.msg("Difficulty must be a number between 1 and 50.")
                    return
                diff += mod
                mssg += "Attempting a critical hit."
        if create_queued:
            if combat.ndb.shutting_down:
                self.msg("Combat is shutting down. Unqueuing command.")
                return
            caller.msg("Queuing this action for later.")
            caller.combat.set_queued_action("attack", targ, mssg, diff, mod)
            return
        caller.msg(mssg)
        caller.combat.do_attack(targ, attack_penalty=diff, dmg_penalty=-mod)
            

class CmdSlay(CmdAttack):
    """
    Kill a player character
    Usage:
        +coupdegrace <character>
        +coupdegrace/critical <character>

    Attacks an incapacitated character with the intent on finishing them
    off. We require a separate command for this to ensure that all deaths
    of player characters are intentional, rather than accidental. While
    accidental deaths are realistic, we feel they aren't very compelling
    from a narrative standpoint. You cannot finish off a character until
    any characters defending them are similarly incapacitated.
    
    Characters that are flagged as NPCs do not have this protection, and
    may be killed via +attack in hilarious training accidents and the
    like.
    """
    key = "+coupdegrace"
    aliases = ["kill"]
    locks = "cmd:all()"
    help_category = "Combat"
    can_kill = True
    can_bypass = False


class CmdReadyTurn(ArxCommand):
    """
    Mark yourself ready for combat to proceed
    Usage:
        continue
        pass

    When in the setup phase of combat, 'continue' or 'ready' will mark you
    as being ready to move on to the combat round. During your turn in
    combat, you can choose to take no action and pass your turn by typing
    'pass'.
    
    Combat is turn-based without any timers to ensure that players have
    adequate time in order to roleplay during fights. This is not a license
    to attempt to stall to avoid consequences in RP, however, and trying
    to freeze combat by not taking your turn or marking yourself ready is
    very strictly prohibited.
    """
    key = "continue"
    aliases = ["ready"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        phase = combat.ndb.phase
        if phase == 2:
            self.msg("Use 'pass' or 'delay' to pass your turn in phase 2.")
            return
        # phase 1, mark us ready to proceed for phase 2
        if combat and not combat.ndb.shutting_down:
            caller.combat.character_ready()


class CmdPassTurn(ArxCommand):
    """
    Pass your turn in combat
    Usage
        pass
        delay

    Passes your turn in combat. If 'delay' is used instead, will
    defer your turn until everyone else has been offered a chance to
    go.
    """
    key = "pass"
    aliases = ["delay"]
    help_category = "Combat"

    def func(self):
        """Executes the command"""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        cmdstr = self.cmdstring.lower()

        phase = combat.ndb.phase
        if phase == 2:
            delay = cmdstr == "delay"
            if combat.ndb.active_character != caller:
                caller.msg("Queuing this action for later.")
                mssg = "You %s your turn." % cmdstr
                caller.combat.set_queued_action(cmdstr, None, mssg)
                return
            caller.combat.do_pass(delay=delay)
            return
        else:
            caller.msg("Please use '{wpass{n' to pass your turn during combat resolution.")
            return


class CmdCancelAction(ArxCommand):
    """
    cancels your current action
    Usage:
        cancel

    Cancels any current action that you have queued up.
    """
    key = "cancel"
    help_category = "Combat"

    def func(self):
        """Executes the CancelAction command"""
        self.caller.combat.cancel_queued_action()
        combat = self.caller.combat.combat
        self.msg("You clear any queued combat action.")
        if combat:
            combat.build_status_table()
            combat.display_phase_status(self.caller, disp_intro=False)


class CmdFlee(ArxCommand):
    """
    Attempt to run out of combat
    Usage:
        flee <exit>

    Attempts to exit combat by running for the specified exit.name
    Fleeing always takes a full turn - you execute the command,
    and if no one successfully stops you before your next turn,
    you execute 'flee <exit>' again to leave.
    """
    key = "flee"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        exit_obj = caller.search(self.args)
        if not exit_obj:
            return
        if not exit_obj.is_exit:
            caller.msg("That is not an exit.")
            return
        caller.combat.do_flee(exit_obj)
        return


class CmdFlank(ArxCommand):
    """
    Attempt to ambush an opponent
    Usage:
        flank <character>
        flank/only <character>

    Represents trying to maneuver around to the unprotected side of a
    character for a more successful attack. While the normal {wattack{n
    command attempts to simply barrel past someone's guards, flank
    attempts to evade them and strike the person being guarded before
    they can respond. If the 'only' switch is used, you will back off
    and refrain from attacking guards if you're spotted. Otherwise,
    you will attack the guard who stops you by default.
    """
    key = "flank"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        if combat.ndb.phase != 2 or combat.ndb.active_character != caller:
            caller.msg("You may only perform this action on your turn.")
            return
        targ = caller.search(self.args)
        if not check_targ(caller, targ):
            return
        if not targ.conscious and not targ.db.npc:
            caller.msg("You must use '{w+coupdegrace{n' to kill characters.")
            return
        # Check whether we attack guards
        attack_guards = "only" not in self.switches
        # to do later - adding in sneaking/invisibility into game
        caller.combat.do_flank(targ, sneaking=False, invis=False, attack_guard=attack_guards)
        return


class CmdCombatStance(ArxCommand):
    """
    Defines how character fights
    Usage:
        stance <type>

    Roughly defines how your character behaves in a fight, applying
    both defensive and offensive modifiers. <type> must be one of the
    following words, which are styles from the most defensive to the most
    aggressive: 'defensive', 'guarded', 'balanced', 'aggressive', 'reckless'.
    Combat stance of the attacker has no effect on flanking attacks.
    Changing your combat stance does not use up your combat action for your
    turn. Unlike most combat settings, stance is actually persistent between
    fights if not changed.
    """
    key = "stance"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if self.args not in combat_settings.COMBAT_STANCES:
            message = "Your stance must be one of the following: "
            message += "{w%s{n" % str(combat_settings.COMBAT_STANCES)
            caller.msg(message)
            return
        combat = check_combat(caller)
        if combat and combat.ndb.phase != 1:
            self.msg("Can only change stance between rounds.")
            return
        caller.combat.change_stance(self.args)
        return


class CmdCatch(ArxCommand):
    """
    Attempt to stop someone from running
    Usage:
        catch <character>
        
    Attempts to maneuver your character to block another character from
    fleeing. You can only attempt to catch one character at a time, though
    you may declare your intent at any time, before a character decides
    whether they would wish to attempt to run or not.
    """
    key = "catch"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        targ = caller.search(self.args)
        if not check_targ(caller, targ, "Catch"):
            return
        caller.combat.do_stop_flee(targ)
        return


class CmdCoverRetreat(ArxCommand):
    """
    Attempt to cover the retreat of other characters
    Usage:
        cover <character>[,<character2>,<character3>...]
        cover/stop <character>
        
    Cover has your character declare your intent to remain behind and fight
    others while you cover the retreat of one or more characters. Covering
    a retreat does not take your action for the round, but prevents you
    from fleeing yourself and imposes a difficulty penalty on attacks due
    to the distraction.
    """
    key = "cover"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        if combat.ndb.phase != 2 or combat.ndb.active_character != caller:
            caller.msg("You may only perform this action on your turn.")
            return
        if "stop" in self.switches and not self.args:
            caller.combat.stop_covering(quiet=False)
            return
        arglist = self.args.split(",")
        targlist = [caller.search(arg) for arg in arglist]
        targlist = [targ for targ in targlist if check_targ(caller, targ, "Cover")]
        if not targlist:
            caller.msg("No valid targets found to cover.")
            return
        if "stop" in self.switches:
            for targ in targlist:
                caller.combat.stop_covering(targ)
        else:
            caller.combat.begin_covering(targlist)


class CmdVoteAFK(ArxCommand):
    """
    Attempt to stop someone from running
    Usage:
        +vote_afk <character>
        
    People have to go AFK sometimes. It's a game, and RL has to take priority.
    Unfortunately, with turn based combat, that can mean you can wait a long
    time for someone to take their turn. If it's someone's turn and they're
    AFK, you can +vote_afk to give them 2 minutes to take an action. At the
    end of that period, +vote_afk begins to accumulate votes against them
    to kick them. Voting must be unanimous by all except the player in who
    is being voted upon.
    """
    key = "+vote_afk"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        assert caller in combat.ndb.combatants, "Error: caller not in combat."
        targ = caller.player.search(self.args)
        if not targ:
            return
        targ = targ.db.char_ob
        if not check_targ(caller, targ, "+vote_afk"):
            return
        # if they're no longer there, just remove them automatically
        if targ.location != combat.ndb.combat_location:
            combat.remove_combatant(targ)
            return
        combat.afk_check(caller, targ)


class CmdCombatStats(ArxCommand):
    """
    View your combat stats
    Usage:
        +combatstats
        +combatstats/view <character>
        
    Displays your combat stats.
    """
    key = "+combatstats"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if "view" in self.switches:
            if not self.caller.player.check_permstring("builders"):
                self.msg("Only GMs can view +combatstats of other players.")
                return
            pc = caller.player.search(self.args)
            if not pc:
                return
            char = pc.db.char_ob
        else:
            char = caller
        fighter = char.combat
        msg = "\n{c%s{w's Combat Stats\n" % char
        self.msg(msg + fighter.display_stats())


"""
----------------------------------------------------
These commands will all be a part of the staff
commands for manipulating combat: observing combat,
as well as changing events.
----------------------------------------------------
"""


class CmdObserveCombat(ArxCommand):
    """
    Enters combat as an observer
    Usage:
            @spectate_combat
            @spectate_combat/stop
    Enters combat if it is present in your current location.
    """
    key = "@spectate_combat"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if "stop" in self.switches:
            combat = self.caller.combat.combat
            if not combat:
                self.msg("You are not watching a combat.")
                return
            combat.remove_observer(caller, quiet=False)
            return
        combat = check_combat(caller)
        if not combat:
            return
        if caller in combat.ndb.combatants:
            caller.msg("You are already involved in this combat.")
            return
        combat.add_observer(caller)


class CmdFightStatus(ArxCommand):
    """
    Displays the status of combat

    Usage:
        +combatstatus

    Displays status of fight at your room.
    """
    key = "+combatstatus"
    aliases = ["+fightstatus", "+cs"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Executes the flee command"""
        combat = check_combat(self.caller)
        if not combat:
            return
        combat.build_status_table()
        combat.display_phase_status(self.caller, disp_intro=False)


class CmdAdminCombat(ArxCommand):
    """
    Admin commands for combat
    Usage:
        @admin_combat/kick <character> - removes a character from combat.
        @admin_combat/pass <character> - Makes character pass their turn
        @admin_combat/ready <character> - Marks character as ready to proceed
        @admin_combat/stopfight - ends combat completely
        @admin_combat/afk <character> - Moves AFK player to observers
        @admin_combat/view <character> - shows combat stats
        @admin_combat/readyall - Marks all characters ready

    A few commands to allow a GM to move combat along by removing AFK or
    stalling characters or forcing them to pass their turn or ending a
    fight completely.
    """
    key = "@admin_combat"
    locks = "cmd:perm(admin_combat) or perm(Wizards)"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = check_combat(caller)
        if not combat:
            return
        switches = self.switches
        if not switches:
            caller.msg("@admin_combat requires switches.")
            return
        # As a note, we use .key rather than .name for admins to ensure they use
        # their real GM name rather than some false name that .name can return
        if "stopfight" in switches:
            combat.msg("%s has ended the fight." % caller.key)
            combat.end_combat()
            return
        if "readyall" in switches:
            if combat.ndb.phase == 2:
                self.msg("They are already in phase 2.")
                return
            combat.start_phase_2()
            return
        targ = caller.search(self.args)
        if not check_targ(caller, targ, "Admin"):
            return
        if "kick" in switches:
            combat.msg("%s has kicked %s." % (caller.key, targ.name))
            combat.remove_combatant(targ)
            return
        if "pass" in switches:
            combat.msg("%s makes %s pass their turn." % (caller.key, targ.name))
            targ.combat.do_pass()
            return
        if "ready" in switches:
            combat.msg("%s marks %s as ready to proceed." % (caller.key, targ.name))
            targ.combat.character_ready()
            return
        if "afk" in switches:
            combat.msg("%s has changed %s to an observer." % (caller.key, targ.name))
            combat.move_to_observer(targ)
            return
        if "view" in self.switches:
            cdat = combat.get_fighter_data(targ.id)
            caller.msg("{wStats for %s.{n" % cdat)
            caller.msg(cdat.display_stats())
            return
        pass

NPC = "typeclasses.npcs.npc.MultiNpc"
UNIQUE_NPC = "typeclasses.npcs.npc.Npc"


class CmdCreateAntagonist(ArxCommand):
    """
    Creates an object to act as an NPC antagonist for combat.
    Usage:
        @spawn
        @spawn/new <type>,<threat>,<qty>,<sname>,<pname>[,<desc>]=<Spawn Message>
        @spawn/overwrite <ID>,<type>,<threat>,<qty>,<sname>,<pname>[,desc>]=<Msg>
        @spawn/preset <ID #>,<qty>,<threat>=Spawn Message
        @spawn/dismiss <monster>

    sname is singular name, pname is plural. type is one of the names of
    the preset npc templates - 'guard', etc. /preset keeps the existing
    names, type, and description of the npc, just changing its threat and
    quantity. /new spawns a new template, while /ovewrite allows you to
    replace an old, unsured template by its ID number with new data. Use 'champion'
    to spawn unique npcs. When spawning a unique, quantity will always be 1.
    """
    key = "@spawn"
    locks = "cmd:perm(spawn) or perm(Builders)"
    help_category = "GMing"

    def func(self):
        """Execute command."""
        caller = self.caller
        # get list of available npcs and types
        npcs = list(ObjectDB.objects.filter(Q(db_typeclass_path=NPC) | Q(db_typeclass_path=UNIQUE_NPC)))
        unused = [npc for npc in npcs if not npc.location]
        ntype = None
        if not self.switches and not self.args:
            # list available types
            ntypes = npc_types.npc_templates.keys()
            caller.msg("Valid npc types: %s" % ", ".join(ntypes))
            
            table = evtable.EvTable("ID", "Name", "Type", "Amt", "Threat", "Location", width=78)
            for npc in npcs:
                ntype = npc_types.get_npc_singular_name(npc.db.npc_type)
                num = npc.db.num_living if ntype.lower() != "champion" else "Unique"
                table.add_row(npc.id, npc.key or "None", ntype, num,
                              npc.db.npc_quality, npc.location.id if npc.location else None)
            caller.msg(str(table), options={'box': True})
            return
        if not self.switches or 'new' in self.switches or 'overwrite' in self.switches:
            if 'new' in self.switches and 'overwrite' in self.switches:
                caller.msg("Those switches are exclusive.")
                return
            try:
                desc = None
                npc_id = None
                if 'new' in self.switches or not self.switches:                   
                    if len(self.lhslist) > 5:
                        desc = ", ".join(self.lhslist[5:])
                    ntypename, threat, qty, sname, pname = self.lhslist[:5]
                else:
                    if len(self.lhslist) > 6:
                        desc = ", ".join(self.lhslist[6:])
                    npc_id, ntypename, threat, qty, sname, pname = self.lhslist[:6]
                    npc_id = int(npc_id)
                ntype = npc_types.npc_templates[ntypename]
                qty = int(qty)
                threat = int(threat)
            except ValueError:
                caller.msg("Require type,threat,number,name as args.")
                return
            except KeyError:
                caller.msg("No match found in npc templates for %s." % ntype)
                return
            if not self.rhs:
                caller.msg("Must supply a spawn message.")
                return
            if 'overwrite' in self.switches:
                try:
                    npc = ObjectDB.objects.get(Q(Q(db_typeclass_path=NPC) | Q(db_typeclass_path=UNIQUE_NPC))
                                               & Q(id=npc_id))
                except ObjectDB.DoesNotExist:
                    caller.msg("No npc found for that ID.")
                    return
            else:
                if ntypename.lower() != "champion":
                    npc = create.create_object(key=sname, typeclass=NPC)
                else:
                    npc = create.create_object(key=sname, typeclass=UNIQUE_NPC)
                    qty = 1
            npc.setup_npc(ntype, threat, qty, sing_name=sname, plural_name=pname, desc=desc)
            npc.location = caller.location
            caller.location.msg_contents(self.rhs)
            return
        if 'preset' in self.switches:
            try:
                npc_id, num, threat = [int(val) for val in self.lhslist]
                npc = ObjectDB.objects.get(id=npc_id)
            except ValueError:
                caller.msg("Wrong number of arguments.")
                return
            except ObjectDB.DoesNotExist:
                caller.msg("No npc found by that ID.")
                return
            if npc not in unused:
                caller.msg("That is not an inactive npc. Dismiss it, or create a new npc instead.")
                return
            npc.setup_npc(threat=threat, num=num, keepold=True)
            npc.location = caller.location
            caller.location.msg_contents(self.rhs)
            return
        if 'dismiss' in self.switches:
            targ = caller.search(self.args)
            if not targ:
                return
            if not hasattr(targ, 'dismiss'):
                caller.msg("Invalid target - you cannot dismiss that.")
                return
            targ.dismiss()
            caller.msg("Dismissed %s." % targ)
            return
        caller.msg("Invalid switch.")
        return


class CmdHarm(ArxCommand):
    """
    Harms characters and sends them a message

    Usage:
        @harm <character1, character2, etc>=amount/<message>
        @harm/mercy <character1, character2>=amount/<message>
        @harm/private <character1,...>=amount/<message>
        @harm/noarmor <char1, char2, ...>=amount/message

    Causes damage to the characters listed. If the mercy switch is
    specified, a character cannot be killed instantly. Otherwise, they can
    only be killed if they're already unconscious. <message> is broadcast
    to the room if specified. If the private switch is specified, <message>
    is sent only to the character.
    """
    key = "@harm"
    locks = "cmd:all()"
    help_category = "GMing"

    def func(self):
        """Executes the harm command"""
        if not self.lhslist:
            self.msg("Must provide one or more character names.")
            return
        message = ""
        amt = None
        one_shot = "mercy" not in self.switches
        rhs = self.rhs or ""
        rhslist = rhs.split("/")
        try:
            amt = int(rhslist[0])
            message = rhslist[1]
        except (TypeError, ValueError):
            self.msg("Must provide a character = number for damage amount.")
            return
        except IndexError:
            pass
        players = []
        for arg in self.lhslist:
            player = self.caller.player.search(arg)
            if player:
                players.append(player)
        charlist = [ob.db.char_ob for ob in players if ob.db.char_ob]
        if not self.can_harm_others():
            if any(ob for ob in charlist if ob != self.caller):
                self.msg("Non-GM usage. Pruning all other characters.")
            charlist = [ob for ob in charlist if ob == self.caller]
        if not charlist:
            return
        if message and "private" not in self.switches:
            rooms = set([ob.location for ob in charlist if ob.location])
            for room in rooms:
                room.msg_contents(message)
        damage_msgs = []
        for obj in charlist:
            damage = amt
            if "noarmor" not in self.switches:
                damage = obj.combat.modify_damage_by_mitigation(damage)
            if not obj.location:
                if not message:
                    message = "You have taken %s damage." % damage
                obj.player_ob.inform(message, category="Damage")
            elif "private" in self.switches and message:
                obj.msg(message)
            if damage:
                obj.combat.take_damage(damage, lethal=True, allow_one_shot=one_shot)
            damage_msgs.append("%s damage on %s" % (damage, obj))
        self.msg("You inflicted %s." % ", ".join(damage_msgs))
        
    def can_harm_others(self):
        """Checks if the caller can harm other players"""
        if self.caller.check_permstring("builders"):
            return True
        event = self.caller.location.event
        if not event:
            return False
        return self.caller.Dominion in event.gms.all()


class CmdHeal(ArxCommand):
    """
    Administers medical care to a character.
    Usage:
        +heal <character>
        +heal/permit <character>
        +heal/gmallow <character>[=<bonus if positive, negative for penalty>]

    Helps administer medical care to a character who is not
    presently in combat. This will attempt to wake them up
    if they have been knocked unconscious. You must have permission
    to attempt to heal someone, which is granted via the /permit switch.
    """
    key = "+heal"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        targ = caller.search(self.lhs)
        if not targ:
            return
        if "permit" in self.switches:
            permits = targ.ndb.healing_permits or set()
            permits.add(caller)
            targ.ndb.healing_permits = permits
            self.msg("{wYou permit {c%s {wto heal you." % targ)
            targ.msg("{c%s {whas permitted you to heal them." % caller)
            return
        event = caller.location.event
        if "gmallow" in self.switches:
            if not event or caller.player.Dominion not in event.gms.all() and not caller.check_permstring("builders"):
                self.msg("This may only be used by the GM of an event.")
                return
            modifier = 0
            if self.rhs:
                try:
                    modifier = int(self.rhs)
                except ValueError:
                    self.msg("Modifier must be a number.")
                    return
            targ.ndb.healing_gm_allow = modifier
            noun = "bonus" if modifier > 0 else "penalty"
            self.msg("You have allowed %s to use +heal, with a %s to their roll of %s." % (targ, noun, abs(modifier)))
            return
        if not targ.dmg:
            caller.msg("%s does not require any medical attention." % targ)
            return
        if not hasattr(targ, 'recovery_test'):
            caller.msg("%s is not capable of being healed." % targ)
            return
        combat = check_combat(caller, quiet=True)
        if combat:
            if caller in combat.ndb.combatants or targ in combat.ndb.combatants:
                caller.msg("You cannot heal someone in combat.")
                return
        if event and caller.ndb.healing_gm_allow is None:
            self.msg("There is an event here and you have not been granted GM permission to use +heal.")
            return
        aid_given = caller.db.administered_aid or {}
        # timestamp of aid time
        aid_time = aid_given.get(targ.id, 0)
        import time
        timediff = time.time() - aid_time
        if timediff < 3600:
            caller.msg("You have assisted them too recently.")
            caller.msg("You can help again in %s seconds." % (3600 - timediff))
            return
        permits = caller.ndb.healing_permits or set()
        if targ.player and targ not in permits:
            self.msg("%s has not granted you permission to heal them. Have them use +heal/permit." % targ)
            targ.msg("%s wants to heal you, but isn't permitted. You can let them with +heal/permit." % caller)
            return
        # record healing timestamp
        aid_given[targ.id] = time.time()
        caller.db.administered_aid = aid_given
        modifier = 0
        if caller.ndb.healing_gm_allow is not None:
            modifier = caller.ndb.healing_gm_allow
            caller.ndb.healing_gm_allow = None
        # give healin'
        blessed = caller.db.blessed_by_lagoma
        antimagic_aura = random.randint(0, 5)
        try:
            antimagic_aura += int(caller.location.db.antimagic_aura or 0)
        except (TypeError, ValueError):
            pass
        # if they have Lagoma's favor, we see if the Despite of Fable stops it
        if blessed:
            try:
                blessed = random.randint(0, blessed + 1)
            except (TypeError, ValueError):
                blessed = 0
            blessed -= antimagic_aura
            if blessed > 0:
                caller.msg("{cYou feel Lagoma's favor upon you.{n")
            else:
                blessed = 0
            keep = blessed + caller.db.skills.get("medicine", 0) + 2
            modifier += 5 * blessed
            heal_roll = do_dice_check(caller, stat_list=["mana", "intellect"], skill="medicine",
                                      difficulty=15-modifier, keep_override=keep)
        else:
            heal_roll = do_dice_check(caller, stat="intellect", skill="medicine", difficulty=15-modifier)
        caller.msg("You rolled a %s on your heal roll." % heal_roll)
        targ.msg("%s tends to your wounds, rolling %s on their heal roll." % (caller, heal_roll))
        script = targ.scripts.get("Recovery")
        if script:
            script = script[0]
            script.attempt_heal(heal_roll, caller)


class CmdStandYoAssUp(ArxCommand):
    """
    Heals up a player character
    Usage:
        +standyoassup <character>
        +standyoassup/noheal <character>

    Heals a puny mortal and wakes them up. Use /noheal if you just wanna wake
    them but want them to remain injured.
    """
    key = "+standyoassup"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def func(self):
        """Execute command."""
        caller = self.caller
        targ = caller.search(self.args)
        if not targ:
            return
        if "noheal" not in self.switches:
            targ.dmg = 0
            targ.msg("You have been healed.")
            caller.msg("You heal %s because they're a sissy mortal who needs everything done for them." % targ)
        targ.wake_up()
        return
