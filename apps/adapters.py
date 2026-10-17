from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .models import Teacher


class PendingSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        user = sociallogin.user
        if sociallogin.is_existing and user and not user.is_active:
            messages.error(
                request,
                "Akkauntingiz admin tomonidan hali faollashtirilmagan.",
            )
            raise ImmediateHttpResponse(redirect("login"))

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not Teacher.objects.exists() and not user.is_superuser:
            user.is_active = True
            user.is_staff = True
            user.save(update_fields=["is_active", "is_staff"])
            Teacher.ensure_first_user_is_admin(user)
            return user

        user.is_active = False
        user.save(update_fields=["is_active"])
        Teacher.objects.get_or_create(
            user=user,
            defaults={
                "first_name": user.first_name or user.username,
                "last_name": user.last_name or "",
            },
        )
        return user
