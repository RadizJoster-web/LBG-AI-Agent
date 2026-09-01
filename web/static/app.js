"use strict";

const $ = (id) => document.getElementById(id);
const state = { rows: [], pollTimer: null };

const STATUS_META = {
  new:            { label: "BARU",        cls: "badge-new" },
  "disc-new":     { label: "DISC (baru)", cls: "badge-disc" },
  "disc-append":  { label: "DISC (+link)",cls: "badge-disc" },
  exists:         { label: "SUDAH ADA",   cls: "badge-exists" },
  blocked:        { label: "TERBLOKIR",   cls: "badge-blocked" },
};

function show(id) { $(id).classList.remove("hidden"); }
function hide(id) { $(id).classList.add("hidden"); }

function showError(msg) {
  const el = $("error");
  el.textContent = "Error: " + msg;
  show("error");
}

// ─────────────── scan ───────────────
async function scan() {
  hide("intro"); hide("results"); hide("error"); hide("progress");
  show("loading");
  $("btn-scan").disabled = true;
  try {
    const res = await fetch("/api/scan", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    state.rows = data.candidates;
    renderGrid(data);
    hide("loading");
    show("results");
  } catch (err) {
    hide("loading");
    showError(err.message);
  } finally {
    $("btn-scan").disabled = false;
  }
}

function renderGrid(data) {
  $("summary").textContent =
    `${data.count} game belum diproses · ${data.today} di-upload hari ini`;

  const onlyToday = $("f-only-today").checked;
  const hideExists = $("f-hide-exists").checked;
  const body = $("grid-body");
  body.innerHTML = "";

  let shown = 0;
  for (const row of state.rows) {
    if (onlyToday && !row.is_today) continue;
    if (hideExists && row.status === "exists") continue;
    shown++;

    const meta = STATUS_META[row.status] || { label: row.status, cls: "badge-exists" };
    const tr = document.createElement("tr");
    if (!row.selectable) tr.classList.add("not-selectable");
    if (row.is_today) tr.classList.add("row-today");

    const warns = (row.warnings || []).map((w) => `<span class="warn-text">⚠ ${w}</span>`).join("");

    tr.innerHTML = `
      <td class="col-check">
        <input type="checkbox" data-fid="${row.file_id}"
          ${row.selectable ? "" : "disabled"} ${row.default_checked ? "checked" : ""}>
      </td>
      <td><strong>${escapeHtml(row.title || row.file_name)}</strong>${warns}</td>
      <td>${escapeHtml(row.platform)}</td>
      <td>${escapeHtml(row.region || "")}</td>
      <td>${escapeHtml(row.disc || "")}</td>
      <td>${escapeHtml(row.file_size || "")}</td>
      <td>${escapeHtml(row.uploaded_date || "?")}${row.is_today ? " ·<strong>hari ini</strong>" : ""}</td>
      <td><span class="badge ${meta.cls}">${meta.label}</span></td>
    `;
    body.appendChild(tr);
  }

  if (shown === 0) {
    body.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:1.4rem">
      Tidak ada baris yang cocok dengan filter.</td></tr>`;
  }

  body.querySelectorAll("input[type=checkbox]").forEach((cb) =>
    cb.addEventListener("change", updateSelectedCount)
  );
  updateSelectedCount();
}

function selectedFileIds() {
  return [...document.querySelectorAll("#grid-body input[type=checkbox]:checked")]
    .map((cb) => cb.dataset.fid);
}

function updateSelectedCount() {
  const n = selectedFileIds().length;
  $("selected-count").textContent = `${n} dipilih`;
  $("btn-upload").disabled = n === 0;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ─────────────── upload ───────────────
async function upload(fileIds) {
  if (!fileIds.length) return;
  hide("results");
  show("progress");
  hide("progress-done");
  $("log").innerHTML = "";
  $("bar-fill").style.width = "0%";
  $("progress-label").textContent = `0 / ${fileIds.length}`;

  try {
    const res = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_ids: fileIds }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    pollJob(data.job_id, 0);
  } catch (err) {
    showError(err.message);
    show("results");
    hide("progress");
  }
}

function pollJob(jobId, after) {
  clearTimeout(state.pollTimer);
  fetch(`/api/ingest/${jobId}?after=${after}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) throw new Error(data.error);

      for (const ev of data.events) appendLog(ev);
      const pct = data.total ? Math.round((data.done / data.total) * 100) : 0;
      $("bar-fill").style.width = pct + "%";
      $("progress-label").textContent = `${data.done} / ${data.total}`;

      if (data.finished) {
        finishJob(data.summary);
      } else {
        state.pollTimer = setTimeout(() => pollJob(jobId, data.event_count), 500);
      }
    })
    .catch((err) => {
      appendLog({ level: "error", message: "Polling gagal: " + err.message });
      state.pollTimer = setTimeout(() => pollJob(jobId, after), 1500);
    });
}

function appendLog(ev) {
  const li = document.createElement("li");
  if (ev.level && ev.level !== "info") li.className = ev.level;
  li.textContent = ev.message;
  const log = $("log");
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}

function finishJob(summary) {
  $("bar-fill").style.width = "100%";
  const s = summary || {};
  let txt = `✅ ${s.created || 0} game dibuat · ${s.disc_appended || 0} link disc ditambahkan · ${s.skipped || 0} dilewati.`;
  if (s.errors && s.errors.length) txt += `\n⚠ ${s.errors.length} error — lihat log di atas.`;
  $("done-summary").textContent = txt;
  show("progress-done");
}

// ─────────────── wire up ───────────────
$("btn-scan").addEventListener("click", scan);
$("btn-rescan").addEventListener("click", scan);
$("f-only-today").addEventListener("change", () => renderGrid({
  count: state.rows.length,
  today: state.rows.filter((r) => r.is_today).length,
}));
$("f-hide-exists").addEventListener("change", () => renderGrid({
  count: state.rows.length,
  today: state.rows.filter((r) => r.is_today).length,
}));
$("check-all").addEventListener("change", (e) => {
  document.querySelectorAll("#grid-body input[type=checkbox]:not(:disabled)")
    .forEach((cb) => { cb.checked = e.target.checked; });
  updateSelectedCount();
});
$("btn-upload").addEventListener("click", () => upload(selectedFileIds()));
$("btn-upload-today").addEventListener("click", () => {
  const ids = state.rows.filter((r) => r.selectable && r.is_today).map((r) => r.file_id);
  if (!ids.length) { alert("Tidak ada game baru yang di-upload hari ini."); return; }
  upload(ids);
});
