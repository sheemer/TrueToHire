from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import ImprovementRequestForm
from .models import ImprovementRequest
from django.contrib.auth.decorators import user_passes_test



@login_required
def submit_improvement(request):
    if request.method == 'POST':
        form = ImprovementRequestForm(request.POST)
        if form.is_valid():
            improvement = form.save(commit=False)
            improvement.user = request.user  # Assign logged-in user
            improvement.save()
            return redirect('home')  # Redirect after submission
    else:
        form = ImprovementRequestForm()

    return render(request, 'contactus/submit_improvement.html', {'form': form})


def is_admin(user):
    return user.is_staff or user.is_superuser

@user_passes_test(is_admin)
def admin_improvements(request):
    improvements = ImprovementRequest.objects.all()
    return render(request, '/admin_improvements.html', {'improvements': improvements})