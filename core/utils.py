import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def is_json_request(request):
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept

def send_email(to_email: str, subject: str, html_content: str) -> None:
    """
    Sends an email. Raises on failure so callers can handle it.
    Dev: uses Django console backend. Production: uses Django SMTP.
    """

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Please view this email in an HTML-compatible client.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info("Dev email sent to %s (subject=%s)", to_email, subject)
        return True
    except Exception as e:
        logger.exception("Dev email failed to %s: %s", to_email, e)
        raise
