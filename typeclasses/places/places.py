"""
Places for tabletalk
"""

from django.conf import settings
from typeclasses.objects import Object
from cmdset_places import DefaultCmdSet, SittingCmdSet
from evennia.utils.utils import make_iter

class Place(Object):
    """
    Class for placed objects that allow the 'tabletalk' command.
    """

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        self.db.occupants = []
        self.db.max_spots = 6
        self.desc = "A place for people to privately chat. Dropping it in a room will make it part of the room."
        # locks so characters cannot 'get' it
        self.locks.add("get:perm(Builders)")
        self.at_init()      
        
    def leave(self, character):
        """
        Character leaving the table.
        """
        occupants = self.db.occupants or []
        if character in occupants:
            occupants.remove(character)
            self.db.occupants = occupants
            character.cmdset.delete(SittingCmdSet)
            character.db.sitting_at_table = None
            self.location.msg_contents("%s has left the %s." % (character.name, self.key), exclude=character)
            return

    def join(self, character):
        """
        Character joins the table
        """
        occupants = self.db.occupants or []
        character.cmdset.add(SittingCmdSet, permanent=True)
        character.db.sitting_at_table = self
        occupants.append(character)
        self.db.occupants = occupants
        self.location.msg_contents("%s has joined the %s." % (character.name, self.key), exclude=character)
    
    def tt_msg(self, message, exclude=None):
        """
        Send msg to characters at table. Note that if this method was simply named
        'msg' rather than tt_msg, it would be called by msg_contents in rooms, causing
        characters at the places to receive redundant messages, since they are still
        objects in the room as well.
        """
        # utils.make_iter checks to see if an object is a list, set, etc, and encloses it in a list if not
        # needed so that 'ob not in exclude' can function if we're just passed a character
        exclude = make_iter(exclude)
        for ob in self.db.occupants:
            if ob not in exclude:
                ob.msg(message, is_pose=True)

    def at_after_move(self, source_location):
        "If new location is not our wearer, remove."
        location = self.location
        # first, remove ourself from the source location's places, if it exists
        if source_location and hasattr(source_location, 'is_room') and source_location.is_room:
            if source_location.db.places and self in source_location.db.places:
                source_location.db.places.remove(self)
        # if location is a room, add cmdset
        if location.is_room:
            places = location.db.places or []
            self.cmdset.add_default(DefaultCmdSet, permanent=True)
            places.append(self)
            location.db.places = places
        # if location not a room, remove cmdset
        else:
            self.cmdset.delete_default()

    

    
