from world.dominion import models


class Journey(object):
    """
    A class which represents a journey between two points.  Unlike Expedition, this
    class is not meant to be persisted; Expedition uses Journey for calculations, but
    the instance can be thrown away when no longer needed.
    """

    origin = None
    destination = None
    path = None

    def __init__(self, origin, destination, route=None):
        self.origin = origin
        self.destination = destination
