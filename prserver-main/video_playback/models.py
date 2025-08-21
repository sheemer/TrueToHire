from django.db import models

class RecordedSession(models.Model):
    test_id = models.CharField(max_length=100, unique=True)
    video_path = models.CharField(max_length=500)  # Path to the saved video
    video_path = models.CharField(max_length=500)  # Path to the video file on the server
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.test_id}"