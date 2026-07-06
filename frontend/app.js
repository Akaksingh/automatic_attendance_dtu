// Minimal teacher web app. No framework — vanilla JS against the FastAPI backend.
const API = ""; // same origin
let token = localStorage.getItem("token") || "";
let role = localStorage.getItem("role") || "";
let session = null;   // current session detail
let photoFile = null;
let pollTimer = null;

const $ = (id) => document.getElementById(id);

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (token) headers["Authorization"] = "Bearer " + token;
  let payload = body;
  if (body && !form) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(API + path, { method, headers, body: payload });
  if (res.status === 401) { logout(); throw new Error("Session expired"); }
  const data = res.status === 204 ? {} : await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ---- Auth ----
async function login() {
  $("loginErr").textContent = "";
  const form = new URLSearchParams({ username: $("email").value, password: $("password").value });
  try {
    const res = await fetch(API + "/auth/login", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    token = data.access_token; role = data.role;
    localStorage.setItem("token", token); localStorage.setItem("role", role);
    await showApp();
  } catch (e) { $("loginErr").textContent = e.message; }
}

function logout() {
  token = ""; role = ""; localStorage.clear();
  if (pollTimer) clearInterval(pollTimer);
  $("appView").hidden = true; $("loginView").hidden = false;
  $("logoutBtn").hidden = true; $("who").textContent = "";
}

async function showApp() {
  $("loginView").hidden = true; $("appView").hidden = false; $("logoutBtn").hidden = false;
  const me = await api("/auth/me");
  $("who").textContent = `${me.email} (${me.role})`;
  await loadCourses();
}

async function loadCourses() {
  const courses = await api("/courses");
  const sel = $("courseSelect");
  sel.innerHTML = "";
  if (!courses.length) {
    sel.innerHTML = '<option value="">No courses — ask an admin to create one</option>';
    return;
  }
  for (const c of courses) {
    const o = document.createElement("option");
    o.value = c.id; o.textContent = `${c.code} — ${c.name}`;
    o.dataset.name = `${c.code} — ${c.name}`;
    sel.appendChild(o);
  }
}

// ---- Session flow ----
async function startSession() {
  const sel = $("courseSelect");
  const courseId = parseInt(sel.value, 10);
  if (!courseId) return;
  session = await api("/sessions", { method: "POST", body: { course_id: courseId } });
  $("sessId").textContent = session.id;
  $("courseName").textContent = sel.selectedOptions[0].dataset.name;
  $("captureCard").hidden = false;
  $("reviewCard").hidden = true;
  $("status").textContent = "";
  $("preview").hidden = true;
  $("uploadBtn").disabled = true;
  photoFile = null;
}

function onPhotoPick(e) {
  photoFile = e.target.files[0] || null;
  if (photoFile) {
    const img = $("preview");
    img.src = URL.createObjectURL(photoFile);
    img.hidden = false;
    $("uploadBtn").disabled = false;
  }
}

async function uploadPhoto() {
  if (!photoFile || !session) return;
  $("uploadBtn").disabled = true;
  $("status").textContent = "Uploading & recognising… this takes a few seconds.";
  const fd = new FormData();
  fd.append("file", photoFile);
  await api(`/sessions/${session.id}/photo`, { method: "POST", body: fd, form: true });
  pollSession();
}

function pollSession() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const s = await api(`/sessions/${session.id}`);
    if (s.state === "review" || s.state === "finalized") {
      clearInterval(pollTimer);
      session = s;
      renderReview(s);
    } else if (s.state === "failed") {
      clearInterval(pollTimer);
      $("status").textContent = "Processing failed: " + (s.error || "unknown error");
      $("uploadBtn").disabled = false;
    }
  }, 1500);
}

function renderReview(s) {
  $("status").textContent = "";
  $("reviewCard").hidden = false;
  $("facesDetected").textContent = s.faces_detected;
  $("rosterCount").textContent = s.records.length;
  const list = $("rosterList");
  list.innerHTML = "";
  for (const r of s.records) {
    const li = document.createElement("li");
    li.className = r.status;
    li.dataset.studentId = r.student_id;
    li.dataset.status = r.status;
    const conf = r.confidence != null ? ` <span class="conf">${(r.confidence * 100).toFixed(0)}%</span>` : "";
    li.innerHTML = `
      <span><span class="name">${r.full_name}</span> <span class="roll">${r.roll_no}</span>${conf}</span>
      <span class="tag">${r.status.toUpperCase()}</span>`;
    li.onclick = () => toggle(li);
    list.appendChild(li);
  }
  updatePresentCount();
}

function toggle(li) {
  const next = li.dataset.status === "present" ? "absent" : "present";
  li.dataset.status = next;
  li.className = next;
  li.querySelector(".tag").textContent = next.toUpperCase();
  updatePresentCount();
}

function updatePresentCount() {
  const items = document.querySelectorAll("#rosterList li");
  const present = [...items].filter((li) => li.dataset.status === "present").length;
  $("presentCount").textContent = present;
}

async function finalize() {
  const corrections = [...document.querySelectorAll("#rosterList li")].map((li) => ({
    student_id: parseInt(li.dataset.studentId, 10),
    status: li.dataset.status,
  }));
  const s = await api(`/sessions/${session.id}/corrections`, {
    method: "POST", body: { corrections },
  });
  session = s;
  $("finalMsg").textContent = `Finalised — ${s.records.filter((r) => r.status === "present").length} present recorded.`;
}

// ---- wire up ----
$("loginBtn").onclick = login;
$("logoutBtn").onclick = logout;
$("startBtn").onclick = startSession;
$("photoInput").onchange = onPhotoPick;
$("uploadBtn").onclick = uploadPhoto;
$("finalizeBtn").onclick = finalize;

if (token) showApp().catch(logout);
