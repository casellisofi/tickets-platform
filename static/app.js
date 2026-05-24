const video = document.getElementById("video");
const startCameraButton = document.getElementById("start-camera");
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

let barcodeDetector = null;
let currentPayload = null;
let scanning = false;
let lastPayloadText = "";

function setMessage(text, kind = "info") {
  scanMessage.textContent = text;
  scanMessage.style.background = kind === "error" ? "#ffe7e7" : kind === "success" ? "#e6f9e6" : "#eef4ff";
  scanMessage.style.color = kind === "error" ? "#8f2222" : kind === "success" ? "#1b5d25" : "#1a3567";
}

function hideMessage() {
  scanMessage.textContent = "";
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
  if (!payload || typeof payload !== "object") {
    return false;
  }
  if (!payload.id || !payload.nombre || !payload.dni || !payload.evento) {
    return false;
  }
  return true;
}

async function initDetector() {
  if (!window.BarcodeDetector) {
    return false;
  }
  try {
    const supported = await BarcodeDetector.getSupportedFormats?.();
    if (supported && !supported.includes("qr_code")) {
      return false;
    }
    barcodeDetector = new BarcodeDetector({ formats: ["qr_code"] });
    return true;
  } catch (error) {
    return false;
  }
}

async function setupCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    video.srcObject = stream;
    await video.play();
    return true;
  } catch (error) {
    return false;
  }
}

async function scanFrame() {
  if (!scanning || !barcodeDetector) {
    return;
  }
  try {
    const barcodes = await barcodeDetector.detect(video);
    if (barcodes.length > 0) {
      const payloadText = barcodes[0].rawValue?.trim();
      if (payloadText && payloadText !== lastPayloadText) {
        lastPayloadText = payloadText;
        processPayloadText(payloadText);
      }
    }
  } catch (error) {
    console.warn("Error detectando QR:", error);
  }
  requestAnimationFrame(scanFrame);
}

async function startCamera() {
  hideMessage();
  resetResult();
  lastPayloadText = "";
  const cameraReady = await setupCamera();
  if (!cameraReady) {
    cameraWarning.classList.remove("hidden");
    manualWrapper.classList.remove("hidden");
    setMessage("Cámara no disponible. Usá el ingreso manual si es necesario.", "error");
    return;
  }
  const detectorReady = await initDetector();
  if (!detectorReady) {
    cameraWarning.classList.remove("hidden");
    manualWrapper.classList.remove("hidden");
    setMessage("El navegador no admite lectura QR automática. Usá el campo manual.", "error");
    return;
  }
  cameraWarning.classList.add("hidden");
  manualWrapper.classList.add("hidden");
  scanning = true;
  scanFrame();
  setMessage("Cámara activa. Acercá el QR delante de la cámara.");
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
    setMessage("El QR no tiene el formato esperado. Verificá la entrada.", "error");
    return;
  }

  showScanResult(payload);
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
      setMessage(result.message || "No se pudo marcar presente.", "error");
      return;
    }
    setMessage(`Presente registrado: ${result.checkin_time}`, "success");
    refreshCheckinList();
    resetResult();
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
        <span>${item.evento}</span>
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
    }
  } catch (error) {
    console.warn("Error al actualizar la lista:", error);
  }
}

startCameraButton.addEventListener("click", startCamera);
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
