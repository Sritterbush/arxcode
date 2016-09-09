"""
Basic starting cmdsets for characters. Each of these
cmdsets attempts to represent some aspect of how
characters function, so that different conditions
on characters can extend/modify/remove functionality
from them without explicitly calling individual commands.

"""
import traceback
try:
    from evennia.commands.default import help, admin, system, building, batchprocess
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading default commands: %s" % err)
try:
    from evennia.commands.default import general as default_general
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading default.general commands: %s" % err)
try:
    from commands.commands import staff_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading staff_commands: %s" % err)
try:
    from commands.commands import roster
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading roster commands: %s" % err)
try:
    from commands.commands import general
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading general commands: %s" % err)
try:
    from typeclasses import rooms as extended_room
    from evennia.contrib.extended_room import CmdExtendedLook
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading extended_room: %s" % err)
try:
    from commands.commands import social
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading social commands: %s" % err)
try:
    from commands.commands import xp
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading xp commands: %s" % err)
try:
    from commands.commands import maps
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading maps commands: %s" % err)
try:
    from typeclasses.places import cmdset_places
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading places commands: %s" % err)
try:
    from commands.cmdsets import combat
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading combat commands: %s" % err)
try:
    from world.dominion import commands as domcommands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading dominion commands: %s" % err)
try:
    from commands.commands import crafting
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading crafting commands: %s" % err)
try:
    from commands.cmdsets import home
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading home commands: %s" % err)
try:
    from web.character import investigation
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading investigation commands: %s" % err)
try:
    from commands.commands import overrides
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in override commands: %s" % err)
try:
    from commands.commands import help as arxhelp
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in overriding help: %s" % err)
from evennia.commands.cmdset import CmdSet

class OOCCmdSet(CmdSet):
    "Character-specific OOC commands. Most OOC commands defined in player."    
    key = "OOCCmdSet"
    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(overrides.CmdInventory())
        self.add(default_general.CmdNick())
        self.add(default_general.CmdAccess())
        self.add(general.CmdDiceString())
        self.add(general.CmdDiceCheck())
        self.add(general.CmdPage())
        self.add(general.CmdBriefMode())
        self.add(extended_room.CmdGameTime())
        self.add(xp.CmdVoteXP())
        self.add(social.CmdPosebreak())
        self.add(arxhelp.CmdHelp())
        self.add(social.CmdSocialScore())

class StateIndependentCmdSet(CmdSet):
    """
    Character commands that will always exist, regardless of character state.
    Poses and emits, for example, should be allowed even when a character is
    dead, because they might be posing something about the corpse, etc.
    """  
    key = "StateIndependentCmdSet"   
    def at_cmdset_creation(self):
        self.add(default_general.CmdPose())
        #emit was originally an admin command. Replaced those with gemit
        self.add(overrides.CmdEmit())
        #backup look for non-extended rooms, unsure if still used anywhere
        self.add(general.CmdLook())
        self.add(general.CmdOOCSay())
        self.add(general.CmdDirections())
        self.add(general.CmdKeyring())
        self.add(general.CmdGlance())
        # sorta IC commands, since information is interpretted by the
        # character and may not be strictly accurate.
        self.add(CmdExtendedLook())
        self.add(roster.CmdHere())
        self.add(social.CmdHangouts())
        self.add(social.CmdWhere())
        self.add(social.CmdJournal())
        self.add(social.CmdMessenger())
        self.add(social.CmdRoomHistory())
        self.add(maps.CmdMap())

class MobileCmdSet(CmdSet):
    """
    Commands that should only be allowed if the character is able to move.
    Thought about making a 'living' cmdset, but there honestly aren't any
    current commands that could be executed while a player is alive but
    unable to move. The sets are just equal.
    """
    key = "MobileCmdSet"
    def at_cmdset_creation(self):
        self.add(overrides.CmdGet())
        self.add(overrides.CmdDrop())
        self.add(overrides.CmdGive())
        self.add(default_general.CmdSay())
        self.add(general.CmdWhisper())
        self.add(general.CmdFollow())
        self.add(general.CmdDitch())
        self.add(general.CmdShout())
        self.add(general.CmdPut())
        self.add(xp.CmdTrain())
        self.add(xp.CmdUseXP())
        self.add(cmdset_places.CmdListPlaces())
        self.add(combat.CmdStartCombat())
        self.add(combat.CmdProtect())
        self.add(combat.CmdAutoattack())
        self.add(combat.CmdCombatStats())
        self.add(combat.CmdHeal())
        self.add(domcommands.CmdGuards())
        self.add(domcommands.CmdTask())
        self.add(domcommands.CmdSupport())
        self.add(crafting.CmdCraft())
        self.add(crafting.CmdRecipes())
        self.add(crafting.CmdJunk())
        self.add(social.CmdPraise())
        self.add(social.CmdCondemn())
        self.add(social.CmdThink())
        self.add(social.CmdFeel())
        self.add(social.CmdDonate())
        self.add(investigation.CmdInvestigate())

class StaffCmdSet(CmdSet):
    "OOC staff and building commands. Character-based due to interacting with game world."   
    key = "StaffCmdSet"   
    def at_cmdset_creation(self):
        # The help system       
        self.add(help.CmdSetHelp())
        # System commands
        self.add(system.CmdScripts())
        self.add(system.CmdObjects())
        self.add(system.CmdPlayers())
        self.add(system.CmdService())
        self.add(system.CmdAbout())
        self.add(system.CmdTime())
        self.add(system.CmdServerLoad())
        # Admin commands
        self.add(admin.CmdBoot())
        self.add(admin.CmdBan())
        self.add(admin.CmdUnban())  
        self.add(admin.CmdPerm())
        self.add(admin.CmdWall())
        # Building and world manipulation
        self.add(building.CmdTeleport())
        self.add(building.CmdSetObjAlias())
        self.add(building.CmdListCmdSets())
        self.add(building.CmdWipe())
        self.add(building.CmdSetAttribute())
        self.add(building.CmdName())
        self.add(building.CmdCpAttr())
        self.add(building.CmdMvAttr())
        self.add(building.CmdCopy())
        self.add(building.CmdFind())
        self.add(building.CmdOpen())
        self.add(building.CmdLink())
        self.add(building.CmdUnLink())
        self.add(building.CmdCreate())
        self.add(building.CmdDig())
        self.add(building.CmdTunnel())
        self.add(building.CmdDestroy())
        self.add(building.CmdExamine())
        self.add(building.CmdTypeclass())
        self.add(building.CmdLock())
        self.add(building.CmdScript())
        self.add(building.CmdSetHome())
        self.add(building.CmdTag())
        # Batchprocessor commands
        self.add(batchprocess.CmdBatchCommands())
        self.add(batchprocess.CmdBatchCode())
        # more recently implemented staff commands
        self.add(staff_commands.CmdGemit())
        self.add(staff_commands.CmdWall())
        self.add(staff_commands.CmdHome())
        self.add(staff_commands.CmdResurrect())
        self.add(staff_commands.CmdKill())
        self.add(staff_commands.CmdForce())
        self.add(staff_commands.CmdCcolor())
        self.add(extended_room.CmdExtendedDesc())
        self.add(xp.CmdAdjustSkill())
        self.add(xp.CmdAwardXP())
        self.add(maps.CmdMapCreate())
        self.add(maps.CmdMapRoom())
        self.add(combat.CmdObserveCombat())
        self.add(combat.CmdAdminCombat())
        self.add(combat.CmdCreateAntagonist())
        self.add(combat.CmdStandYoAssUp())
        self.add(domcommands.CmdSetRoom())
        # home commands
        self.add(home.CmdAllowBuilding())
        self.add(home.CmdBuildRoom())
        self.add(home.CmdManageRoom())
