"""
Commands for flashbacks and other scene management stuff in the Character app.
Flashbacks are for the Arx equivalent of play-by-post: players can create a 
flashback of a scene that happened in the past with a clear summary and end-goal
in mind, and then invite others to RP about it.
"""
from django.db.models import Q

from server.utils.arx_utils import ArxPlayerCommand
from web.character.models import Flashback


class CmdFlashback(ArxPlayerCommand):
    """
    Create, read, or participate in a flashback
    
    Usage:
        flashback
        flashback <ID #>
        flashback/catchup <ID #>
        flashback/create <title>[=<summary>]
        flashback/title <ID #>=<new title>
        flashback/summary <ID #>=<new summary>
        flashback/invite <ID #>=<player>
        flashback/uninvite <ID #>=<player>
        flashback/post <ID #>=<message>
    """
    key = "flashback"
    aliases = ["flashbacks"]
    locks = "cmd:all()"
    help_category = "scenes"
    player_switches = ("invite", "uninvite")
    change_switches = ("title", "summary", "post")
    
    @property
    def roster_entry(self):
        return self.caller.roster
        
    @property
    def accessible_flashbacks(self):
        return Flashback.objects.filter(Q(owner=self.roster_entry) | 
                                        Q(allowed=self.roster_entry)).distinct()

    def func(self):
        if not self.switches and not self.args:
            return self.list_flashbacks()
        if "create" in self.switches:
            return self.create_flashback()
        flashback = self.get_flashback()
        if not flashback:
            return
        if not self.switches:
            return self.view_flashback(flashback)
        if "catchup" in self.switches:
            return self.read_new_posts(flashback)
        if self.check_switches(self.player_switches):
            return self.manage_invites(flashback)
        if "post" in self.switches:
            return self.post_message(flashback)
        if self.check_switches(self.change_switches):
            return self.update_flashback(flashback)
        self.msg("Invalid switch.")
            
    def list_flashbacks(self):
        from evennia.utils.evtable import EvTable
        table = EvTable("ID", "Title", "Owner", "New Posts", width=80, border="cells")
        for flashback in self.accessible_flashbacks:
            table.add_row(flashback.id, flashback.title, flashback.owner,
                          len(flashback.get_new_posts(self.roster_entry)))
        self.msg(str(table))
    
    def create_flashback(self):
        title = self.lhs
        summary = self.rhs or ""
        if Flashback.objects.filter(title__iexact=title).exists():
            self.msg("There is already a flashback with that title. Please choose another.")
            return
        flashback = self.roster_entry.created_flashbacks.create(title=title, summary=summary)
        self.msg("You have created a new flashback with the ID of #%s." % flashback.id)
    
    def get_flashback(self):
        try:
            return self.accessible_flashbacks.get(id=int(self.lhs))
        except (Flashback.DoesNotExist, ValueError):
            self.msg("No flashback by that ID number.")
            self.list_flashbacks()
    
    def view_flashback(self, flashback):
        self.msg(flashback.display())

    def read_new_posts(self, flashback):
        msg = "New posts for %s\n" % flashback.id
        msg += "\n".join(post.display() for post in flashback.get_new_posts(self.roster_entry))
        self.msg(msg)
    
    def manage_invites(self, flashback):
        pass
    
    def post_message(self, flashback):
        pass
    
    def update_flashback(self, flashback):
        pass
