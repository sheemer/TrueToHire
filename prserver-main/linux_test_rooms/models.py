from django.db import models
from dashboard.models import TestRequest, SubTest


class LinuxTestInstance(models.Model):
    instance_id = models.CharField(max_length=100)
    test_request = models.OneToOneField(TestRequest, on_delete=models.CASCADE, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=50, default='pending')
    guacamole_connection_id = models.IntegerField(null=True, blank=True)  # Add this field
    sub_tests = models.ManyToManyField(SubTest, blank=True)  
