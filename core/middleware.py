from django.http import HttpResponsePermanentRedirect
from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Adds security headers that Django does not emit directly.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        csp = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if csp and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = csp

        permissions_policy = getattr(settings, "PERMISSIONS_POLICY", "")
        if permissions_policy and "Permissions-Policy" not in response:
            response["Permissions-Policy"] = permissions_policy

        return response


class EnforceCustomDomainMiddleware:
    """
    Redirects any traffic hitting the Render domain to the primary custom domain.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()
        # Check if the request is coming through the Render domain
        if 'onrender.com' in host:
            # Replace with your actual domain name
            custom_domain = getattr(settings, 'BASE_FRONTEND_URL', None)
            redirect_url = f"https://{custom_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(redirect_url)

        return self.get_response(request)
