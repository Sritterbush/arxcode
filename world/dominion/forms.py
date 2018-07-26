"""
Forms for Dominion
"""
from django import forms
from world.dominion.models import RPEvent


class RPEventCommentForm(forms.Form):
    """Form for commenting on an existing RPEvent"""
    journal_text = forms.CharField(widget=forms.Textarea)
    private = forms.BooleanField(initial=False, required=False)

    def post_comment(self, char, event):
        msg = self.cleaned_data['journal_text']
        white = not self.cleaned_data['private']
        char.messages.add_event_journal(event, msg, white=white)
    

class RPEventCreateForm(forms.ModelForm):
    """Form for creating a RPEvent. We'll actually try using it in commands for validation"""
    class Meta:
        """Meta options for setting up the form"""
        model = RPEvent
        fields = ['location', 'plotroom', 'desc', 'date', 'celebration_tier', 'name', 'room_desc', 'risk',
                  'public_event']

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner')
        self.hosts = kwargs.pop('hosts', [])
        self.invites = kwargs.pop('invites', [])
        self.org_invites = kwargs.pop('org_invites', [])
        self.gms = kwargs.pop('gms', [])
        super(RPEventCreateForm, self).__init__(*args, **kwargs)
        self.fields['desc'].required = True
        self.fields['date'].required = True

    def save(self, commit=True):
        """Saves the instance and adds the form's owner as the owner of the petition"""
        event = super(RPEventCreateForm, self).save(commit)
        # TODO setup the orgparticipation and playerparticipation models
        for host in self.hosts:
            event.add_host(host)
        for gm in self.gms:
            event.add_gm(gm)
        for pc_invite in self.invites:
            event.add_guest(pc_invite)
        for org in self.org_invites:
            event.invite_org(org)
        return event

    def display(self):
        """Returns a game-friend display string"""
        from world.dominion.models import Organization
        msg = "{wEvent Being Created:\n"
        msg += "{wName:{n %s\n" % self.data.get('name')
        msg += "{wPublic:{n %s\n" % self.data.get('public_event', True)
        msg += "{wDescription:{n %s\n" % self.data.get('desc')
        msg += "{wDate:{n %s\n" % self.data.get('date')
        msg += "{wLocation:{n %s\n" % self.data.get('location')
        msg += "{wLargesse:{n %s\n" % dict(RPEvent.LARGESSE_CHOICES).get(self.data.get('celebration_tier', 0))
        if self.gms:
            msg += "{wGMs:{n %s\n" % ", ".join(str(ob) for ob in self.gms)
            msg += "{wRisk:{n %s\n" % dict(RPEvent.RISK_CHOICES).get(self.data.get('risk', RPEvent.NORMAL_RISK))
        if self.orgs:
            msg += "{wOrg invitations:{n %s\n" % ", ".join(str(org) for org in self.orgs)
        if self.invites:
            msg += "{wInvitations:{n %s\n" % ", ".join(str(ob) for ob in self.invites)
        return msg

    def display_errors(self):
        """Returns a game-friendly errors string"""
        msg = "Please correct the following errors:\n"
        msg += "\n".join("%s: %s" % (field,
                                     ", ".join(str(err.args[0]) for err in errs))
                         for field, errs in self.errors.as_data().items())
        return msg
