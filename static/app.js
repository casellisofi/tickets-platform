const video = document.getElementById("video");
const startCameraButton = document.getElementById("start-camera");
const stopCameraButton = document.getElementById("stop-camera");
const cameraWarning = document.getElementById("camera-warning");
const manualWrapper = document.getElementById("manual-wrapper");
const manualInput = document.getElementById("manual-input");
const parseManualButton = document.getElementById("parse-manual");
const scanResult = document.getElementById("scan-result");
const detailNombre = document.getElementById("detail-nombre");
const detailDni = document.getElementById("detail-dni");
const detailId = document.getElementById("detail-id");
const detailEvento = document.getElementById("detail-evento");
const checkinButton = document.getElementById("checkin-button");
const scanMessage = document.getElementById("scan-message");
const refreshButton = document.getElementById("refresh-button");
const checkinList = document.getElementById("checkin-list");
const statsPresent = document.getElementById("stats-present");
const statsTotal = document.getElementById("stats-total");
const statsTotalWrap = document.getElementById("stats-total-wrap");
const resultFlash = document.getElementById("result-flash");
const resultFlashIcon = document.getElementById("result-flash-icon");
const resultFlashText = document.getElementById("result-flash-text");

let barcodeDetector = null;
let useJsQR = false;
let currentPayload = null;
let scanning = false;
let lastPayloadText = "";
let lastPayloadAt = 0;
let scanCanvas = null;
let scanCtx = null;

function setMessage(text, kind = "info") {
  scanMessage.textContent = text;
  scanMessage.style.background = kind === "error" ? "#ffe7e7" : kind === "success" ? "#e6f9e6" : "#eef4ff";
  scanMessage.style.color = kind === "error" ? "#8f2222" : kind === "success" ? "#1b5d25" : "#1a3567";
}

function hideMessage() {
  scanMessage.textContent = "";
}

function showResultFlash(ok, text) {
  resultFlashIcon.textContent = ok ? "✓" : "✗";
  resultFlashText.textContent = text;
  resultFlash.classList.remove("hidden", "success", "error");
  resultFlash.classList.add(ok ? "success" : "error");
  clearTimeout(showResultFlash._timer);
  showResultFlash._timer = setTimeout(() => {
    resultFlash.classList.add("hidden");
  }, 1400);
}

function showScanResult(payload) {
  currentPayload = payload;
  detailNombre.textContent = payload.nombre || "-";
  detailDni.textContent = payload.dni || "-";
  detailId.textContent = payload.id || "-";
  detailEvento.textContent = payload.evento || "-";
  scanResult.classList.remove("hidden");
  setMessage("Datos listos para marcar presente.");
}

function resetResult() {
  currentPayload = null;
  scanResult.classList.add("hidden");
  detailNombre.textContent = "-";
  detailDni.textContent = "-";
  detailId.textContent = "-";
  detailEvento.textContent = "-";
}

function validatePayload(payload) {
  if (!payload || typeof payload !== "object") return false;
  if (!payload.id || !payload.nombre || !payload.dni || !payload.evento) return false;
  return true;
}

async function initDetector() {
  // Preferí BarcodeDetector nativo (Chrome/Edge Android). Safari no lo tiene → jsQR.
  if (window.BarcodeDetector) {
    try {
      const supported = await BarcodeDetector.getSupportedFormats?.();
      if (!supported || supported.includes("qr_code")) {
        barcodeDetector = new BarcodeDetector({ formats: ["qr_code"] });
        return true;
      }
    } catch (error) {
      console.warn("BarcodeDetector falló, fallback a jsQR:", error);
    }
  }
  if (typeof jsQR === "function") {
    useJsQR = true;
    scanCanvas = document.createElement("canvas");
    scanCtx = scanCanvas.getContext("2d", { willReadFrequently: true });
    return true;
  }
  return false;
}

async function setupCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    video.srcObject = stream;
    video.setAttribute("playsinline", true);
    await video.play();
    return true;
  } catch (error) {
    console.warn("Cámara no disponible:", error);
    return false;
  }
}

async function scanFrame() {
  if (!scanning) return;
  try {
    let payloadText = null;
    if (barcodeDetector) {
      const barcodes = await barcodeDetector.detect(video);
      if (barcodes.length > 0) payloadText = barcodes[0].rawValue?.trim();
    } else if (useJsQR && video.readyState === video.HAVE_ENOUGH_DATA) {
      const w = video.videoWidth;
      const h = video.videoHeight;
      if (w && h) {
        scanCanvas.width = w;
        scanCanvas.height = h;
        scanCtx.drawImage(video, 0, 0, w, h);
        const imageData = scanCtx.getImageData(0, 0, w, h);
        const code = jsQR(imageData.data, w, h, { inversionAttempts: "dontInvert" });
        if (code) payloadText = code.data?.trim();
      }
    }

    if (payloadText) {
      const now = Date.now();
      // Si es el mismo QR, esperá 3s antes de re-procesar (evita spam).
      if (payloadText !== lastPayloadText || now - lastPayloadAt > 3000) {
        lastPayloadText = payloadText;
        lastPayloadAt = now;
        processPayloadText(payloadText);
      }
    }
  } catch (error) {
    console.warn("Error detectando QR:", error);
  }

  if (useJsQR) {
    setTimeout(scanFrame, 200); // jsQR es más caro, no escaneamos 60 veces/seg
  } else {
    requestAnimationFrame(scanFrame);
  }
}

async function startCamera() {
  hideMessage();
  resetResult();
  lastPayloadText = "";
  const cameraReady = await setupCamera();
  if (!cameraReady) {
    cameraWarning.classList.remove("hidden");
    manualWrapper.classList.remove("hidden");
    setMessage("Cámara no disponible. Usá el ingreso manual.", "error");
    return;
  }
  const detectorReady = await initDetector();
  if (!detectorReady) {
    cameraWarning.classList.remove("hidden");
    manualWrapper.classList.remove("hidden");
    setMessage("Este navegador no puede leer QR. Usá el ingreso manual.", "error");
    return;
  }
  cameraWarning.classList.add("hidden");
  manualWrapper.classList.add("hidden");
  scanning = true;
  scanFrame();
  setMessage("Cámara activa. Acercá el QR al cuadro.");
  startCameraButton.classList.add("hidden");
  stopCameraButton.classList.remove("hidden");
}

function stopCamera() {
  scanning = false;
  const stream = video.srcObject;
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
  }
  startCameraButton.classList.remove("hidden");
  stopCameraButton.classList.add("hidden");
  setMessage("Cámara detenida.");
}

function processPayloadText(text) {
  let payload = null;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    setMessage("El QR no contiene un JSON válido.", "error");
    return;
  }

  if (!validatePayload(payload)) {
    setMessage("El QR no tiene el formato esperado.", "error");
    return;
  }

  showScanResult(payload);
  // Para fluidez: auto-confirmar el check-in. Si preferís confirmación manual, comentá la línea.
  submitCheckin();
}

async function submitCheckin() {
  if (!currentPayload) {
    setMessage("No hay datos para marcar presente.", "error");
    return;
  }
  try {
    const response = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentPayload),
    });
    const result = await response.json();
    if (!result.success) {
      if (result.duplicate) {
        setMessage(`Ya estaba presente desde ${result.checkin_time}.`, "error");
        showResultFlash(false, "YA INGRESÓ");
      } else {
        setMessage(result.message || "No se pudo marcar presente.", "error");
        showResultFlash(false, "RECHAZADO");
      }
      // Limpiar después de un rato para permitir el próximo escaneo
      setTimeout(() => { resetResult(); hideMessage(); lastPayloadText = ""; }, 2500);
      return;
    }
    setMessage(`✓ Presente: ${currentPayload.nombre} — ${result.checkin_time}`, "success");
    showResultFlash(true, "OK");
    refreshCheckinList();
    setTimeout(() => { resetResult(); hideMessage(); lastPayloadText = ""; }, 2500);
  } catch (error) {
    setMessage("Error comunicándose con el servidor.", "error");
    console.error(error);
  }
}

function renderCheckinList(checkins) {
  if (!Array.isArray(checkins) || checkins.length === 0) {
    checkinList.innerHTML = "<div class=\"alert\">Aún no hay asistentes marcados.</div>";
    return;
  }
  checkinList.innerHTML = "";
  checkins.forEach((item) => {
    const row = document.createElement("div");
    row.className = "checkin-item";
    row.innerHTML = `
      <div>
        <strong>${item.nombre}</strong>
        <span>DNI: ${item.dni}</span>
      </div>
      <div>
        <strong>Entrada #${String(item.attendee_id).padStart(3, "0")}</strong>
      </div>
      <div>
        <strong>${item.checkin_time}</strong>
      </div>
    `;
    checkinList.appendChild(row);
  });
}

async function refreshCheckinList() {
  try {
    const response = await fetch("/api/checkins");
    const result = await response.json();
    if (result.success) {
      renderCheckinList(result.checkins);
      if (statsPresent) statsPresent.textContent = result.presentes ?? result.checkins.length;
      if (result.total != null && statsTotal && statsTotalWrap) {
        statsTotal.textContent = result.total;
        statsTotalWrap.classList.remove("hidden");
      }
    }
  } catch (error) {
    console.warn("Error al actualizar la lista:", error);
  }
}

startCameraButton.addEventListener("click", startCamera);
stopCameraButton.addEventListener("click", stopCamera);
parseManualButton.addEventListener("click", () => {
  const text = manualInput.value.trim();
  if (!text) {
    setMessage("Pegá el JSON del QR antes de procesar.", "error");
    return;
  }
  processPayloadText(text);
});
checkinButton.addEventListener("click", submitCheckin);
refreshButton.addEventListener("click", refreshCheckinList);

window.addEventListener("load", () => {
  refreshCheckinList();
  setTimeout(startCamera, 300);
});
