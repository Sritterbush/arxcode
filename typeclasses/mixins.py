class ObjectMixins(object):
    def __desc_get(self):
        return self.db.desc
    def __desc_set(self, val):
        self.db.desc = val
    desc = property(__desc_get, __desc_set)
