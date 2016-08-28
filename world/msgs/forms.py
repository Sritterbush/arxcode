from django import forms
from .models import Msg
from src.objects.models import ObjectDB
import settings



class JournalMarkAllReadForm(forms.Form):
    choices = forms.ModelMultipleChoiceField(
        queryset = Msg.objects.all(),
        widget = forms.MultipleHiddenInput,
        )

class JournalMarkOneReadForm(forms.Form):
    choice = forms.ModelChoiceField(
        queryset = Msg.objects.all(),
        widget = forms.HiddenInput,
        )

class JournalWriteForm(forms.Form):
    character = forms.ModelChoiceField(
        label = "Character for Relationship Update",
        help_text = "Leave blank if this journal is not a relationship",
        empty_label = "(None - not a relationship)",
        required = False,
        queryset = ObjectDB.objects.filter(db_typeclass_path=settings.BASE_CHARACTER_TYPECLASS,
                                           roster__roster__name="Active").order_by('db_key'),
        )
    journal = forms.CharField(
        label = "Journal Text",
        widget = forms.Textarea(attrs = { 'class': "form-control",
                                          'rows': "10" }),
        )
    private = forms.BooleanField(
        label = "Black Journal",
        required = False,
        help_text = "Mark if this is a private, black journal entry",
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

    
    
