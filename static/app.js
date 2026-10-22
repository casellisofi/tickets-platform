/* Check-in por QR — pensado para varios celulares a la vez.
 * - Cámara en vivo (BarcodeDetector nativo o jsQR) + foto como alternativa (funciona sin HTTPS).
 * - El servidor es la única fuente de verdad: todos los celulares consultan /api/state cada pocos segundos.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    video: $("video"),
    cameraStart: $("camera-start"),
    cameraStartText: $("camera-start-text"),
    btnStart: $("btn-start"),
    btnTorch: $("btn-torch"),
    btnFlip: $("btn-flip"),
    hint: $("scan-hint"),
    insecure: $("insecure-warning"),
    photoInput: $("photo-input"),
    lastScansList: $("last-scans-list"),
    statsPresent: $("stats-present"),
    statsTotal: $("stats-total"),
    statsTotalWrap: $("stats-total-wrap"),
    progressBar: $("progress-bar"),
    connDot: $("conn-dot"),
    search: $("search"),
    people: $("people"),
    peopleEmpty: $("people-empty"),
    countAll: $("count-all"),
    countIn: $("count-in"),
    countOut: $("count-out"),
    result: $("result"),
    resultIcon: $("result-icon"),
    resultTitle: $("result-title"),
    resultName: $("result-name"),
    resultMeta: $("result-meta"),
    resultDetail: $("result-detail"),
    sheet: $("sheet"),
    sheetName: $("sheet-name"),
    sheetMeta: $("sheet-meta"),
    sheetStatus: $("sheet-status"),
    sheetAction: $("sheet-action"),
    toast: $("toast"),
  };

  const POLL_MS = 5000;
  const SAME_QR_COOLDOWN_MS = 4000;

  const state = {
    people: [],
    filter: "all",
    query: "",
    view: "view-scan",
    facing: "environment",
    stream: null,
    detector: null,
    scanning: false,
    busy: false,
    resultOpen: false,
    lastText: "",
    lastAt: 0,
    scanTimer: null,
    resultTimer: null,
    sheetPerson: null,
    canvas: null,
    ctx: null,
    audio: null,
    wakeLock: null,
  };

  /* ------------------------------------------------------------ utils */
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function norm(text) {
    return String(text || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function timeOnly(ts) {
    return ts ? ts.slice(11, 16) : "";
  }

  function toast(text, ms = 2600) {
    els.toast.textContent = text;
    els.toast.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => els.toast.classList.add("hidden"), ms);
  }

  /* ------------------------------------------------- sonido / vibración */
  function unlockAudio() {
    if (state.audio) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) state.audio = new Ctx();
    } catch (e) { /* sin audio */ }
    if (state.audio && state.audio.state === "suspended") state.audio.resume();
  }

  function beep(freq, start, dur, vol = 0.25, type = "sine") {
    const a = state.audio;
    if (!a) return;
    const osc = a.createOscillator();
    const gain = a.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol, a.currentTime + start);
    gain.gain.exponentialRampToValueAtTime(0.001, a.currentTime + start + dur);
    osc.connect(gain).connect(a.destination);
    osc.start(a.currentTime + start);
    osc.stop(a.currentTime + start + dur + 0.02);
  }

  function feedback(kind) {
    try {
      if (kind === "ok") {
        beep(880, 0, 0.12); beep(1320, 0.12, 0.18);
        navigator.vibrate && navigator.vibrate(80);
      } else if (kind === "dup") {
        beep(520, 0, 0.14, 0.3, "square"); beep(520, 0.2, 0.14, 0.3, "square");
        navigator.vibrate && navigator.vibrate([120, 80, 120]);
      } else {
        beep(200, 0, 0.35, 0.3, "sawtooth");
        navigator.vibrate && navigator.vibrate([300]);
      }
    } catch (e) { /* ignorar */ }
  }

  /* ------------------------------------------------ resultado (semáforo) */
  function showResult(kind, title, person, detail) {
    clearTimeout(state.resultTimer);
    state.resultOpen = true;
    els.result.className = "result " + kind;
    els.resultIcon.textContent = kind === "ok" ? "✓" : kind === "dup" ? "!" : "✕";
    els.resultTitle.textContent = title;
    els.resultName.textContent = person ? person.nombre : "";
    els.resultMeta.textContent = person
      ? [person.congregacion, person.dni ? "DNI " + person.dni : ""].filter(Boolean).join(" · ")
      : "";
    els.resultDetail.textContent = detail || "";
    feedback(kind);
    state.resultTimer = setTimeout(closeResult, kind === "ok" ? 2200 : 3800);
  }

  function closeResult() {
    clearTimeout(state.resultTimer);
    if (!state.resultOpen) return;
    state.resultOpen = false;
    els.result.className = "result hidden";
    state.lastAt = Date.now(); // arranca el enfriamiento del mismo QR desde que se cierra
  }

  /* ------------------------------------------------------------- red */
  async function api(path, options = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 10000);
    try {
      const res = await fetch(path, {
        ...options,
        signal: ctrl.signal,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      });
      if (res.status === 401) {
        window.location.href = "/login";
        throw new Error("auth");
      }
      let data = null;
      try { data = await res.json(); } catch (e) { data = { success: false, message: "Respuesta inválida del servidor." }; }
      return { status: res.status, data };
    } finally {
      clearTimeout(timer);
    }
  }

  function setConnected(ok) {
    els.connDot.classList.toggle("off", !ok);
    els.connDot.title = ok ? "Conectado" : "Sin conexión con el servidor";
  }

  /* ------------------------------------------------------- estado/lista */
  async function refreshState() {
    try {
      const { data } = await api("/api/state");
      if (!data.success) throw new Error("state");
      state.people = data.people;
      setConnected(true);
      renderAll(data);
    } catch (e) {
      if (e.message !== "auth") setConnected(false);
    }
  }

  function renderAll(meta) {
    const present = state.people.filter((p) => p.ingreso).length;
    const total = (meta && meta.total) || state.people.length;
    els.statsPresent.textContent = present;
    els.statsTotal.textContent = total || "–";
    els.progressBar.style.width = total ? Math.min(100, (present / total) * 100) + "%" : "0";
    els.countAll.textContent = state.people.length;
    els.countIn.textContent = present;
    els.countOut.textContent = state.people.length - present;
    renderLastScans();
    renderPeople();
  }

  function renderLastScans() {
    const last = state.people
      .filter((p) => p.ingreso)
      .sort((a, b) => (a.ingreso < b.ingreso ? 1 : -1))
      .slice(0, 6);
    els.lastScansList.innerHTML = last.length
      ? last.map((p) => `<li><b>${esc(p.nombre)}</b><span>${esc(timeOnly(p.ingreso))}</span></li>`).join("")
      : '<li><b style="color:var(--muted);font-weight:500">Todavía no ingresó nadie</b></li>';
  }

  function matches(person) {
    if (state.filter === "in" && !person.ingreso) return false;
    if (state.filter === "out" && person.ingreso) return false;
    const q = state.query.trim();
    if (!q) return true;
    const digits = q.replace(/\D/g, "");
    const hay = norm(person.nombre + " " + person.congregacion);
    const words = norm(q).split(/\s+/).filter(Boolean);
    if (words.every((w) => hay.includes(w))) return true;
    return digits.length >= 3 && String(person.dni).replace(/\D/g, "").includes(digits);
  }

  function renderPeople() {
    const rows = state.people.filter(matches);
    els.peopleEmpty.classList.toggle("hidden", rows.length > 0);
    els.people.innerHTML = rows.map((p) => `
      <li class="person" data-id="${p.id}">
        <div class="person-main">
          <div class="person-name">${esc(p.nombre)}</div>
          <div class="person-sub">${esc([p.congregacion, p.dni ? "DNI " + p.dni : ""].filter(Boolean).join(" · "))}</div>
        </div>
        ${p.ingreso
          ? `<span class="badge badge-in">Ingresó ${esc(timeOnly(p.ingreso))}</span>`
          : '<span class="badge badge-out">Falta</span>'}
      </li>`).join("");
  }

  /* --------------------------------------------------------- check-in */
  function applyLocalCheckin(id, time) {
    const p = state.people.find((x) => x.id === id);
    if (p) { p.ingreso = time; renderAll({ total: state.people.length }); }
  }

  async function submitCheckin(body) {
    if (state.busy) return;
    state.busy = true;
    try {
      const { status, data } = await api("/api/checkin", { method: "POST", body: JSON.stringify(body) });
      setConnected(true);
      if (data.success) {
        applyLocalCheckin(data.person.id, data.checkin_time);
        showResult("ok", "BIENVENIDO/A", data.person, "Ingreso registrado " + timeOnly(data.checkin_time));
      } else if (data.status === "duplicate") {
        applyLocalCheckin(data.person.id, data.checkin_time);
        showResult("dup", "YA INGRESÓ", data.person, "Entró a las " + timeOnly(data.checkin_time));
      } else {
        showResult("bad", status === 404 ? "NO ESTÁ EN LA LISTA" : "ENTRADA NO VÁLIDA", null, data.message);
      }
      refreshState();
    } catch (e) {
      if (e.message === "auth") return;
      setConnected(false);
      showResult("bad", "SIN CONEXIÓN", null, "No se pudo registrar. Revisá la señal y volvé a escanear.");
      state.lastText = ""; // permitir reintentar el mismo QR enseguida
    } finally {
      state.busy = false;
    }
  }

  function handleQrText(text) {
    let payload = null;
    try { payload = JSON.parse(text); } catch (e) { /* no es JSON */ }
    if (!payload || typeof payload !== "object" || payload.id == null) {
      showResult("bad", "QR NO VÁLIDO", null, "Este código no es una entrada del evento.");
      return;
    }
    submitCheckin(payload);
  }

  /* --------------------------------------------------------- cámara */
  function insecureContext() {
    return !window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia;
  }

  async function initDetector() {
    if (state.detector || state.ctx) return true;
    if ("BarcodeDetector" in window) {
      try {
        const formats = (await BarcodeDetector.getSupportedFormats?.()) || ["qr_code"];
        if (formats.includes("qr_code")) {
          state.detector = new BarcodeDetector({ formats: ["qr_code"] });
          return true;
        }
      } catch (e) { /* cae a jsQR */ }
    }
    if (typeof jsQR === "function") {
      state.canvas = document.createElement("canvas");
      state.ctx = state.canvas.getContext("2d", { willReadFrequently: true });
      return true;
    }
    return false;
  }

  function showCameraOverlay(text, buttonLabel) {
    els.cameraStartText.textContent = text;
    els.btnStart.textContent = buttonLabel || "Activar cámara";
    els.btnStart.classList.toggle("hidden", !buttonLabel);
    els.cameraStart.classList.remove("hidden");
  }

  async function startCamera() {
    if (state.stream) return;
    if (insecureContext()) {
      els.insecure.classList.remove("hidden");
      showCameraOverlay("Cámara en vivo no disponible en esta conexión.", null);
      return;
    }
    els.insecure.classList.add("hidden");
    if (!(await initDetector())) {
      showCameraOverlay("Este navegador no puede leer QR. Usá «Escanear con foto» o la Lista.", null);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: state.facing },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      state.stream = stream;
      els.video.srcObject = stream;
      await els.video.play().catch(() => {});
      els.cameraStart.classList.add("hidden");
      setupTrackControls(stream.getVideoTracks()[0]);
      requestWakeLock();
      state.scanning = true;
      scheduleScan(0);
    } catch (e) {
      const denied = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      showCameraOverlay(
        denied
          ? "Permiso de cámara denegado. Habilitalo en los ajustes del navegador y tocá el botón."
          : "No se pudo abrir la cámara (¿otra app la está usando?).",
        "Reintentar"
      );
    }
  }

  function stopCamera() {
    state.scanning = false;
    clearTimeout(state.scanTimer);
    if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
    state.stream = null;
    els.video.srcObject = null;
    releaseWakeLock();
  }

  function setupTrackControls(track) {
    let caps = {};
    try { caps = track.getCapabilities ? track.getCapabilities() : {}; } catch (e) { /* iOS */ }
    els.btnTorch.classList.toggle("hidden", !caps.torch);
    els.btnTorch.classList.remove("on");
    els.btnTorch.dataset.on = "0";
    els.btnFlip.classList.remove("hidden");
  }

  async function toggleTorch() {
    const track = state.stream && state.stream.getVideoTracks()[0];
    if (!track) return;
    const on = els.btnTorch.dataset.on !== "1";
    try {
      await track.applyConstraints({ advanced: [{ torch: on }] });
      els.btnTorch.dataset.on = on ? "1" : "0";
      els.btnTorch.classList.toggle("on", on);
    } catch (e) {
      toast("Este celular no permite usar la linterna.");
    }
  }

  async function flipCamera() {
    state.facing = state.facing === "environment" ? "user" : "environment";
    stopCamera();
    await startCamera();
  }

  async function requestWakeLock() {
    try {
      if ("wakeLock" in navigator && !state.wakeLock) {
        state.wakeLock = await navigator.wakeLock.request("screen");
        state.wakeLock.addEventListener("release", () => { state.wakeLock = null; });
      }
    } catch (e) { /* no crítico */ }
  }

  function releaseWakeLock() {
    try { state.wakeLock && state.wakeLock.release(); } catch (e) { /* ignorar */ }
    state.wakeLock = null;
  }

  function scheduleScan(delay) {
    clearTimeout(state.scanTimer);
    if (state.scanning) state.scanTimer = setTimeout(scanFrame, delay);
  }

  function decodeCanvas(source, maxSide) {
    const w0 = source.videoWidth || source.naturalWidth || source.width;
    const h0 = source.videoHeight || source.naturalHeight || source.height;
    if (!w0 || !h0) return null;
    const scale = Math.min(1, maxSide / Math.max(w0, h0));
    const w = Math.round(w0 * scale);
    const h = Math.round(h0 * scale);
    state.canvas.width = w;
    state.canvas.height = h;
    state.ctx.drawImage(source, 0, 0, w, h);
    const img = state.ctx.getImageData(0, 0, w, h);
    const code = jsQR(img.data, w, h, { inversionAttempts: "attemptBoth" });
    return code ? code.data : null;
  }

  // fallback=true (fotos): si el detector nativo no halla nada, prueba también con jsQR.
  async function detectFrom(source, maxSide, fallback) {
    if (state.detector) {
      const found = await state.detector.detect(source);
      if (found.length) return (found[0].rawValue || "").trim();
      if (!fallback) return null;
    }
    if (typeof jsQR === "function") {
      if (!state.ctx) {
        state.canvas = document.createElement("canvas");
        state.ctx = state.canvas.getContext("2d", { willReadFrequently: true });
      }
      const text = decodeCanvas(source, maxSide);
      return text ? text.trim() : null;
    }
    return null;
  }

  async function scanFrame() {
    if (!state.scanning) return;
    const paused = document.hidden || state.resultOpen || state.busy || state.view !== "view-scan";
    if (!paused && els.video.readyState >= 2) {
      try {
        const text = await detectFrom(els.video, 720, false);
        if (text) {
          const now = Date.now();
          if (text !== state.lastText || now - state.lastAt > SAME_QR_COOLDOWN_MS) {
            state.lastText = text;
            state.lastAt = now;
            handleQrText(text);
          }
        }
      } catch (e) { /* frame ilegible: seguir */ }
    }
    scheduleScan(state.detector ? 120 : 160);
  }

  /* ------------------------------------------------ escaneo por foto */
  async function loadImage(file) {
    if (window.createImageBitmap) {
      try { return await createImageBitmap(file); } catch (e) { /* cae a <img> */ }
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = URL.createObjectURL(file);
    });
  }

  async function scanPhoto(file) {
    unlockAudio();
    toast("Leyendo la foto…", 1500);
    try {
      if (!(await initDetector())) { toast("Este navegador no puede leer QR."); return; }
      const img = await loadImage(file);
      let text = null;
      for (const side of [1600, 1000, 600]) {
        text = await detectFrom(img, side, true);
        if (text) break;
      }
      if (!text) { toast("No se encontró un QR. Probá de nuevo, más cerca y con buena luz.", 3500); return; }
      state.lastText = text;
      state.lastAt = Date.now();
      handleQrText(text);
    } catch (e) {
      toast("No se pudo leer la foto.");
    }
  }

  /* ---------------------------------------------------- hoja de acciones */
  function openSheet(person) {
    state.sheetPerson = person;
    els.sheetName.textContent = person.nombre;
    els.sheetMeta.textContent = [person.congregacion, person.dni ? "DNI " + person.dni : "", "Entrada #" + person.id]
      .filter(Boolean).join(" · ");
    if (person.ingreso) {
      els.sheetStatus.textContent = "Ya ingresó a las " + timeOnly(person.ingreso);
      els.sheetAction.textContent = "Anular ingreso";
      els.sheetAction.className = "btn btn-danger btn-block";
      els.sheetAction.dataset.mode = "undo";
    } else {
      els.sheetStatus.textContent = "Todavía no ingresó";
      els.sheetAction.textContent = "Marcar ingreso";
      els.sheetAction.className = "btn btn-primary btn-block";
      els.sheetAction.dataset.mode = "in";
    }
    els.sheetAction.disabled = false;
    els.sheet.classList.remove("hidden");
  }

  function closeSheet() {
    els.sheet.classList.add("hidden");
    state.sheetPerson = null;
  }

  async function sheetAction() {
    const person = state.sheetPerson;
    if (!person) return;
    const mode = els.sheetAction.dataset.mode;
    els.sheetAction.disabled = true;
    try {
      if (mode === "in") {
        closeSheet();
        await submitCheckin({ id: person.id, manual: true });
      } else {
        if (!window.confirm("¿Anular el ingreso de " + person.nombre + "?")) { els.sheetAction.disabled = false; return; }
        const { data } = await api("/api/checkin/" + person.id, { method: "DELETE" });
        closeSheet();
        toast(data.success ? "Ingreso anulado." : data.message);
        refreshState();
      }
    } catch (e) {
      if (e.message !== "auth") toast("Sin conexión. Intentá de nuevo.");
      els.sheetAction.disabled = false;
    }
  }

  /* ------------------------------------------------------ navegación */
  function setView(id) {
    state.view = id;
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === id));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === id));
    if (id === "view-scan") {
      startCamera();
    } else {
      stopCamera(); // ahorra batería y libera la cámara
    }
    document.querySelector(".app-main").scrollTop = 0;
  }

  /* ---------------------------------------------------------- eventos */
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { unlockAudio(); setView(t.dataset.view); }));
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === c));
    state.filter = c.dataset.filter;
    renderPeople();
  }));
  els.search.addEventListener("input", () => { state.query = els.search.value; renderPeople(); });
  els.people.addEventListener("click", (ev) => {
    const li = ev.target.closest(".person");
    if (!li) return;
    const person = state.people.find((p) => p.id === Number(li.dataset.id));
    if (person) openSheet(person);
  });
  els.sheet.addEventListener("click", (ev) => { if (ev.target.hasAttribute("data-close")) closeSheet(); });
  els.sheetAction.addEventListener("click", sheetAction);
  els.result.addEventListener("click", closeResult);
  els.btnStart.addEventListener("click", () => { unlockAudio(); startCamera(); });
  els.btnTorch.addEventListener("click", toggleTorch);
  els.btnFlip.addEventListener("click", flipCamera);
  els.photoInput.addEventListener("change", () => {
    const file = els.photoInput.files && els.photoInput.files[0];
    els.photoInput.value = "";
    if (file) scanPhoto(file);
  });
  document.addEventListener("touchstart", unlockAudio, { once: true, passive: true });
  document.addEventListener("click", unlockAudio, { once: true });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    refreshState();
    if (state.view === "view-scan") {
      if (!state.stream) startCamera();
      else requestWakeLock();
    }
  });
  window.addEventListener("online", () => { setConnected(true); refreshState(); });
  window.addEventListener("offline", () => setConnected(false));

  /* ------------------------------------------------------------ inicio */
  refreshState();
  setInterval(() => { if (!document.hidden) refreshState(); }, POLL_MS);
  startCamera();
})();
