from typeclasses.rooms import ArxRoom
from .models import Shardhaven
from .scripts import SpawnMobScript
from .loot import LootGenerator
import random


class ShardhavenRoom(ArxRoom):

    @property
    def shardhaven(self):
        try:
            haven = Shardhaven.objects.get(pk=self.db.haven_id)
            return haven
        except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
            return None

    def at_init(self):
        from exploration_commands import CmdExplorationRoomCommands
        self.cmdset.add(CmdExplorationRoomCommands())

        super(ShardhavenRoom, self).at_init()

    def at_object_receive(self, obj, source_location):
        if not obj.is_typeclass('typeclasses.characters.Character'):
            return

        haven = self.shardhaven
        if not haven:
            return

        entrance_square = haven.entrance
        if entrance_square is not None and entrance_square.room == self:
            return

        characters = []
        for testobj in self.contents:
            if testobj != obj and (testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character)):
                characters.append(testobj)

        player_characters = []
        for testobj in characters:
            if not testobj.is_typeclass("world.exploration.npcs.BossMonsterNpc") \
                    and not testobj.is_typeclass("world.exploration.npcs.MookMonsterNpc"):
                player_characters.append(testobj)

        difficulty = haven.difficulty_rating
        if len(player_characters) == 0:
            difficulty *= 6
        else:
            difficulty *= 2

        chance = random.randint(0, 100)
        if chance < difficulty:
            obj.scripts.add(SpawnMobScript)

        if len(characters) > 0:
            return

        chance = random.randint(0, 100)
        if chance < haven.difficulty_rating:
            if random.randint(0, 5) != 5:
                trinket = LootGenerator.create_trinket(haven)
                trinket.location = self
            else:
                weapon_types = (
                    LootGenerator.WPN_BOW,
                    LootGenerator.WPN_SMALL,
                    LootGenerator.WPN_MEDIUM,
                    LootGenerator.WPN_HUGE
                )
                weapon = LootGenerator.create_weapon(haven, random.choice(weapon_types))
                weapon.location = self

    def at_object_leave(self, obj, target_location):
        if obj.has_player or (hasattr(obj, 'is_character') and obj.is_character):
            mobs = []
            characters = []
            for testobj in self.contents:
                if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                    if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') \
                            or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                        mobs.append(testobj)
                    elif testobj != obj:
                        characters.append(testobj)

            if len(characters) == 0:
                for mob in mobs:
                    mob.location = None

    def softdelete(self):
        self.reset()
        super(ShardhavenRoom, self).softdelete()

    def reset(self):
        try:
            city_center = ArxRoom.objects.get(id=13)
        except ArxRoom.DoesNotExist, ArxRoom.MultipleObjectsReturned:
            city_center = None

        for testobj in self.contents:
            if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') \
                        or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                    testobj.location = None
                else:
                    testobj.location = city_center
            elif testobj.is_typeclass('world.exploration.loot.Trinket') \
                    or testobj.is_typeclass('world.exploration.loot.AncientWeapon') \
                    or testobj.is_typeclass('world.magic.materials.MagicMaterial'):
                testobj.softdelete()
            elif not testobj.is_typeclass('typeclasses.exits.ShardhavenInstanceExit'):
                # Someone dropped something in the shardhaven.  Let's not destroy it.
                testobj.location = None
