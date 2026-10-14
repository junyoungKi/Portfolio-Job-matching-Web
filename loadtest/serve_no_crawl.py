"""
Start the backend for a load test with the LinkedIn crawl turned into a no-op.

``app.main`` schedules a crawl 5 seconds after startup. During a load test that would launch
Chromium and scrape the live site, which both skews the numbers and hits LinkedIn. This wrapper
replaces the scraper with a stub that returns no jobs and then starts uvicorn, without touching
any application file, so it works identically on the baseline commit and on the fixed commit.

Run it from the checkout you want to test (the ``app`` package is imported from the current
directory), keeping this script from the fixed checkout:

    cd ../jm-baseline && PYTHONPATH=. python /path/to/fixed/loadtest/serve_no_crawl.py --port 8000
"""
import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

import uvicorn  # noqa: E402

from app.main import app, job_collector  # noqa: E402


async def _no_crawl(*args, **kwargs):
    return []


job_collector.scrape_linkedin = _no_crawl

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()
    print(f"[loadtest] serving {os.getcwd()} with the crawl disabled")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
