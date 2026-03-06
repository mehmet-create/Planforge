import json
import logging
from django.template.loader import render_to_string
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache 
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.urls import reverse_lazy
# CHANGED: imports come from core
from core.utils import send_email, is_json_request
from core.ratelimit import check_ratelimit, RateLimitError

from .forms import SignUpForm, ProfileUpdateForm, LoginForm, VerifyCodeForm
from .models import UserProfile
from . import services, schemas

logger = logging.getLogger(__name__)
User = get_user_model()


# HELPER FUNCTIONS

def get_ip(request):
    """
    Extract user's real IP address.

    SECURITY: HTTP_X_FORWARDED_FOR is a client-controlled header — any client
    can set it to an arbitrary value. We only trust it when Django has been
    explicitly configured with SECURE_PROXY_SSL_HEADER (i.e. you're behind a
    known reverse proxy that strips/overwrites the header before it reaches us).

    Until then, always use REMOTE_ADDR which is set by the OS and cannot be
    spoofed at the TCP level.
    """
    return request.META.get('REMOTE_ADDR', '')

def json_response(status='success', message=None, data=None, code=None, http_status=200):
    """Standardized JSON response."""
    response = {'status': status}
    if message:
        response['message'] = message
    if data:
        response['data'] = data
    if code:
        response['code'] = code
    return JsonResponse(response, status=http_status)


def get_request_data(request):
    """Extract data from POST or JSON body."""
    if request.POST:
        return request.POST
    if request.body:
        try:
            return json.loads(request.body)
        except json.JSONDecodeError:
            return None
    return {}


def check_cooldown(cache_key, duration=60):
    """Check if action is in cooldown period. Returns True if should block."""
    from django.core.cache import cache
    return cache.get(cache_key) is not None


def set_cooldown(cache_key, duration=60):
    """Set cooldown period for an action."""
    from django.core.cache import cache
    cache.set(cache_key, True, duration)


def send_email_safe(to_email, subject, content, error_context=""):
    """Send email with error handling. Returns (success: bool, error_message or None)."""
    try:
        send_email(to_email, subject, content)
        return True, None
    except Exception as e:
        logger.exception("Failed to send email to %s (%s): %s", to_email, error_context, e)
        return False, "Email failed to send. Please try again."


def handle_error(request, message, is_service_error=False):
    """Unified error handling for both HTML and JSON requests."""
    if is_json_request(request):
        status_code = 400 if is_service_error else 500
        return json_response('error', message, http_status=status_code)
    messages.error(request, message)
    return None


def get_session_user_id(request, session_key='unverified_user_id'):
    """Get user ID from session or return None."""
    return request.session.get(session_key)


def clear_session_key(request, session_key='unverified_user_id'):
    """Remove key from session."""
    request.session.pop(session_key, None)


@require_http_methods(["GET", "POST", "HEAD"])
def health(request):
    """Health check endpoint."""
    return json_response('ok')


def login_view(request):
    # FIXED: now uses LoginForm consistently with every other view
    if request.method != 'POST':
        return render(request, 'accounts/login.html', {'form': LoginForm()})

    form = LoginForm(request.POST)

    ip = get_ip(request)
    username = request.POST.get('username', '').strip()
    ratelimit_key = f"login_fail_{ip}_{username}" if username else f"login_fail_{ip}"

    try:
        check_ratelimit(ratelimit_key, limit=10, period=60)
    except RateLimitError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=429)
        messages.error(request, str(e))
        return render(request, 'accounts/login.html', {'form': form})

    if not form.is_valid():
        messages.error(request, "Please fill in both fields.")
        return render(request, 'accounts/login.html', {'form': form})

    dto = schemas.LoginDTO(
        username=form.cleaned_data['username'],
        password=form.cleaned_data['password'],
    )
    user, status = services.login_service(request, dto)

    if status == "success":
        login(request, user)
        from django.core.cache import cache
        cache.delete(f"ratelimit:{ratelimit_key}")
        if is_json_request(request):
            return json_response('success', data={'user': user.username})
        next_url = request.GET.get("next", "")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect('dashboard')

    from django.core.cache import cache
    attempts_used = cache.get(f"ratelimit:{ratelimit_key}", 0)
    attempts_used = attempts_used if isinstance(attempts_used, int) else 0
    remaining     = max(0, 10 - attempts_used)

    error_msg = "Account not verified." if status == "unverified" else "Invalid credentials."
    if 0 < remaining <= 3:
        error_msg += f" Warning: {remaining} attempts remaining."

    if is_json_request(request):
        return json_response('error', error_msg, code=status, http_status=401)

    messages.error(request, error_msg)

    if status == "unverified" and user:
        request.session['unverified_user_id'] = user.id
        return redirect('accounts:verify_registration')

    return render(request, 'accounts/login.html', {'form': form})

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method != 'POST':
        if is_json_request(request):
            return json_response('success', 'Register endpoint ready.', data={'method': 'POST'})
        return render(request, 'accounts/register.html', {'form': SignUpForm()})

    ip = get_ip(request)
    try:
        check_ratelimit(f"reg_ip_{ip}", limit=50, period=3600)
    except RateLimitError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=429)
        messages.error(request, str(e))
        return redirect('accounts:register')

    data = get_request_data(request)
    if data is None:
        return json_response('error', 'Invalid JSON', http_status=400)

    form = SignUpForm(data)
    if not form.is_valid():
        if is_json_request(request):
            return json_response('error', 'Validation failed', data={'errors': form.errors}, http_status=400)
        messages.error(request, "Please check the form.")
        return render(request, 'accounts/register.html', {'form': form})

    try:
        dto = schemas.RegisterDTO(
            username=form.cleaned_data['username'],
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password'],
            first_name=form.cleaned_data.get('first_name', ''),
            last_name=form.cleaned_data.get('last_name', '')
        )
        user, code = services.register_user(dto)
        request.session['unverified_user_id'] = user.id
    except services.ServiceError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=400)
        messages.error(request, str(e))
        return render(request, 'accounts/register.html', {'form': form})

    success, error = send_email_safe(
        user.email,
        "Verify your Planforge account",
        f"<p>Hi {user.first_name},</p><p>Your verification code is: <strong>{code}</strong></p><p>This code expires in 10 minutes.</p>",
        "registration"
    )

    if not success:
        if is_json_request(request):
            return json_response('error', 'Account created but email failed. Use resend.', http_status=503)
        messages.warning(request, "Account created but email failed. Use 'Resend Code'.")
        return redirect('accounts:verify_registration')

    if is_json_request(request):
        return json_response('success', 'Check email for code.', data={'email': user.email}, http_status=201)

    messages.success(request, f"Code sent to {user.email}")
    return redirect('accounts:verify_registration')


@require_http_methods(["GET", "POST"])
def verify_registration(request):
# template path, redirect names namespaced.
    user_id = get_session_user_id(request)
    if not user_id:
        if is_json_request(request):
            return json_response('error', 'No registration session. Please register first.', http_status=401)
        return redirect('accounts:register')

    try:
        user_obj = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.flush()
        if is_json_request(request):
            return json_response('error', 'User not found. Register again.', http_status=404)
        return redirect('accounts:register')

    if request.method != 'POST':
        if is_json_request(request):
            return json_response('success', 'Verification ready.', data={
                'email': user_obj.email,
                'required_fields': ['code']
            })
        return render(request, 'accounts/verify_registration.html', {'email': user_obj.email})

    data = get_request_data(request)
    if data is None:
        return json_response('error', 'Invalid JSON', http_status=400)

    code = data.get('code')

    try:
        dto     = schemas.VerifyCodeDTO(user_id=user_id, code=code)
        success, msg = services.verify_code(dto, acting_user_id=user_id)

        if is_json_request(request):
            if success:
                clear_session_key(request)
                return json_response('success', msg)
            return json_response('error', msg, http_status=400)

        if success:
            messages.success(request, msg)
            clear_session_key(request)
            return redirect('accounts:login')

        messages.error(request, msg)

    except services.ServiceError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=400)
        messages.error(request, str(e))
    except Exception as e:
        logger.exception("Verification error for user_id=%s: %s", user_id, e)
        if is_json_request(request):
            return json_response('error', 'Verification failed. Try again.', http_status=500)
        messages.error(request, "Verification failed. Try again.")

    return render(request, 'accounts/verify_registration.html', {'email': user_obj.email})


@require_http_methods(["GET", "POST"])
def resend_code(request):
    # template path, redirect names namespaced.
    user_id = get_session_user_id(request)
    if not user_id:
        if is_json_request(request):
            return json_response('error', 'Session expired. Register again.', http_status=401)
        return redirect('accounts:register')

    if request.method == "GET":
        if is_json_request(request):
            return json_response('ready', 'Send POST to resend code.')
        return redirect('accounts:verify_registration')

    cache_key = f"resend_code_cooldown_{user_id}"
    if check_cooldown(cache_key):
        msg = "Please wait a minute before requesting another code."
        if is_json_request(request):
            return json_response('error', msg, http_status=429)
        messages.warning(request, msg)
        return redirect('accounts:verify_registration')

    try:
        dto = schemas.ResendCodeDTO(user_id=user_id)
        success, code_or_error, email = services.resend_code(dto)

        if not success:
            error_msg = code_or_error if isinstance(code_or_error, str) else "Failed to generate code."
            if is_json_request(request):
                return json_response('error', error_msg, http_status=400)
            messages.error(request, error_msg)
            return redirect('accounts:verify_registration')

    except Exception as e:
        logger.exception("Code generation failed for user_id=%s: %s", user_id, e)
        if is_json_request(request):
            return json_response('error', 'Failed to generate code.', http_status=500)
        messages.error(request, "Failed to generate code.")
        return redirect('accounts:verify_registration')

    email_success, email_error = send_email_safe(
        email,
        "Your new Planforge verification code",
        f"<p>Your new code is: <strong>{code_or_error}</strong></p>",
        "resend"
    )

    if not email_success:
        if is_json_request(request):
            return json_response('error', email_error, http_status=503)
        messages.warning(request, email_error)
        return redirect('accounts:verify_registration')

    set_cooldown(cache_key, 60)

    if is_json_request(request):
        return json_response('success', 'Code resent')

    messages.success(request, "Code resent.")
    return redirect('accounts:verify_registration')


@login_required
@require_http_methods(["GET", "POST"])
def verify_email_change(request):
    # template path, redirect names namespaced.
    if request.method != 'POST':
        if is_json_request(request):
            return json_response('ready', 'Send POST with "code" to verify.')
        return render(request, 'accounts/verify_email_change.html')

    data = get_request_data(request)
    if data is None:
        return json_response('error', 'Invalid JSON', http_status=400)

    code = data.get('code')

    try:
        dto     = schemas.VerifyEmailChangeDTO(user_id=request.user.id, code=code)
        success, msg = services.verify_email_change(dto)

        if is_json_request(request):
            return json_response('success' if success else 'error', msg,
                                 http_status=200 if success else 400)
        if success:
            messages.success(request, msg)
            return redirect('accounts:profile')

        messages.error(request, msg)

    except Exception as e:
        logger.exception("Email change verification failed for user_id=%s: %s", request.user.id, e)
        if is_json_request(request):
            return json_response('error', 'Verification failed.', http_status=500)
        messages.error(request, "Verification failed.")

    return redirect('accounts:verify_email_change')


@login_required
@require_http_methods(["GET", "POST"])
def password_change_view(request):
    # template path, redirect names namespaced.
    if request.method != 'POST':
        if is_json_request(request):
            return json_response('ready', data={'required_fields': ['old_password', 'new_password', 'confirm_new_password']})
        return render(request, 'accounts/password_change_form.html')

    data = get_request_data(request)
    if data is None:
        if is_json_request(request):
            return json_response('error', 'Invalid JSON', http_status=400)
        messages.error(request, "Invalid request.")
        return render(request, 'accounts/password_change_form.html')

    try:
        dto = schemas.PasswordChangeDTO(
            user_id=request.user.id,
            old_password=data.get('old_password'),
            new_password=data.get('new_password'),
            confirm_new_password=data.get('confirm_new_password')
        )
        success, msg = services.change_password(request.user, dto)

        if not success:
            raise ValueError(msg)

        request.user.refresh_from_db()
        update_session_auth_hash(request, request.user)

        if is_json_request(request):
            return json_response('success', msg)

        messages.success(request, msg)
        return redirect('accounts:profile')

    except ValueError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=400)
        messages.error(request, str(e))
        return render(request, 'accounts/password_change_form.html')


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def delete_account_view(request):
    # template path, redirect to accounts:register.
    if request.method not in ('POST', 'DELETE'):
        if is_json_request(request):
            return json_response('ready', 'Send POST with "password" to delete.')
        return render(request, 'accounts/delete_account.html')

    data     = get_request_data(request)
    if data is None:
        return json_response('error', 'Invalid JSON', http_status=400)

    password = data.get('password')

    try:
        dto = schemas.DeleteAccountDTO(user_id=request.user.id, password=password)
        services.delete_account(dto)
        logout(request)
        if is_json_request(request):
            return json_response('success', 'Account deleted')
        messages.info(request, "Account deleted.")
        return redirect('accounts:register')

    except Exception as e:
        logger.exception("Account deletion failed for user_id=%s: %s", request.user.id, e)
        if is_json_request(request):
            return json_response('error', str(e), http_status=400)
        messages.error(request, str(e))
        return render(request, 'accounts/delete_account.html')


@require_POST
def logout_view(request):
    # redirect to 'home' instead of 'login'.
    logout(request)
    if is_json_request(request):
        return json_response('success', 'Logged out.')
    return redirect('home')


@require_POST
def cancel_registration(request):
    # lets a user abandon registration and clean up.
    uid = get_session_user_id(request)
    if uid:
        try:
            user = User.objects.get(id=uid)
            if not user.is_active:
                user.delete()
        except User.DoesNotExist:
            pass
        finally:
            request.session.flush()
    return redirect('accounts:register')


@login_required
@require_POST
def resend_verification_code_profile(request):
    # redirect names namespaced.
    cache_key = f"email_change_resend_cooldown_{request.user.id}"

    if check_cooldown(cache_key):
        msg = "Please wait a minute before requesting another code."
        if is_json_request(request):
            return json_response('error', msg, http_status=429)
        messages.warning(request, msg)
        return redirect('accounts:verify_email_change')

    try:
        success, result = services.resend_email_change_code(request.user.id)

        if not success:
            if is_json_request(request):
                return json_response('error', result, http_status=400)
            messages.warning(request, result)
            return redirect('accounts:verify_email_change')

        raw_code, email_to = result

        email_success, email_error = send_email_safe(
            email_to,
            "Your New Planforge Code",
            f"<p>Your new verification code is: <strong>{raw_code}</strong></p>",
            "email_change_resend"
        )

        if not email_success:
            if is_json_request(request):
                return json_response('error', email_error, http_status=503)
            messages.warning(request, email_error)
            return redirect('accounts:verify_email_change')

        set_cooldown(cache_key, 60)

        if is_json_request(request):
            return json_response('success', 'Code resent')

        messages.success(request, f"New code sent to {email_to}")

    except UserProfile.DoesNotExist:
        logger.error("UserProfile missing for user_id=%s", request.user.id)
        if is_json_request(request):
            return json_response('error', 'Profile not found.', http_status=404)
        messages.error(request, "Profile not found.")
    except Exception as e:
        logger.exception("Resend failed for user_id=%s: %s", request.user.id, e)
        if is_json_request(request):
            return json_response('error', 'Something went wrong.', http_status=500)
        messages.error(request, "Something went wrong.")

    return redirect('accounts:verify_email_change')


@login_required
@require_http_methods(["GET", "POST"])
def profile_settings(request):
    # template path, redirect names
    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        logger.error("UserProfile missing for user_id=%s", request.user.id)
        messages.error(request, "Profile not found. Please contact support.")
        return redirect('dashboard')

    if request.method != 'POST':
        if is_json_request(request):
            return json_response('success', data={
                'username':   request.user.username,
                'first_name': request.user.first_name,
                'last_name':  request.user.last_name,
                'email':      request.user.email,
            })
        return render(request, 'accounts/profile.html', {
            'form':    ProfileUpdateForm(instance=request.user),
            'profile': profile
        })

    if 'request_email_change' in request.POST:
        return _handle_email_change_request(request)

    return _handle_profile_update(request, profile)


def _handle_email_change_request(request):
    # redirect names namespaced.
    cache_key = f"email_init_cooldown_{request.user.id}"

    if check_cooldown(cache_key):
        msg = "Please wait a minute before requesting another code."
        if is_json_request(request):
            return json_response('error', msg, http_status=429)
        messages.warning(request, msg)
        return redirect('accounts:profile')

    try:
        dto = schemas.EmailChangeRequestDTO(
            user_id=request.user.id,
            new_email=request.POST.get('email', '').strip(),
            current_email=request.user.email
        )
        raw_code = services.request_email_change(dto)

    except services.ServiceError as e:
        if is_json_request(request):
            return json_response('error', str(e), http_status=400)
        messages.error(request, str(e))
        return redirect('accounts:profile')

    email_success, email_error = send_email_safe(
        dto.new_email,
        "Confirm your Planforge email change",
        f"<p>Your email change code is: <strong>{raw_code}</strong></p>",
        "email_change"
    )

    if not email_success:
        if is_json_request(request):
            return json_response('error', email_error, http_status=503)
        messages.warning(request, email_error)
        return redirect('accounts:profile')

    set_cooldown(cache_key, 60)

    if is_json_request(request):
        return json_response('success', 'Verification code sent.')

    return redirect('accounts:verify_email_change')


def _handle_profile_update(request, profile):
    # template path, redirect names namespaced
    post_data         = request.POST.copy()
    post_data['email'] = request.user.email

    form = ProfileUpdateForm(post_data, instance=request.user)

    if not form.is_valid():
        if is_json_request(request):
            return json_response('error', 'Validation failed', data={'errors': form.errors}, http_status=400)
        messages.error(request, "Please correct the errors below.")
        return render(request, 'accounts/profile.html', {'form': form, 'profile': profile})

    try:
        form.save()
    except IntegrityError:
        msg = "That username is already taken."
        if is_json_request(request):
            return json_response('error', msg, http_status=400)
        messages.error(request, msg)
        return render(request, 'accounts/profile.html', {'form': form, 'profile': profile})

    if is_json_request(request):
        return json_response('success', data={
            'username':   request.user.username,
            'first_name': request.user.first_name,
            'last_name':  request.user.last_name,
            'email':      request.user.email,
        })

    messages.success(request, 'Profile updated.')
    return redirect('accounts:profile')


# PASSWORD RESET
# Django's built-in password reset flow, pointed at our templates.


class PlanforgePasswordResetView(PasswordResetView):
    template_name         = "accounts/password_reset.html"
    email_template_name   = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url           = reverse_lazy("accounts:password_reset_done")

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):

        from django.conf import settings

        # Build the reset URL directly from context
        uid      = context.get('uid')
        token    = context.get('token')
        domain   = context.get('domain')
        protocol = context.get('protocol')
        reset_url = f"{protocol}://{domain}/accounts/password/reset/{uid}/{token}/"

        if settings.DEBUG:
            # Print cleanly to the terminal — no encoding, no line wrapping
            print("\n" + "="*60)
            print("PASSWORD RESET LINK")
            print(reset_url)
            print("="*60 + "\n")
            return

        # Production — send real email
        
        subject      = render_to_string(subject_template_name, context).strip()
        html_content = render_to_string(email_template_name, context)
        send_email(to_email, subject, html_content)

class PlanforgePasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PlanforgePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PlanforgePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


# ERROR HANDLERS 

def custom_400_handler(request, exception=None):
    if is_json_request(request):
        return json_response('error', 'Bad Request', http_status=400)
    return render(request, 'errors/400.html', status=400)


def custom_403_handler(request, exception=None):
    if is_json_request(request):
        return json_response('error', 'Forbidden', http_status=403)
    return render(request, 'errors/403.html', status=403)


def custom_404_handler(request, exception):
    if is_json_request(request):
        return json_response('error', 'Not Found', http_status=404)
    return render(request, 'errors/404.html', status=404)


def custom_500_handler(request):
    if is_json_request(request):
        return json_response('error', 'Server Error', http_status=500)
    return render(request, 'errors/500.html', status=500)