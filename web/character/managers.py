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
            ObjectDB.objects.get(db_key__iexact=name,
                                 roster__roster__isnull=False)
        except ObjectDB.DoesNotExist:
            return None
