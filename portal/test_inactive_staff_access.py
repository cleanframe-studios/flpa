from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Teacher


class InactiveStaffAccessTests(TestCase):
    def create_inactive_staff(self, username, phone_number, email):
        user = get_user_model().objects.create_user(username=username, password='pass123')
        Teacher.objects.create(
            first_name='Inactive',
            last_name='Staff',
            phone_number=phone_number,
            email=email,
            status='Inactive',
            user=user,
        )
        return user

    def test_inactive_staff_cannot_log_in_and_is_directed_to_public_home(self):
        user = self.create_inactive_staff(
            'inactive-staff',
            '08034561236',
            'inactive-staff@example.com',
        )

        response = self.client.post(reverse('login'), {
            'username': user.username,
            'password': 'pass123',
        })

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'You are no longer a staff member', status_code=403)
        self.assertContains(response, 'href="/"', status_code=403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_inactive_staff_session_is_logged_out_and_locked_out_of_portal(self):
        user = self.create_inactive_staff(
            'inactive-session-staff',
            '08034561237',
            'inactive-session-staff@example.com',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'You are no longer a staff member', status_code=403)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(reverse('public_home')).status_code, 200)
