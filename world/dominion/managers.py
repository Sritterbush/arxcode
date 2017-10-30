from django.db.models import Q, Manager


class CrisisManager(Manager):
    def viewable_by_player(self, player):
        if player.check_permstring("builders"):
            qs = self.all()
        else:
            qs = self.filter(Q(public=True) | Q(required_clue__discoveries__in=player.roster.finished_clues))
        return qs
