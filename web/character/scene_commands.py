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
        flashback <ID #>[=<post #>]
        flashback/new <ID #>
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
        if not self.switches or "new" in self.switches:
            return self.view_flashback(flashback)
        if self.check_switches(self.player_switches):
            return self.manage_invites(flashback)
        if self.check_switches(self.change_switches):
            return self.update_flashback(flashback)
        self.msg("Invalid switch.")
            
    def list_flashbacks(self):
        pass
    
    def create_flashback(self):
        pass
    
    def view_flashback(self, flashback):
        pass
    
    def manage_invites(self, flashback):
        pass
    
    def update_flashback(self, flashback):
        pass
