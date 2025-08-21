from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

class CustomUser(AbstractUser):
    email = models.EmailField(max_length=254, unique=True, default="", blank=True)  # Add if not present
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)

    def has_2fa_enabled(self):
        return self.totpdevice_set.filter(confirmed=True).exists()