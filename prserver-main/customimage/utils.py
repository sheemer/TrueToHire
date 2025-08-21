from background_task import background
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
import os
import subprocess
from botocore.exceptions import ClientError, WaiterError
from concurrent.futures import ThreadPoolExecutor
from dashboard.models import TestRequest
import base64
import logging
import time
import uuid
import boto3
import psycopg2
import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now
from django.contrib.auth.hashers import check_password
from dashboard.models import TestRequest, TestType, SubTest
import winrm
import paramiko
from utils.secrets import get_secret
from django.views.decorators.http import require_GET
from accounts.models import CustomUser, Company
from datetime import datetime, timedelta
from django.http import HttpResponseNotFound
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import os

logger = logging.getLogger(__name__)

# AWS Configuration
AWS_REGION = get_secret("AWS_REGION", "us-east-1")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE", "t2.micro")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

# Database Configuration
DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"


ec2 = boto3.client("ec2", region_name="us-east-1")

def wait_for_instance(instance_id, public_id, timeout=300, interval=10):
    """
    Waits for the EC2 instance to reach 'running' state and have a public IP address.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response["Reservations"][0]["Instances"][0]
            state = instance["State"]["Name"]
            public_ip = instance.get("PublicIpAddress")

            if state == "running" and public_ip:
                logger.info(f"Instance {instance_id} is ready with IP: {public_ip}")
                return public_ip

            logger.info(f"Waiting for instance {instance_id} to be ready... Current state: {state}")
        except Exception as e:
            logger.warning(f"Error checking instance state: {e}")
        time.sleep(interval)

    logger.error(f"Timeout while waiting for instance {instance_id} ({public_id}) to become ready.")
    return None


def get_instance_ip(instance_id):
    """
    Returns the public IP address of the given EC2 instance.
    """
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        return instance.get("PublicIpAddress")
    except Exception as e:
        logger.error(f"Error fetching public IP for instance {instance_id}: {e}")
        return None


def decrypt_password(encrypted_password, private_key_pem):
    """
    Decrypts the base64-encoded Windows password using the provided RSA private key.
    """
    encrypted_data = base64.b64decode(encrypted_password)

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
        backend=default_backend()
    )

    decrypted_password = private_key.decrypt(
        encrypted_data,
        padding.PKCS1v15()
    )

    return decrypted_password.decode("utf-8")


def get_rdp_credentials(instance_id, os_type, public_ip=None, retries=20, delay=10, public_id=None):
    for attempt in range(retries):
        try:
            # inside your get_rdp_credentials function...
            if os_type == "windows":
                password_data = ec2.get_password_data(InstanceId=instance_id)
                encrypted_password = password_data.get("PasswordData")

                if encrypted_password:
                    with open("/run/secrets/windows_key", "r") as f:
                        private_key = f.read()

                    plaintext_password = decrypt_password(encrypted_password, private_key)
                    ip = get_instance_ip(instance_id)

                    if public_id:
                        try:
                            test_request = TestRequest.objects.get(public_id=public_id)

                            # Encrypt the decrypted plaintext password using Fernet
                            fernet = Fernet(os.environ["RDP_ENCRYPTION_KEY"])
                            encrypted_rdp_password = fernet.encrypt(plaintext_password.encode()).decode()

                            test_request.rdp_password = encrypted_rdp_password
                            test_request.save()

                            logger.info(f"Stored encrypted RDP password for {public_id}")
                        except TestRequest.DoesNotExist:
                            logger.warning(f"No TestRequest found for public_id: {public_id}")

                    return {
                        "username": "Administrator",
                        "password": plaintext_password,  # still return plaintext for immediate use
                        "ip_address": ip
                    }

                logger.info(f"Password not ready for {instance_id}, retrying...")

            else:
                return {
                    "username": "ec2-user",
                    "password": get_secret("AMI_LINUX_PASS", "default"),
                    "ip_address": public_ip
                }

        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Error retrieving credentials: {e}")

        time.sleep(delay)

    logger.error(f"Password retrieval failed after {retries} retries for instance {instance_id}")
    return None

def add_guacamole_connection(instance_id, protocol, port, credentials, public_id, os_type):
    try:
        instance_ip = credentials["ip_address"]
        username = credentials["username"]
        password = credentials["password"]

        # For Linux, we use a private key instead of password
        if os_type == "linux":
            with open("/run/secrets/windows_key", "r") as key_file:
                private_key_contents = key_file.read().strip()
        else:
            private_key_contents = None  # Not used for Windows

        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO guacamole_connection (connection_name, protocol)
            VALUES (%s, %s)
            RETURNING connection_id
            """,
            (f"Instance {instance_id}", protocol)
        )
        connection_id = cursor.fetchone()[0]

        # Common parameters
        params = [
            (connection_id, "hostname", instance_ip),
            (connection_id, "port", str(port)),
            (connection_id, "username", username),
            (connection_id, "security", "any"),
            (connection_id, "ignore-cert", "true"),
        ]

        # OS-specific parameters
        if os_type == "linux":
            params.append((connection_id, "private-key", private_key_contents))
        else:  # Windows
            params.append((connection_id, "password", password))

        cursor.executemany(
            """
            INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
            VALUES (%s, %s, %s)
            """,
            params
        )

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"Guacamole connection added for instance {instance_id} with ID {connection_id}.")
        return connection_id
    except Exception as e:
        logger.error(f"Error adding Guacamole connection for instance {instance_id}: {e}")
        raise
