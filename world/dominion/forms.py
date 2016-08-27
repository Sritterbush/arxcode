from django import forms



class RPEventCommentForm(forms.Form):
    journal_text = forms.CharField(widget=forms.Textarea)
    private = forms.BooleanField(initial=False, required=False)

    def post_comment(self, char, event):
        msg = self.cleaned_data['journal_text']
        white = not self.cleaned_data['private']
        char.messages.add_event_journal(event, msg, white=white)
    
    
