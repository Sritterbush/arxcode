from django import forms
from evennia.comms.models import Msg
from evennia.objects.models import ObjectDB
from django.conf import settings
from django.db.models import Q


class JournalMarkAllReadForm(forms.Form):
    choices = forms.ModelMultipleChoiceField(
        queryset=Msg.objects.all(),
        widget=forms.MultipleHiddenInput,
        )


class JournalMarkOneReadForm(forms.Form):
    choice = forms.ModelChoiceField(
        queryset=Msg.objects.all(),
        widget=forms.HiddenInput,
        )


class JournalMarkFavorite(forms.Form):
    tagged = forms.ModelChoiceField(
        queryset=Msg.objects.all(),
        widget=forms.HiddenInput,
    )

    def tag_msg(self, char):
        msg = self.cleaned_data['tagged']
        char.messages.tag_favorite(msg, char.player_ob)


class JournalRemoveFavorite(forms.Form):
    untagged = forms.ModelChoiceField(
        queryset=Msg.objects.all(),
        widget=forms.HiddenInput,
    )

    def untag_msg(self, char):
        msg = self.cleaned_data['untagged']
        char.messages.untag_favorite(msg, char.player_ob)


class CharacterChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.key


class JournalWriteForm(forms.Form):

    journal = forms.CharField(
        label="Journal Text",
        widget=forms.Textarea(attrs={'class': "form-control",
                                     'rows': "10"}),
        )
    character = CharacterChoiceField(
        label="Character for Relationship Update",
        help_text="Leave blank if this journal is not a relationship",
        empty_label="(None - not a relationship)",
        required=False,
        queryset=ObjectDB.objects.filter(Q(db_typeclass_path=settings.BASE_CHARACTER_TYPECLASS) & Q(
            Q(roster__roster__name="Active") | Q(roster__roster__name="Gone") |
            Q(roster__roster__name="Available"))).order_by('db_key'),
    )
    private = forms.BooleanField(
        label="Black Journal",
        required=False,
        help_text="Mark if this is a private, black journal entry",
        )

    def create_journal(self, char):
        targ = self.cleaned_data['character']
        msg = self.cleaned_data['journal']
        white = not self.cleaned_data['private']
        if targ:
            # add a relationship
            char.messages.add_relationship(msg, targ, white)     
        else:
            # regular journal
            char.messages.add_journal(msg, white)
