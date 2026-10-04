import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_NAME = "Chibani Lotfi AI API"
WORKER_API_KEY = os.getenv("WORKER_API_KEY", "")
JOBS = {}

app = FastAPI(title=APP_NAME, version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

def worker_auth(x_worker_key: Optional[str]):
    if WORKER_API_KEY and x_worker_key != WORKER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid worker key")

class CreateJob(BaseModel):
    subject: str = Field(min_length=2, max_length=500)
    language: str = "ar"
    aspect_ratio: str = "9:16"
    duration: int = Field(default=30, ge=10, le=300)
    voice: str = "ar-male"
    subtitles: bool = True
    subtitle_provider: str = "edge"
    video_source: str = "pexels"
    video_count: int = Field(default=1, ge=1, le=5)
    script: Optional[str] = None
    music: bool = True

@app.get("/health")
async def health():
    return {"ok": True, "service": APP_NAME, "time": time.time()}

@app.post("/api/jobs")
async def create_job(payload: CreateJob):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0, "stage": "queued", "created_at": time.time(), "updated_at": time.time(), "request": payload.model_dump(), "output_url": None, "error": None}
    return JOBS[job_id]

@app.get("/api/jobs")
async def list_jobs():
    return list(reversed(list(JOBS.values())))[:30]

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/worker/jobs/next")
async def worker_next(x_worker_key: Optional[str] = Header(None)):
    worker_auth(x_worker_key)
    for job in JOBS.values():
        if job["status"] == "queued":
            job.update({"status":"processing", "stage":"claimed", "progress":1, "updated_at":time.time()})
            return {"job": job}
    return {"job": None}

class WorkerUpdate(BaseModel):
    status: str
    progress: int = Field(ge=0, le=100)
    stage: str
    output_url: Optional[str] = None
    error: Optional[str] = None

@app.post("/api/worker/jobs/{job_id}/update")
async def worker_update(job_id: str, payload: WorkerUpdate, x_worker_key: Optional[str] = Header(None)):
    worker_auth(x_worker_key)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.update(payload.model_dump()); job["updated_at"] = time.time()
    return job

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, x_worker_key: Optional[str] = Header(None)):
    worker_auth(x_worker_key)
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    del JOBS[job_id]
    return {"ok": True}

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=False)
