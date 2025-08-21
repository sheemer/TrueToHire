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
from .forms import TestTypeSubTestForm  # Assumes you have a form for TestType/SubTest creation
from dashboard.models import TestRequest, TestType, SubTest
import winrm
import paramiko
from utils.secrets import get_secret
from django.views.decorators.http import require_GET
from accounts.models import CustomUser, Company
from datetime import datetime, timedelta
from .tasks import cleanup_instance_tasks
from .tasks import complete_instance_setup
from django.http import HttpResponseNotFound
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from .utils import wait_for_instance, add_guacamole_connection, get_rdp_credentials, decrypt_password , get_instance_ip
from background_task import background

logger = logging.getLogger(__name__)

AWS_REGION = get_secret("AWS_REGION", "us-east-1")
INSTANCE_TYPE = get_secret("INSTANCE_TYPE", "t2.micro")
KEY_NAME = get_secret("KEY_NAME")
SECURITY_GROUP = get_secret("SECURITY_GROUP")

DB_HOST = "db"
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("postgres_password")
DB_NAME = get_secret("DB_NAME")
DB_PORT = "5432"

ec2 = boto3.client("ec2", region_name=AWS_REGION)

@login_required
def custom_image_home(request):
    try:
        test_types = TestType.objects.filter(created_by=request.user) | TestType.objects.filter(is_public=True)
        sub_tests = SubTest.objects.filter(created_by=request.user) | SubTest.objects.filter(is_public=True)
        test_requests = TestRequest.objects.filter(created_by=request.user)
        return render(request, 'customimage/home.html', {
            'test_types': test_types,
            'sub_tests': sub_tests,
            'test_requests': test_requests
        })
    except Exception as e:
        logger.error(f"Error in custom_image_home for user {request.user.username}: {e}")
        messages.error(request, "Failed to load test data. Please try again.")
        return render(request, 'customimage/home.html', {
            'test_types': [],
            'sub_tests': [],
            'test_requests': []
        })


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
        auth_resp = requests.post(f"{guac_api_url}/api/tokens",  data={"username": username, "password": password})
        auth_resp.raise_for_status()
        token = auth_resp.json()["authToken"]
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

def execute_remote_windows_script(sub_test, public_ip):
    """
    Run a PowerShell script on a Windows instance using WinRM.
    """
    try:
        session = winrm.Session(public_ip, auth=('Administrator', get_secret("AMI_WIN_PASS", "DefaultWindowsPass")), transport='ntlm')
        response = session.run_ps(sub_test.script)
        logger.info(f"Windows script output: {response.std_out.decode()}")
        return 'pass' if response.status_code == 0 else 'fail'
    except Exception as e:
        logger.error(f"Error executing Windows script: {e}")
        return 'fail'

def execute_remote_linux_script(sub_test, public_ip):
    """
    Run a script on a Linux instance using SSH.
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(public_ip, username='ec2-user', password=get_secret("AMI_LINUX_PASS", "DefaultLinuxPass"))
        stdin, stdout, stderr = client.exec_command(sub_test.script)
        output = stdout.read().decode()
        error = stderr.read().decode()
        logger.info(f"Linux script output: {output}")
        if error:
            logger.error(f"Linux script error: {error}")
        return 'pass' if not error else 'fail'
    except Exception as e:
        logger.error(f"Error executing Linux script: {e}")
        return 'fail'

def create_ami(instance_id, public_id):
    """
    Create an AMI from the specified EC2 instance.
    """
    try:
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        ami_name = f"test-{public_id}-{timestamp}"
        response = ec2.create_image(
            InstanceId=instance_id,
            Name=ami_name,
            Description=f"AMI created for test {public_id}",
            NoReboot=True
        )
        ami_id = response['ImageId']
        logger.info(f"Created AMI {ami_id} for instance {instance_id}")

        waiter = ec2.get_waiter('image_available')
        waiter.wait(ImageIds=[ami_id])
        logger.info(f"AMI {ami_id} is now available")
        return ami_id
    except Exception as e:
        logger.error(f"Error creating AMI for instance {instance_id}: {e}")
        return None

def start_instance(request, public_id):
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        if test_request.instance_id:
            logger.info(f"Instance {test_request.instance_id} already running for test_id {public_id}")
            response = ec2.describe_instances(InstanceIds=[test_request.instance_id])
            state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
            if state in ["running", "pending"]:
                messages.info(request, f"Instance already running for test {public_id}.")
                return redirect("view_test_room", public_id=public_id)
            else:
                test_request.instance_id = None
                test_request.public_ip = None
                test_request.status = "pending"
                test_request.guacamole_connection_id = None
                test_request.save()

        sub_tests = test_request.sub_tests.all()
        sub_test = sub_tests.first() if sub_tests.exists() else None

        if not sub_test:
            raise Exception("No SubTest found for this TestRequest.")

        ami_id = sub_test.ami_id
        os_type = sub_test.os_type.lower()

        if not ami_id:
            raise Exception(f"No AMI ID configured for {os_type}.")

        logger.info(f"Launching {os_type.upper()} instance for test_id {public_id}")

        response = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=INSTANCE_TYPE,
            KeyName=KEY_NAME,
            SecurityGroupIds=[SECURITY_GROUP],
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "TestID", "Value": str(public_id)},
                    {"Key": "Name", "Value": sub_test.name}
                ]
            }],
        )
        instance_id = response["Instances"][0]["InstanceId"]
        logger.info(f"Started instance {instance_id} for test_id {public_id}")

        public_ip = wait_for_instance(instance_id, public_id)
        if not public_ip:
            ec2.terminate_instances(InstanceIds=[instance_id])
            raise Exception("Instance did not become ready.")
        logger.info(f"Waiting 30 seconds for instance {instance_id} to finish setup.")
        setup_wait_time = 55 if os_type == "windows" else 30
        if os_type == "windows":
            logger.info(f"Queuing background setup for instance {instance_id} / {public_id}")
            complete_instance_setup(instance_id, public_id, os_type)

            return render(request, "customimage/loading_and_redirect.html", {"public_id": public_id})

        logger.info(f"Waiting {setup_wait_time} seconds for {os_type} instance {instance_id} to finish setup.")
        time.sleep(setup_wait_time)

        credentials = get_rdp_credentials(instance_id, os_type, public_ip=public_ip)
        if not credentials:
            ec2.terminate_instances(InstanceIds=[instance_id])
            raise Exception("Failed to retrieve credentials.")

        protocol = "rdp" if os_type == "windows" else "ssh"
        port = 3389 if os_type == "windows" else 22
        connection_id = add_guacamole_connection(instance_id, protocol, port, credentials, public_id, os_type)

        test_request.instance_id = instance_id
        test_request.public_ip = public_ip
        test_request.status = "running"
        test_request.guacamole_connection_id = str(connection_id)
        test_request.save()

        messages.success(request, f"{os_type.capitalize()} instance started successfully.")
        return redirect("view_test_room", public_id=public_id)
    except Exception as e:
        logger.error(f"Error starting instance for test_id {public_id}: {e}")
        messages.error(request, f"Instance operation failed: {e}")
        return render(request, "customimage/error.html", {"message": str(e)})

@login_required
def create_and_launch_test(request):
    """
    Create a TestType, SubTest, and TestRequest, then launch an EC2 instance.
    """
    if request.method == 'POST':
        form = TestTypeSubTestForm(request.POST)
        if form.is_valid():
            try:
                public_id = str(uuid.uuid4())

                test_type = form.cleaned_data['test_type_name'] 
                sub_test = SubTest.objects.create(
                    name=form.cleaned_data['sub_test_name'],
                    test_type=test_type,
                    created_by=request.user,
                    is_public=form.cleaned_data['is_public'],
                    ami_id=form.cleaned_data['ami_id'],
                    details=form.cleaned_data['details'],
                    instructions=form.cleaned_data['instructions'],
                    time_limit=form.cleaned_data['time_limit'],
                    os_type=form.cleaned_data['os_type'],
                    script=form.cleaned_data['script']

                )

                test_request = TestRequest.objects.create(
                    public_id=public_id,
                    title=form.cleaned_data['sub_test_name'],
                    test_type=test_type,
                    password=make_password(form.cleaned_data['password']) if form.cleaned_data['password'] else '',
                    created_by=request.user,
                    company=request.user.company
                )
                test_request.sub_tests.add(sub_test)

                return start_instance(request, public_id)
            except Exception as e:
                logger.exception(f"Failed to create test or launch instance for user {request.user.username}: {e}")
                messages.error(request, f"Error: {str(e)}")
                return render(request, "customimage/error.html", {"message": str(e)})
        else:
            messages.error(request, "Invalid form submission.")
    else:
        form = TestTypeSubTestForm()

    return render(request, "customimage/create_test.html", {"form": form})

@login_required
def view_test_room(request, public_id):
    """
    View an existing test room for a TestRequest, with password authentication.
    """
    try:
        test_request = TestRequest.objects.get(public_id=public_id)
        sub_tests = test_request.sub_tests.all()
        sub_test = sub_tests.first()

        if not sub_test:
            messages.error(request, "No subtest found for this test session.")
            return redirect('custom_image_home')

        failed_attempts_key = f'failed_attempts_test_{public_id}'
        failed_attempts = request.session.get(failed_attempts_key, 0)

        if failed_attempts >= 3:
            return render(request, "customimage/error.html", {
                "message": "Too many incorrect attempts. Test room is locked."
            })

        if request.session.get("authenticated_test_id") != str(public_id) and test_request.created_by != request.user:
            if request.method == "POST":
                if request.session.get("test_room_active", False):
                    messages.info(request, "A test room is already being set up.")
                    return redirect("view_test_room", public_id=public_id)

                request.session["test_room_active"] = True
                try:
                    entered_password = request.POST.get("password")
                    if not test_request.password or check_password(entered_password, test_request.password):
                        request.session["authenticated_test_id"] = str(public_id)
                        test_request.accessed_by_name = request.POST.get("name")
                        test_request.accessed_by_email = request.POST.get("email")
                        test_request.is_accessed = True
                        test_request.save()
                        request.session.pop(failed_attempts_key, None)
                    else:
                        request.session[failed_attempts_key] = failed_attempts + 1
                        return render(request, "customimage/password_prompt.html", {
                            "test_request": test_request,
                            "error": "Incorrect password. Please try again."
                        })
                finally:
                    request.session["test_room_active"] = False
            else:
                return render(request, "customimage/password_prompt.html", {
                    "test_request": test_request
                })
        instance = TestRequest.objects.filter(public_id=public_id).first()
        if not instance:
            logger.info(f"No instance found for test_id {public_id}. Starting new instance.")
            return start_instance(request, public_id)

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

        response = render(request, "customimage/test_room.html", {
            "test_request": test_request,
            "sub_test": sub_test,
            "instance": instance,
            "guacamole_server": guacamole_server,
            "guacamole_token": token,
            "guacamole_connection_id": encoded_id,
            "instance_id": test_request.instance_id,
            "public_ip": test_request.public_ip,
        })

        response.set_cookie(
            key="GUAC_AUTH",
            value=token,
            httponly=True,
            secure=True,
            domain=".truetohire.com",
            path="/guacamole"
        )

        return response
    except TestRequest.DoesNotExist:
        messages.error(request, "Test session not found.")
        return redirect('custom_image_home')
    except Exception as e:
        logger.error(f"Error in test room view for test_id {public_id}: {e}")
        return render(request, "customimage/error.html", {
            "message": f"Failed to load test room: {str(e)}"
        })
        
@login_required
def stop_instances(request, public_id):
    test_request = None

    try:
        test_request = TestRequest.objects.filter(public_id=public_id).first()

        if test_request:
            logger.info(f"Found TestRequest for public_id {public_id}. Dispatching cleanup task.")
            cleanup_instance_tasks(str(public_id))  # Assumes this is an async task
        else:
            logger.warning(f"No TestRequest found for public_id {public_id}. Skipping cleanup task.")
    except Exception as e:
        logger.exception(f"Error during stop_instance for public_id {public_id}: {e}")

    return render(request, "customimage/thank_you.html", {
        "test_request": test_request  # Can be None; handle accordingly in template
    })

def thank_you_view(request):
    return render(request, 'customimage/thank_you.html')
