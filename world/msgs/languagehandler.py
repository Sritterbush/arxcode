from evennia.utils.utils import make_iter


class LanguageHandler(object):
    def __init__(self, obj):
        """
        A simple handler for determining our languages
        """
        # the ObjectDB instance
        self.obj = obj

    @property
    def known_languages(self):
        return make_iter(self.obj.tags.get(category="languages") or [])

    def add_language(self, language):
        self.obj.tags.add(language, category="languages")

    def remove_language(self, language):
        self.obj.tags.remove(language, category="languages")

    @property
    def current_language(self):
        return self.obj.db.currently_speaking or "arvani"

    @property
    def max_languages(self):
        val = self.obj.db.skills.get("linguistics", 0)
        if val < 1:
            return 0
        if val == 1:
            return 1
        if val == 2:
            return 2
        if val == 3:
            return 4
        if val == 4:
            return 6
        if val >= 5:
            return 9
