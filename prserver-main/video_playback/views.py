from django.shortcuts import render, get_object_or_404
from .models import RecordedSession
from django.contrib.auth.decorators import login_required
from django.http import Http404
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import logging
from django.conf import settings
import os
from django.http import JsonResponse
from botocore.exceptions import ClientError
from utils.secrets import get_secret
from django.core.exceptions import PermissionDenied



logger = logging.getLogger(__name__)

@login_required
def play_video(request, public_id):
    """
    Render the video playback page with the S3 pre-signed video URL for a given session.
    """
    # Generate S3 presigned URL
    #s3_client = boto3.client('s3', region_name=AWS_REGION)
    video_location = f"recordings/{public_id}.mp4"

    # Check if file exists in S3
    try:

     '''   s3_client.head_object(Bucket=AWS_S3_BUCKET_NAME, Key=s3_key)
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            error_message = f"Video file {test_id}.mp4 not found in S3."
        else:
            error_message = f"Error checking video file: {e}"
        return render(request, 'video_playback/play_video.html', {
            "test_id": public_id,
            "error": error_message
        })'''

    # Generate 
'''   try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': AWS_S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=3600  # URL valid for 1 hour
        )
    except ClientError as e:
        error_message = f"Could not generate a video URL for test ID {public_id}: {e}"
        return render(request, 'video_playback/play_video.html', {
            "test_id": public_id,
            "error": error_message,
        })'''
