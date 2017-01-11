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
