from django.shortcuts import  get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from .models import TestRequest, Room
from .forms import TestRequestForm
from django.http import JsonResponse
from .models import SubTest
from django.utils.timezone import now
from accounts.models import CustomUser 
from django.db import IntegrityError
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied
import string
import random
from utils.secrets import get_secret




@login_required
def dashboard_view(request):
    user_company = request.user.company 

    open_test_requests = TestRequest.objects.filter(company=user_company, is_accessed=False)
    finished_test_requests = TestRequest.objects.filter(company=user_company, is_accessed=True).only("id", "recorded_session")

    return render(request, 'dashboard/room_detail.html', {
        'user': request.user,
        'open_test_requests': open_test_requests,
        'finished_test_requests': finished_test_requests,
    })
    
@login_required
def new_request_view(request):
    if request.method == 'POST':
        # Handle the creation of a new request here (e.g., save to database)
        return redirect('dashboard')
    return render(request, 'dashboard/new_request.html')


@login_required
def delete_test_request(request, test_id):
    test_request = get_object_or_404(TestRequest, id=test_id)  # No user filter
    test_request.delete()
    return redirect("room_detail", room_id=test_request.room.id)  # ✅ Corrected

@login_required
def create_test_request(request, room_id):
    room = Room.objects.get(id=room_id)
    if request.method == "POST":
        form = TestRequestForm(request.POST)
        if form.is_valid():
            test_request = form.save(commit=False)
            test_request.room = room
            test_request.created_by = request.user
            test_request.company = request.user.company
            
            # Hash the password before saving
            test_request.password = make_password(form.cleaned_data["password"])
            test_request.save()

            sub_tests = form.cleaned_data.get("sub_tests")
            if sub_tests:
                test_request.sub_tests.set(sub_tests)

            return redirect("room_detail", room_id=room.id)

    else:
        form = TestRequestForm()
        # Handle AJAX request to fetch SubTest details
        sub_test_id = request.GET.get("sub_test_id")
        if sub_test_id:
            try:
                sub_test = SubTest.objects.get(id=sub_test_id)
                return JsonResponse({
                    "name": sub_test.name,
                    "details": sub_test.details,
                    "instructions": sub_test.instructions,
                })
            except SubTest.DoesNotExist:
                return JsonResponse({"error": "SubTest not found"}, status=404)

        # Filter SubTests to match the selected TestType
        test_type_id = request.GET.get("test_type")
        if test_type_id:
            try:
                selected_test_type = TestType.objects.get(id=test_type_id)
                form.fields["sub_tests"].queryset = SubTest.objects.filter(test_type=selected_test_type)
            except TestType.DoesNotExist:
                form.fields["sub_tests"].queryset = SubTest.objects.none()

    return render(request, "dashboard/new_request.html", {
        "form": form,
        "room": room,
    })

@login_required
def get_subtests(request):
    test_type_id = request.GET.get("test_type")
    
    if test_type_id:
        sub_tests = SubTest.objects.filter(test_type_id=test_type_id).values("id", "name")
        return JsonResponse({"sub_tests": list(sub_tests)})
    
    return JsonResponse({"sub_tests": []})  # Return empty list if no test type

@login_required
def sub_tests_api(request):
    test_type_id = request.GET.get('test_type')
    sub_tests = SubTest.objects.filter(test_type_id=test_type_id).values('id', 'name')
    return JsonResponse({'sub_tests': list(sub_tests)})

@login_required
def send_test_link(request):
    if request.method == "POST":
        test_id = request.POST.get("test_id")
        recipient_email = request.POST.get("email")

        try:
            test = TestRequest.objects.get(public_id=test_id)
            
            sub_test = test.sub_tests.first()  # Get the first related sub-test
            if sub_test and sub_test.os_type.lower() == "windows":
                room_url = f"https://truetohire.com/windows_test_rooms/windows_test_room/{test.public_id}/"
            elif sub_test and sub_test.os_type.lower() == "linux":
                room_url = f"https://truetohire.com/linux_test_rooms/linux_test_rooms/{test.public_id}/" 
            else:
                return JsonResponse({"success": False, "message": "Invalid test type"})
            # Send the email with the test room link
            send_mail(
                subject="Your Test Room Link",
                message=f"Click the link to access your test: {room_url}",
                from_email="noreply@truetohire.com",
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            return redirect("rooms")
        
        except TestRequest.DoesNotExist:
            return JsonResponse({"success": False, "message": "Test not found"})
    
    return JsonResponse({"success": False, "message": "Invalid request"}, status=400)

@login_required
def rooms_view(request):
    rooms = Room.objects.filter(created_by=request.user)
    return render(request, 'dashboard/mainds.html', {'rooms': rooms})

@login_required
def create_room_view(request):
    if request.method == "POST":
        room_name = request.POST.get("name")
        if room_name:
            if isinstance(request.user, CustomUser):
                try:
                    # Ensure user exists in the database before creating the room
                    if not CustomUser.objects.filter(id=request.user.id).exists():
                        return render(request, "dashboard/create_room.html", {"error": "Invalid user."})

                    Room.objects.create(name=room_name, created_by=request.user)
                except IntegrityError as e:
                    print(f"Error: {e}")
                    return render(request, "dashboard/create_room.html", {"error": "Failed to create room. Please try again!"})
        return redirect("rooms")
    return render(request, "dashboard/create_room.html")

@login_required
def delete_room(request, room_id):
    """Permanently deletes the room."""
    room = get_object_or_404(Room, id=room_id, created_by=request.user)
    room.delete()
    return redirect("rooms")


@login_required
def room_detail_view(request, room_id):
    room = Room.objects.get(id=room_id)
 
    # Fetch latest test requests
    open_test_requests = TestRequest.objects.filter(room=room, is_accessed=False).order_by('-date_created')
    finished_test_requests = TestRequest.objects.filter(room=room, is_accessed=True).order_by('-date_created')

    return render(request, 'dashboard/room_detail.html', {
        'room': room,
        'open_test_requests': open_test_requests,
        'finished_test_requests': finished_test_requests
    })

@login_required
def get_sub_tests(request):
    test_type_id = request.GET.get('test_type_id')
    sub_tests = SubTest.objects.filter(test_type_id=test_type_id).values("id", "name")
    return JsonResponse({"sub_tests": list(sub_tests)})


