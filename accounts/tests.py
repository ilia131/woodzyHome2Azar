from django.core.cache import cache
from rest_framework.test import APITestCase
from .models import User


class AuthenticationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = 'Strong!passTest42'
        self.phone = '09121234567'

    def test_registration_login_refresh_and_logout(self):
        result = self.client.post('/api/v1/auth/register/', {'phone': self.phone, 'password': self.password})
        self.assertEqual(result.status_code, 201, result.data)
        user = User.objects.get()
        self.assertEqual(user.phone, '+989121234567')
        self.assertTrue(user.check_password(self.password))
        result = self.client.post('/api/v1/auth/login/', {'phone': self.phone, 'password': self.password})
        self.assertEqual(result.status_code, 200, result.data)
        tokens = self.client.post('/api/v1/auth/token/refresh/', {'refresh': result.data['refresh']}).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.get('/api/v1/auth/me/').data['phone'], user.phone)
        self.assertEqual(self.client.post('/api/v1/auth/logout/', {'refresh': tokens['refresh']}).status_code, 204)
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']}).status_code, 401)

    def test_invalid_phone_and_private_profile(self):
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
        result = self.client.post('/api/v1/auth/register/', {'phone': 'invalid', 'password': self.password})
        self.assertEqual(result.status_code, 400)

    def test_duplicate_normalized_phone_and_password_validation(self):
        url = '/api/v1/auth/register/'
        self.assertEqual(self.client.post(url, {'phone': self.phone, 'password': '123'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'phone': self.phone, 'password': self.password}).status_code, 201)
        self.assertEqual(self.client.post(url, {'phone': '+989121234567', 'password': self.password}).status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_password_change_revokes_all_old_tokens(self):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        user = User.objects.create_user(self.phone, self.password)
        login = '/api/v1/auth/login/'
        sessions = [self.client.post(login, {'phone': self.phone, 'password': self.password}).data for _ in range(2)]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sessions[0]['access']}")
        url = '/api/v1/auth/password/change/'
        data = {'old_password': self.password, 'password': 'Next!StrongPass87'}
        self.assertEqual(self.client.post(url, {**data, 'password': '123'}).status_code, 400)
        self.assertEqual(self.client.post(url, {**data, 'old_password': 'wrong'}).status_code, 400)
        self.assertEqual(self.client.post(url, data).status_code, 204)
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        for tokens in sessions:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
            self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
            self.client.credentials()
            self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']}).status_code, 401)
        self.assertEqual(self.client.post(login, {'phone': self.phone, 'password': self.password}).status_code, 401)
        self.assertEqual(self.client.post(login, {'phone': self.phone, 'password': data['password']}).status_code, 200)

    def test_profile_and_logout_are_scoped_to_current_user(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        first = User.objects.create_user(self.phone, self.password)
        second = User.objects.create_user('09121234568', self.password, first_name='Private')
        own = RefreshToken.for_user(first)
        other = RefreshToken.for_user(second)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {own.access_token}')
        response = self.client.patch(f'/api/v1/auth/me/?user={second.pk}',
                                     {'id': second.pk, 'phone': second.phone, 'first_name': 'Updated'})
        self.assertEqual(response.data['id'], first.pk)
        self.assertEqual(response.data['phone'], first.phone)
        second.refresh_from_db()
        self.assertEqual(second.first_name, 'Private')
        self.assertEqual(self.client.post('/api/v1/auth/logout/', {'refresh': str(other)}).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': str(other)}).status_code, 200)
