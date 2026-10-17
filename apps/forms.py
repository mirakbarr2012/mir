from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django import forms


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, label="Ism")
    last_name = forms.CharField(max_length=50, label="Familiya")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name")
