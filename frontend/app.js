/**
 * AttendAI — Full SPA (Teacher + Admin)
 * Vanilla JS, no framework. Communicates with the FastAPI backend.
 */
"use strict";

const API = "";   // same origin

// ── State ──────────────────────────────────────────────
let _token = localStorage.getItem("token") || "";
let _role  = localStorage.getItem("role")  || "";
let _me    = null;

let currentSession   = null;  // current take-attendance session
let photoFile        = null;
let pollTimer        = null;
let studentsOffset   = 0;
const PAGE_SIZE      = 100;

let rosterCourseId   = null;  // course whose roster is open in slide panel

// ── DOM helpers ────────────────────────────────────────
const $ = id => document.getElementById(id);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls)  e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

// ── API helper ─────────────────────────────────────────
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (_token) headers["Authorization"] = "Bearer " + _token;
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

// ── Toast notifications ────────────────────────────────
function toast(msg, type = "info") {
  const t = el("div", `toast ${type}`);
  const icon = type === "success" ? "✓" : type === "error" ? "✕" : "ℹ";
  t.innerHTML = `<strong>${icon}</strong> ${msg}`;
  $("toastContainer").appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

// ── Modal system ───────────────────────────────────────
function openModal(title, bodyHTML, footerHTML) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = bodyHTML;
  $("modalFooter").innerHTML = footerHTML;
  $("modalOverlay").hidden = false;
}
function closeModal() { $("modalOverlay").hidden = true; }
$("modalClose").onclick = closeModal;
$("modalOverlay").onclick = e => { if (e.target === $("modalOverlay")) closeModal(); };

// ── Auth ───────────────────────────────────────────────
$("loginForm").onsubmit = async e => {
  e.preventDefault();
  const errEl = $("loginErr");
  errEl.hidden = true;
  const btn = $("loginBtn");
  btn.disabled = true;
  $("loginBtnText").hidden = true;
  $("loginSpinner").hidden = false;
  const form = new URLSearchParams({
    username: $("loginEmail").value,
    password: $("loginPassword").value,
  });
  try {
    const res = await fetch(API + "/auth/login", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    _token = data.access_token;
    _role  = data.role;
    localStorage.setItem("token", _token);
    localStorage.setItem("role",  _role);
    await showApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    $("loginBtnText").hidden = false;
    $("loginSpinner").hidden = true;
  }
};

function logout() {
  _token = ""; _role = ""; _me = null;
  localStorage.clear();
  if (pollTimer) clearInterval(pollTimer);
  $("appShell").hidden = true;
  $("loginScreen").hidden = false;
}
$("logoutBtn").onclick = logout;

async function showApp() {
  $("loginScreen").hidden = true;
  $("appShell").hidden = false;

  _me = await api("/auth/me");
  $("userFullName").textContent = _me.full_name || _me.email;
  $("userRole").textContent     = _me.role;
  $("userAvatar").textContent   = (_me.full_name || _me.email)[0].toUpperCase();

  // Show admin UI elements
  if (_me.role === "admin") {
    document.querySelectorAll(".admin-only").forEach(e => e.style.display = "");
  }

  activateView("take-attendance");
  loadCourses();
  populateSessionCourseFilter();
}

// ── Navigation ──────────────────────────────────────────
function activateView(viewId) {
  // Deactivate all
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  const view = $(`view-${viewId}`);
  if (view) view.classList.add("active");

  const nav = document.querySelector(`[data-view="${viewId}"]`);
  if (nav) nav.classList.add("active");

  // Page title
  const titles = {
    "take-attendance": "Take Attendance",
    "my-sessions":     "Sessions",
    "admin-courses":   "Courses",
    "admin-students":  "Students",
    "admin-users":     "Users",
    "admin-reports":   "Reports",
  };
  $("pageTitle").textContent = titles[viewId] || viewId;

  // Load data for each view
  if (viewId === "my-sessions")    loadMySessions();
  if (viewId === "admin-courses")  loadAdminCourses();
  if (viewId === "admin-students") { studentsOffset = 0; loadAdminStudents(false); }
  if (viewId === "admin-users")    loadAdminUsers();
  if (viewId === "admin-reports")  loadReportCourseSelect();
}

document.querySelectorAll(".nav-item").forEach(nav => {
  nav.addEventListener("click", e => {
    e.preventDefault();
    activateView(nav.dataset.view);
  });
});

// ══════════════════════════════════════════════════════════
// TEACHER FLOW: Take Attendance
// ══════════════════════════════════════════════════════════

let courses = [];

async function loadCourses() {
  try {
    courses = await api("/courses");
    const sel = $("courseSelect");
    sel.innerHTML = "";
    if (!courses.length) {
      sel.innerHTML = '<option value="">No courses — ask an admin to create one</option>';
      $("startBtn").disabled = true;
      return;
    }
    for (const c of courses) {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = `${c.code} — ${c.name}`;
      sel.appendChild(o);
    }
    $("startBtn").disabled = false;
  } catch (err) {
    toast("Failed to load courses: " + err.message, "error");
  }
}

$("courseSelect").onchange = () => {
  $("startBtn").disabled = !$("courseSelect").value;
};

$("startBtn").onclick = async () => {
  const courseId = parseInt($("courseSelect").value, 10);
  if (!courseId) return;
  try {
    $("startBtn").disabled = true;
    currentSession = await api("/sessions", { method: "POST", body: { course_id: courseId } });
    const course   = courses.find(c => c.id === courseId);
    $("sessIdBadge").textContent    = currentSession.id;
    $("courseNameLabel").textContent = course ? `${course.code} — ${course.name}` : "";
    // Reset UI
    $("photoInput").value    = "";
    $("photoPreview").hidden = true;
    $("uploadZoneInner").hidden = false;
    $("uploadBtn").disabled  = true;
    $("progressRow").hidden  = true;
    $("cardReview").hidden   = true;
    $("finalMsg").hidden     = true;
    $("cardCapture").hidden  = false;
    // Step wizard
    setStep(1);
    photoFile = null;
    toast("Session started!", "success");
  } catch (err) {
    toast("Error: " + err.message, "error");
    $("startBtn").disabled = false;
  }
};

function setStep(n) {
  for (let i = 1; i <= 4; i++) {
    const s = $(`step${i}`);
    s.classList.remove("active", "done");
    if (i < n)  s.classList.add("done");
    if (i === n) s.classList.add("active");
  }
}

// Photo pick
$("photoInput").onchange = e => {
  photoFile = e.target.files[0] || null;
  if (!photoFile) return;
  const img = $("photoPreview");
  img.src    = URL.createObjectURL(photoFile);
  img.hidden = false;
  $("uploadZoneInner").hidden = true;
  $("uploadBtn").disabled = false;
  setStep(2);
};

// Drag-and-drop on upload zone
const zone = $("uploadZone");
zone.addEventListener("dragover", e => { e.preventDefault(); zone.style.borderColor = "var(--accent)"; });
zone.addEventListener("dragleave", ()  => { zone.style.borderColor = ""; });
zone.addEventListener("drop", e => {
  e.preventDefault();
  zone.style.borderColor = "";
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith("image/")) {
    photoFile = file;
    $("photoPreview").src = URL.createObjectURL(file);
    $("photoPreview").hidden = false;
    $("uploadZoneInner").hidden = true;
    $("uploadBtn").disabled = false;
    setStep(2);
  }
});

$("cancelSessionBtn").onclick = () => {
  currentSession = null;
  photoFile = null;
  $("cardCapture").hidden = true;
  $("cardReview").hidden  = true;
  $("startBtn").disabled  = false;
  setStep(1);
};

$("uploadBtn").onclick = async () => {
  if (!photoFile || !currentSession) return;
  $("uploadBtn").disabled = true;
  $("progressRow").hidden = false;
  animateProgress();
  const fd = new FormData();
  fd.append("file", photoFile);
  try {
    await api(`/sessions/${currentSession.id}/photo`, { method: "POST", body: fd, form: true });
    setStep(3);
    pollSession();
  } catch (err) {
    toast("Upload failed: " + err.message, "error");
    $("uploadBtn").disabled = false;
    $("progressRow").hidden = true;
  }
};

function animateProgress() {
  let pct = 0;
  const fill  = $("progressFill");
  const label = $("progressLabel");
  const msgs  = ["Uploading…", "Detecting faces…", "Matching roster…", "Almost done…"];
  let msgIdx  = 0;
  const iv = setInterval(() => {
    pct = Math.min(pct + (Math.random() * 8), 90);
    fill.style.width = pct + "%";
    if (pct > msgIdx * 22 && msgIdx < msgs.length) {
      label.textContent = msgs[msgIdx++];
    }
  }, 500);
  // Store so we can stop it
  $("progressFill")._iv = iv;
}

function stopProgress() {
  clearInterval($("progressFill")._iv);
  $("progressFill").style.width = "100%";
}

function pollSession() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const s = await api(`/sessions/${currentSession.id}`);
      if (s.state === "review" || s.state === "finalized") {
        clearInterval(pollTimer);
        stopProgress();
        currentSession = s;
        renderReview(s);
      } else if (s.state === "failed") {
        clearInterval(pollTimer);
        stopProgress();
        toast("Processing failed: " + (s.error || "unknown"), "error");
        $("uploadBtn").disabled = false;
      }
    } catch {}
  }, 1500);
}

function renderReview(s) {
  $("progressRow").hidden = true;
  $("cardReview").hidden  = false;
  $("finalMsg").hidden    = true;
  setStep(3);

  const present = s.records.filter(r => r.status === "present").length;
  const absent  = s.records.length - present;
  $("statFaces").textContent   = s.faces_detected;
  $("statPresent").textContent = present;
  $("statAbsent").textContent  = absent;
  $("statTotal").textContent   = s.records.length;

  const list = $("rosterList");
  list.innerHTML = "";
  for (const r of s.records) {
    list.appendChild(makeRosterItem(r));
  }

  // Export CSV button (only for finalized)
  const exportBtn = $("exportSessionBtn");
  if (s.state === "finalized") {
    exportBtn.href   = `/reports/sessions/${s.id}/attendance.csv`;
    exportBtn.hidden = false;
  } else {
    exportBtn.hidden = true;
  }

  $("finalizeBtn").hidden = (s.state === "finalized");
  if (s.state === "finalized") {
    const msg = $("finalMsg");
    msg.textContent = `✓ Finalised — ${present} present recorded.`;
    msg.hidden = false;
    setStep(4);
  }
}

function makeRosterItem(r) {
  const li = el("li", `roster-item ${r.status}`);
  li.dataset.studentId = r.student_id;
  li.dataset.status    = r.status;
  li.dataset.name      = r.full_name.toLowerCase();
  li.dataset.roll      = r.roll_no.toLowerCase();
  const conf = r.confidence != null ? `<span class="roster-conf">${(r.confidence * 100).toFixed(0)}% match</span>` : "";
  const tag  = r.method === "auto" ? "" : r.method === "liveness_fail"
    ? `<span class="badge badge-red" title="Failed anti-spoofing check">⚠ spoof?</span>`
    : `<span class="badge badge-amber">manual</span>`;
  const liveBadge = r.liveness_score != null
    ? `<span class="roster-conf" title="Liveness score">live ${(r.liveness_score * 100).toFixed(0)}%</span>`
    : "";
  li.innerHTML = `
    <div class="roster-item-left">
      <span class="roster-name">${r.full_name}</span>
      <div class="roster-meta"><span>${r.roll_no}</span>${conf}${liveBadge}${tag}</div>
    </div>
    <span class="badge ${r.status === 'present' ? 'badge-green' : 'badge-red'}" id="tag-${r.student_id}">
      ${r.status.toUpperCase()}
    </span>`;
  li.onclick = () => toggleRoster(li);
  return li;
}

function toggleRoster(li) {
  if (currentSession?.state === "finalized") return;
  const next = li.dataset.status === "present" ? "absent" : "present";
  li.dataset.status = next;
  li.className = `roster-item ${next}`;
  const tag = li.querySelector(".badge");
  tag.className = `badge ${next === "present" ? "badge-green" : "badge-red"}`;
  tag.textContent = next.toUpperCase();
  updateStatCounts();
}

function updateStatCounts() {
  const items = document.querySelectorAll("#rosterList .roster-item");
  let p = 0;
  items.forEach(li => { if (li.dataset.status === "present") p++; });
  $("statPresent").textContent = p;
  $("statAbsent").textContent  = items.length - p;
}

// Roster search
$("rosterSearch").oninput = e => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#rosterList .roster-item").forEach(li => {
    const match = !q || li.dataset.name.includes(q) || li.dataset.roll.includes(q);
    li.classList.toggle("hidden-item", !match);
  });
};

// Finalize
$("finalizeBtn").onclick = async () => {
  const corrections = [...document.querySelectorAll("#rosterList .roster-item")].map(li => ({
    student_id: parseInt(li.dataset.studentId, 10),
    status: li.dataset.status,
  }));
  try {
    $("finalizeBtn").disabled = true;
    const s = await api(`/sessions/${currentSession.id}/corrections`, {
      method: "POST", body: { corrections },
    });
    currentSession = s;
    renderReview(s);
    toast("Attendance finalised!", "success");
  } catch (err) {
    toast("Error: " + err.message, "error");
    $("finalizeBtn").disabled = false;
  }
};

// ══════════════════════════════════════════════════════════
// MY SESSIONS view
// ══════════════════════════════════════════════════════════
let mySessionsOffset = 0;
const SESSIONS_PAGE = 50;
let mySessionsFilters = { course_id: "", state: "" };

async function loadMySessions(append = false) {
  if (!append) mySessionsOffset = 0;

  const tbody = $("sessionsTableBody");
  const empty = $("sessionsEmpty");
  if (!append) {
    tbody.innerHTML = "";
    empty.hidden = true;
  }

  try {
    let qs = `?limit=${SESSIONS_PAGE}&offset=${mySessionsOffset}`;
    if (mySessionsFilters.course_id) qs += `&course_id=${mySessionsFilters.course_id}`;
    if (mySessionsFilters.state)     qs += `&state=${mySessionsFilters.state}`;

    const rows = await api(`/sessions${qs}`);

    if (!rows.length && !append) {
      empty.hidden = false;
      $("sessionsLoadMore").hidden = true;
      return;
    }

    for (const s of rows) {
      tbody.appendChild(makeSessionRow(s));
    }
    mySessionsOffset += rows.length;
    $("sessionsLoadMore").hidden = rows.length < SESSIONS_PAGE;
  } catch (err) {
    toast("Error loading sessions: " + err.message, "error");
  }
}

function makeSessionRow(s) {
  const tr = el("tr");
  const date = new Date(s.started_at);
  const dateStr = date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  const timeStr = date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

  const stateColors = {
    created:    "badge-muted",
    processing: "badge-blue",
    review:     "badge-amber",
    finalized:  "badge-green",
    failed:     "badge-red",
  };
  const stateLabels = {
    created:    "Created",
    processing: "Processing…",
    review:     "Awaiting Review",
    finalized:  "Finalised",
    failed:     "Failed",
  };

  const badge = `<span class="badge ${stateColors[s.state] || 'badge-muted'}">${stateLabels[s.state] || s.state}</span>`;

  const actions = [];
  if (s.state === "review" || s.state === "finalized") {
    actions.push(`<button class="btn btn-ghost btn-sm" data-action="sess-review" data-id="${s.id}">Review</button>`);
  }
  if (s.state === "finalized") {
    actions.push(`<a class="btn btn-ghost btn-sm" href="/reports/sessions/${s.id}/attendance.csv">CSV</a>`);
  }

  tr.innerHTML = `
    <td><div>${dateStr}</div><div class="text-muted" style="font-size:0.78rem">${timeStr}</div></td>
    <td><strong>${s.course_code}</strong> <span class="text-muted">${s.course_name}</span></td>
    <td>${badge}</td>
    <td>${s.faces_detected}</td>
    <td class="text-muted" style="font-size:0.82rem">${s.teacher_name}</td>
    <td style="display:flex;gap:6px;flex-wrap:wrap">${actions.join("")}</td>`;
  return tr;
}

// Session filter controls
document.addEventListener("DOMContentLoaded", () => {
  const stateFilter  = $("sessionStateFilter");
  const courseFilter = $("sessionCourseFilter");
  if (stateFilter)  stateFilter.onchange  = () => { mySessionsFilters.state     = stateFilter.value;  loadMySessions(false); };
  if (courseFilter) courseFilter.onchange = () => { mySessionsFilters.course_id = courseFilter.value; loadMySessions(false); };
});

$("sessionsLoadMore") && ($("sessionsLoadMore").onclick = () => loadMySessions(true));

// Review action from sessions table (event delegation)
$("sessionsTableBody").onclick = async e => {
  const btn = e.target.closest("[data-action='sess-review']");
  if (!btn) return;
  const sid = parseInt(btn.dataset.id, 10);
  try {
    const s = await api(`/sessions/${sid}`);
    currentSession = s;
    activateView("take-attendance");
    // Show the review card directly
    $("cardCapture").hidden = true;
    renderReview(s);
    toast("Session loaded for review", "info");
  } catch (err) {
    toast("Could not load session: " + err.message, "error");
  }
};

// Populate course filter in sessions view when courses load
async function populateSessionCourseFilter() {
  const sel = $("sessionCourseFilter");
  if (!sel) return;
  try {
    const cs = await api("/courses");
    for (const c of cs) {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = `${c.code} — ${c.name}`;
      sel.appendChild(o);
    }
  } catch {}
}

// ══════════════════════════════════════════════════════════
// ADMIN: COURSES
// ══════════════════════════════════════════════════════════
let allCourses = [];

async function loadAdminCourses() {
  try {
    allCourses = await api("/courses");
    renderCoursesTable(allCourses);
  } catch (err) {
    toast("Error loading courses: " + err.message, "error");
  }
}

function renderCoursesTable(data) {
  const tbody = $("coursesTableBody");
  const empty = $("coursesEmpty");
  tbody.innerHTML = "";
  empty.hidden = data.length > 0;
  for (const c of data) {
    const tr = el("tr");
    tr.innerHTML = `
      <td><strong>${c.code}</strong></td>
      <td>${c.name}</td>
      <td><span class="badge badge-muted">${c.department || "—"}</span></td>
      <td><span class="badge badge-blue">${c.enrolled_count}</span></td>
      <td>
        <button class="btn btn-ghost btn-sm" data-action="roster"  data-id="${c.id}" data-code="${c.code}" data-name="${c.name}">Roster</button>
        <button class="btn btn-ghost btn-sm" data-action="edit-c"  data-id="${c.id}" data-code="${c.code}" data-name="${c.name}" data-dept="${c.department}">Edit</button>
        <button class="btn btn-danger btn-sm" data-action="del-c"  data-id="${c.id}" data-code="${c.code}">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

$("courseSearch").oninput = e => {
  const q = e.target.value.toLowerCase();
  renderCoursesTable(allCourses.filter(c =>
    c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
  ));
};

$("addCourseBtn").onclick = () => {
  openModal("Add Course", `
    <div class="field-group"><label>Code</label><input id="mCode" placeholder="CS301" /></div>
    <div class="field-group"><label>Name</label><input id="mName" placeholder="Data Structures" /></div>
    <div class="field-group"><label>Department</label><input id="mDept" placeholder="CSE" /></div>
  `, `
    <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    <button class="btn btn-primary" id="saveCourseBtn">Create</button>
  `);
  $("saveCourseBtn").onclick = async () => {
    try {
      await api("/courses", { method: "POST", body: {
        code: $("mCode").value.trim(),
        name: $("mName").value.trim(),
        department: $("mDept").value.trim(),
      }});
      closeModal(); toast("Course created", "success"); loadAdminCourses();
    } catch (err) { toast(err.message, "error"); }
  };
};

// Course table actions (event delegation)
$("coursesTableBody").onclick = async e => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const { action, id, code, name, dept } = btn.dataset;
  const cid = parseInt(id, 10);

  if (action === "roster") {
    openRosterPanel(cid, `${code} — ${name}`);
  }
  if (action === "edit-c") {
    openModal(`Edit: ${code}`, `
      <div class="field-group"><label>Name</label><input id="mName" value="${name}" /></div>
      <div class="field-group"><label>Department</label><input id="mDept" value="${dept || ""}" /></div>
    `, `
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" id="saveCourseEditBtn">Save</button>
    `);
    $("saveCourseEditBtn").onclick = async () => {
      try {
        await api(`/courses/${cid}`, { method: "PATCH", body: {
          name: $("mName").value.trim(), department: $("mDept").value.trim()
        }});
        closeModal(); toast("Course updated", "success"); loadAdminCourses();
      } catch (err) { toast(err.message, "error"); }
    };
  }
  if (action === "del-c") {
    if (!confirm(`Delete course "${code}"? This will remove all its sessions and attendance records.`)) return;
    try {
      await api(`/courses/${cid}`, { method: "DELETE" });
      toast("Course deleted", "success"); loadAdminCourses();
    } catch (err) { toast(err.message, "error"); }
  }
};

// ── Roster panel ─────────────────────────────────────────
async function openRosterPanel(courseId, title) {
  rosterCourseId = courseId;
  $("rosterPanelTitle").textContent = title + " · Roster";
  $("rosterPanel").hidden = false;
  $("rosterAddInput").value = "";
  await refreshRoster(courseId);
}

$("closeRosterBtn").onclick = () => { $("rosterPanel").hidden = true; };

$("rosterAddBtn").onclick = async () => {
  if (!rosterCourseId) return;
  const raw    = $("rosterAddInput").value;
  const rolls  = raw.split(",").map(r => r.trim()).filter(Boolean);
  if (!rolls.length) return;
  try {
    await api(`/courses/${rosterCourseId}/roster`, { method: "POST", body: { roll_nos: rolls } });
    $("rosterAddInput").value = "";
    toast("Students added to roster", "success");
    await refreshRoster(rosterCourseId);
    loadAdminCourses();  // refresh enrolled_count
  } catch (err) { toast(err.message, "error"); }
};

async function refreshRoster(courseId) {
  const tbody = $("rosterTableBody");
  const empty = $("rosterEmpty");
  tbody.innerHTML = "";
  const roster = await api(`/courses/${courseId}/roster`);
  empty.hidden = roster.length > 0;
  for (const s of roster) {
    const tr = el("tr");
    tr.innerHTML = `
      <td><code>${s.roll_no}</code></td>
      <td>${s.full_name}</td>
      <td>${s.biometric_consent
        ? `<span class="badge badge-green">Yes</span>`
        : `<span class="badge badge-red">No</span>`
      }</td>
      <td>${s.has_embedding
        ? `<span class="badge badge-green">Enrolled</span>`
        : `<span class="badge badge-muted">None</span>`
      }</td>
      <td>
        <button class="btn btn-danger btn-sm" data-action="rm-roster" data-sid="${s.id}">Remove</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

$("rosterTableBody").onclick = async e => {
  const btn = e.target.closest("[data-action='rm-roster']");
  if (!btn) return;
  const sid = parseInt(btn.dataset.sid, 10);
  if (!confirm("Remove this student from the roster?")) return;
  try {
    await api(`/courses/${rosterCourseId}/roster/${sid}`, { method: "DELETE" });
    toast("Removed from roster", "success");
    refreshRoster(rosterCourseId);
    loadAdminCourses();
  } catch (err) { toast(err.message, "error"); }
};

// ══════════════════════════════════════════════════════════
// ADMIN: STUDENTS
// ══════════════════════════════════════════════════════════
let allStudents = [];
let studentSearchQuery = "";

async function loadAdminStudents(append = false) {
  if (!append) studentsOffset = 0;
  try {
    const qs   = `?limit=${PAGE_SIZE}&offset=${studentsOffset}&search=${encodeURIComponent(studentSearchQuery)}`;
    const rows = await api(`/students${qs}`);
    if (!append) {
      allStudents = rows;
    } else {
      allStudents = [...allStudents, ...rows];
    }
    studentsOffset += rows.length;
    renderStudentsTable();
    $("studentsLoadMore").hidden = rows.length < PAGE_SIZE;
  } catch (err) {
    toast("Error: " + err.message, "error");
  }
}

function renderStudentsTable() {
  const tbody = $("studentsTableBody");
  const empty = $("studentsEmpty");
  tbody.innerHTML = "";
  empty.hidden = allStudents.length > 0;
  for (const s of allStudents) {
    const tr = el("tr");
    tr.innerHTML = `
      <td><code>${s.roll_no}</code></td>
      <td>${s.full_name}</td>
      <td><span class="badge badge-muted">${s.department || "—"}</span></td>
      <td>${s.biometric_consent
        ? `<span class="badge badge-green" title="${s.consent_recorded_at ? new Date(s.consent_recorded_at).toLocaleDateString() : ''}">Granted</span>`
        : `<span class="badge badge-red">Pending</span>`
      }</td>
      <td>${s.has_embedding
        ? `<span class="badge badge-green">✓</span>`
        : `<span class="badge badge-muted">—</span>`
      }</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        ${!s.biometric_consent
          ? `<button class="btn btn-ghost btn-sm" data-action="consent" data-id="${s.id}" data-name="${s.full_name}">Grant Consent</button>`
          : `<button class="btn btn-ghost btn-sm" data-action="revoke"  data-id="${s.id}" data-name="${s.full_name}">Revoke</button>`
        }
        <button class="btn btn-ghost btn-sm" data-action="edit-s" data-id="${s.id}"
          data-roll="${s.roll_no}" data-name="${s.full_name}" data-dept="${s.department}">Edit</button>
        <button class="btn btn-danger btn-sm" data-action="del-s" data-id="${s.id}" data-roll="${s.roll_no}">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

let studentSearchTimer = null;
$("studentSearch").oninput = e => {
  studentSearchQuery = e.target.value;
  clearTimeout(studentSearchTimer);
  studentSearchTimer = setTimeout(() => loadAdminStudents(false), 350);
};

$("studentsLoadMore").onclick = () => loadAdminStudents(true);

$("addStudentBtn").onclick = () => {
  openModal("Add Student", `
    <div class="field-group"><label>Roll No</label><input id="mRoll" placeholder="2021CSE001" /></div>
    <div class="field-group"><label>Full Name</label><input id="mName" placeholder="Priya Sharma" /></div>
    <div class="field-group"><label>Department</label><input id="mDept" placeholder="CSE" /></div>
    <div class="field-group" style="flex-direction:row;align-items:center;gap:10px">
      <input type="checkbox" id="mConsent" style="width:auto" />
      <label for="mConsent" style="margin:0">Biometric consent granted (DPDP Act 2023)</label>
    </div>
  `, `
    <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    <button class="btn btn-primary" id="saveStudentBtn">Create</button>
  `);
  $("saveStudentBtn").onclick = async () => {
    try {
      await api("/students", { method: "POST", body: {
        roll_no: $("mRoll").value.trim(),
        full_name: $("mName").value.trim(),
        department: $("mDept").value.trim(),
        biometric_consent: $("mConsent").checked,
      }});
      closeModal(); toast("Student created", "success"); loadAdminStudents(false);
    } catch (err) { toast(err.message, "error"); }
  };
};

$("studentsTableBody").onclick = async e => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const { action, id, name, roll, dept } = btn.dataset;
  const sid = parseInt(id, 10);

  if (action === "consent") {
    if (!confirm(`Record biometric consent for ${name}?\n\nConfirm this student has given written consent per DPDP Act 2023.`)) return;
    try {
      await api(`/students/${sid}/consent`, { method: "POST", body: { granted: true } });
      toast("Consent recorded", "success"); loadAdminStudents(false);
    } catch (err) { toast(err.message, "error"); }
  }
  if (action === "revoke") {
    if (!confirm(`Revoke consent for ${name}?\n\nThis will also delete their face embedding.`)) return;
    try {
      await api(`/students/${sid}/consent`, { method: "POST", body: { granted: false } });
      toast("Consent revoked and embedding deleted", "success"); loadAdminStudents(false);
    } catch (err) { toast(err.message, "error"); }
  }
  if (action === "edit-s") {
    openModal(`Edit: ${name}`, `
      <div class="field-group"><label>Full Name</label><input id="mName" value="${name}" /></div>
      <div class="field-group"><label>Department</label><input id="mDept" value="${dept || ""}" /></div>
    `, `
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" id="saveStudentEditBtn">Save</button>
    `);
    $("saveStudentEditBtn").onclick = async () => {
      try {
        await api(`/students/${sid}`, { method: "PATCH", body: {
          full_name: $("mName").value.trim(), department: $("mDept").value.trim()
        }});
        closeModal(); toast("Student updated", "success"); loadAdminStudents(false);
      } catch (err) { toast(err.message, "error"); }
    };
  }
  if (action === "del-s") {
    if (!confirm(`Delete student ${roll}? This permanently removes all their data.`)) return;
    try {
      await api(`/students/${sid}`, { method: "DELETE" });
      toast("Student deleted", "success"); loadAdminStudents(false);
    } catch (err) { toast(err.message, "error"); }
  }
};

// ══════════════════════════════════════════════════════════
// ADMIN: USERS
// ══════════════════════════════════════════════════════════
async function loadAdminUsers() {
  try {
    const users = await api("/auth/users");
    const tbody = $("usersTableBody");
    tbody.innerHTML = "";
    for (const u of users) {
      const isMe = _me && u.id === _me.id;
      const tr   = el("tr");
      tr.innerHTML = `
        <td><strong>${u.full_name || "—"}</strong>${isMe ? ' <span class="badge badge-purple">You</span>' : ""}</td>
        <td>${u.email}</td>
        <td><span class="badge ${u.role === 'admin' ? 'badge-amber' : 'badge-blue'}">${u.role}</span></td>
        <td><span class="badge ${u.is_active ? 'badge-green' : 'badge-muted'}">${u.is_active ? "Active" : "Disabled"}</span></td>
        <td style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" data-action="edit-u" data-id="${u.id}"
            data-name="${u.full_name}" data-role="${u.role}">Edit</button>
          ${!isMe && u.is_active
            ? `<button class="btn btn-danger btn-sm" data-action="del-u" data-id="${u.id}" data-name="${u.full_name}">Disable</button>`
            : ""}
        </td>`;
      tbody.appendChild(tr);
    }
  } catch (err) {
    toast("Error: " + err.message, "error");
  }
}

$("addUserBtn").onclick = () => {
  openModal("Add User", `
    <div class="field-group"><label>Email</label><input id="mEmail" type="email" placeholder="teacher@dtu.ac.in" /></div>
    <div class="field-group"><label>Full Name</label><input id="mName" placeholder="Dr. Anita Singh" /></div>
    <div class="field-group"><label>Password (min 8 chars)</label><input id="mPw" type="password" /></div>
    <div class="field-group"><label>Role</label>
      <select id="mRole"><option value="teacher">Teacher</option><option value="admin">Admin</option></select>
    </div>
  `, `
    <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    <button class="btn btn-primary" id="saveUserBtn">Create</button>
  `);
  $("saveUserBtn").onclick = async () => {
    try {
      await api("/auth/users", { method: "POST", body: {
        email: $("mEmail").value.trim(),
        full_name: $("mName").value.trim(),
        password: $("mPw").value,
        role: $("mRole").value,
      }});
      closeModal(); toast("User created", "success"); loadAdminUsers();
    } catch (err) { toast(err.message, "error"); }
  };
};

$("usersTableBody").onclick = async e => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const { action, id, name, role } = btn.dataset;
  const uid = parseInt(id, 10);

  if (action === "edit-u") {
    openModal(`Edit: ${name}`, `
      <div class="field-group"><label>Full Name</label><input id="mName" value="${name || ""}" /></div>
      <div class="field-group"><label>Role</label>
        <select id="mRole">
          <option value="teacher" ${role==='teacher'?'selected':''}>Teacher</option>
          <option value="admin"   ${role==='admin'?'selected':''}>Admin</option>
        </select>
      </div>
    `, `
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" id="saveUserEditBtn">Save</button>
    `);
    $("saveUserEditBtn").onclick = async () => {
      try {
        await api(`/auth/users/${uid}`, { method: "PATCH", body: {
          full_name: $("mName").value.trim(),
          role: $("mRole").value,
        }});
        closeModal(); toast("User updated", "success"); loadAdminUsers();
      } catch (err) { toast(err.message, "error"); }
    };
  }
  if (action === "del-u") {
    if (!confirm(`Disable user ${name}? They will no longer be able to log in.`)) return;
    try {
      await api(`/auth/users/${uid}`, { method: "DELETE" });
      toast("User disabled", "success"); loadAdminUsers();
    } catch (err) { toast(err.message, "error"); }
  }
};

// ══════════════════════════════════════════════════════════
// ADMIN: REPORTS
// ══════════════════════════════════════════════════════════
async function loadReportCourseSelect() {
  const sel = $("reportCourse");
  sel.innerHTML = '<option value="">Select course…</option>';
  try {
    const cs = await api("/courses");
    for (const c of cs) {
      const o = document.createElement("option");
      o.value       = c.id;
      o.textContent = `${c.code} — ${c.name}`;
      sel.appendChild(o);
    }
  } catch {}
}

$("runReportBtn").onclick = async () => {
  const cid  = $("reportCourse").value;
  if (!cid) { toast("Select a course first", "info"); return; }
  const from = $("reportFrom").value;
  const to   = $("reportTo").value;
  let qs     = `?`;
  if (from) qs += `from_date=${from}&`;
  if (to)   qs += `to_date=${to}&`;

  try {
    $("runReportBtn").disabled = true;
    const data = await api(`/reports/courses/${cid}/attendance${qs}`);
    $("reportEmpty").hidden = true;
    $("reportResults").hidden = false;

    // Summary chips
    const avgPct = data.students.length
      ? (data.students.reduce((s, r) => s + r.percentage, 0) / data.students.length).toFixed(1)
      : "—";
    $("reportSummary").innerHTML = `
      <div class="report-summary-item"><div class="val">${data.total_sessions}</div><div class="lbl">Sessions</div></div>
      <div class="report-summary-item"><div class="val">${data.students.length}</div><div class="lbl">Students</div></div>
      <div class="report-summary-item"><div class="val">${avgPct}%</div><div class="lbl">Avg Attendance</div></div>
      <div class="report-summary-item"><div class="val">${data.students.filter(s=>s.percentage<75).length}</div><div class="lbl">Below 75%</div></div>
    `;

    const tbody = $("reportTableBody");
    tbody.innerHTML = "";
    for (const s of data.students) {
      const cls = s.percentage >= 75 ? "fill-green" : s.percentage >= 50 ? "fill-amber" : "fill-red";
      const tr  = el("tr");
      tr.innerHTML = `
        <td><code>${s.roll_no}</code></td>
        <td>${s.full_name}</td>
        <td>${s.total_sessions}</td>
        <td>${s.attended}</td>
        <td><strong style="color:${s.percentage>=75?'var(--green)':s.percentage>=50?'var(--amber)':'var(--red)'}">${s.percentage}%</strong></td>
        <td>
          <div class="attendance-bar">
            <div class="attendance-fill ${cls}" style="width:${s.percentage}%"></div>
          </div>
        </td>`;
      tbody.appendChild(tr);
    }

    // CSV download button
    const dlBtn = $("downloadReportBtn");
    dlBtn.href   = `/reports/courses/${cid}/attendance.csv${qs}`;
    dlBtn.hidden = false;
  } catch (err) {
    toast("Error: " + err.message, "error");
  } finally {
    $("runReportBtn").disabled = false;
  }
};

// ══════════════════════════════════════════════════════════
// BOOT
// ══════════════════════════════════════════════════════════
if (_token) {
  showApp().catch(() => logout());
}
