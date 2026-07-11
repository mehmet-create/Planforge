from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .middleware import SecurityHeadersMiddleware


class SecurityHeadersMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        CONTENT_SECURITY_POLICY="default-src 'self'; object-src 'none'",
        PERMISSIONS_POLICY="camera=(), microphone=()",
    )
    def test_adds_configured_security_headers(self):
        middleware = SecurityHeadersMiddleware(lambda request: HttpResponse("ok"))
        response = middleware(self.factory.get("/"))

        self.assertEqual(
            response["Content-Security-Policy"],
            "default-src 'self'; object-src 'none'",
        )
        self.assertEqual(response["Permissions-Policy"], "camera=(), microphone=()")

    @override_settings(
        CONTENT_SECURITY_POLICY="default-src 'self'",
        PERMISSIONS_POLICY="camera=()",
    )
    def test_preserves_existing_security_headers(self):
        def get_response(request):
            response = HttpResponse("ok")
            response["Content-Security-Policy"] = "default-src 'none'"
            response["Permissions-Policy"] = "geolocation=()"
            return response

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy"], "default-src 'none'")
        self.assertEqual(response["Permissions-Policy"], "geolocation=()")
