# app/forms.py
from django import forms
from .models import Submission

class EventRegistrationForm(forms.Form):
    event_id = forms.IntegerField(widget=forms.HiddenInput)

class EventCancelForm(forms.Form):
    registration_id = forms.IntegerField(widget=forms.HiddenInput)

class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["activity", "event_slot", "evidence_url", "evidence_file"]
        widgets = {
            "event_slot": forms.Select(attrs={"required": False}),
            "evidence_url": forms.URLInput(attrs={"placeholder":"https://..."}),
        }

class RedemptionForm(forms.Form):
    reward_id = forms.IntegerField(widget=forms.HiddenInput)
