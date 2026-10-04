const API_BASE_URL = (
  window.CHIBANI_API_BASE_URL || window.location.origin
).replace(/\/$/, "");

const $ = (id) => document.getElementById(id);

const POLL_INTERVAL = 8000;
const REQUEST_TIMEOUT = 15000;

let pollTimer = null;
let loadingJobs = false;
let pageVisible = true;


/* =========================================================
   HTTP
========================================================= */

function headers() {
  return {
    "Content-Type": "application/json"
  };
}


async function api(path, options = {}) {

  const controller = new AbortController();

  const timeout = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT);

  try {

    const res = await fetch(
      API_BASE_URL + path,
      {
        ...options,

        headers: {
          ...headers(),
          ...(options.headers || {})
        },

        signal: controller.signal
      }
    );

    if (!res.ok) {

      let message = "";

      try {
        message = await res.text();
      } catch {
        message = "";
      }

      throw new Error(
        message || `HTTP ${res.status}`
      );
    }

    return await res.json();

  } catch (error) {

    if (error.name === "AbortError") {
      throw new Error("انتهت مهلة الاتصال بالخادم.");
    }

    throw error;

  } finally {

    clearTimeout(timeout);

  }
}


/* =========================================================
   API STATUS
========================================================= */

async function ping() {

  const state = $("apiState");

  if (!state) return;

  try {

    await api("/health");

    state.textContent = "ONLINE";

    const pill = state.closest(".live-pill");

    if (pill) {
      pill.classList.add("online");
    }

  } catch {

    state.textContent = "OFFLINE";

    const pill = state.closest(".live-pill");

    if (pill) {
      pill.classList.remove("online");
    }

  }
}


/* =========================================================
   CREATE VIDEO
========================================================= */

const createForm = $("createForm");

if (createForm) {

  createForm.addEventListener(
    "submit",
    async (event) => {

      event.preventDefault();

      const message = $("message");
      const button = createForm.querySelector(
        'button[type="submit"]'
      );

      const subject =
        $("subject")?.value.trim() || "";

      if (!subject) {

        if (message) {
          message.textContent =
            "اكتب فكرة الفيديو أولاً.";
        }

        $("subject")?.focus();

        return;
      }


      if (message) {
        message.textContent =
          "جاري إرسال المهمة إلى محرك الذكاء الاصطناعي...";
      }


      if (button) {

        button.disabled = true;

        button.classList.add("loading");

        const originalText =
          button.dataset.originalText ||
          button.querySelector(".btn-text")?.textContent ||
          "إنشاء الفيديو";

        button.dataset.originalText =
          originalText;

        const text =
          button.querySelector(".btn-text");

        if (text) {
          text.textContent =
            "جاري الإرسال...";
        }
      }


      try {

        const payload = {

          subject,

          language:
            $("language")?.value || "ar",

          aspect_ratio:
            $("aspect_ratio")?.value || "9:16",

          duration:
            Number($("duration")?.value || 30),

          video_source:
            $("video_source")?.value || "pexels",

          voice:
            $("voice")?.value || "edge",

          subtitles:
            Boolean($("subtitles")?.checked),

          subtitle_provider:
            $("subtitle_provider")?.value || "edge",

          music:
            Boolean($("music")?.checked)

        };


        await api(
          "/api/jobs",
          {
            method: "POST",

            body: JSON.stringify(payload)
          }
        );


        if (message) {

          message.textContent =
            "تمت إضافة المهمة بنجاح ✓ جاري تجهيز الفيديو...";

          message.classList.add("success");

        }


        $("subject").value = "";

        const counter =
          $("promptCount");

        if (counter) {
          counter.textContent = "0";
        }


        await loadJobs(true);


      } catch (error) {

        if (message) {

          message.textContent =
            "فشل إرسال المهمة: " +
            error.message;

          message.classList.remove("success");

        }

      } finally {

        if (button) {

          button.disabled = false;

          button.classList.remove("loading");

          const text =
            button.querySelector(".btn-text");

          if (text) {

            text.textContent =
              button.dataset.originalText ||
              "إنشاء الفيديو";

          }
        }
      }
    }
  );
}


/* =========================================================
   JOB REFRESH BUTTON
========================================================= */

const refreshButton =
  $("refresh");

if (refreshButton) {

  refreshButton.addEventListener(
    "click",
    async () => {

      refreshButton.disabled = true;

      refreshButton.classList.add("loading");

      try {

        await loadJobs(true);

      } finally {

        refreshButton.disabled = false;

        refreshButton.classList.remove("loading");

      }

    }
  );
}


/* =========================================================
   JOB HTML
========================================================= */

function jobHTML(job) {

  const request =
    job?.request || {};

  const subject =
    escapeHtml(
      request.subject ||
      "مهمة فيديو"
    );


  const status =
    escapeHtml(
      job?.status ||
      "unknown"
    );


  const stage =
    escapeHtml(
      job?.stage ||
      "processing"
    );


  const progress =
    Math.max(
      0,
      Math.min(
        100,
        Number(job?.progress || 0)
      )
    );


  let output = "";

  if (job?.output_url) {

    const safeUrl =
      escapeAttribute(
        job.output_url
      );

    output = `
      <a
        class="download"
        href="${safeUrl}"
        target="_blank"
        rel="noopener noreferrer"
      >
        فتح الفيديو ↗
      </a>
    `;
  }


  let error = "";

  if (job?.error) {

    error = `
      <small class="job-error">
        ${escapeHtml(job.error)}
      </small>
    `;
  }


  return `
    <article class="job">

      <div class="jobHead">

        <strong>
          ${subject}
        </strong>

        <span class="status">
          ${status}
        </span>

      </div>


      <small>
        ${stage}
        ·
        ${progress}%
      </small>


      <div
        class="progress"
        aria-label="Progress"
      >

        <div
          class="bar"
          style="width:${progress}%"
        ></div>

      </div>


      ${output}

      ${error}

    </article>
  `;
}


/* =========================================================
   LOAD JOBS
========================================================= */

async function loadJobs(force = false) {

  if (loadingJobs && !force) {
    return;
  }

  if (!pageVisible && !force) {
    return;
  }


  loadingJobs = true;


  try {

    const jobs =
      await api("/api/jobs");


    const container =
      $("jobs");


    if (!container) {
      return;
    }


    if (
      !Array.isArray(jobs) ||
      jobs.length === 0
    ) {

      container.innerHTML = `
        <div class="empty-jobs">
          لا توجد مهام بعد.
        </div>
      `;

      return;
    }


    container.innerHTML =
      jobs
        .map(jobHTML)
        .join("");


  } catch (error) {

    const container =
      $("jobs");

    if (!container) {
      return;
    }


    /*
      لا نستبدل قائمة المهام الموجودة
      برسالة خطأ في كل polling.
    */

    if (!container.children.length) {

      container.innerHTML = `
        <div class="empty-jobs">
          تعذر الاتصال بالخادم حالياً.
        </div>
      `;

    }

  } finally {

    loadingJobs = false;

  }
}


/* =========================================================
   SMART POLLING
========================================================= */

function startPolling() {

  stopPolling();


  if (!pageVisible) {
    return;
  }


  pollTimer =
    setInterval(
      () => {

        if (
          document.hidden ||
          !pageVisible
        ) {
          return;
        }

        loadJobs();

      },
      POLL_INTERVAL
    );
}


function stopPolling() {

  if (pollTimer !== null) {

    clearInterval(
      pollTimer
    );

    pollTimer = null;

  }
}


/* =========================================================
   PAGE VISIBILITY
========================================================= */

document.addEventListener(
  "visibilitychange",
  () => {

    pageVisible =
      !document.hidden;


    if (pageVisible) {

      /*
        تحديث فوري عند العودة
        للصفحة.
      */

      ping();

      loadJobs(true);

      startPolling();

    } else {

      /*
        إيقاف الطلبات أثناء
        وجود الصفحة في الخلفية.
      */

      stopPolling();

    }

  }
);


/* =========================================================
   SAFE HTML
========================================================= */

function escapeHtml(value) {

  return String(
    value ?? ""
  ).replace(
    /[&<>"']/g,
    (char) => {

      const map = {

        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"

      };

      return map[char];

    }
  );
}


function escapeAttribute(value) {

  return String(
    value ?? ""
  )
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

}


/* =========================================================
   INITIAL STARTUP
========================================================= */

(async function init() {

  pageVisible =
    !document.hidden;


  /*
    فحص API مرة واحدة.
  */

  await ping();


  /*
    تحميل المهام مباشرة.
  */

  await loadJobs(true);


  /*
    بعدها polling خفيف:
    كل 8 ثواني.
  */

  startPolling();

})();
