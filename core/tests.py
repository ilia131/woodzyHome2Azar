from django.test import SimpleTestCase
from drf_spectacular.generators import EndpointEnumerator, SchemaGenerator


class OpenAPICoverageTests(SimpleTestCase):
    def test_schema_documents_all_versioned_api_operations(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        actual = {(path, method.upper()) for path, methods in schema['paths'].items()
                  for method in methods if path.startswith('/api/v1/') and method in {'get', 'post', 'patch', 'put', 'delete'}}
        expected = {(path.replace('{pk}', '{id}'), method)
                    for path, _, method, _ in EndpointEnumerator().get_api_endpoints()
                    if path.startswith('/api/v1/')}
        self.assertTrue(expected)
        self.assertEqual(actual, expected)
        for path in ('/api/v1/auth/logout/', '/api/v1/auth/password/change/'):
            self.assertIn('204', schema['paths'][path]['post']['responses'])
