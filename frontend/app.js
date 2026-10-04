const API_BASE_URL = (window.CHIBANI_API_BASE_URL || window.location.origin).replace(/\/$/, "");
const $ = (id) => document.getElementById(id);
const headers = () => ({"Content-Type":"application/json"});
async function api(path, options={}) {
  const res = await fetch(API_BASE_URL + path, {...options, headers:{...headers(), ...(options.headers || {})}});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function ping(){ try { await api("/health"); $("apiState").textContent="ONLINE"; } catch { $("apiState").textContent="OFFLINE"; } }
$("createForm").addEventListener("submit", async (e)=>{
  e.preventDefault(); $("message").textContent="جاري إرسال المهمة...";
  try {
    const payload={subject:$("subject").value.trim(),language:$("language").value,aspect_ratio:$("aspect_ratio").value,duration:Number($("duration").value),video_source:$("video_source").value,voice:$("voice").value,subtitles:$("subtitles").checked,subtitle_provider:$("subtitle_provider").value,music:$("music").checked};
    await api("/api/jobs",{method:"POST",body:JSON.stringify(payload)}); $("message").textContent="تمت إضافة المهمة للطابور ✅"; $("subject").value=""; loadJobs();
  } catch(err){ $("message").textContent="فشل: "+err.message; }
});
$("refresh").onclick=loadJobs;
function jobHTML(j){ const output=j.output_url?`<a class="download" href="${j.output_url}" target="_blank" rel="noopener">فتح الفيديو ↗</a>`:""; return `<article class="job"><div class="jobHead"><strong>${escapeHtml(j.request.subject)}</strong><span class="status">${escapeHtml(j.status)}</span></div><small>${escapeHtml(j.stage)} · ${j.progress}%</small><div class="progress"><div class="bar" style="width:${j.progress}%"></div></div>${output}${j.error?`<small style="color:#ff8da2">${escapeHtml(j.error)}</small>`:""}</article>`; }
async function loadJobs(){ try{ const jobs=await api("/api/jobs"); $("jobs").innerHTML=jobs.length?jobs.map(jobHTML).join(""):"<p>لا توجد مهام بعد.</p>"; }catch(e){$("jobs").innerHTML="<p>تعذر الاتصال بالـAPI.</p>";} }
function escapeHtml(s){ return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c])); }
ping(); loadJobs(); setInterval(loadJobs,2500);
