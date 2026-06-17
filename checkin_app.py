import json
import os
import sqlite3
from datetime import datetime
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

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = SECRET_KEY


def get_db():
    db = getattr(g, "db", None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        g.db = db
    return db


@app.teardown_appcontext
def close_db(exception=None):
    db = getattr(g, "db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
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


_attendees_cache = {"by_id": {}, "by_dni": {}, "mtime": None}


def load_attendees():
    """Carga asistentes desde el Excel. Cachea por mtime — si el archivo cambia, recarga."""
    if openpyxl is None or not os.path.exists(ATTENDEES_XLSX):
        return _attendees_cache

    try:
        mtime = os.path.getmtime(ATTENDEES_XLSX)
    except OSError:
        return _attendees_cache

    if _attendees_cache["mtime"] == mtime and _attendees_cache["by_id"]:
        return _attendees_cache

    wb = openpyxl.load_workbook(ATTENDEES_XLSX, read_only=True, data_only=True)
    ws = wb.active

    headers = [str(cell.value).strip().lower() if cell.value else "" for cell in ws[1]]
    col_map = {}
    for i, h in enumerate(headers):
        if "nombre" in h or "name" in h:
            col_map.setdefault("nombre", i)
        elif "dni" in h or "documento" in h:
            col_map.setdefault("dni", i)

    by_id = {}
    by_dni = {}
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not any(row):
            continue
        nombre = str(row[col_map.get("nombre", 0)] or "").strip()
        dni = str(row[col_map.get("dni", 1)] or "").strip()
        if not nombre:
            continue
        attendee_id = row_num - 1
        entry = {"id": attendee_id, "nombre": nombre, "dni": dni}
        by_id[attendee_id] = entry
        if dni:
            by_dni[dni] = entry

    wb.close()

    _attendees_cache["by_id"] = by_id
    _attendees_cache["by_dni"] = by_dni
    _attendees_cache["mtime"] = mtime
    return _attendees_cache


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def validate_payload(payload):
    """Verifica formato del QR. Devuelve (ok, message)."""
    if not isinstance(payload, dict):
        return False, "El QR no contiene un objeto válido."

    for field in ("id", "nombre", "dni", "evento"):
        if field not in payload:
            return False, f"Falta el campo '{field}' en el QR."

    try:
        attendee_id = int(payload["id"])
    except (TypeError, ValueError):
        return False, "El id del QR no es válido."

    if attendee_id <= 0:
        return False, "El id del QR no es válido."

    if not str(payload["nombre"]).strip() or not str(payload["dni"]).strip():
        return False, "El QR no tiene nombre o DNI."

    return True, ""


def verify_against_attendees(payload):
    """Verifica que el id+dni del QR coincida con la lista de asistentes. Devuelve (ok, message)."""
    attendees = load_attendees()
    if not attendees["by_id"]:
        # Sin lista cargada, no podemos verificar — aceptamos por compatibilidad
        return True, ""

    attendee_id = int(payload["id"])
    dni = str(payload["dni"]).strip()

    expected = attendees["by_id"].get(attendee_id)
    if not expected:
        return False, f"No existe asistente con entrada #{attendee_id} en la lista."

    if expected["dni"] and expected["dni"] != dni:
        return False, "El DNI del QR no coincide con el de la lista."

    return True, ""


def get_checkin_by_attendee(attendee_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM checkins WHERE attendee_id = ?",
        (attendee_id,),
    ).fetchone()
    return row


def save_checkin(payload):
    attendee_id = int(payload["id"])
    db = get_db()
    existing = get_checkin_by_attendee(attendee_id)
    if existing:
        return False, existing["checkin_time"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO checkins (attendee_id, nombre, dni, evento, raw_payload, checkin_time) VALUES (?, ?, ?, ?, ?, ?)",
        (
            attendee_id,
            str(payload["nombre"]).strip(),
            str(payload["dni"]).strip(),
            str(payload["evento"]).strip(),
            json.dumps(payload, ensure_ascii=False),
            now,
        ),
    )
    db.commit()
    return True, now


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
        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("checkin"))
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/checkin")
@login_required
def checkin():
    return render_template("checkin.html", evento=EVENT_NAME)


@app.route("/api/checkins")
@login_required
def api_checkins():
    db = get_db()
    rows = db.execute(
        "SELECT attendee_id, nombre, dni, evento, checkin_time FROM checkins ORDER BY checkin_time DESC"
    ).fetchall()
    checkins = [dict(row) for row in rows]
    attendees = load_attendees()
    total = len(attendees["by_id"]) if attendees["by_id"] else None
    return jsonify({
        "success": True,
        "checkins": checkins,
        "presentes": len(checkins),
        "total": total,
    })


@app.route("/api/checkin", methods=["POST"])
@login_required
def api_checkin():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "message": "No se recibió un JSON válido."}), 400

    ok, msg = validate_payload(payload)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    ok, msg = verify_against_attendees(payload)
    if not ok:
        return jsonify({"success": False, "message": msg}), 404

    accepted, timestamp = save_checkin(payload)
    if not accepted:
        return jsonify(
            {
                "success": False,
                "message": "Esta entrada ya fue marcada como presente.",
                "duplicate": True,
                "checkin_time": timestamp,
            }
        ), 409

    return jsonify(
        {
            "success": True,
            "message": "Asistente marcado como presente.",
            "checkin_time": timestamp,
        }
    )


# Inicializa la DB al importar — necesario bajo WSGI (PythonAnywhere) donde no corre __main__.
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
