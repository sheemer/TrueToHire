from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.forms import UserCreationForm
from .forms import CustomUserCreationForm  
from .models import Company, CustomUser
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from allauth_2fa.utils import user_has_valid_totp_device
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_ratelimit.decorators import ratelimit
from django.core.cache import cache
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from ipware import get_client_ip
from django.core.exceptions import PermissionDenied
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.conf import settings
from django.utils.timezone import now

def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            request.session['signup_data'] = {
                'username': form.cleaned_data['username'],
                'email': form.cleaned_data['email'],
                'password': form.cleaned_data['password1'],
                'company_name': form.cleaned_data['company_name'],
            }
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/signup.html', {'form': form})

@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect('home') 
        else:
            return render(request, 'accounts/change_password.html', {'form': form})
    
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@receiver(user_login_failed)
def login_failed(sender, credentials, request, **kwargs):
    ip, is_routable = get_client_ip(request)
    username = credentials.get("username", "unknown")
    cache_key = f"failed_login:{ip}:{username}"
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, timeout=300)  # Store for 5 minutes

    if attempts >= 5:
        print(f"ALERT: Repeated failed login for {username} from {ip}")

@ratelimit(key='ip', rate='5/m', method='POST', block=True)  # Rate limit: 5 attempts per minute
@csrf_protect
@never_cache
@sensitive_post_parameters("password")
def login_view(request):
    if request.method == 'POST':
        ip, is_routable = get_client_ip(request)
        username = request.POST.get('username', '')
        user = get_user_model().objects.filter(username=username).exists()
        cache_key = f'failed_attempts:{username}:{ip}'
        failed_attempts = cache.get(cache_key, 0)
        if failed_attempts >= 5:
            return render(request, 'accounts/login.html', {'error': 'Account temporarily locked due to multiple failed login attempts. Try again later.'})

        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            cache.delete(cache_key)  
            request.session.flush()  
            if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
                request.session['pre_2fa_user_id'] = user.id 
                return redirect('two-factor-authenticate')
            else:
                login(request, user)
                return redirect('two-factor-setup') 
            login(request, user)
            return redirect('dashboard')

        else:
            cache.set(cache_key, failed_attempts + 1, timeout=300)  

        return render(request, 'accounts/login.html', {'error': 'Invalid username or password'})

    return render(request, 'accounts/login.html', {'error': None})


def two_factor_authenticate_view(request):
    user_id = request.session.get('pre_2fa_user_id')

    if not user_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect('login')

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, "User does not exist.")
        return redirect('login')  
    error = None
    if request.method == 'POST':
        otp_code = request.POST.get('otp')
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

        if device and device.verify_token(otp_code):
            request.session.pop('pre_2fa_user_id', None)
            login(request, user)  
            return redirect('home')  

        error = "Invalid OTP code. Please try again."

    return render(request, 'accounts/two_factor_authenticate.html', {'error': error})

