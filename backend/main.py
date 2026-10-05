import json
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "Chibani Lotfi AI API"

WORKER_API_KEY = os.getenv(
    "WORKER_API_KEY",
    ""
)

RENDER_CALLBACK_SECRET = os.getenv(
    "RENDER_CALLBACK_SECRET",
    ""
)

GITHUB_DISPATCH_TOKEN = os.getenv(
    "GITHUB_DISPATCH_TOKEN",
    ""
)

GITHUB_OWNER = os.getenv(
    "GITHUB_OWNER",
    "koreaone10-del"
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "MPT-Worker-POC"
)

GITHUB_EVENT_TYPE = os.getenv(
    "GITHUB_EVENT_TYPE",
    "mpt_job"
)

GITHUB_API_URL = os.getenv(
    "GITHUB_API_URL",
    "https://api.github.com"
).rstrip("/")


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

FRONTEND_DIR = BASE_DIR / "frontend"

VIDEO_DIR = BASE_DIR / "generated_videos"

VIDEO_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# Maximum uploaded video size: 100 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version="1.0.2",
)


# ============================================================
# CORS
# ============================================================

cors_origins_raw = os.getenv(
    "CORS_ORIGINS",
    "*"
)

if cors_origins_raw.strip() == "*":

    cors_origins = ["*"]

else:

    cors_origins = [
        origin.strip()
        for origin in cors_origins_raw.split(",")
        if origin.strip()
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# JOB STORE
# ============================================================

JOBS: dict[str, dict] = {}


# ============================================================
# MODELS
# ============================================================

class CreateJob(BaseModel):

    subject: str = Field(
        ...,
        min_length=2,
        max_length=500
    )

    language: str = "ar"

    aspect_ratio: str = "9:16"

    duration: int = Field(
        default=30,
        ge=10,
        le=300
    )

    voice: str = "ar-male"

    subtitles: bool = True

    subtitle_provider: str = "edge"

    video_source: str = "pexels"

    video_count: int = Field(
        default=1,
        ge=1,
        le=5
    )

    script: Optional[str] = None

    music: bool = True


class WorkerUpdate(BaseModel):

    status: str

    progress: int = Field(
        default=0,
        ge=0,
        le=100
    )

    stage: str = ""

    output_url: Optional[str] = None

    error: Optional[str] = None


class WorkerCallback(BaseModel):

    status: str

    progress: int = Field(
        default=0,
        ge=0,
        le=100
    )

    stage: str = ""

    output_url: Optional[str] = None

    error: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================

def now() -> float:

    return time.time()


def clamp_progress(value: int) -> int:

    return max(
        0,
        min(
            100,
            int(value)
        )
    )


def worker_authorized(
    request: Request
) -> bool:

    if not WORKER_API_KEY:
        return False

    provided = request.headers.get(
        "X-Worker-Key",
        ""
    )

    return provided == WORKER_API_KEY


def callback_authorized(
    request: Request
) -> bool:

    if not RENDER_CALLBACK_SECRET:
        return False

    provided = request.headers.get(
        "X-Callback-Secret",
        ""
    )

    return provided == RENDER_CALLBACK_SECRET


# ============================================================
# GITHUB DISPATCH
# ============================================================

def dispatch_to_github(
    job_id: str,
    payload: dict
) -> None:

    if not GITHUB_DISPATCH_TOKEN:

        raise RuntimeError(
            "GITHUB_DISPATCH_TOKEN is not configured"
        )

    url = (
        f"{GITHUB_API_URL}"
        f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/dispatches"
    )

    body = {

        "event_type": GITHUB_EVENT_TYPE,

        "client_payload": {

            "job_id": job_id,

            "video_subject": payload.get(
                "subject",
                ""
            ),

            "aspect": payload.get(
                "aspect_ratio",
                "9:16"
            ),

            "video_count": payload.get(
                "video_count",
                1
            ),

            "request": payload
        }
    }

    data = json.dumps(
        body
    ).encode("utf-8")

    github_request = urllib.request.Request(

        url,

        data=data,

        method="POST",

        headers={

            "Accept":
                "application/vnd.github+json",

            "Authorization":
                f"Bearer {GITHUB_DISPATCH_TOKEN}",

            "X-GitHub-Api-Version":
                "2022-11-28",

            "Content-Type":
                "application/json",

            "User-Agent":
                "Chibani-Lotfi-AI"
        }
    )

    try:

        with urllib.request.urlopen(
            github_request,
            timeout=30
        ) as response:

            status_code = response.status

            if status_code != 204:

                response_body = (
                    response
                    .read()
                    .decode(
                        "utf-8",
                        errors="replace"
                    )
                )

                raise RuntimeError(
                    "GitHub dispatch returned "
                    f"HTTP {status_code}: "
                    f"{response_body[:500]}"
                )

    except urllib.error.HTTPError as exc:

        error_body = (
            exc
            .read()
            .decode(
                "utf-8",
                errors="replace"
            )
        )

        raise RuntimeError(
            "GitHub dispatch failed "
            f"HTTP {exc.code}: "
            f"{error_body[:500]}"
        ) from exc

    except urllib.error.URLError as exc:

        raise RuntimeError(
            f"GitHub dispatch network error: {exc}"
        ) from exc


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {

        "ok": True,

        "service": APP_NAME,

        "time": now(),

        "github_dispatch_configured":
            bool(GITHUB_DISPATCH_TOKEN),

        "github_repository":
            GITHUB_REPO,

        "github_event_type":
            GITHUB_EVENT_TYPE,

        "callback_configured":
            bool(RENDER_CALLBACK_SECRET),

        "frontend_configured":
            FRONTEND_DIR.exists(),

        "video_storage_configured":
            VIDEO_DIR.exists()
    }


# ============================================================
# CREATE JOB
# ============================================================

@app.post("/api/jobs")
def create_job(
    payload: CreateJob
):

    job_id = str(
        uuid.uuid4()
    )

    created_at = now()

    job = {

        "job_id":
            job_id,

        "status":
            "queued",

        "progress":
            0,

        "stage":
            "queued",

        "created_at":
            created_at,

        "updated_at":
            created_at,

        "output_url":
            None,

        "error":
            None,

        "request":
            payload.model_dump()
    }

    JOBS[job_id] = job

    try:

        dispatch_to_github(
            job_id,
            payload.model_dump()
        )

        job["status"] = "dispatched"

        job["progress"] = 1

        job["stage"] = "github_actions"

        job["updated_at"] = now()

    except Exception as exc:

        job["status"] = "failed"

        job["progress"] = 100

        job["stage"] = "dispatch_failed"

        job["error"] = str(exc)

        job["updated_at"] = now()

        raise HTTPException(

            status_code=502,

            detail={

                "message":
                    "Unable to start GitHub Worker",

                "job_id":
                    job_id,

                "error":
                    str(exc)
            }
        )

    return job


# ============================================================
# LIST JOBS
# ============================================================

@app.get("/api/jobs")
def list_jobs():

    jobs = list(
        JOBS.values()
    )

    jobs.sort(

        key=lambda item:
            item.get(
                "created_at",
                0
            ),

        reverse=True
    )

    return jobs[:30]


# ============================================================
# GET JOB
# ============================================================

@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str
):

    job = JOBS.get(
        job_id
    )

    if not job:

        raise HTTPException(

            status_code=404,

            detail="Job not found"
        )

    return job


# ============================================================
# UPLOAD VIDEO FROM GITHUB WORKER
# ============================================================

@app.post(
    "/api/worker/jobs/{job_id}/upload"
)
async def upload_worker_video(
    job_id: str,
    request: Request
):

    # --------------------------------------------------------
    # Secret check
    # --------------------------------------------------------

    if not RENDER_CALLBACK_SECRET:

        raise HTTPException(

            status_code=500,

            detail=
                "RENDER_CALLBACK_SECRET "
                "is not configured"
        )


    # --------------------------------------------------------
    # Authorization
    # --------------------------------------------------------

    if not callback_authorized(request):

        raise HTTPException(

            status_code=401,

            detail="Invalid callback secret"
        )


    # --------------------------------------------------------
    # Job check
    # --------------------------------------------------------

    job = JOBS.get(
        job_id
    )

    if not job:

        raise HTTPException(

            status_code=404,

            detail="Job not found"
        )


    # --------------------------------------------------------
    # Content type check
    # --------------------------------------------------------

    content_type = request.headers.get(
        "Content-Type",
        ""
    ).lower()

    if "video/mp4" not in content_type:

        raise HTTPException(

            status_code=415,

            detail="Expected video/mp4"
        )


    # --------------------------------------------------------
    # Output path
    # --------------------------------------------------------

    output_path = (
        VIDEO_DIR /
        f"{job_id}.mp4"
    )


    total_size = 0


    # --------------------------------------------------------
    # Stream upload
    # --------------------------------------------------------

    try:

        with output_path.open(
            "wb"
        ) as video_file:

            async for chunk in request.stream():

                if not chunk:
                    continue

                total_size += len(chunk)

                if total_size > MAX_VIDEO_SIZE:

                    video_file.close()

                    if output_path.exists():
                        output_path.unlink()

                    raise HTTPException(

                        status_code=413,

                        detail=
                            "Video file is too large"
                    )

                video_file.write(
                    chunk
                )

    except HTTPException:

        raise

    except Exception as exc:

        if output_path.exists():
            output_path.unlink()

        raise HTTPException(

            status_code=500,

            detail=
                f"Video upload failed: {exc}"
        )


    # --------------------------------------------------------
    # Empty file check
    # --------------------------------------------------------

    if total_size <= 0:

        if output_path.exists():
            output_path.unlink()

        raise HTTPException(

            status_code=400,

            detail="Uploaded video is empty"
        )


    # --------------------------------------------------------
    # Public video URL
    # --------------------------------------------------------

    output_url = (
        f"/api/jobs/{job_id}/video"
    )


    # --------------------------------------------------------
    # Update job
    # --------------------------------------------------------

    job["output_url"] = output_url

    job["updated_at"] = now()

    job["stage"] = "video_uploaded"


    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {

        "ok": True,

        "job_id":
            job_id,

        "size":
            total_size,

        "output_url":
            output_url
    }


# ============================================================
# SERVE GENERATED VIDEO
# ============================================================

@app.get(
    "/api/jobs/{job_id}/video"
)
def get_job_video(
    job_id: str
):

    video_path = (
        VIDEO_DIR /
        f"{job_id}.mp4"
    )


    if not video_path.exists():

        raise HTTPException(

            status_code=404,

            detail="Video not found"
        )


    return FileResponse(

        path=str(
            video_path
        ),

        media_type="video/mp4",

        filename=f"{job_id}.mp4"
    )


# ============================================================
# GITHUB WORKER CALLBACK
# ============================================================

@app.post(
    "/api/worker/jobs/{job_id}/callback"
)
def worker_callback(

    job_id: str,

    update: WorkerCallback,

    request: Request
):

    # --------------------------------------------------------
    # Secret check
    # --------------------------------------------------------

    if not RENDER_CALLBACK_SECRET:

        raise HTTPException(

            status_code=500,

            detail=
                "RENDER_CALLBACK_SECRET "
                "is not configured"
        )


    # --------------------------------------------------------
    # Authorization
    # --------------------------------------------------------

    if not callback_authorized(
        request
    ):

        raise HTTPException(

            status_code=401,

            detail=
                "Invalid callback secret"
        )


    # --------------------------------------------------------
    # Job lookup
    # --------------------------------------------------------

    job = JOBS.get(
        job_id
    )

    if not job:

        raise HTTPException(

            status_code=404,

            detail="Job not found"
        )


    # --------------------------------------------------------
    # Update status
    # --------------------------------------------------------

    job["status"] = (
        update.status
    )

    job["progress"] = clamp_progress(
        update.progress
    )

    job["stage"] = (
        update.stage
    )

    job["updated_at"] = now()


    # --------------------------------------------------------
    # Output URL
    # --------------------------------------------------------

    if update.output_url:

        job["output_url"] = (
            update.output_url
        )


    # --------------------------------------------------------
    # Error
    # --------------------------------------------------------

    if update.error:

        job["error"] = (
            update.error
        )


    # --------------------------------------------------------
    # Completed
    # --------------------------------------------------------

    if update.status == "completed":

        job["progress"] = 100

        job["stage"] = (
            update.stage
            or
            "completed"
        )


    # --------------------------------------------------------
    # Failed
    # --------------------------------------------------------

    elif update.status == "failed":

        job["progress"] = 100

        job["stage"] = (
            update.stage
            or
            "failed"
        )


    return {

        "ok": True,

        "job_id":
            job_id,

        "status":
            job["status"],

        "progress":
            job["progress"],

        "stage":
            job["stage"],

        "output_url":
            job.get(
                "output_url"
            )
    }


# ============================================================
# LEGACY WORKER POLLING
# ============================================================

@app.get(
    "/api/worker/jobs/next"
)
def worker_next_job(
    request: Request
):

    if not worker_authorized(
        request
    ):

        raise HTTPException(

            status_code=401,

            detail="Invalid worker key"
        )


    for job in JOBS.values():

        if job.get(
            "status"
        ) == "queued":

            job["status"] = (
                "processing"
            )

            job["progress"] = 5

            job["stage"] = (
                "worker_started"
            )

            job["updated_at"] = now()

            return job


    return None


# ============================================================
# LEGACY WORKER UPDATE
# ============================================================

@app.post(
    "/api/worker/jobs/{job_id}/update"
)
def update_job_from_worker(

    job_id: str,

    update: WorkerUpdate,

    request: Request
):

    if not worker_authorized(
        request
    ):

        raise HTTPException(

            status_code=401,

            detail="Invalid worker key"
        )


    job = JOBS.get(
        job_id
    )

    if not job:

        raise HTTPException(

            status_code=404,

            detail="Job not found"
        )


    job["status"] = (
        update.status
    )

    job["progress"] = clamp_progress(
        update.progress
    )

    job["stage"] = (
        update.stage
    )

    job["updated_at"] = now()


    if update.output_url:

        job["output_url"] = (
            update.output_url
        )


    if update.error:

        job["error"] = (
            update.error
        )


    return {

        "ok": True,

        "job":
            job
    }


# ============================================================
# DELETE JOB
# ============================================================

@app.delete(
    "/api/jobs/{job_id}"
)
def delete_job(
    job_id: str
):

    if job_id not in JOBS:

        raise HTTPException(

            status_code=404,

            detail="Job not found"
        )


    # Delete associated video too
    video_path = (
        VIDEO_DIR /
        f"{job_id}.mp4"
    )

    if video_path.exists():

        try:
            video_path.unlink()
        except Exception:
            pass


    del JOBS[job_id]


    return {

        "ok": True,

        "job_id":
            job_id
    }


# ============================================================
# FRONTEND STATIC FILES
#
# IMPORTANT:
# API routes are defined BEFORE this mount.
# ============================================================

if FRONTEND_DIR.exists():

    assets_dir = (
        FRONTEND_DIR /
        "assets"
    )


    if assets_dir.exists():

        app.mount(

            "/assets",

            StaticFiles(
                directory=str(
                    assets_dir
                )
            ),

            name="assets"
        )


    app.mount(

        "/",

        StaticFiles(

            directory=str(
                FRONTEND_DIR
            ),

            html=True
        ),

        name="frontend"
    )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(

        "backend.main:app",

        host="0.0.0.0",

        port=port,

        reload=False
    )
