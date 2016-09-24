from django.db import models

class ArxRosterManager(models.Manager):
    @property
    def active(self):
        return self.get(name="Active")
    
    @property
    def available(self):
        return self.get(name="Available")
    
    @property
    def unavailable(self):
        return self.get(name="Unavailable")
    
    @property
    def incomplete(self):
        return self.get(name="Incomplete")

    def get_all_active_characters(self):
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(roster__roster=self.active).order_by('db_key')
    
    def get_all_available_characters(self):
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(roster__roster=self.available).order_by('db_key')
    
    def get_all_unavailable_characters(self):
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(roster__roster=self.unavailable).order_by('db_key')
    
    def get_all_incomplete_characters(self):
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(roster__roster=self.incomplete).order_by('db_key')

    def get_character(self, name):
        from evennia.objects.models import ObjectDB
        try:
            return ObjectDB.objects.get(db_key__iexact=name,
                                     roster__roster__isnull=False)
        except ObjectDB.DoesNotExist:
            return None

    def search_by_filters(self, list_of_filters, roster_type = "active",
                          concept="None", fealty="None", social_rank = "None",
                          family="None"):
        """
        Looks through the active characters and returns all who match
        the filters specified. Filters include: male, female, young, adult,
        mature, elder, married, single, concept, social_class, fealty, and family.
        If concept, fealty, social_class, or family are passed, it expects for the
        corresponding varaibles to be defined.
        """
        from evennia.objects.models import ObjectDB
        match_set = set()
        char_list = []
        char_list = ObjectDB.objects.filter(roster__roster__name__iexact=roster_type)
        match_set = set(char_list)
        if not char_list:
            return
        for filter in list_of_filters:
            if filter == "male":
                for char in char_list:
                    if not char.db.gender or char.db.gender.lower() != "male":
                        match_set.discard(char)
            if filter == "female":
                for char in char_list:
                    if not char.db.gender or char.db.gender.lower() != "female":
                        match_set.discard(char)
            if filter == "young":
                for char in char_list:
                    if not char.db.age or char.db.age > 20:
                        match_set.discard(char)
            if filter == "adult":
                for char in char_list:
                    if  not char.db.age or char.db.age >= 40 or char.db.age < 21:
                        match_set.discard(char)
            if filter == "mature":
                for char in char_list:
                    if not char.db.age or char.db.age < 40 or char.db.age >= 60:
                        match_set.discard(char)
            if filter == "elder":
                for char in char_list:
                    if not char.db.age or char.db.age < 60:
                        match_set.discard(char)
            if filter == "concept":
                for char in char_list:
                    if not char.db.concept or concept.lower() not in char.db.concept.lower():
                        match_set.discard(char)
            if filter == "fealty":
                for char in char_list:
                    if not char.db.fealty or fealty.lower() not in char.db.fealty.lower():
                        match_set.discard(char)
            if filter == "social rank":
                for char in char_list:
                    try:
                        if int(social_rank) != int(char.db.social_rank):
                            match_set.discard(char)
                    except Exception:
                        match_set.discard(char)
            if filter == "married":
                for char in char_list:
                    if not char.db.marital_status or char.db.marital_status.lower() != "married":
                        match_set.discard(char)
            if filter == "single":
                for char in char_list:
                    if not char.db.marital_status or char.db.marital_status.lower() != "unmarried":
                        match_set.discard(char)
            if filter == "family":
                for char in char_list:
                    if not char.db.family or family.lower() not in char.db.family.lower():
                        match_set.discard(char)
        return match_set
