"""Chibani Lotfi AI - Cloud Video Worker v0.4

Render = control plane
Colab = compute worker
MoneyPrinterTurbo = video engine
Google Drive = output storage
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


# ============================================================
# Configuration
# ============================================================

CONTROL_API_URL = os.environ["CONTROL_API_URL"].rstrip("/")
WORKER_API_KEY = os.environ.get("WORKER_API_KEY", "").strip()

MPT_DIR = Path(
    os.environ.get(
        "MPT_DIR",
        "/content/MoneyPrinterTurbo",
    )
)

MPT_PORT = int(os.environ.get("MPT_PORT", "8080"))
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))

MPT_API_KEY = os.environ.get("MPT_API_KEY", "").strip()

REQUEST_TIMEOUT = 30
MPT_TIMEOUT = 60
TASK_POLL_SECONDS = 2

HEADERS = (
    {"x-worker-key": WORKER_API_KEY}
    if WORKER_API_KEY
    else {}
)

MPT_HEADERS = (
    {"x-api-key": MPT_API_KEY}
    if MPT_API_KEY
    else {}
)


# ============================================================
# Control API
# ============================================================

def update_job(
    job_id: str,
    status: str,
    progress: int,
    stage: str,
    output_url: str | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "stage": stage,
        "output_url": output_url,
        "error": error,
    }

    response = requests.post(
        f"{CONTROL_API_URL}/api/worker/jobs/{job_id}/update",
        json=payload,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()


def get_next_job() -> dict[str, Any]:
    response = requests.get(
        f"{CONTROL_API_URL}/api/worker/jobs/next",
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Invalid response from control API")

    return data


# ============================================================
# MoneyPrinterTurbo
# ============================================================

def wait_for_mpt() -> None:
    url = (
        f"http://127.0.0.1:{MPT_PORT}"
        "/api/v1/tasks?page=1&page_size=1"
    )

    last_error = None

    for _ in range(90):
        try:
            response = requests.get(
                url,
                headers=MPT_HEADERS,
                timeout=5,
            )

            if response.status_code < 500:
                return

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        except requests.RequestException as exc:
            last_error = str(exc)

        time.sleep(1)

    raise RuntimeError(
        "MoneyPrinterTurbo API did not become ready"
        + (f": {last_error}" if last_error else "")
    )


def start_mpt() -> subprocess.Popen:
    main_file = MPT_DIR / "main.py"
    config_file = MPT_DIR / "config.toml"

    if not main_file.exists():
        raise RuntimeError(
            f"MoneyPrinterTurbo main.py not found: {main_file}"
        )

    if not config_file.exists():
        raise RuntimeError(
            f"MoneyPrinterTurbo config.toml not found: {config_file}"
        )

    process = subprocess.Popen(
        [
            sys.executable,
            "main.py",
        ],
        cwd=MPT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )

    try:
        wait_for_mpt()
    except Exception:
        process.kill()
        raise

    return process


def stop_mpt(process: subprocess.Popen | None) -> None:
    if process is None:
        return

    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


# ============================================================
# Voice
# ============================================================

VOICE_MAP = {
    "ar-male": "ar-DZ-IsmaelNeural-Male",
    "ar-female": "ar-DZ-AminaNeural-Female",

    "fr-male": "fr-FR-HenriNeural-Male",
    "fr-female": "fr-FR-DeniseNeural-Female",

    "en-male": "en-US-GuyNeural-Male",
    "en-female": "en-US-JennyNeural-Female",
}


def voice_for(language: str, voice: str | None) -> str:
    if voice and voice in VOICE_MAP:
        return VOICE_MAP[voice]

    defaults = {
        "ar": os.environ.get(
            "MPT_VOICE_AR",
            "ar-DZ-IsmaelNeural-Male",
        ),
        "fr": os.environ.get(
            "MPT_VOICE_FR",
            "fr-FR-HenriNeural-Male",
        ),
        "en": os.environ.get(
            "MPT_VOICE_EN",
            "en-US-GuyNeural-Male",
        ),
    }

    return defaults.get(
        language,
        "ar-DZ-IsmaelNeural-Male",
    )


# ============================================================
# MPT payload
# ============================================================

def build_mpt_payload(request: dict[str, Any]) -> dict[str, Any]:
    duration = int(request.get("duration", 30))

    language = str(
        request.get("language", "ar")
    )

    video_count = max(
        1,
        min(
            int(request.get("video_count", 1)),
            5,
        ),
    )

    paragraph_number = max(
        1,
        min(
            8,
            round(duration / 30),
        ),
    )

    script = (
        request.get("script")
        or ""
    ).strip()

    payload = {
        "video_subject": request["subject"],

        "video_script": script,

        "video_aspect": request.get(
            "aspect_ratio",
            "9:16",
        ),

        "video_clip_duration": 5,

        "video_count": video_count,

        "video_source": request.get(
            "video_source",
            "pexels",
        ),

        "video_language": language,

        "voice_name": voice_for(
            language,
            request.get("voice"),
        ),

        "voice_mode": "tts",

        "voice_volume": 1.0,

        "voice_rate": 1.0,

        "bgm_type": (
            "random"
            if request.get("music", True)
            else "none"
        ),

        "bgm_volume": 0.12,

        "subtitle_enabled": bool(
            request.get("subtitles", True)
        ),

        "subtitle_display_mode": "sentence",

        "subtitle_position": "bottom",

        "font_name": os.environ.get(
            "MPT_FONT_NAME",
            "STHeitiMedium.ttc",
        ),

        "text_fore_color": "#FFFFFF",

        "subtitle_background_enabled": True,

        "subtitle_background_color": "#000000",

        "font_size": 60,

        "stroke_color": "#000000",

        "stroke_width": 1.5,

        "n_threads": 2,

        "paragraph_number": paragraph_number,
    }

    return payload


# ============================================================
# Create MPT task
# ============================================================

def create_mpt_task(
    payload: dict[str, Any],
) -> str:
    response = requests.post(
        f"http://127.0.0.1:{MPT_PORT}/api/v1/videos",
        json=payload,
        headers=MPT_HEADERS,
        timeout=MPT_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    task_id = (
        data
        .get("data", {})
        .get("task_id")
    )

    if not task_id:
        raise RuntimeError(
            "MoneyPrinterTurbo returned no task_id: "
            f"{str(data)[:1000]}"
        )

    return str(task_id)


# ============================================================
# Task polling
# ============================================================

def extract_video_path(
    task_id: str,
    data: dict[str, Any],
) -> str:
    videos = data.get("videos") or []

    if not videos:
        raise RuntimeError(
            "Task completed but no video output was returned"
        )

    video = videos[0]

    if isinstance(video, str):
        if video.startswith(("http://", "https://")):
            response = requests.get(
                video,
                headers=MPT_HEADERS,
                timeout=120,
            )

            response.raise_for_status()

            output = (
                MPT_DIR
                / "storage"
                / "tasks"
                / task_id
                / "final-1.mp4"
            )

            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            output.write_bytes(
                response.content
            )

            return str(output)

        candidate = (
            MPT_DIR
            / "storage"
            / "tasks"
            / task_id
            / Path(video).name
        )

        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "Could not locate generated video: "
        f"{video}"
    )


def wait_for_task(
    task_id: str,
    job_id: str,
) -> str:
    last_progress = -1

    while True:
        response = requests.get(
            f"http://127.0.0.1:{MPT_PORT}"
            f"/api/v1/tasks/{task_id}",
            headers=MPT_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        body = response.json()

        data = body.get("data") or {}

        state = int(
            data.get("state", 0)
        )

        progress = int(
            data.get("progress", 0)
        )

        if progress != last_progress:
            update_job(
                job_id,
                "processing",
                min(progress, 99),
                "rendering",
            )

            last_progress = progress

        # MPT: completed
        if state == 1:
            return extract_video_path(
                task_id,
                data,
            )

        # MPT: failed
        if state == -1:
            raise RuntimeError(
                str(
                    data.get(
                        "error",
                        "MoneyPrinterTurbo task failed",
                    )
                )
            )

        time.sleep(
            TASK_POLL_SECONDS
        )


# ============================================================
# Google Drive
# ============================================================

def upload_to_drive(
    local_path: str,
) -> str:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import google.auth
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive dependencies are missing"
        ) from exc

    credentials, _ = google.auth.default()

    service = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    file_name = Path(
        local_path
    ).name

    media = MediaFileUpload(
        local_path,
        mimetype="video/mp4",
        resumable=True,
    )

    created = (
        service
        .files()
        .create(
            body={
                "name": file_name,
            },
            media_body=media,
            fields="id,name",
        )
        .execute()
    )

    file_id = created["id"]

    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader",
        },
    ).execute()

    return (
        "https://drive.google.com/file/d/"
        f"{file_id}/view"
    )


# ============================================================
# Job processing
# ============================================================

def process_job(
    job: dict[str, Any],
) -> None:
    job_id = job["id"]

    mpt_process = None

    try:
        update_job(
            job_id,
            "processing",
            3,
            "starting",
        )

        mpt_process = start_mpt()

        update_job(
            job_id,
            "processing",
            5,
            "mpt_ready",
        )

        payload = build_mpt_payload(
            job["request"]
        )

        task_id = create_mpt_task(
            payload
        )

        update_job(
            job_id,
            "processing",
            8,
            f"mpt:{task_id}",
        )

        video_path = wait_for_task(
            task_id,
            job_id,
        )

        if not Path(video_path).exists():
            raise RuntimeError(
                f"Generated video not found: {video_path}"
            )

        update_job(
            job_id,
            "processing",
            95,
            "uploading",
        )

        output_url = upload_to_drive(
            video_path
        )

        update_job(
            job_id,
            "completed",
            100,
            "done",
            output_url=output_url,
        )

    except Exception as exc:
        error_message = (
            f"{type(exc).__name__}: {exc}"
        )

        try:
            update_job(
                job_id,
                "failed",
                100,
                "error",
                error=error_message,
            )
        except Exception:
            pass

    finally:
        stop_mpt(
            mpt_process
        )


# ============================================================
# Main worker loop
# ============================================================

def main() -> None:
    print(
        "Chibani Lotfi AI worker started",
        flush=True,
    )

    while True:
        try:
            response = get_next_job()

            job = response.get("job")

            if not job:
                time.sleep(
                    POLL_SECONDS
                )
                continue

            process_job(job)

        except KeyboardInterrupt:
            print(
                "Worker stopped",
                flush=True,
            )
            break

        except Exception as exc:
            print(
                f"Worker loop error: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            time.sleep(
                max(POLL_SECONDS, 3)
            )


if __name__ == "__main__":
    main()
