"""
Managers for Msg app, mostly proxy models for comms.Msg
"""
from django.db.models import Manager, Q


WHITE_TAG = "white_journal"
BLACK_TAG = "black_journal"


class QueryTypeMixins(object):
    white_query = Q(db_tags__db_key=WHITE_TAG)
    black_query = Q(db_tags__db_key=BLACK_TAG)
    all_journals_query = Q(white_query | black_query)
    
    
class MsgProxyManager(QueryTypeMixins, Manager):
    def get_read_by(self, user):
        return super(MsgProxyManager, self).get_queryset().filter(db_receivers_players=user)


class JournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(JournalManager, self).get_queryset().filter(self.all_journals_query)
        
        
class BlackJournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(BlackJournalManager, self).get_queryset().filter(self.black_query)
        
        
class WhiteJournalManager(MsgProxyManager):
    def get_queryset(self):
        return super(WhiteJournalManager, self).get_queryset().filter(self.white_query)