import logging
import boto3
from background_task import background
from .models import LinuxTestInstance, TestRequest
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
import os
import paramiko
from utils.secrets import get_secret
import subprocess
import psycopg2


logger = logging.getLogger(__name__)
AWS_REGION = get_secret("AWS_REGION", "us-east-1")
AMI_ID = get_secret("AMI_ID")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"



def terminate_instance(instance):
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)  # Use the configured region
        ec2.terminate_instances(InstanceIds=[instance.instance_id])
        instance.status = "terminated"
        instance.save()
        logger.info(f"Terminated EC2 instance: {instance.instance_id}")
    except Exception as e:
        logger.error(f"Failed to terminate instance {instance.instance_id}: {e}")
        raise

@background(schedule=1)
def cleanup_instance_tasks(public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        instance = LinuxTestInstance.objects.get(test_request=test_request)
        
        terminate_instance(instance)

        if instance.guacamole_connection_id:
            remove_guacamole_connection(instance.guacamole_connection_id)

        if upload_recording_to_s3(public_id):
            logger.info(f"Recording for public_id {public_id} uploaded successfully.")
        else:
            logger.warning(f"Recording upload for public_id {public_id} failed.")

    except ObjectDoesNotExist:
        logger.error(f"No instance found for public_id {public_id}. Cleanup skipped.")
    except Exception as e:
        logger.error(f"Error during cleanup for public_id {public_id}: {e}")

        
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

def get_container_id(container_name):
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get container ID for {container_name}: {e.stderr}")
        return None

def upload_recording_to_s3(public_id):
    container_id = get_container_id("custom-guac-recorder")

    if not container_id:
        logger.error("No running container found for custom-guac-recorder")
        return False

    try:
        logger.info(f"Executing upload script for public_id {public_id} in {container_id}.")

        result = subprocess.run(
            ["docker", "exec", container_id, "bash", "-c", f"/usr/local/bin/upload_script.sh {public_id}"],
            capture_output=True, text=True, check=True
        )

        if result.stdout:
            logger.info(f"Script output: {result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"Script error output: {result.stderr.strip()}")

        logger.info(f"Upload for {public_id} executed successfully.")

        # Update TestRequest with recording path
        try:
            test_request = TestRequest.objects.get(public_id=public_id)
            test_request.recorded_session = f"recordings/testid-{public_id}.mp4"
            test_request.save()
            logger.info(f"Recording path updated for public_id {public_id}.")
        except ObjectDoesNotExist:
            logger.error(f"TestRequest with public_id {public_id} not found. Could not update recorded session.")

        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Upload script failed for public_id {public_id}: {e.stderr}")
        return False
