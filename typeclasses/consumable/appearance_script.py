from typeclasses.scripts.scripts import Script


class AppearanceScript(Script):
    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        self.key = "Appearance"
        self.persistent = True
        self.interval = 3600
        self.db.scent_time_remaining = 86400
        self.db.scent = ""
        self.start_delay = True

    def at_repeat(self):
        if self.db.scent:
            self.db.scent_time_remaining -= self.interval
            if self.db.scent_time_remaining <= 0:
                self.db.scent = ""
        if not self.has_mods:
            self.stop()

    def set_scent(self, scent):
        self.db.scent_time_remaining = 86400
        self.db.scent = scent.scent_desc

    @property
    def has_mods(self):
        return self.db.scent

    def is_valid(self):
        return self.db.scent
