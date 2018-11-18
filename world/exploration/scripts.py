from typeclasses.scripts import Script
from .models import Monster, Shardhaven
import random
from server.utils.picker import WeightedPicker


class SpawnMobScript(Script):

    def at_script_creation(self):
        """
        Setup the script
        """
        self.desc = "Spawn in monsters"
        self.interval = 1
        self.persistent = False
        self.start_delay = True

    def at_repeat(self):
        try:
            haven = Shardhaven.objects.get(pk=self.obj.location.db.haven_id)
        except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
            self.stop()
            return

        monsters = Monster.objects.filter(habitats__in=[haven.haven_type], difficulty__lte=haven.difficulty_rating)
        if monsters.count() == 0:
            self.stop()
            return

        picker = WeightedPicker()
        for monster in monsters.all():
            picker.add_option(monster, monster.weight_spawn)

        monster = picker.pick()
        mob_instance = monster.create_instance(self.obj.location)
        self.obj.location.msg_contents("{} attacks {}!".format(mob_instance.name, self.obj.name))
        mob_instance.attack(self.obj.name, kill=True)
        self.stop()
