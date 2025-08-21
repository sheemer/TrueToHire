import base64
import logging
import time
import uuid
import boto3
import psycopg2
import requests
from background_task import background
from dashboard.models import TestRequest, TestType, SubTest
from accounts.models import CustomUser, Company
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
import os
import paramiko
import subprocess
from utils.secrets import get_secret
from datetime import datetime
from botocore.exceptions import ClientError, WaiterError
from concurrent.futures import ThreadPoolExecutor
from .utils import wait_for_instance, add_guacamole_connection, get_rdp_credentials, decrypt_password, get_instance_ip
from background_task import background



logger = logging.getLogger(__name__)
AWS_REGION = get_secret("AWS_REGION", "us-east-1")
AMI_ID = get_secret("AMI_ID")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

# Database Configuration
DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"

def create_ami(instance_id, name_prefix):
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        ami_name = f"{name_prefix}-ami-{timestamp}"

        response = ec2.create_image(
            InstanceId=instance_id,
            Name=ami_name,
            Description=f"AMI created from instance {instance_id} for test {name_prefix}",
            NoReboot=True
        )
        image_id = response['ImageId']
        logger.info(f"AMI creation started for {image_id} from instance {instance_id}")

        waiter = ec2.get_waiter('image_available')
        waiter.wait(ImageIds=[image_id], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        return image_id

    except WaiterError as we:
        logger.error(f"Timeout waiting for AMI to become available: {we}")
        return None
    except Exception as e:
        logger.exception(f"Error creating AMI from instance {instance_id}: {e}")
        return None


def terminate_instance(test_request):
    try:
        if not isinstance(test_request, TestRequest):
            raise ValueError("Invalid test_request object")

        public_id = str(test_request.public_id)
        sub_test = test_request.sub_tests.first()
        if not sub_test:
            raise ValueError("No subtest found for this test request.")

        if not test_request.instance_id:
            logger.warning(f"No instance_id found for test_id {public_id}")
            return False, "No instance ID to terminate or create AMI from."

        # Execute cleanup script if defined
        if sub_test.script:
            os_type = (sub_test.os_type or "").lower()
            try:
                if os_type == "windows":
                    sub_test.pass_fail = execute_remote_windows_script(sub_test, test_request.public_ip)
                elif os_type == "linux":
                    sub_test.pass_fail = execute_remote_linux_script(sub_test, test_request.public_ip)
                else:
                    raise ValueError(f"Unsupported OS type: {sub_test.os_type}")
                sub_test.save()
            except Exception as e:
                logger.warning(f"Failed to execute script for test_id {public_id}: {e}")
        else:
            logger.info(f"No script defined for sub_test of test_id {public_id}")

        ec2 = boto3.client("ec2", region_name=AWS_REGION)

        # Create AMI
        try:
            ami_id = create_ami(test_request.instance_id, public_id)
            if ami_id:
                sub_test.ami_id = ami_id
                sub_test.save()
                logger.info(f"AMI {ami_id} created for test_id {public_id}")
            else:
                logger.warning(f"Failed to create AMI for instance {test_request.instance_id}")
        except Exception as e:
            logger.warning(f"AMI creation failed for test_id {public_id}: {e}")

        # Terminate instance
        try:
            ec2.terminate_instances(InstanceIds=[test_request.instance_id])
            logger.info(f"Terminated instance {test_request.instance_id} for test_id {public_id}")
        except ClientError as e:
            logger.error(f"Failed to terminate instance {test_request.instance_id}: {e}")
            return False, f"Failed to terminate instance: {str(e)}"

        # Update test request fields
        TestRequest.objects.filter(id=test_request.id).update(
            status="terminated",
            instance_id=None,
            public_ip=None,
        )

        logger.info(f"Cleanup completed for test_id {public_id}")
        return True, "Instance stopped and cleanup completed."

    except Exception as e:
        logger.exception(f"Error stopping instance for test_id {test_request.public_id}: {e}")
        return False, f"Error stopping instance: {str(e)}"

@background(schedule=1)
def cleanup_instance_tasks(public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        
        # Terminate instance
        success, message = terminate_instance(test_request)
        if not success:
            logger.error(f"Failed to terminate instance for test_id {public_id}: {message}")
            return
    except TestRequest.DoesNotExist:
        logger.error(f"No TestRequest found for test_id {public_id}. Cleanup skipped.")
    except Exception as e:
        logger.error(f"Error during cleanup for test_id {public_id}: {e}")

def remove_guacamole_connection(instance_id):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s",
            (f"Instance {instance_id}",),
        )
        connection_id = cursor.fetchone()

        if connection_id:
            cursor.execute(
                "DELETE FROM guacamole_connection_parameter WHERE connection_id = %s",
                (connection_id,),
            )
            cursor.execute(
                "DELETE FROM guacamole_connection WHERE connection_id = %s",
                (connection_id,),
            )

        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Guacamole connection removed for instance {instance_id}.")
    except Exception as e:
        logger.error(f"Error removing Guacamole connection for instance {instance_id}: {e}")



@background(schedule=0)
def complete_instance_setup(instance_id, public_id, os_type):
    try:
        logger.info(f"[{public_id}] Starting background setup for instance {instance_id} ({os_type})")

        logger.info(f"[{public_id}] Waiting for instance to be in 'running' state with public IP...")
        public_ip = wait_for_instance(instance_id, public_id)
        if not public_ip:
            logger.error(f"[{public_id}] Instance {instance_id} failed to become ready. Terminating.")
            ec2.terminate_instances(InstanceIds=[instance_id])
            return

        logger.info(f"[{public_id}] Fetching credentials for instance {instance_id}")
        credentials = get_rdp_credentials(instance_id, os_type, public_ip=public_ip)
        if not credentials:
            logger.error(f"[{public_id}] Failed to retrieve credentials. Terminating instance.")
            ec2.terminate_instances(InstanceIds=[instance_id])
            return

        logger.info(f"[{public_id}] Retrieved credentials. Adding Guacamole connection.")
        protocol = "rdp" if os_type == "windows" else "ssh"
        port = 3389 if os_type == "windows" else 22
        connection_id = add_guacamole_connection(instance_id, protocol, port, credentials, public_id, os_type)

        logger.info(f"[{public_id}] Guacamole connection created with ID: {connection_id}")

        logger.info(f"[{public_id}] Updating database record with instance and connection info.")
        test_request = TestRequest.objects.get(public_id=public_id)
        test_request.instance_id = instance_id
        test_request.public_ip = public_ip
        test_request.status = "running"
        test_request.guacamole_connection_id = str(connection_id)
        test_request.save()

        logger.info(f"[{public_id}] Test room is now ready with instance {instance_id} and connection ID {connection_id}.")
    except Exception as e:
        logger.exception(f"[{public_id}] Background task error: {e}")