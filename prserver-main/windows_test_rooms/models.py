from django.db import models
from dashboard.models import TestRequest, SubTest


class WindowsTestInstance(models.Model):
    instance_id = models.CharField(max_length=100)
    test_request = models.OneToOneField(TestRequest, on_delete=models.CASCADE, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=50, default='pending')
    sub_tests = models.ManyToManyField(SubTest, blank=True)  