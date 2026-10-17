from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from allauth.core.exceptions import ImmediateHttpResponse

from .adapters import PendingSocialAccountAdapter
from .models import Attendance, Group, Student, Teacher


User = get_user_model()


class RoleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher_one",
            password="Teacher-password-2026!",
            is_active=True,
        )
        self.teacher = Teacher.objects.create(
            user=self.user,
            first_name="Teacher",
            last_name="One",
        )
        self.assigned_group = Group.objects.create(name="Assigned group")
        self.assigned_group.teachers.add(self.teacher)
        self.assigned_student = Student.objects.create(
            first_name="Assigned",
            last_name="Student",
            group=self.assigned_group,
        )
        self.other_group = Group.objects.create(name="Other group")
        self.other_student = Student.objects.create(
            first_name="Other",
            last_name="Student",
            group=self.other_group,
        )
        self.client.force_login(self.user)

    def test_teacher_only_sees_assigned_group_data(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Student")
        self.assertNotContains(response, "Other Student")
        self.assertNotContains(response, 'name="add_student"')

        response = self.client.get(
            f"/attendance/history/?group_id={self.other_group.pk}"
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(f"/groups/{self.other_group.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_manage_students_or_funds(self):
        response = self.client.post(
            "/", {"add_student": "1", "first_name": "New", "last_name": "Student"}
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/fund/")
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            "/groups/", {"add_group": "1", "name": "Forbidden"}
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.telegram.send_attendance_notification")
    def test_teacher_can_only_save_assigned_attendance_as_self(self, _notify):
        other_user = User.objects.create_user(
            username="teacher_two",
            password="Teacher-password-2026!",
            is_active=True,
        )
        other_teacher = Teacher.objects.create(
            user=other_user,
            first_name="Teacher",
            last_name="Two",
        )

        response = self.client.post("/", {
            "save_attendance": "1",
            "date": "2026-10-06",
            "teacher_id": str(other_teacher.pk),
            f"status_{self.assigned_student.pk}": "present",
            f"status_{self.other_student.pk}": "present",
        })

        self.assertEqual(response.status_code, 302)
        attendance = Attendance.objects.get(student=self.assigned_student)
        self.assertTrue(attendance.is_present)
        self.assertEqual(attendance.teacher, self.teacher)
        self.assertFalse(Attendance.objects.filter(student=self.other_student).exists())

    def test_active_user_without_assigned_teacher_profile_cannot_log_in(self):
        User.objects.create_user(
            username="unassigned",
            password="Teacher-password-2026!",
            is_active=True,
        )
        self.client.logout()

        response = self.client.post("/login/", {
            "username": "unassigned",
            "password": "Teacher-password-2026!",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_teacher_can_log_in_only_after_admin_activates_them(self):
        self.client.logout()
        pending_user = User.objects.create_user(
            username="pending_teacher",
            password="Teacher-password-2026!",
            is_active=False,
        )
        pending_teacher = Teacher.objects.create(
            user=pending_user,
            first_name="Pending",
            last_name="Teacher",
        )

        response = self.client.post("/login/", {
            "username": "pending_teacher",
            "password": "Teacher-password-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

        admin_user = User.objects.create_superuser(
            username="activation_admin",
            email="activation@example.com",
            password="Admin-password-2026!",
        )
        self.client.force_login(admin_user)
        response = self.client.post(reverse("admin:apps_teacher_changelist"), {
            "action": "activate_accounts",
            "_selected_action": [str(pending_teacher.pk)],
            "index": "0",
        })
        self.assertEqual(response.status_code, 302)

        pending_user.refresh_from_db()
        self.assertTrue(pending_user.is_active)
        self.client.logout()
        response = self.client.post("/login/", {
            "username": "pending_teacher",
            "password": "Teacher-password-2026!",
        })
        self.assertRedirects(response, "/")
        self.assertEqual(
            str(self.client.session["_auth_user_id"]), str(pending_user.pk)
        )

    def test_deactivated_teacher_cannot_keep_using_an_existing_session(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_social_login_rejects_existing_inactive_account(self):
        self.client.logout()
        request = RequestFactory().get("/accounts/github/login/callback/")
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        inactive_user = User.objects.create_user(
            username="inactive_social",
            password="Teacher-password-2026!",
            is_active=False,
        )

        class SocialLogin:
            is_existing = True
            user = inactive_user

        with self.assertRaises(ImmediateHttpResponse) as raised:
            PendingSocialAccountAdapter().pre_social_login(request, SocialLogin())

        self.assertEqual(raised.exception.response.status_code, 302)
        self.assertEqual(raised.exception.response["Location"], "/login/")

    def test_inactive_account_page_uses_project_styling(self):
        self.client.logout()

        response = self.client.get("/accounts/inactive/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/account_inactive.html")
        self.assertContains(response, "Hisobingiz tasdiqlanishi kutilmoqda")
        self.assertContains(response, 'class="status-card"')
        self.assertContains(response, 'href="/login/"')
        self.assertContains(response, 'href="/register/"')

    @patch(
        "apps.adapters.DefaultSocialAccountAdapter.save_user",
        autospec=True,
    )
    def test_new_social_user_is_created_inactive(self, save_social_user):
        self.client.logout()
        user = User.objects.create_user(
            username="new_social",
            password="Teacher-password-2026!",
            is_active=True,
        )
        save_social_user.return_value = user
        request = RequestFactory().post("/accounts/github/login/")

        saved_user = PendingSocialAccountAdapter().save_user(
            request, type("SocialLogin", (), {"user": user})()
        )

        self.assertEqual(saved_user, user)
        self.assertFalse(saved_user.is_active)
        self.assertEqual(saved_user.teacher_profile.role, Teacher.Role.TEACHER)

    def test_registration_creates_pending_teacher_account(self):
        self.client.logout()
        response = self.client.post("/register/", {
            "username": "new_teacher",
            "first_name": "New",
            "last_name": "Teacher",
            "password1": "Long-strong-password-2026!",
            "password2": "Long-strong-password-2026!",
        })

        self.assertRedirects(response, "/login/")
        user = User.objects.get(username="new_teacher")
        self.assertFalse(user.is_active)
        self.assertEqual(user.teacher_profile.role, Teacher.Role.TEACHER)

    @patch(
        "apps.adapters.DefaultSocialAccountAdapter.save_user",
        autospec=True,
    )
    def test_first_social_user_becomes_admin_when_no_admin_exists(self, save_social_user):
        User.objects.all().delete()
        Teacher.objects.all().delete()

        user = User.objects.create_user(
            username="first_admin_social",
            first_name="First",
            last_name="Admin",
            email="first@example.com",
            password="Strong-password-2026!",
            is_active=True,
        )
        save_social_user.return_value = user
        request = RequestFactory().post("/accounts/google/login/")
        request.session = self.client.session
        request._messages = FallbackStorage(request)

        saved_user = PendingSocialAccountAdapter().save_user(
            request,
            type("SocialLogin", (), {"user": user})(),
        )

        self.assertTrue(saved_user.is_active)
        self.assertTrue(saved_user.is_staff)
        self.assertEqual(saved_user.teacher_profile.role, Teacher.Role.ADMIN)

    @override_settings(SOCIALACCOUNT_PROVIDERS={
        "google": {"APP": {"client_id": "", "secret": ""}},
        "github": {"APP": {"client_id": "", "secret": ""}},
    })
    def test_social_login_buttons_are_clickable_without_credentials_and_show_message(self):
        self.client.logout()
        response = self.client.get("/register/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/social-login/google/"')
        self.assertContains(response, 'href="/social-login/github/"')

        response = self.client.get("/social-login/google/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google bilan kirish hozir sozlanmagan")

        response = self.client.get("/social-login/github/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GitHub bilan kirish hozir sozlanmagan")

    @override_settings(SOCIALACCOUNT_PROVIDERS={
        "google": {"APP": {"client_id": "test-google-id", "secret": "test-google-secret"}},
        "github": {"APP": {"client_id": "test-github-id", "secret": "test-github-secret"}},
    })
    def test_social_login_buttons_link_to_allauth_when_credentials_exist(self):
        self.client.logout()
        response = self.client.get("/register/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/social-login/google/"')
        self.assertContains(response, 'href="/social-login/github/"')

        google_response = self.client.get("/social-login/google/")
        github_response = self.client.get("/social-login/github/")
        self.assertEqual(google_response.status_code, 302)
        self.assertEqual(google_response["Location"], "/accounts/google/login/")
        self.assertEqual(github_response.status_code, 302)
        self.assertEqual(github_response["Location"], "/accounts/github/login/")

        google_response = self.client.get(google_response["Location"])
        github_response = self.client.get(github_response["Location"])
        self.assertEqual(google_response.status_code, 302)
        self.assertIn("accounts.google.com", google_response["Location"])
        self.assertEqual(github_response.status_code, 302)
        self.assertIn("github.com", github_response["Location"])

    def test_admin_can_open_management_pages(self):
        admin = User.objects.create_superuser(
            username="site_admin",
            email="admin@example.com",
            password="Admin-password-2026!",
        )
        self.client.force_login(admin)

        self.assertEqual(self.client.get("/fund/").status_code, 200)

    def test_admin_role_has_management_access(self):
        admin_user = User.objects.create_user(
            username="app_admin",
            password="Admin-password-2026!",
            is_active=True,
        )
        Teacher.objects.create(
            user=admin_user,
            first_name="App",
            last_name="Admin",
            role=Teacher.Role.ADMIN,
        )
        self.client.force_login(admin_user)

        self.assertEqual(self.client.get("/fund/").status_code, 200)
        response = self.client.get("/")
        self.assertContains(response, "Other Student")
