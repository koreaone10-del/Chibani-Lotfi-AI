import json
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# =========================================================
# APP CONFIG
# =========================================================

APP_NAME = "Chibani Lotfi AI API"

WORKER_API_KEY = os.getenv("WORKER_API_KEY", "")

GITHUB_DISPATCH_TOKEN = os.getenv(
    "GITHUB_DISPATCH_TOKEN",
    "",
)

GITHUB_OWNER = os.getenv(
    "GITHUB_OWNER",
    "koreaone10-del",
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "MPT-Worker-POC",
)

GITHUB_EVENT_TYPE = os.getenv(
    "GITHUB_EVENT_TYPE",
    "mpt_job",
)

GITHUB_API_URL = os.getenv(
    "GITHUB_API_URL",
    "https://api.github.com",
).rstrip("/")


# =========================================================
# IN-MEMORY JOB STORE
# =========================================================

JOBS = {}


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title=APP_NAME,
    version="0.4.0",
)


# =========================================================
# CORS
# =========================================================

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "*",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# WORKER AUTH
# =========================================================

def worker_auth(
    x_worker_key: Optional[str],
):
    if (
        WORKER_API_KEY
        and x_worker_key != WORKER_API_KEY
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid worker key",
        )


# =========================================================
# CREATE JOB MODEL
# =========================================================

class CreateJob(BaseModel):

    subject: str = Field(
        min_length=2,
        max_length=500,
    )

    language: str = "ar"

    aspect_ratio: str = "9:16"

    duration: int = Field(
        default=30,
        ge=10,
        le=300,
    )

    voice: str = "ar-male"

    subtitles: bool = True

    subtitle_provider: str = "edge"

    video_source: str = "pexels"

    video_count: int = Field(
        default=1,
        ge=1,
        le=5,
    )

    script: Optional[str] = None

    music: bool = True


# =========================================================
# WORKER UPDATE MODEL
# =========================================================

class WorkerUpdate(BaseModel):

    status: str

    progress: int = Field(
        ge=0,
        le=100,
    )

    stage: str

    output_url: Optional[str] = None

    error: Optional[str] = None


# =========================================================
# GITHUB DISPATCH
# =========================================================

def dispatch_to_github(
    job_id: str,
    payload: CreateJob,
):
    """
    Trigger the MPT Worker GitHub Actions workflow
    using repository_dispatch.
    """

    if not GITHUB_DISPATCH_TOKEN:
        raise RuntimeError(
            "GITHUB_DISPATCH_TOKEN is not configured on Render."
        )

    url = (
        f"{GITHUB_API_URL}"
        f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/dispatches"
    )

    # Keep the top-level client_payload small.
    # GitHub supports client_payload for custom workflow data.
    client_payload = {
        "job_id": job_id,

        "video_subject": payload.subject,

        "aspect": payload.aspect_ratio,

        "video_count": payload.video_count,

        # Preserve the complete original request
        # for future Worker versions.
        "request": payload.model_dump(),
    }

    body = {
        "event_type": GITHUB_EVENT_TYPE,
        "client_payload": client_payload,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": (
                f"Bearer {GITHUB_DISPATCH_TOKEN}"
            ),
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Chibani-Lotfi-AI",
        },
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            status_code = response.status

            if status_code != 204:
                raise RuntimeError(
                    f"GitHub dispatch returned HTTP {status_code}"
                )

            return True

    except urllib.error.HTTPError as error:

        # Never expose the GitHub token.
        try:
            response_body = (
                error.read()
                .decode("utf-8", errors="replace")
            )
        except Exception:
            response_body = ""

        # GitHub dispatch normally returns 204.
        # Any other status means the dispatch failed.
        raise RuntimeError(
            f"GitHub dispatch failed: "
            f"HTTP {error.code}"
            + (
                f" - {response_body[:500]}"
                if response_body
                else ""
            )
        ) from error

    except urllib.error.URLError as error:

        raise RuntimeError(
            f"Unable to reach GitHub API: {error.reason}"
        ) from error

    except Exception as error:

        raise RuntimeError(
            f"GitHub dispatch error: {error}"
        ) from error


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {
        "ok": True,
        "service": APP_NAME,
        "time": time.time(),

        # Safe diagnostic information.
        # Never expose the token itself.
        "github_dispatch_configured": bool(
            GITHUB_DISPATCH_TOKEN
        ),

        "github_repository": (
            f"{GITHUB_OWNER}/{GITHUB_REPO}"
        ),

        "github_event_type": GITHUB_EVENT_TYPE,
    }


# =========================================================
# CREATE JOB
# =========================================================

@app.post("/api/jobs")
async def create_job(
    payload: CreateJob,
):

    job_id = str(uuid.uuid4())

    now = time.time()

    job = {
        "id": job_id,

        "status": "queued",

        "progress": 0,

        "stage": "queued",

        "created_at": now,

        "updated_at": now,

        "request": payload.model_dump(),

        "output_url": None,

        "error": None,
    }

    JOBS[job_id] = job

    # -----------------------------------------------------
    # SEND JOB TO GITHUB ACTIONS
    # -----------------------------------------------------

    try:

        dispatch_to_github(
            job_id=job_id,
            payload=payload,
        )

    except Exception as error:

        job.update(
            {
                "status": "failed",

                "stage": "github_dispatch_failed",

                "progress": 0,

                "error": str(error),

                "updated_at": time.time(),
            }
        )

        # Return a useful API error to the frontend.
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to dispatch job to GitHub Actions.",
                "job_id": job_id,
                "error": str(error),
            },
        )

    # -----------------------------------------------------
    # DISPATCH SUCCESS
    # -----------------------------------------------------

    job.update(
        {
            "status": "dispatched",

            "stage": "github_actions",

            "progress": 1,

            "updated_at": time.time(),
        }
    )

    return job


# =========================================================
# LIST JOBS
# =========================================================

@app.get("/api/jobs")
async def list_jobs():

    return list(
        reversed(
            list(
                JOBS.values()
            )
        )
    )[:30]


# =========================================================
# GET SINGLE JOB
# =========================================================

@app.get("/api/jobs/{job_id}")
async def get_job(
    job_id: str,
):

    job = JOBS.get(job_id)

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job


# =========================================================
# LEGACY WORKER QUEUE ENDPOINT
# =========================================================

@app.get("/api/worker/jobs/next")
async def worker_next(
    x_worker_key: Optional[str] = Header(None),
):

    worker_auth(
        x_worker_key
    )

    for job in JOBS.values():

        if job["status"] == "queued":

            job.update(
                {
                    "status": "processing",

                    "stage": "claimed",

                    "progress": 1,

                    "updated_at": time.time(),
                }
            )

            return {
                "job": job
            }

    return {
        "job": None
    }


# =========================================================
# WORKER UPDATE
# =========================================================

@app.post(
    "/api/worker/jobs/{job_id}/update"
)
async def worker_update(
    job_id: str,
    payload: WorkerUpdate,
    x_worker_key: Optional[str] = Header(None),
):

    worker_auth(
        x_worker_key
    )

    job = JOBS.get(
        job_id
    )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    job.update(
        payload.model_dump()
    )

    job["updated_at"] = time.time()

    return job


# =========================================================
# DELETE JOB
# =========================================================

@app.delete(
    "/api/jobs/{job_id}"
)
async def delete_job(
    job_id: str,
    x_worker_key: Optional[str] = Header(None),
):

    worker_auth(
        x_worker_key
    )

    if job_id not in JOBS:

        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    del JOBS[job_id]

    return {
        "ok": True
    }


# =========================================================
# FRONTEND
# =========================================================

FRONTEND_DIR = (
    Path(__file__)
    .resolve()
    .parent.parent
    / "frontend"
)


if FRONTEND_DIR.exists():

    app.mount(
        "/assets",
        StaticFiles(
            directory=FRONTEND_DIR
        ),
        name="assets",
    )


# =========================================================
# INDEX
# =========================================================

@app.get("/")
async def index():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8080",
            )
        ),
        reload=False,
    )
