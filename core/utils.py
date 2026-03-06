import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def is_json_request(request):
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept

def send_email(to_email: str, subject: str, html_content: str) -> None:
    """
    Send an email synchronously. Raises on failure so callers can handle it.
    Dev: uses Django console backend. Production: uses Django SMTP.

    Use this only when you need to know the email succeeded before continuing
    (e.g. password reset, where Django's built-in view needs the send to complete).
    For everything else — registration codes, resend codes, email change — use
    send_email_async() so the WSGI worker is not blocked waiting on SMTP.
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
        logger.info("Email sent to %s (subject=%s)", to_email, subject)
        return True
    except Exception as e:
        logger.exception("Email failed to %s: %s", to_email, e)
        raise


def send_email_async(to_email: str, subject: str, html_content: str, context: str = "") -> None:
    """
    Fire-and-forget email on a daemon thread.

    The WSGI worker returns to the client immediately — SMTP latency (1-5 s on
    Gmail) no longer blocks request throughput. The daemon flag means the thread
    won't prevent the server from shutting down cleanly.

    Errors are logged but NOT raised — the caller cannot await the result.
    Only use this for non-critical emails where the user can request a resend
    if delivery fails (registration codes, resend codes, email-change codes).

    Once Celery is added, replace calls to this function with a proper task —
    threads give no retry logic, no dead-letter queue, and no visibility.
    """
    def _send():
        try:
            send_email(to_email, subject, html_content)
        except Exception as e:
            # Already logged inside send_email; re-log with context for traceability.
            logger.error(
                "Async email delivery failed to %s (context=%s): %s",
                to_email, context, e
            )

    thread = threading.Thread(target=_send, daemon=True, name=f"email-{context}")
    thread.start()