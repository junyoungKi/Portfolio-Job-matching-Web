"""
Author: Joonyoung Ki

Locust load-test definition for the Smart Job AI API.

Covers all three endpoints:
    - ``GET /stats``                (cheap DB read)
    - ``POST /process-resume``      (PDF parse, embedding, DB write; varied resumes)
    - ``GET /match/{resume_id}``    (vector search, LLM re-rank, 10 bilingual LLM analyses, Redis cache)

How the run is shaped is controlled with environment variables (all optional):

    LOAD_MODE         warm (default) or cold.
                      warm: every user uploads one resume from a fixed, deterministic pool and then
                            repeats /match with a small set of filter combinations, so after the
                            first pass most requests are served from Redis / stored analyses.
                      cold: every /match runs on a brand-new resume (a unique upload first), so
                            each one misses Redis and has no stored analyses and exercises the full
                            LLM pipeline. The setup upload is reported as its own row; read the
                            "(cold)" /match row for the cold /match numbers.
    RESUME_POOL_SIZE  number of distinct resumes in the warm pool (default 20)
    LOCUST_SEED       seed for resume content and per-user choices (default 1234)
    WAIT_MIN/WAIT_MAX think time between tasks in seconds (default 1 and 3)

See docs/load-testing.md for the full before/after procedure. Run it with, for example:

    locust -f locustfile.py --headless --host http://127.0.0.1:8000 -u 20 -r 2 -t 5m
"""
import os
import random
import uuid

from locust import HttpUser, between, task

try:
    import pymupdf
except ImportError:  # older PyMuPDF releases only expose the ``fitz`` name
    import fitz as pymupdf

MODE = os.getenv("LOAD_MODE", "warm").strip().lower()
if MODE not in ("warm", "cold"):
    raise SystemExit(f"LOAD_MODE must be 'warm' or 'cold', got {MODE!r}")

SEED = os.getenv("LOCUST_SEED", "1234")
POOL_SIZE = max(1, int(os.getenv("RESUME_POOL_SIZE", "20")))
WAIT_MIN = float(os.getenv("WAIT_MIN", "1"))
WAIT_MAX = float(os.getenv("WAIT_MAX", "3"))

# Keep in sync with JobCollector.NA_HUBS; /match filters postings by this exact location.
LOCATIONS = [
    "North America", "Seattle, WA", "Toronto, ON", "San Francisco, CA",
    "Austin, TX", "New York, NY", "Vancouver, BC", "Los Angeles, CA", "Montreal, QC",
]
SKILL_POOL = [
    "Python", "Java", "Go", "TypeScript", "React", "SQL", "PostgreSQL", "Redis",
    "Docker", "Kubernetes", "AWS", "FastAPI", "C++", "Rust", "Kafka", "GraphQL",
]
ROLES = ["Backend Engineer", "Full Stack Developer", "Data Engineer", "Platform Engineer", "ML Engineer"]

# Query strings for /match. Each distinct combination is a separate Redis cache key.
MATCH_FILTERS = [
    "",
    "levels=Entry",
    "levels=Junior&levels=Mid",
    "types=Full-time",
    "skills=Python",
    "levels=Senior&skills=Docker",
]


def make_resume_pdf(token: str) -> tuple:
    """Build a small text PDF whose content (hence content hash and embedding) depends on ``token``."""
    rng = random.Random(f"{SEED}-{token}")
    skills = rng.sample(SKILL_POOL, 6)
    text = "\n".join([
        f"Candidate {token}",
        f"{rng.choice(ROLES)} with {rng.randint(1, 12)} years of experience.",
        f"Skills: {', '.join(skills)}.",
        f"Built services with {skills[0]} and {skills[1]}; operated them on {skills[2]}.",
        f"Led a team of {rng.randint(2, 9)} engineers and shipped {rng.randint(3, 40)} releases.",
        f"Seed {rng.getrandbits(48):012x}.",
    ])
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 760), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return f"resume_{token}.pdf", data, rng.choice(LOCATIONS)


# Warm pool: identical on every run with the same LOCUST_SEED, which keeps runs comparable.
WARM_POOL = [make_resume_pdf(f"pool-{i}") for i in range(POOL_SIZE)]
# Cold resumes must be unseen by the server, so they carry a per-process random nonce.
RUN_NONCE = uuid.uuid4().hex[:8]


class SmartJobUser(HttpUser):
    """Virtual user mixing cheap stats reads, resume uploads and the expensive /match call."""

    wait_time = between(WAIT_MIN, WAIT_MAX)
    user_counter = 0

    def on_start(self):
        SmartJobUser.user_counter += 1
        self.index = SmartJobUser.user_counter
        self.rng = random.Random(f"{SEED}-user-{self.index}")
        self.cold_counter = 0
        self.resume_id = None
        if MODE == "warm":
            self.resume_id = self._upload(*WARM_POOL[(self.index - 1) % POOL_SIZE], name="/process-resume (warm setup)")

    def _upload(self, filename, data, location, name):
        """POST a resume; return the stored resume id, or None if the upload failed."""
        with self.client.post(
            "/process-resume",
            params={"location": location},
            files={"file": (filename, data, "application/pdf")},
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return None
            try:
                resume_id = response.json()["id"]
            except (ValueError, KeyError):
                response.failure("response has no resume id")
                return None
            response.success()
            return resume_id

    def _match(self, resume_id, query, name):
        """GET /match; an empty list counts as a failure so missing seed data cannot look fast."""
        url = f"/match/{resume_id}" + (f"?{query}" if query else "")
        with self.client.get(url, name=name, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                body = response.json()
            except ValueError:
                response.failure("response is not JSON")
                return
            if not isinstance(body, list) or not body:
                response.failure("empty match result (is the database seeded?)")
                return
            response.success()

    @task(2)
    def check_stats(self):
        self.client.get("/stats")

    @task(1)
    def upload_resume(self):
        """Upload a varied resume (warm: from the fixed pool; cold: always a new one)."""
        if MODE == "warm":
            filename, data, location = self.rng.choice(WARM_POOL)
            self._upload(filename, data, location, name="/process-resume")
        else:
            self.cold_counter += 1
            filename, data, location = make_resume_pdf(f"{RUN_NONCE}-u{self.index}-{self.cold_counter}")
            self._upload(filename, data, location, name="/process-resume")

    @task(3)
    def match(self):
        if MODE == "warm":
            if self.resume_id is None:
                return
            query = self.rng.choice(MATCH_FILTERS)
            self._match(self.resume_id, query, name="/match/[id] (warm)")
        else:
            self.cold_counter += 1
            filename, data, location = make_resume_pdf(f"{RUN_NONCE}-m{self.index}-{self.cold_counter}")
            resume_id = self._upload(filename, data, location, name="/process-resume (cold setup)")
            if resume_id is not None:
                self._match(resume_id, self.rng.choice(MATCH_FILTERS), name="/match/[id] (cold)")
