"""
Author: Joonyoung Ki

Locust load-test definition for the Smart Job AI API.

Simulates users that poll ``/stats`` (database read) and upload a resume to ``/process-resume``
(file I/O plus AI analysis, the expected bottleneck). Run it with ``locust -f locustfile.py``.
"""
import os
from locust import HttpUser, task, between

class SmartJobUser(HttpUser):
    """Virtual user that mixes lightweight stats reads with heavier resume uploads."""

    # Wait time between tasks for each virtual user (random between 1 and 3 seconds)
    wait_time = between(1, 3)

    @task(2) # Task weight: Higher number means higher execution frequency (reads stats more frequently)
    def check_stats(self):
        """DB Communication Load Test: Retrieve count of stored job postings"""
        self.client.get("/stats")

    @task(1)
    def upload_resume(self):
        """
        File I/O and AI analysis load test (expected primary bottleneck).
        Uploads a resume and requests matching results.
        """
        file_path = "test_resume.pdf"
        
        # Create a temporary PDF file for testing if it does not exist (to prevent errors)
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(b"%PDF-1.4 Dummy PDF Content for Load Testing")

        with open(file_path, "rb") as f:
            # Send data matched to the /process-resume endpoint structure in main.py
            self.client.post(
                "/process-resume",
                params={
                    "keyword": "Software Engineer", 
                    "location": "North America"
                },
                files={"file": ("test_resume.pdf", f, "application/pdf")}
            )