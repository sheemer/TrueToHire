import os
import logging
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils.timezone import now
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from .models import LinuxTestInstance, TestRequest
import boto3
import psycopg2
import time
import base64
from botocore.exceptions import ClientError
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import requests
import subprocess
import json
import paramiko
from background_task import background
from .tasks import cleanup_instance_tasks
from dashboard.models import SubTest  
import shlex
from utils.secrets import get_secret
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)

AWS_REGION = get_secret("AWS_REGION", "us-east-1")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"

ec2 = boto3.client("ec2", region_name=AWS_REGION)

def start_linux_instance(request, public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        existing_instance = LinuxTestInstance.objects.filter(test_request=test_request, status="running").first()

        if existing_instance:
            logger.info(f"Existing running instance found for test_id {public_id}: {existing_instance.instance_id}")
            return redirect("test_room", public_id=public_id)

        sub_tests = test_request.sub_tests.all()
        sub_test = sub_tests.first() if sub_tests.exists() else None

        if not sub_test or not sub_test.ami_id:
            raise Exception("No valid AMI ID found for the selected SubTest.")

        logger.debug(f"Starting instance for test_id {public_id} using AMI {sub_test.ami_id}")

        ami_id = sub_test.ami_id
        time_limit = sub_test.time_limit

        response = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=INSTANCE_TYPE,
            KeyName=KEY_NAME,
            SecurityGroupIds=[SECURITY_GROUP],
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": [{"Key": "TestID", "Value": str(public_id)}]},
            ],
        )
        instance_id = response["Instances"][0]["InstanceId"]
        logger.info(f"Started new instance {instance_id} for test_id {public_id}")

        if not wait_for_instance(instance_id):
            raise Exception("Instance did not become ready. Please try again later.")

        if LinuxTestInstance.objects.filter(test_request=test_request).exists():
            logger.warning(f"LinuxTestInstance already exists for test_id {public_id}, skipping creation.")
            messages.warning(request, "An instance is already registered for this test.")
            return redirect("test_room", public_id=public_id)

        linux_instance = LinuxTestInstance.objects.create(
            test_request=test_request,
            instance_id=instance_id,
            status="pending",
            start_time=now(),
            end_time=now() + timedelta(minutes=time_limit),
        )

        instance_details = ec2.describe_instances(InstanceIds=[instance_id])
        instance_ip = instance_details["Reservations"][0]["Instances"][0]["PublicIpAddress"]

        guacamole_connection_id = add_guacamole_connection(
            instance_id=instance_id,
            protocol="ssh",
            port=22,
            public_id=public_id,
            instance_ip=instance_ip,
        )

        linux_instance.guacamole_connection_id = guacamole_connection_id
        linux_instance.save()

        test_request.instance_id = instance_id
        test_request.save()

        messages.success(request, "Linux instance started successfully.")
        return redirect("test_room", public_id=public_id)

    except Exception as e:
        logger.error(f"Error starting Linux instance for test_id {public_id}: {e}")
        messages.error(request, f"Instance operation failed: {e}")
        return render(request, "linux_test_rooms/access_denied.html", {
            "message": str(e),
        })

def wait_for_instance(instance_id, max_attempts=5, delay=30):
    """
    Waits for the instance to transition to the 'running' state in AWS.
    """
    for attempt in range(max_attempts):
        try:
            instance_details = ec2.describe_instances(InstanceIds=[instance_id])
            state = instance_details["Reservations"][0]["Instances"][0]["State"]["Name"]
            if state == "running":
                logger.info(f"Instance {instance_id} is now running.")
                return True
            else:
                logger.info(f"Instance {instance_id} is in {state} state. Waiting {delay} seconds before retrying...")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}: Could not check state for instance {instance_id}. Retrying...")
        
        time.sleep(delay)
    
    logger.error(f"Instance {instance_id} did not reach 'running' state after {max_attempts} attempts.")
    return False


def execute_remote_linux_script(instance):
    """Run the remote Linux script using SSH with a private key."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        private_key = paramiko.RSAKey(filename="/path/to/private-key.pem")  # Change this to the correct path
        ssh.connect(instance.ip_address, username='ec2-user', pkey=private_key)
        stdin, stdout, stderr = ssh.exec_command(instance.sub_test.script)
        output = stdout.read().decode()
        error = stderr.read().decode()

        print(output)
        if error:
            print(f"Error: {error}")

        ssh.close()

        return 'pass' if not error else 'fail'
    except Exception as e:
        print(f"Error executing remote script: {e}")
        return 'fail'
def stop_instance(request, public_id):
    test_request = get_object_or_404(TestRequest, public_id=public_id)
    instance = get_object_or_404(LinuxTestInstance, test_request=test_request)

    sub_test = instance.test_request.sub_tests.first()  # Get the first related SubTest
    if sub_test:
        if sub_test.script and sub_test.script.strip():
            sub_test.pass_fail = execute_remote_linux_script(instance)
        else:
            sub_test.pass_fail = 'NA'
        sub_test.save()

    cleanup_instance_tasks(str(public_id))

    return render(request, "linux_test_rooms/thank_you.html")

def thank_you_view(request):
    return render(request, 'linux_test_rooms/thank_you.html')

def add_guacamole_connection(instance_id, protocol, port, public_id, instance_ip, username="ec2-user"):
    conn = None
    cursor = None
    try:
        with open("/run/secrets/windows_key", "r") as key_file:
            private_key_contents = key_file.read().strip()

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

        cursor.executemany(
            """
            INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value) 
            VALUES (%s, %s, %s)
            """,
            [
                (connection_id, "hostname", instance_ip),
                (connection_id, "port", str(port)),
                (connection_id, "username", username),
                (connection_id, "private-key", private_key_contents),
                (connection_id, "security", "any"),
                (connection_id, "ignore-cert", "true"),
                (connection_id, "enable-recording", "true"),
                (connection_id, "recording-path", "/prserver/recordings"),
                (connection_id, "recording-name", f"testid-{public_id}"),
                (connection_id, "automatically-create-recording-path", "true"),
            ]
        )

        logger.info(f"Inserted parameters for connection_id {connection_id}")
        conn.commit()
        logger.info(f"Guacamole SSH connection added for instance {instance_id} with ID {connection_id}")
        return connection_id

    except psycopg2.Error as db_error:
        logger.error(f"Database error for instance {instance_id}: {db_error}")
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error for instance {instance_id}: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_guacamole_connection_id(instance_id):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        cursor = conn.cursor()
        
        query = "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s"
        cursor.execute(query, (f"Instance {instance_id}",))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error retrieving Guacamole connection ID for instance {instance_id}: {e}")
        return None
        
def generate_guacamole_connection_identifier(connection_id, auth_provider="postgresql"):
     try:
         type_flag = "c"  # 'c' for connection
         raw_string = f"{connection_id}\0{type_flag}\0{auth_provider}"
 
         encoded_identifier = base64.b64encode(raw_string.encode("utf-8")).decode("utf-8")
 
         return encoded_identifier
 
     except Exception as e:
         logger.error(f"Error generating Guacamole connection identifier: {e}")
         return None

def generate_guacamole_token():
     guac_url = "guacamole:8080/guacamole" 
     username = get_secret("GUACAMOLE_USERNAME")  # e.g., "tim"
     password = get_secret("GUACAMOLE_PASSWORD")  # Ensure this matches
     if not all([guac_url, username, password]):
         logger.error("Missing required environment variables for Guacamole authentication.")
         raise ValueError("GUACAMOLE_SERVER, GUACAMOLE_USERNAME, or GUACAMOLE_PASSWORD is not set.")
         
     url = f"http://{guac_url}/api/tokens"
     payload = f"username={username}&password={password}"
     headers = {"Content-Type": "application/x-www-form-urlencoded"}
 
     logger.info(f"Attempting to generate token for Guacamole server at: {guac_url}")
 
     try:
         response = requests.post(url, data=payload, headers=headers)
         response.raise_for_status()
 
         # Parse the response JSON
         token = response.json().get("authToken")
         if not token:
             logger.error(f"No token found in response: {response.text}")
         return token
 
     except requests.exceptions.RequestException as e:
         logger.error(f"Request error: {e}")
     except Exception as e:
         logger.error(f"Unexpected error: {e}")
     return None
 
 


@require_GET
def guacamole_tunnel(request):
    identifier = request.GET.get("identifier")  # This is your base64 connection ID
    if not identifier:
        return HttpResponseBadRequest("Missing identifier")

    guac_api_url = "https://guac.truetohire.com/guacamole/#"
    username = get_secret("GUACAMOLE_USERNAME")  # e.g., "tim"
    password = get_secret("GUACAMOLE_PASSWORD") 
    try:
        # Step 1: Authenticate to Guacamole REST API
        auth_resp = requests.post(f"{guac_api_url}/api/tokens",  data={"username": username, "password": password})
        auth_resp.raise_for_status()
        token = auth_resp.json()["authToken"]
        # Step 2: Create a tunnel (via REST)
        tunnel_resp = requests.post(
            f"{guac_api_url}/api/session/tunnels?token={token}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"connection": encoded_identifier}
        )
        tunnel_resp.raise_for_status()
        tunnel_uuid = tunnel_resp.json()["identifier"]  
        logger.info(f"Tunnel created for {identifier} with ID {tunnel_uuid}")

        return JsonResponse({
            "guac_token": token,
            "guac_tunnel_id": tunnel_uuid,
            "guac_api_url": guac_api_url,
        })

    except Exception as e:
        logger.error(f"Failed to create Guacamole tunnel: {e}")
        return HttpResponse(status=500)



def test_room_view(request, public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        sub_tests = test_request.sub_tests.all()

        if not sub_tests.exists():
            raise ValueError(f"No SubTest found for TestRequest {public_id}. Please check your database.")

        sub_test = sub_tests.first()
        ami_id = sub_test.ami_id
        time = sub_test.time_limit
        instructions = getattr(sub_test, "instructions", "No instructions available.")

        if not ami_id:
            raise Exception("No valid AMI ID found for the selected SubTest.")

        session_key = f"failed_attempts_{str(public_id)}"

        failed_attempts = request.session.get(session_key, 0)

        # Lockout after 3 wrong attempts
        if failed_attempts >= 3:
            return render(request, "linux_test_rooms/access_denied.html", 
                          {"message": "Too many incorrect attempts. Test room access is locked."})

        if request.session.get("authenticated_test_id") != str(public_id):
            if request.method == "POST":
                if request.session.get("test_room_active", False):
                    messages.info(request, "A test room is already being set up. Please wait.")
                    return redirect("test_room", public_id=public_id)

                request.session["test_room_active"] = True
                try:
                    entered_password = request.POST.get("password")
                    participant_name = request.POST.get("name")
                    participant_email = request.POST.get("email")

                    if check_password(entered_password, test_request.password):
                        request.session["authenticated_test_id"] = str(public_id)
                        test_request.accessed_by_name = participant_name
                        test_request.accessed_by_email = participant_email
                        test_request.is_accessed = True
                        test_request.save()

                        request.session[session_key] = 0
                    else:
                        failed_attempts += 1
                        request.session[session_key] = failed_attempts
                        logger.warning(f"Failed password attempt {failed_attempts}/3 for test_id {public_id}")

                        return render(
                            request,
                            "linux_test_rooms/password_prompt.html",
                            {"test_request": test_request, "error": "Incorrect password. Please try again."},
                        )
                finally:
                    request.session["test_room_active"] = False
            else:
                return render(request, "linux_test_rooms/password_prompt.html", {"test_request": test_request})

        instance = LinuxTestInstance.objects.filter(test_request=test_request).first()

        if not instance:
            logger.info(f"No instance found for test_id {public_id}. Attempting to start a new instance.")
            try:
                response = start_linux_instance(request, public_id)
                return response
            except Exception as e:
                logger.error(f"Failed to start instance for test_id {public_id}: {e}")
                return render(
                    request,
                    "linux_test_rooms/access_denied.html",
                    {"message": "Could not start the test room. Please try again later."},
                )

        if instance.end_time < now():
            logger.info(f"Instance for test_id {public_id} has expired. Cleaning up.")
            try:
                upload_recording_to_s3(public_id)
            except Exception as e:
                logger.error(f"Error while stopping expired instance for test_id {public_id}: {e}")
            return render(
                request,
                "linux_test_rooms/access_denied.html",
                {"message": "Your session has expired. Please request a new session."},
            )

        guacamole_connection_id = get_guacamole_connection_id(instance.instance_id)
        if not guacamole_connection_id:
            logger.info(f"Creating a new Guacamole connection for instance {instance.instance_id}")
            try:
                guacamole_connection_id = add_guacamole_connection(
                    instance_id=instance.instance_id,
                    protocol="ssh",
                    port=22,
                    public_id=public_id,
                )
            except Exception as e:
                logger.error(f"Error adding Guacamole connection for instance {instance.instance_id}: {e}")
                return render(
                    request,
                    "linux_test_rooms/access_denied.html",
                    {"message": "Could not configure SSH session. Please contact support."},
                )

        guacamole_server = get_secret("GUACAMOLE_SERVER", "default-guacamole-server.com")
        guacamole_token = generate_guacamole_token()
        if not guacamole_token:
            logger.error("Failed to generate Guacamole token.")
            return render(
                request,
                "linux_test_rooms/access_denied.html",
                {"message": "Could not retrieve SSH session. Please contact support."},
            )

        encoded_identifier = generate_guacamole_connection_identifier(guacamole_connection_id)

        guac_api_url = "http://guacamole:8080/guacamole"
        guac_username = get_secret("GUACAMOLE_USERNAME")
        guac_password = get_secret("GUACAMOLE_PASSWORD")

        auth_resp = requests.post(f"{guac_api_url}/api/tokens", data={
            "username": guac_username,
            "password": guac_password
        })
        auth_resp.raise_for_status()
        token = auth_resp.json()["authToken"]

        logger.info(f"Guacamole connection encoded for iframe with ID {encoded_identifier}")

        return render(
            request,
            "linux_test_rooms/test_room.html",
            {
                "test_request": test_request,
                "instance": instance,
                "guacamole_server": guacamole_server,
                "guacamole_token": token,
                "guacamole_connection_id": encoded_identifier,
                "end_time": instance.end_time,
                "time_limit": time,
                "instructions": instructions,
            },
        )

    except Exception as e:
        logger.error(f"Error in test room view for test_id {public_id}: {e}")
        return render(
            request,
            "linux_test_rooms/access_denied.html",
            {"message": "Failed to load the test room. Please try again later."},
        )
