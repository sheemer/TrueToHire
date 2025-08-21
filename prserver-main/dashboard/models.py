from django.db import models
from django.contrib.auth.hashers import make_password
from django import forms
from video_playback.models import RecordedSession  # Import from video_playback app
from accounts.models import CustomUser, Company
from django.conf import settings
from django.contrib.auth.models import User
import string
import random
import uuid


def generate_unique_id():
    return str(uuid.uuid4())


class TestType(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE,  null=True, blank=True)
    is_public = models.BooleanField(default=False, help_text="If true, visible to all users", null=True)

    def __str__(self):
        return self.name


class SubTest(models.Model):
    name = models.CharField(max_length=255)
    test_type = models.ForeignKey(TestType, on_delete=models.CASCADE, related_name='sub_tests')
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    is_public = models.BooleanField(default=False, help_text="If true, visible to all users", null=True)
    ami_id = models.CharField(max_length=255, blank=True, null=True)  # Hidden AMI field
    details = models.TextField(blank=True, null=True)  # Description of the test process
    instructions = models.TextField(blank=True, null=True)  # Step-by-step instructions for the test
    time_limit = models.PositiveIntegerField(default=30)  # Time allotted in minutes
    rdp_password = models.CharField(max_length=255, blank=True, null=True)
    os_type = models.CharField(
        max_length=10,
        choices=[('linux', 'Linux'), ('windows', 'Windows')],
        default='windows'
    )
    script = models.TextField(null=True, blank=True, help_text="Command or file path to execute on shutdown")
    pass_fail = models.CharField(
        max_length=10,
        choices=[('pass', 'Pass'), ('fail', 'Fail'), ('NA', 'na')],
        null=True,
        blank=True,
        help_text="Indicates whether the test passed or failed"
    )

    @property
    def test_requests(self):
        return self.testrequest_set.all()

    def __str__(self):
        return self.name


class Room(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


class TestRequest(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="test_requests", null=True, blank=True)
    instance_id = models.CharField(max_length=100, null=True)
    title = models.CharField(max_length=100)
    test_type = models.ForeignKey(TestType, on_delete=models.CASCADE)
    sub_tests = models.ManyToManyField(SubTest, blank=False)
    password = models.CharField(max_length=128)
    date_created = models.DateTimeField(auto_now_add=True)
    accessed_by_name = models.CharField(max_length=100, blank=True, null=True)
    accessed_by_email = models.EmailField(blank=True, null=True)
    is_accessed = models.BooleanField(default=False)
    recorded_session = models.CharField(max_length=500, blank=True, null=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="created_test_requests", null=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="assigned_test_requests", null=True, blank=True)
    public_ip = models.CharField(max_length=15, blank=True, null=True)
    status = models.CharField(max_length=20, default='pending')

    def __str__(self):
        return self.title