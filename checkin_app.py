import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import openpyxl
except ImportError:
    openpyxl = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("CHECKIN_DB", os.path.join(BASE_DIR, "checkin.db"))
ATTENDEES_XLSX = os.environ.get(
    "CHECKIN_ATTENDEES_XLSX",
    os.path.join(BASE_DIR, "data", "asistentes.xlsx"),
)
SECRET_KEY = os.environ.get("SECRET_KEY", "evento_checkin_2026_secret")
USERNAME = os.environ.get("CHECKIN_USERNAME", "admin")
PASSWORD = os.environ.get("CHECKIN_PASSWORD", "evento123")
EVENT_NAME = os.environ.get("CHECKIN_EVENT_LABEL", "CONFERENCIA VOZ QUE CLAMA 2026")

# Argentina no tiene horario de verano; UTC-3 fijo evita depender de tzdata
# y muestra la hora correcta aunque el servidor (PythonAnywhere) esté en UTC.
LOCAL_TZ = timezone(timedelta(hours=-3))

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=SECRET_KEY,
    PERMANENT_SESSION_LIFETIME=timedelta(days=2),  # el staff no debe desloguearse en pleno evento
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def now_local():
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ DB
def get_db():
    db = getattr(g, "db", None)
    if db is None:
        # timeout: con varios celulares escribiendo a la vez, esperar el lock en vez de fallar.
        db = sqlite3.connect(DATABASE, timeout=15)
        db.row_factory = sqlite3.Row
        g.db = db
    return db


@app.teardown_appcontext
def close_db(exception=None):
    db = getattr(g, "db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE, timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendee_id INTEGER NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            dni TEXT NOT NULL,
            evento TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            checkin_time TEXT NOT NULL
        )
        """
    )
    db.commit()
    db.close()


# ----------------------------------------------------------- Asistentes
_attendees_cache = {"by_id": {}, "mtime": None}


def _norm_dni(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def load_attendees():
    """Carga asistentes desde el Excel. Cachea por mtime — si el archivo cambia, recarga.
    Si el Excel está bloqueado/a medio guardar, se sigue usando la última copia buena."""
    if openpyxl is None or not os.path.exists(ATTENDEES_XLSX):
        return _attendees_cache

    try:
        mtime = os.path.getmtime(ATTENDEES_XLSX)
    except OSError:
        return _attendees_cache

    if _attendees_cache["mtime"] == mtime and _attendees_cache["by_id"]:
        return _attendees_cache

    try:
        wb = openpyxl.load_workbook(ATTENDEES_XLSX, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception:
        return _attendees_cache

    if not rows:
        return _attendees_cache

    headers = [str(c).strip().lower() if c else "" for c in rows[0]]
    col_map = {}
    for i, h in enumerate(headers):
        if "nombre" in h or "name" in h:
            col_map.setdefault("nombre", i)
        elif "dni" in h or "documento" in h:
            col_map.setdefault("dni", i)
        elif "congreg" in h or "iglesia" in h:
            col_map.setdefault("congregacion", i)

    def cell(row, key, default_idx=None):
        idx = col_map.get(key, default_idx)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    by_id = {}
    for row_num, row in enumerate(rows[1:], start=2):
        if not row or not any(row):
            continue
        nombre = cell(row, "nombre", 0)
        if not nombre:
            continue
        attendee_id = row_num - 1  # mismo criterio que generar_entradas.py
        by_id[attendee_id] = {
            "id": attendee_id,
            "nombre": nombre,
            "dni": cell(row, "dni", 1),
            "congregacion": cell(row, "congregacion"),
        }

    _attendees_cache["by_id"] = by_id
    _attendees_cache["mtime"] = mtime
    return _attendees_cache


# ----------------------------------------------------------------- Auth
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "status": "auth", "message": "Sesión vencida. Volvé a ingresar."}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


# --------------------------------------------------------------- Check-in
def get_checkin_by_attendee(attendee_id):
    return get_db().execute(
        "SELECT * FROM checkins WHERE attendee_id = ?", (attendee_id,)
    ).fetchone()


def save_checkin(attendee_id, nombre, dni, evento, raw):
    """Inserta el ingreso. El UNIQUE(attendee_id) hace la operación atómica:
    si dos celulares escanean el mismo QR a la vez, solo uno gana."""
    db = get_db()
    now = now_local()
    try:
        db.execute(
            "INSERT INTO checkins (attendee_id, nombre, dni, evento, raw_payload, checkin_time) VALUES (?, ?, ?, ?, ?, ?)",
            (attendee_id, nombre, dni, evento, json.dumps(raw, ensure_ascii=False), now),
        )
        db.commit()
        return True, now
    except sqlite3.IntegrityError:
        db.rollback()
        existing = get_checkin_by_attendee(attendee_id)
        return False, existing["checkin_time"] if existing else now


def fail(status, message, code):
    return jsonify({"success": False, "status": status, "message": message}), code


@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("checkin"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        ok = hmac.compare_digest(username.encode(), USERNAME.encode()) & hmac.compare_digest(
            password.encode(), PASSWORD.encode()
        )
        if ok:
            session.clear()
            session["logged_in"] = True
            session.permanent = True
            return redirect(url_for("checkin"))
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error, evento=EVENT_NAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/checkin")
@login_required
def checkin():
    return render_template("checkin.html", evento=EVENT_NAME)


@app.route("/healthz")
def healthz():
    return "ok"


@app.route("/api/state")
@login_required
def api_state():
    """Lista completa + quién ya ingresó. Es lo que consultan todos los celulares cada pocos segundos."""
    attendees = load_attendees()["by_id"]
    rows = get_db().execute("SELECT attendee_id, nombre, dni, checkin_time FROM checkins").fetchall()
    checked = {r["attendee_id"]: r for r in rows}

    people = []
    for a in attendees.values():
        c = checked.get(a["id"])
        people.append({
            "id": a["id"],
            "nombre": a["nombre"],
            "dni": a["dni"],
            "congregacion": a["congregacion"],
            "ingreso": c["checkin_time"] if c else None,
        })
    # Ingresos que no están en la lista (p. ej. el Excel cambió o no hay lista cargada).
    for aid, c in checked.items():
        if aid not in attendees:
            people.append({"id": aid, "nombre": c["nombre"], "dni": c["dni"],
                           "congregacion": "", "ingreso": c["checkin_time"]})

    people.sort(key=lambda p: p["nombre"].lower())
    return jsonify({
        "success": True,
        "people": people,
        "presentes": len(checked),
        "total": len(attendees) or None,
        "server_time": now_local(),
    })


@app.route("/api/checkins")
@login_required
def api_checkins():
    """Compatibilidad: solo los presentes, más recientes primero."""
    rows = get_db().execute(
        "SELECT attendee_id, nombre, dni, checkin_time FROM checkins ORDER BY checkin_time DESC"
    ).fetchall()
    attendees = load_attendees()
    return jsonify({
        "success": True,
        "checkins": [dict(r) for r in rows],
        "presentes": len(rows),
        "total": len(attendees["by_id"]) or None,
    })


@app.route("/api/checkin", methods=["POST"])
@login_required
def api_checkin():
    """Registra un ingreso.
    - Desde el QR: {id, nombre, dni, evento} → se valida id + DNI contra la lista.
    - Manual desde la lista: {id, manual: true} → solo se valida que el id exista."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return fail("invalid", "No se recibió un JSON válido.", 400)

    try:
        attendee_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return fail("invalid", "QR inválido: el número de entrada no es válido.", 400)
    if attendee_id <= 0:
        return fail("invalid", "QR inválido: el número de entrada no es válido.", 400)

    manual = bool(payload.get("manual"))
    attendees = load_attendees()["by_id"]
    expected = attendees.get(attendee_id)

    if attendees:
        if not expected:
            return fail("invalid", f"La entrada #{attendee_id} no existe en la lista.", 404)
        if not manual:
            qr_dni = _norm_dni(payload.get("dni"))
            if not qr_dni:
                return fail("invalid", "QR inválido: no trae DNI.", 400)
            if _norm_dni(expected["dni"]) != qr_dni:
                return fail("invalid", "El DNI del QR no coincide con el de la lista. Entrada no válida.", 400)
        nombre, dni, congregacion = expected["nombre"], expected["dni"], expected["congregacion"]
    else:
        # Sin lista cargada no se puede verificar: se acepta lo que trae el QR.
        nombre = str(payload.get("nombre") or "").strip()
        dni = str(payload.get("dni") or "").strip()
        congregacion = ""
        if not nombre or not dni:
            return fail("invalid", "QR inválido: falta nombre o DNI.", 400)

    evento = str(payload.get("evento") or EVENT_NAME).strip()
    accepted, when = save_checkin(attendee_id, nombre, dni, evento, payload)

    person = {"id": attendee_id, "nombre": nombre, "dni": dni, "congregacion": congregacion}
    if not accepted:
        return jsonify({
            "success": False,
            "status": "duplicate",
            "duplicate": True,
            "message": "Esta entrada ya fue usada.",
            "checkin_time": when,
            "person": person,
        }), 409

    return jsonify({
        "success": True,
        "status": "ok",
        "message": "Ingreso registrado.",
        "checkin_time": when,
        "person": person,
    })


@app.route("/api/checkin/<int:attendee_id>", methods=["DELETE"])
@login_required
def api_undo_checkin(attendee_id):
    """Anula un ingreso marcado por error."""
    db = get_db()
    cur = db.execute("DELETE FROM checkins WHERE attendee_id = ?", (attendee_id,))
    db.commit()
    if cur.rowcount == 0:
        return fail("invalid", "Esa persona no estaba marcada como presente.", 404)
    return jsonify({"success": True, "status": "undone", "message": "Ingreso anulado."})


# Inicializa la DB al importar — necesario bajo WSGI (PythonAnywhere) donde no corre __main__.
init_db()


if __name__ == "__main__":
    if PASSWORD == "evento123" or SECRET_KEY == "evento_checkin_2026_secret":
        print("⚠️  Estás usando la contraseña/clave por defecto. Definí CHECKIN_PASSWORD y SECRET_KEY en .env.")
    app.run(host="0.0.0.0", port=5000, threaded=True)
