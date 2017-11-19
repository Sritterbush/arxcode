from django import forms

from cloudinary.forms import CloudinaryFileField, CloudinaryJsFileField, CloudinaryUnsignedJsFileField
# Next two lines are only used for generating the upload preset sample name
from cloudinary.compat import to_bytes
import cloudinary
import hashlib

from .models import Photo, FlashbackPost, Flashback, RosterEntry


class PhotoModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.title:
            return obj.title
        return obj.image.public_id


class PortraitSelectForm(forms.Form):
    select_portrait = PhotoModelChoiceField(queryset=None, empty_label="(No Portrait)")
    portrait_height = forms.IntegerField(initial=480)
    portrait_width = forms.IntegerField(initial=320)
    
    def __init__(self, object_id=None, *args, **kwargs):
        super(PortraitSelectForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields['select_portrait'].queryset = qset


class PhotoEditForm(forms.Form):
    select_photo = PhotoModelChoiceField(queryset=None, empty_label="(No Image Selected)")
    title = forms.CharField(max_length=200)
    alt_text = forms.CharField(max_length=200)
    
    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoEditForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields['select_photo'].queryset = qset


class PhotoDeleteForm(forms.Form):
    select_photo = PhotoModelChoiceField(queryset=None, empty_label="(No Image Selected)")

    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoDeleteForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields['select_photo'].queryset = qset


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ['title', 'alt_text', 'image']
        image = CloudinaryFileField(options={'use_filename': True,
                                             'unique_filename': False,
                                             'overwrite': False})


class PhotoDirectForm(PhotoForm):
    image = CloudinaryJsFileField()


class PhotoUnsignedDirectForm(PhotoForm):
    upload_preset_name = "Arx_Default_Unsigned"
    image = CloudinaryUnsignedJsFileField(upload_preset_name)


class FlashbackPostForm(forms.Form):
    actions = forms.CharField(label="Post Text", widget=forms.Textarea(attrs={'class': "form-control", 'rows': "10"}),)

    def add_post(self, flashback, poster):
        actions = self.cleaned_data['actions']
        flashback.add_post(actions, poster)
