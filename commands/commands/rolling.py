"""
Commands for dice checks.
"""
from server.utils.arx_utils import ArxCommand
from world import stats_and_skills
from world.roll import Roll


class CmdDiceString(ArxCommand):
    """
    @dicestring

    Usage:
      @dicestring <your very own dicestring here>

    Customizes a message you see whenever any character does a @check,
    in order to ensure that it is a real @check and not a pose.
    """
    key = "@dicestring"
    locks = "cmd:all()"
    
    def func(self):
        """ Handles the toggle """
        caller = self.caller
        args = self.args
        dicest = caller.db.dice_string
        if not dicest:
            dicest = "None."
        if not args:
            caller.msg("Your current dicestring is: {w%s" % dicest)
            caller.msg("To change your dicestring: {w@dicestring <word or phrase>")
            return
        caller.attributes.add("dice_string", args)
        caller.msg("Your dice string is now: %s" % args)
        return


class CmdDiceCheck(ArxCommand):
    """
    @check

    Usage:
      @check <stat>[+<skill>][ at <difficulty number>][=receivers]

    Performs a stat/skill check for your character, generally to
    determine success in an attempted action. For example, if you
    tell a GM you want to climb up the wall of a castle, they might
    tell you to check your 'check dex + athletics, difficulty 30'.
    You would then '@check dexterity+athletics at 30'. You can also
    specify checks only to specific receivers. For example, if you
    are attempting to lie to someone in a whispered conversation,
    you might '@check charm+manipulation=Bob' for lying to Bob at
    the default difficulty of 15.

    The dice roll system has a stronger emphasis on skills than
    stats. A character attempting something that they have a skill
    of 0 in may find the task very difficult while someone with a
    skill of 2 may find it relatively easy.
    """

    key = "@check"
    aliases = ['+check', '+roll']
    locks = "cmd:all()"
    
    def func(self):
        """Run the OOCsay command"""

        caller = self.caller
        skill = None
        maximum_difference = 100

        if not self.args:
            caller.msg("Usage: @check <stat>[+<skill>][ at <difficulty number>][=receiver1,receiver2,etc]")
            return
        args = self.lhs if self.rhs else self.args
        args = args.lower()
        # if args contains ' at ', then we split into halves. otherwise, it's default of 6
        diff_list = args.split(' at ')
        difficulty = stats_and_skills.DIFF_DEFAULT
        if len(diff_list) > 1:
            if not diff_list[1].isdigit() or not 0 < int(diff_list[1]) < maximum_difference:
                caller.msg("Difficulty must be a number between 1 and %s." % maximum_difference)
                return
            difficulty = int(diff_list[1])
        args = diff_list[0]
        arg_list = args.split("+")
        if len(arg_list) > 1:
            skill = arg_list[1].strip()
        stat = arg_list[0].strip()
        matches = stats_and_skills.get_partial_match(stat, "stat")
        if not matches or len(matches) > 1:
            caller.msg("There must be one unique match for a character stat. Please check spelling and try again.")
            return
        # get unique string that matches stat
        stat = matches[0]
        
        if skill:
            matches = stats_and_skills.get_partial_match(skill, "skill")
            if not matches:
                # check for a skill not in the normal valid list
                if skill in caller.db.skills:
                    matches = [skill]
                else:
                    caller.msg("No matches for a skill by that name. Check spelling and try again.")
                    return
            if len(matches) > 1:
                caller.msg("There must be one unique match for a character skill. Please check spelling and try again.")
                return
            skill = matches[0]
        if not self.rhs:
            stats_and_skills.do_dice_check(caller, stat, skill, difficulty, quiet=False)
        else:
            result = stats_and_skills.do_dice_check(caller, stat, skill, difficulty)
            if result+difficulty >= difficulty:
                resultstr = "resulting in %s, %s {whigher{n than the difficulty" % (result+difficulty, result)
            else:
                resultstr = "resulting in %s, %s {rlower{n than the difficulty" % (result+difficulty, -result)

            if not skill:
                roll_msg = "checked %s against difficulty %s, %s{n." % (stat, difficulty, resultstr)
            else:
                roll_msg = "checked %s + %s against difficulty %s, %s{n." % (stat, skill, difficulty, resultstr)
            caller.msg("You " + roll_msg)
            roll_msg = caller.name + " " + roll_msg
            # if they have a recipient list, only tell those people (and GMs)
            if self.rhs:
                namelist = [name.strip() for name in self.rhs.split(",")]
                for name in namelist:
                    rec_ob = caller.search(name, use_nicks=True)
                    if rec_ob:
                        orig_msg = roll_msg
                        if rec_ob.attributes.has("dice_string"):
                            roll_msg = "{w<" + rec_ob.db.dice_string + "> {n" + roll_msg
                        rec_ob.msg(roll_msg)
                        roll_msg = orig_msg
                        rec_ob.msg("Private roll sent to: %s" % ", ".join(namelist))
                # GMs always get to see rolls.
                staff_list = [x for x in caller.location.contents if x.check_permstring("Builders")]
                for GM in staff_list:
                    GM.msg("{w(Private roll){n" + roll_msg)
                return
            # not a private roll, tell everyone who is here
            caller.location.msg_contents(roll_msg, exclude=caller, options={'roll': True})
        

class CmdSpoofCheck(ArxCommand):
    """
    @gmcheck
    
    Usage:
        @gmcheck <stat>/<value>[+<skill>/<value>][ at <difficulty>]
        @gmcheck/can_crit <stat>/<value>[+<skill>/<value>][ at <difficulty>]
        
    Performs a stat + skill at difficulty check with specified values. If no
    difficulty is set, default is used. Intended for GMs to make rolls for NPCs 
    that don't necessarily exist as characters in-game. The /can_crit switch
    allows the roll to crit.
    """
    
    key = "@gmcheck"
    locks = "cmd:all()"
    
    def get_value_pair(self, argstr):
        try:
            argstr = argstr.strip()
            args = argstr.split("/")
            key = args[0]
            val = int(args[1])
            if val < 1 or val > 20:
                self.msg("Please enter a value between 1 and 20.")
                return
            return key, val
        except (IndexError, TypeError, ValueError):
            self.msg("Specify name/value for stats/skills.")
    
    def func(self):
        maximum_difference = 100
        crit = "can_crit" in self.switches
        roll = Roll(can_crit=crit, quiet=False, announce_room=self.caller.location, announce_values=True)
        try:
            # rest of the command here. PS, I love you. <3
            # checks to see if difficulty exists. PPS Love you too!
            args_list = self.args.lower().split(' at ')
            if len(args_list) > 1:
                if not args_list[1].isdigit() or not 0 < int(args_list[1]) < maximum_difference:
                    self.msg("Difficulty must be a number between 1 and %s." % maximum_difference)
                    return
                difficulty = int(args_list[1])
                roll.difficulty = difficulty
            # 'args' here is the remainder after difficulty was split away.
            # it is not self.args
            args = args_list[0]
            other_list = args.split("+")
            if len(other_list) > 1:
                skilltup = self.get_value_pair(other_list[1])
                if not skilltup:
                    return
                roll.skills = {skilltup[0]: skilltup[1]}
            else:
                roll.stat_keep = True
                roll.skill_keep = False
            stattup = self.get_value_pair(other_list[0])
            if not stattup:
                return
            roll.stats = {stattup[0]: stattup[1]}
            roll.character_name = "%s GM Roll" % self.caller
            # Just so you know, you are beautiful and I love you. <3
            roll.roll()
        except IndexError:
            self.msg("usage: @gmcheck <stat>/<value>[+<skill>/<value>] at <difficulty number>")
            return
