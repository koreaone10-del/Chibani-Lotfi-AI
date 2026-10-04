"""Chibani Lotfi AI fast control-plane worker."""
from __future__ import annotations
import os, subprocess, sys, time
from pathlib import Path
from typing import Any
import requests

CONTROL_API_URL=os.environ["CONTROL_API_URL"].rstrip("/")
WORKER_API_KEY=os.environ.get("WORKER_API_KEY","")
MPT_DIR=Path(os.environ.get("MPT_DIR","/content/MoneyPrinterTurbo"))
MPT_PORT=int(os.environ.get("MPT_PORT","8080"))
POLL_SECONDS=float(os.environ.get("POLL_SECONDS","2"))
MPT_API_KEY=os.environ.get("MPT_API_KEY","")
HEADERS={"x-worker-key":WORKER_API_KEY} if WORKER_API_KEY else {}
MPT_HEADERS={"x-api-key":MPT_API_KEY} if MPT_API_KEY else {}

def update(job_id,status,progress,stage,output_url=None,error=None):
    r=requests.post(f"{CONTROL_API_URL}/api/worker/jobs/{job_id}/update",json={"status":status,"progress":progress,"stage":stage,"output_url":output_url,"error":error},headers=HEADERS,timeout=20); r.raise_for_status()
def get_next()->dict[str,Any]:
    r=requests.get(f"{CONTROL_API_URL}/api/worker/jobs/next",headers=HEADERS,timeout=20); r.raise_for_status(); return r.json()
def wait_for_mpt():
    url=f"http://127.0.0.1:{MPT_PORT}/api/v1/tasks?page=1&page_size=1"
    for _ in range(45):
        try:
            r=requests.get(url,headers=MPT_HEADERS,timeout=3)
            if r.status_code<500:return
        except requests.RequestException:pass
        time.sleep(1)
    raise RuntimeError("MoneyPrinterTurbo API did not become ready")
def start_mpt():
    if not (MPT_DIR/"config.toml").exists(): raise RuntimeError(f"Missing {MPT_DIR}/config.toml")
    proc=subprocess.Popen([sys.executable,"main.py"],cwd=MPT_DIR,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,env=os.environ.copy()); wait_for_mpt(); return proc
def voice_for(language,voice):
    explicit={"ar-male":"ar-DZ-IsmaelNeural-Male","ar-female":"ar-DZ-AminaNeural-Female","fr-male":"fr-FR-HenriNeural-Male","en-male":"en-US-GuyNeural-Male"}
    if voice in explicit:return explicit[voice]
    return {"ar":os.environ.get("MPT_VOICE_AR","ar-DZ-IsmaelNeural-Male"),"fr":os.environ.get("MPT_VOICE_FR","fr-FR-HenriNeural-Male"),"en":os.environ.get("MPT_VOICE_EN","en-US-GuyNeural-Male")}.get(language,"ar-DZ-IsmaelNeural-Male")
def build_mpt_payload(req):
    duration=int(req.get("duration",30)); language=req.get("language","ar")
    return {"video_subject":req["subject"],"video_script":req.get("script") or "","video_aspect":req.get("aspect_ratio","9:16"),"video_clip_duration":5,"video_count":min(int(req.get("video_count",1)),5),"video_source":req.get("video_source","pexels"),"video_language":language,"voice_name":voice_for(language,req.get("voice")),"voice_volume":1.0,"voice_rate":1.0,"bgm_type":"random" if req.get("music",True) else "none","bgm_volume":0.12,"subtitle_enabled":bool(req.get("subtitles",True)),"subtitle_position":"bottom","font_name":os.environ.get("MPT_FONT_NAME","STHeitiMedium.ttc"),"text_fore_color":"#FFFFFF","text_background_color":True,"font_size":60,"stroke_color":"#000000","stroke_width":1.5,"n_threads":2,"paragraph_number":max(1,min(8,round(duration/30)))}
def create_task(payload):
    r=requests.post(f"http://127.0.0.1:{MPT_PORT}/api/v1/videos",json=payload,headers=MPT_HEADERS,timeout=60); r.raise_for_status(); tid=r.json().get("data",{}).get("task_id")
    if not tid: raise RuntimeError(f"MoneyPrinterTurbo returned no task_id: {r.text[:500]}")
    return tid
def wait_task(task_id,job_id):
    last=-1
    while True:
        r=requests.get(f"http://127.0.0.1:{MPT_PORT}/api/v1/tasks/{task_id}",headers=MPT_HEADERS,timeout=20); r.raise_for_status(); data=r.json().get("data",{}); state=int(data.get("state",0)); progress=int(data.get("progress",0))
        if progress!=last:update(job_id,"processing",min(progress,99),"rendering"); last=progress
        if state==1 and data.get("videos"):
            video=data["videos"][0]
            if isinstance(video,str) and video.startswith(("http://","https://")):
                r2=requests.get(video,headers=MPT_HEADERS,timeout=120); r2.raise_for_status(); tmp=MPT_DIR/"storage"/"tasks"/task_id/"final-1.mp4"; tmp.parent.mkdir(parents=True,exist_ok=True); tmp.write_bytes(r2.content); return str(tmp)
            return str(MPT_DIR/"storage"/"tasks"/task_id/Path(str(video)).name)
        if state<0:raise RuntimeError(f"MoneyPrinterTurbo failed: {data.get('error')}")
        time.sleep(1.5)
def upload_to_drive(local_path):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import google.auth
    except ImportError as exc:raise RuntimeError("Google Drive dependencies are missing") from exc
    creds,_=google.auth.default(); service=build("drive","v3",credentials=creds,cache_discovery=False); media=MediaFileUpload(local_path,mimetype="video/mp4",resumable=True); created=service.files().create(body={"name":Path(local_path).name},media_body=media,fields="id").execute(); fid=created["id"]; service.permissions().create(fileId=fid,body={"type":"anyone","role":"reader"}).execute(); return f"https://drive.google.com/file/d/{fid}/view"
def main():
    mpt=start_mpt(); print("Chibani Lotfi AI worker started")
    try:
        while True:
            job=get_next().get("job")
            if not job:time.sleep(POLL_SECONDS); continue
            jid=job["id"]
            try:
                update(jid,"processing",3,"starting"); tid=create_task(build_mpt_payload(job["request"])); update(jid,"processing",8,f"mpt:{tid}"); video=wait_task(tid,jid); update(jid,"processing",95,"uploading"); url=upload_to_drive(video); update(jid,"completed",100,"done",output_url=url)
            except Exception as exc: update(jid,"failed",100,"error",error=f"{type(exc).__name__}: {exc}")
    finally:
        mpt.terminate()
        try:mpt.wait(timeout=8)
        except subprocess.TimeoutExpired:mpt.kill()
if __name__=="__main__":main()
