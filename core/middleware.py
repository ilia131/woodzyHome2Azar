from django.utils.cache import add_never_cache_headers


class PrivateAPICacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(('/api/v1/auth/', '/api/v1/admin/', '/api/v1/payments/')):
            add_never_cache_headers(response)
        return response
