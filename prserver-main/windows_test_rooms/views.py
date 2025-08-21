import os
import logging
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils.timezone import now
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from .models import WindowsTestInstance, TestRequest
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
import winrm
from utils.secrets import get_secret
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.db import transaction
from django.utils import timezone
from cryptography.fernet import Fernet
import os


# Logger setup
logger = logging.getLogger(__name__)

# AWS Configuration
AWS_REGION = get_secret("AWS_REGION", "us-east-1")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

# Database Configuration
DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"



# Initialize AWS EC2 client
ec2 = boto3.client("ec2", region_name=AWS_REGION)
'''
def start_instance(request, public_id):
    try:
        # Prevent race condition with session lock
        if request.session.get("starting_instance_lock", False):
            messages.info(request, "Instance is already being created, please wait...")
            return redirect("windows_test_room", public_id=public_id)

        # Set the session lock
        request.session["starting_instance_lock"] = True

        # Fetch the TestRequest
        test_request = TestRequest.objects.get(public_id=public_id)

        # Don't create a new instance if one already exists
        if WindowsTestInstance.objects.filter(test_request=test_request).exists():
            logger.info(f"Instance already exists for test_id {public_id}, skipping new launch.")
            return redirect("windows_test_room", public_id=public_id)

        # Fetch first SubTest
        sub_tests = test_request.sub_tests.all()
        sub_test = sub_tests.first() if sub_tests.exists() else None

        if not sub_test:
            raise Exception("No SubTest found for this TestRequest.")

        print(f"[DEBUG] Starting instance for test_id {public_id}")
        print(f"[DEBUG] SubTest: {sub_test.name}")
        print(f"[DEBUG] AMI ID: {sub_test.ami_id}")
        print(f"[DEBUG] OS Type: {sub_test.os_type}")

        ami_id = sub_test.ami_id
        time = sub_test.time_limit

        if not ami_id:
            raise Exception("No valid AMI ID found for the selected SubTest.")

        # Launch a new EC2 instance
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

        # Wait until instance is ready
        if not wait_for_instance(request, instance_id, public_id):
            raise Exception("Instance did not become ready. Please try again later.")

        # Save the instance record
        WindowsTestInstance.objects.create(
            test_request=test_request,
            instance_id=instance_id,
            status="pending",
            start_time=now(),
            end_time=now() + timedelta(minutes=time),
        )

        # Retrieve credentials
        logger.info(f"Retrieving RDP credentials for instance {instance_id}")
        rdp_credentials = get_rdp_credentials(instance_id)

        if not rdp_credentials:
            logger.error(f"Failed to retrieve RDP credentials. Terminating instance {instance_id}.")
            ec2.terminate_instances(InstanceIds=[instance_id])
            raise Exception("Instance initialization failed. Please try again later.")

        # Add Guacamole connection
        guacamole_connection_id = add_guacamole_connection(instance_id, "rdp", 3389, rdp_credentials, public_id)

        # Save instance and connection info to TestRequest
        test_request.instance_id = instance_id
        test_request.guacamole_connection_id = guacamole_connection_id
        test_request.save()

        messages.success(request, "Instance started successfully.")

        # Redirect to the appropriate test room
        if sub_test.os_type == "windows":
            return redirect("windows_test_room", public_id=public_id)
        elif sub_test.os_type == "linux":
            return redirect("linux_test_room", public_id=public_id)

    except Exception as e:
        logger.error(f"Error starting instance for test_id {public_id}: {e}")
        messages.error(request, f"Instance operation failed: {e}")
        return render(request, "windows_test_rooms/access_denied.html", {"message": str(e)})

    finally:
        # Always release the session lock
        request.session["starting_instance_lock"] = False
'''


def start_instance(request, public_id):
    try:
        # Fetch the TestRequest
        test_request = TestRequest.objects.get(public_id=public_id)

        # Ensure the TestRequest has at least one SubTest linked
        sub_tests = test_request.sub_tests.all()
        sub_test = sub_tests.first() if sub_tests.exists() else None
        
        print(f"[DEBUG] Starting instance for test_id {public_id}")
        print(f"[DEBUG] SubTest: {sub_test.name if sub_test else 'None'}")
        print(f"[DEBUG] AMI ID: {sub_test.ami_id if sub_test else 'None'}")
        print(f"[DEBUG] OS Type: {sub_test.os_type if hasattr(sub_test, 'os_type') else 'Unknown'}")

        ami_id = sub_test.ami_id
        time = sub_test.time_limit

        if not ami_id:
            raise Exception("No valid AMI ID found for the selected SubTest.")

        # Launch a new instance
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

        if not wait_for_instance(request, instance_id, public_id):
            raise Exception("Instance did not become ready. Please try again later.")
        # Save instance details
        WindowsTestInstance.objects.create(
            test_request=test_request,
            instance_id=instance_id,
            status="pending",
            start_time=now(),
            end_time=now() + timedelta(minutes=time),
        )

        # Retrieve RDP credentials
        logger.info(f"Retrieving RDP credentials for instance {instance_id}.")
        rdp_credentials = get_rdp_credentials(instance_id)

        if not rdp_credentials:
            logger.error(f"Failed to retrieve RDP credentials for instance {instance_id}. Terminating instance.")
            ec2.terminate_instances(InstanceIds=[instance_id])
            raise Exception("Instance initialization failed. Please try again later.")

        # Add Guacamole connection
        guacamole_connection_id = add_guacamole_connection(instance_id, "rdp", 3389, rdp_credentials, public_id)

        # Update TestRequest with instance details
        test_request.instance_id = instance_id
        test_request.guacamole_connection_id = guacamole_connection_id
        test_request.save()

        messages.success(request, "Instance started successfully.")
        if sub_test.os_type == "windows":
            return redirect("windows_test_room", public_id=public_id)  
        elif sub_test.os_type == "linux":
            return redirect("linux_test_room",public_id=public_id)

    except Exception as e:
        logger.error(f"Error starting instance for test_id {public_id}: {e}")
        messages.error(request, f"Instance operation failed: {e}")
        return render(request, "windows_test_rooms/access_denied.html", {"message": str(e)})




def get_rdp_credentials(instance_id, retries=10, delay=20):
    """Retries fetching public IP and static credentials"""
    for attempt in range(retries):
        try:
            instance_details = ec2.describe_instances(InstanceIds=[instance_id])
            state = instance_details["Reservations"][0]["Instances"][0]["State"]["Name"]
            public_ip = instance_details["Reservations"][0]["Instances"][0].get("PublicIpAddress")

            if state != "running":
                logger.warning(f"⏳ Instance {instance_id} is {state}. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue

            if not public_ip:
                logger.warning(f"⚠️ No Public IP yet. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue

            username = "Administrator"
            fernet = Fernet(os.environ["RDP_ENCRYPTION_KEY"])

            # Decrypt stored password
            decrypted_password = fernet.decrypt(test_request.rdp_password.encode()).decode()

            return {
                "username": username,
                "password": decrypted_password,
                "ip_address": public_ip
            }
        except Exception as e:
            logger.error(f"⚠️ Error retrieving RDP credentials for {instance_id}: {e}")
            time.sleep(delay)

    logger.error(f"❌ Failed to retrieve RDP credentials for {instance_id} after multiple attempts.")
    return None
    

def wait_for_instance(request, instance_id, public_id, max_attempts=10, delay=30, timeout=300):
    """
    Waits for the EC2 instance to become 'running'. Timeout defaults to 5 minutes.
    """
    start_time = time.time()

    for attempt in range(max_attempts):
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.error(f"⏳ Timeout! Instance {instance_id} didn't start within {timeout} seconds.")
            return False

        try:
            instance_details = ec2.describe_instances(InstanceIds=[instance_id])
            state = instance_details["Reservations"][0]["Instances"][0]["State"]["Name"]

            if state == "running":
                logger.info(f"✅ Instance {instance_id} is now running.")
                return True  
            
            logger.info(f"⏳ Attempt {attempt + 1}: Instance {instance_id} is {state}. Waiting {delay} seconds...")
        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt + 1}: Could not retrieve instance {instance_id}. Retrying... Error: {e}")

        time.sleep(delay)

    logger.error(f"❌ Instance {instance_id} did not become available after {max_attempts * delay} seconds.")
    return False


def execute_remote_windows_script(instance):
    """Run the remote PowerShell script on the Windows machine using WinRM."""
    try:
        session = winrm.Session(instance.ip_address, auth=('Administrator', instance.private_key), transport='ntlm')
        response = session.run_ps(instance.sub_test.script)
        print(response.std_out.decode())
        return 'pass' if response.status_code == 0 else 'fail'
    except Exception as e:
        print(f"Error executing remote script: {e}")
        return 'fail'


def windows_stop_instance(request, public_id):
    test_request = get_object_or_404(TestRequest, public_id=public_id)
    instance = get_object_or_404(WindowsTestInstance, test_request=test_request)

    sub_test = instance.sub_tests.first()  # Get SubTest
    if sub_test:
        if sub_test.script and sub_test.script.strip():
            sub_test.pass_fail = execute_remote_linux_script(instance)
        else:
            sub_test.pass_fail = 'NA'
        sub_test.save()


    # Schedule cleanup tasks asynchronously
    cleanup_instance_tasks(str(public_id))
    return render(request, "windows_test_rooms/thank_you.html")

def thank_you_view(request):
    return render(request, 'windows_test_rooms/thank_you.html')


def add_guacamole_connection(instance_id, protocol, port, rdp_credentials, public_id):
    """
    Adds a Guacamole connection for the specified EC2 instance with session recording enabled.
    """
    try:
        instance_ip = rdp_credentials["ip_address"]
        username = rdp_credentials["username"]
        password = rdp_credentials["password"]

        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        cursor = conn.cursor()
        # Insert connection details into Guacamole and get the connection_id
        cursor.execute(
            """
            INSERT INTO guacamole_connection (connection_name, protocol)
            VALUES (%s, %s)
            RETURNING connection_id
            """,
            (f"Instance {instance_id}", protocol)
        )
        connection_id = cursor.fetchone()[0]

        # Insert hostname, port, username, and password parameters
        cursor.executemany(
            """
            INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value) 
            VALUES (%s, %s, %s)
            """,
            [
                (connection_id, "hostname", instance_ip),
                (connection_id, "port", str(port)),
                (connection_id, "username", username),
                (connection_id, "password", password),
                (connection_id, "security", "any"),
                (connection_id, "ignore-cert", "true"),
                (connection_id, "enable-recording", "true"),
                (connection_id, "recording-path", "/prserver/recordings"),
                (connection_id, "recording-name", f"testid-{public_id}"),
                (connection_id, "automatically-create-recording-path", "true"),
            ],
        )

        # Commit and close the connection
        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"Guacamole connection added for instance {instance_id} with ID {connection_id}.")
        return connection_id  # Explicitly return connection_id

    except Exception as e:
        logger.error(f"Error adding Guacamole connection for instance {instance_id}: {e}")
        raise


def get_guacamole_connection_id(instance_id):
    """
    Retrieve the Guacamole connection ID for a given instance ID.
    """
    try:
                # Establish a connection to the Guacamole database
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        cursor = conn.cursor()
        
        # Query the database for the connection ID
        query = "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s"
        cursor.execute(query, (f"Instance {instance_id}",))
        result = cursor.fetchone()
        
        # Close the connection
        cursor.close()
        conn.close()
        
        # Return the connection ID if found
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error retrieving Guacamole connection ID for instance {instance_id}: {e}")
        return None


def generate_guacamole_connection_identifier(connection_id, auth_provider="postgresql"):
     try:
         # Prepare the components
         type_flag = "c"  # 'c' for connection
         raw_string = f"{connection_id}\0{type_flag}\0{auth_provider}"
 
         # Encode the components in Base64
         encoded_identifier = base64.b64encode(raw_string.encode("utf-8")).decode("utf-8")
 
         return encoded_identifier
 
     except Exception as e:
         logger.error(f"Error generating Guacamole connection identifier: {e}")
         return None
 
def generate_guacamole_token():
     """
     Generates an authentication token for Guacamole using provided credentials.
     """
     guac_url = "guacamole:8080/guacamole" 
     username = get_secret("GUACAMOLE_USERNAME")  # e.g., "tim"
     password = get_secret("GUACAMOLE_PASSWORD")  # Ensure this matches
     # Ensure all environment variables are set
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

def windows_test_room_view(request, public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        sub_tests = test_request.sub_tests.all()

        if not sub_tests.exists():
            raise ValueError(f"No SubTest found for TestRequest {public_id}")

        sub_test = sub_tests.first()
        ami_id = sub_test.ami_id
        time = sub_test.time_limit
        instructions = getattr(sub_test, "instructions", "No instructions available.")

        if not ami_id:
            raise Exception("No valid AMI ID found.")

        failed_attempts_key = f'failed_attempts_test_{str(public_id)}'
        failed_attempts = request.session.get(failed_attempts_key, 0)

        if failed_attempts >= 3:
            return render(request, "windows_test_rooms/access_denied.html", {
                "message": "Too many incorrect attempts. Test room is now locked."
            })

        if request.session.get("authenticated_test_id") != str(public_id):
            if request.method == "POST":
                if request.session.get("windows_test_room_active", False):
                    messages.info(request, "A test room is already being set up.")
                    return redirect("windows_test_room", public_id=public_id)

                request.session["windows_test_room_active"] = True
                try:
                    entered_password = request.POST.get("password")
                    if check_password(entered_password, test_request.password):
                        request.session["authenticated_test_id"] = str(public_id)
                        test_request.accessed_by_name = request.POST.get("name")
                        test_request.accessed_by_email = request.POST.get("email")
                        test_request.is_accessed = True
                        test_request.save()
                        request.session.pop(failed_attempts_key, None)
                    else:
                        request.session[failed_attempts_key] = failed_attempts + 1
                        return render(request, "windows_test_rooms/password_prompt.html", {
                            "test_request": test_request,
                            "error": "Incorrect password. Please try again.",
                        })
                finally:
                    request.session["windows_test_room_active"] = False
            else:
                return render(request, "windows_test_rooms/password_prompt.html", {
                    "test_request": test_request
                })

        # 🔒 Use transaction to avoid race condition
        with transaction.atomic():
            instance = WindowsTestInstance.objects.select_for_update().filter(test_request=test_request).first()

            if not instance:
                logger.info(f"No instance found for test_id {public_id}. Launching...")
                return start_instance(request, public_id)  # Assumes this view ends after this

        # 🧠 At this point instance must be valid
        if not instance or not instance.instance_id:
            raise Exception("WindowsTestInstance exists but instance_id is missing.")

        guacamole_server = get_secret("GUACAMOLE_SERVER", "default-guacamole-server.com")
        guacamole_token = generate_guacamole_token()
        if not guacamole_token:
            return render(request, "windows_test_rooms/access_denied.html", {
                "message": "Could not retrieve RDP session."
            })

        guac_conn_id = get_guacamole_connection_id(instance.instance_id)
        encoded_id = generate_guacamole_connection_identifier(guac_conn_id)

        guac_api_url = "http://guacamole:8080/guacamole"
        guac_username = get_secret("GUACAMOLE_USERNAME")
        guac_password = get_secret("GUACAMOLE_PASSWORD")

        auth_resp = requests.post(f"{guac_api_url}/api/tokens", data={
            "username": guac_username,
            "password": guac_password
        })
        auth_resp.raise_for_status()
        token = auth_resp.json()["authToken"]

        response = render(request, "windows_test_rooms/test_room.html", {
            "test_request": test_request,
            "instance": instance,
            "guacamole_server": guacamole_server,
            "guacamole_token": token,
            "guacamole_connection_id": encoded_id,
            "end_time": instance.end_time,
            "time_limit": time,
            "instructions": instructions,
        })
        response.set_cookie(
            key="GUAC_AUTH",
            value=token,
            httponly=True,
            secure=True,
            domain=".truetohire.com",
            path="/guacamole",
        )
        return response

    except Exception as e:
        logger.error(f"Error in test room view for test_id {public_id}: {e}")
        return render(request, "windows_test_rooms/access_denied.html", {
            "message": "Failed to load the test room."
        })