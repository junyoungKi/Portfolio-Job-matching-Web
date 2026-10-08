"""
Author: Joonyoung Ki

Concurrency smoke test for the ``/process-resume`` endpoint.

Fires many simultaneous resume uploads at a locally running server to check that the semaphore
and temp-file handling in the API stay stable under load, then prints how many succeeded.
Run it with ``python test_concurrent.py`` while the server is running.
"""
import asyncio
import httpx

URL = "http://127.0.0.1:8000/process-resume"
FILE_PATH = "test_resume.pdf"  # Test PDF file located in the project folder

async def send_request(client, request_id):
    """Upload the test PDF once and return the HTTP status code, or None if the request failed."""
    print(f"[Request {request_id}] Sending")
    try:
        with open(FILE_PATH, "rb") as f:
            files = {"file": (FILE_PATH, f, "application/pdf")}
            params = {"location": "North America"}
            response = await client.post(URL, files=files, params=params, timeout=30.0)
            print(f"[Response {request_id}] Status: {response.status_code}")
            return response.status_code
    except Exception as e:
        print(f"[Error {request_id}] {e}")
        return None

async def main():
    """Run all uploads concurrently and print a success summary."""
    # Create concurrent requests (verifies behavior beyond the existing limit of 10)
    async with httpx.AsyncClient() as client:
        tasks = [send_request(client, i) for i in range(1, 100)]
        results = await asyncio.gather(*tasks)
        print(f"\nCompleted {len(results)} requests in total (successful: {results.count(200)})")

if __name__ == "__main__":
    asyncio.run(main())