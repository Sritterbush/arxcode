"""
Forms for Dominion
"""
from django import forms

from typeclasses.rooms import ArxRoom
from world.dominion.models import RPEvent, Organization, PlayerOrNpc, PlotRoom


class RPEventCommentForm(forms.Form):
    """Form for commenting on an existing RPEvent"""
    journal_text = forms.CharField(widget=forms.Textarea)
    private = forms.BooleanField(initial=False, required=False)

    def post_comment(self, char, event):
        """Posts a comment for an RPEvent"""
        msg = self.cleaned_data['journal_text']
        white = not self.cleaned_data['private']
        char.messages.add_event_journal(event, msg, white=white)
    

class RPEventCreateForm(forms.ModelForm):
    """Form for creating a RPEvent. We'll actually try using it in commands for validation"""
    hosts = forms.ModelMultipleChoiceField(queryset=PlayerOrNpc.objects.all(), required=False, widget=forms.HiddenInput())
    invites = forms.ModelMultipleChoiceField(queryset=PlayerOrNpc.objects.all(), required=False, widget=forms.HiddenInput())
    gms = forms.ModelMultipleChoiceField(queryset=PlayerOrNpc.objects.all(), required=False, widget=forms.HiddenInput())
    org_invites = forms.ModelMultipleChoiceField(queryset=Organization.objects.all(), required=False, widget=forms.HiddenInput())
    location = forms.ModelChoiceField(queryset=ArxRoom.objects.all(), widget=forms.HiddenInput(), required=False)
    room_name = forms.CharField(required=False, help_text="Location")

    class Meta:
        """Meta options for setting up the form"""
        model = RPEvent
        fields = ['location', 'plotroom', 'desc', 'date', 'celebration_tier', 'name', 'room_desc', 'risk',
                  'public_event', 'actions']

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner')
        super(RPEventCreateForm, self).__init__(*args, **kwargs)
        self.fields['desc'].required = True
        self.fields['date'].required = True
        self.fields['actions'].queryset = self.owner.actions.all()

    @property
    def cost(self):
        """Returns the amount of money needed for validation"""
        try:
            return dict(RPEvent.LARGESSE_VALUES)[int(self.data.get('celebration_tier', 0))][0]
        except (KeyError, TypeError, ValueError):
            self.add_error('celebration_tier', "Invalid largesse value.")

    def clean(self):
        """Validates that we can pay for things. Any special validation should be here"""
        cleaned_data = super(RPEventCreateForm, self).clean()
        self.check_risk()
        self.check_costs()
        return cleaned_data

    def clean_location(self):
        room_name = self.data.get('room_name')
        if room_name:
            try:
                try:
                    room = ArxRoom.objects.get(db_key__icontains=room_name)
                except ArxRoom.MultipleObjectsReturned:
                    room = ArxRoom.objects.get(db_key__iexact=room_name)
            except ArxRoom.DoesNotExist:
                self.add_error('room_name', "No unique match for a room by that name.")
                return super(RPEventCreateForm, self).clean_location()
            return room
        return super(RPEventCreateForm, self).clean_location()

    def check_costs(self):
        """Checks if we can pay, if not, adds an error"""
        if self.cost > self.owner.player.char_ob.currency:
            self.add_error('celebration_tier', "You cannot afford to pay the cost of %s." % self.cost)

    def check_risk(self):
        """Checks that our risk field is acceptable"""
        gms = self.cleaned_data.get('gms', [])
        risk = self.cleaned_data.get('risk', RPEvent.NORMAL_RISK)
        if not any(gm for gm in gms if gm.player.is_staff or gm.player.check_permstring("builders")):
            if risk != RPEvent.NORMAL_RISK:
                self.add_error('risk', "Risk cannot be altered without a staff member as GM. Set to: %r" % risk)

    def save(self, commit=True):
        """Saves the instance and adds the form's owner as the owner of the petition"""
        event = super(RPEventCreateForm, self).save(commit)
        event.add_host(self.owner, main_host=True)
        for host in self.cleaned_data.get('hosts', []):
            event.add_host(host)
        for gm in self.cleaned_data.get('gms', []):
            event.add_gm(gm)
        for pc_invite in self.cleaned_data.get('invites', []):
            event.add_guest(pc_invite)
        for org in self.cleaned_data.get('org_invites', []):
            event.invite_org(org)
        self.pay_costs()
        self.post_event(event)
        return event

    def pay_costs(self):
        """Pays the costs of the event"""
        cost = self.cost
        if cost:
            self.owner.player.char_ob.pay_money(cost)
            self.owner.player.msg("You pay %s coins for the event." % cost)

    def post_event(self, event):
        """Makes a post of this event"""
        from evennia.scripts.models import ScriptDB
        if event.public_event:
            event_manager = ScriptDB.objects.get(db_key="Event Manager")
            event_manager.post_event(event, self.owner.player, self.display())

    def display(self):
        """Returns a game-friend display string"""
        msg = "{wName:{n %s\n" % self.data.get('name')
        msg += "{wMain Host:{n %s\n" % self.owner
        hosts = PlayerOrNpc.objects.filter(id__in=self.data.get('hosts', []))
        if hosts:
            msg += "{wOther Hosts:{n %s\n" % ", ".join(str(ob) for ob in hosts)
        msg += "{wPublic:{n %s\n" % "Public" if self.data.get('public_event', True) else "Private"
        msg += "{wDescription:{n %s\n" % self.data.get('desc')
        msg += "{wDate:{n %s\n" % self.data.get('date')
        location = self.data.get('location')
        if location:
            location = ArxRoom.objects.get(id=location)
        msg += "{wLocation:{n %s\n" % location
        plotroom = self.data.get('plotroom')
        if plotroom:
            plotroom = Plotroom.objects.get(id=plotroom)
            msg += "{wPlotroom:{n %s\n" % plotroom
        msg += "{wLargesse:{n %s\n" % dict(RPEvent.LARGESSE_CHOICES).get(self.data.get('celebration_tier', 0))
        gms = PlayerOrNpc.objects.filter(id__in=self.data.get('gms', []))
        if gms:
            msg += "{wGMs:{n %s\n" % ", ".join(str(ob) for ob in gms)
            msg += "{wRisk:{n %s\n" % dict(RPEvent.RISK_CHOICES).get(self.data.get('risk', RPEvent.NORMAL_RISK))
        orgs = PlayerOrNpc.objects.filter(id__in=self.data.get('orgs', []))
        if orgs:
            msg += "{wOrg invitations:{n %s\n" % ", ".join(str(org) for org in self.orgs)
        invites = PlayerOrNpc.objects.filter(id__in=self.data.get('invites', []))
        if invites:
            msg += "{wInvitations:{n %s\n" % ", ".join(str(ob) for ob in invites)
        actions = self.data.get('actions', [])
        if actions:
            msg += "{wRelated Actions:{n %s\n" % ", ".join(str(ob) for ob in actions)
        return msg

    def display_errors(self):
        """Returns a game-friendly errors string"""
        def format_name(field_name):
            """Formats field names for error display"""
            if field_name == "celebration_tier":
                return "{wLargesse{n"
            return "{w%s{n" % field_name.capitalize()
        msg = "Please correct the following errors:\n"
        msg += "\n".join("%s: {r%s{n" % (format_name(field), ", ".join(errs)) for field, errs in self.errors.items())
        return msg
