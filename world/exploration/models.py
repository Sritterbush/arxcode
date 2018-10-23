from world.dominion.models import Land, MapLocation, PlotRoom, ShardhavenType
from evennia.typeclasses.models import SharedMemoryModel
from django.db import models
from random import random


class ShardhavenLayoutExit(SharedMemoryModel):
    """
    This class represents a single exit between two ShardhavenLayoutSquares
    """

    layout = models.ForeignKey('ShardhavenLayout', related_name='exits')

    # TODO: Add optional ShardhavenEvent reference.


class ShardhavenLayoutSquare(SharedMemoryModel):
    """
    This class represents a single 'tile' of a ShardhavenLayout.  When the ShardhavenLayout is
    no longer in use, all these tiles should be removed.
    """
    layout = models.ForeignKey('ShardhavenLayout', related_name='rooms')
    x_coord = models.PositiveSmallIntegerField()
    y_coord = models.PositiveSmallIntegerField()

    # We use '+' for the related name because Django will then not create a reverse relationship.
    # We don't need such, and it would just be excessive.
    tile = models.ForeignKey(PlotRoom, related_name='+')

    # Exits are stored on the exit class as the direction the room is relative to the exit.
    room_north = models.ForeignKey(ShardhavenLayoutExit, related_name='exit_south')
    room_east = models.ForeignKey(ShardhavenLayoutExit, related_name='exit_west')
    room_south = models.ForeignKey(ShardhavenLayoutExit, related_name='exit_north')
    room_west = models.ForeignKey(ShardhavenLayoutExit, related_name='exit_east')

    # TODO: Add optional ShardhavenEvent reference


class ShardhavenLayout(SharedMemoryModel):
    width = models.PositiveSmallIntegerField(default=5)
    height = models.PositiveSmallIntegerField(default=4)
    type = models.ForeignKey(ShardhavenType)

    entrance_x = models.PositiveSmallIntegerField(default=0)
    entrance_y = models.PositiveSmallIntegerField(default=0)

    matrix = None

    def cache_room_matrix(self):
        matrix = []
        for r in range(0, width):
            row = []
            for c in range(0, height):
                row.append(None)
            matrix.append(row)

        for room in self.rooms:
            matrix[room.x_coord][room.y_coord] = room

    def save_rooms(self):
        for room in self.rooms:
            room.save()
        for room_exit in self.exits:
            room_exit.save()

    def destroy_haven(self):
        self.exits.delete()
        self.rooms.delete()

    def build_rooms(self):
        """
        This function is called when a new ShardhavenLayout is created; it will generate
        a random shardhaven fitting in a grid of <width>x<height> squares.  If an existing
        ShardhavenLayout exists for this Shardhaven, it will delete it first.

        :return:
        """

        def connect_rooms(room1, room2):
            delta_x = room1.x_coord - room2.x_coord
            delta_y = room1.y_coord - room2.y_coord

            if (delta_x != 0) and (delta_y != 0):
                return None

            new_exit = ShardhavenLayoutExit()

            if delta_x == -1:
                new_exit.room_east = room1
                new_exit.room_west = room2
            elif delta_x == 1:
                new_exit.room_west = room1
                new_exit.room_east = room2
            elif delta_y == -1:
                new_exit.room_south = room1
                new_exit.room_north = room2
            elif delta_y == 1:
                new_exit.room_north = room1
                new_exit.room_south = room2
            else:
                return None

            return new_exit

        def valid_direction(room, x, y):
            if (x < 0) or (x >= self.width):
                return False
            if (y < 0) or (y >= self.height):
                return False

            delta_x = room1.x_coord - x
            delta_y = room1.y_coord - y

            if (delta_x != 0) and (delta_y != 0):
                return False

            if delta_x == -1:
                return not room.exit_west
            elif delta_x == 1:
                return not room.exit_east
            elif delta_y == -1:
                return not room.exit_north
            elif delta_y == 1:
                return not room.exit_south
            else:
                return False

        def walk_random(x, y):
            new_x = x
            new_y = y

            direction = random.randint(0,3)
            if direction == 0:
                new_x -= 1
            elif direction == 1:
                new_x += 1
            elif direction == 2:
                new_y -= 1
            elif direction == 3:
                new_y += 1

            return new_x, new_y

        self.destroy_haven()

        matrix = []
        for r in range(0, width):
            row = []
            for c in range(0, height):
                row.append(None)
            matrix.append(row)

        # First let's cache our tiles
        tiles = PlotRoom.objects.filter(shardhaven_type=type)
        tile_count = tiles.count()

        new_rooms = []
        new_exits = []

        # Pick a starting point
        current_x = random.randint(0, self.width)
        current_y = random.randint(0, self.height)

        # Set the entrance
        self.entrance_x = current_x
        self.entrance_y = current_y

        # Pick how many rooms we want to generate for this particular Shardhaven
        # (i.e. how dense it should be within its grid).
        min_rooms = (self.width * self.height) / 2
        max_rooms = ((self.width * self.height) / 3) * 2
        num_rooms = random.randint(min_rooms, max_rooms)

        room = None
        old_room = None
        backed_up = False

        for counter in range(0, num_rooms):
            # Create the room if needed
            if not room:
                room = ShardhavenLayoutSquare()
                room.x_coord = current_x
                room.y_coord = current_y
                room.tile = tiles[random.randint(0, tile_count)]
                new_rooms.append(room)

            # If there was an old room, make the exit from that room to this.
            if old_room:
                connected_exit = connect_rooms(old_room, room)
                if connected_exit:
                    new_exits.append(connected_exit)

            # Pick a cardinal direction to move for our next room.
            new_x = -1
            new_y = -1

            walk_room = room
            counter = 0
            while not valid_direction(walk_room, new_x, new_y):
                new_x, new_y = walk_random(walk_room.x_coord, walk_room.y_coord)
                if counter++ > 4:
                    if not backed_up:
                        # Abort and back up a room
                        walk_room = old_room
                        backed_up = True
                    else:
                        # Give up and call it done.
                        continue

            # Connect to whatever room we walked out of, and check if there's a room
            # already there.
            old_room = walk_room
            room = matrix[new_x][new_y]

        ShardhavenLayoutSquare.objects.bulk_create(new_rooms)
        ShardhavenLayoutExit.objects.bulk_create(new_exits)


