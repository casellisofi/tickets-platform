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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "checkin.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "evento_checkin_2026_secret")
USERNAME = os.environ.get("CHECKIN_USERNAME", "admin")
PASSWORD = os.environ.get("CHECKIN_PASSWORD", "evento123")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = SECRET_KEY

CHECKIN_EVENT_LABEL = "Nombre del Evento"


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


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def validate_payload(payload):
    if not isinstance(payload, dict):
        return False

    if "id" not in payload or "nombre" not in payload or "dni" not in payload or "evento" not in payload:
        return False

    try:
        attendee_id = int(payload["id"])
    except (TypeError, ValueError):
        return False

    if attendee_id <= 0:
        return False

    if not str(payload["nombre"]).strip() or not str(payload["dni"]).strip():
        return False

    return True


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
    return render_template("checkin.html", evento=CHECKIN_EVENT_LABEL)


@app.route("/api/checkins")
@login_required
def api_checkins():
    db = get_db()
    rows = db.execute(
        "SELECT attendee_id, nombre, dni, evento, checkin_time FROM checkins ORDER BY checkin_time DESC"
    ).fetchall()
    checkins = [dict(row) for row in rows]
    return jsonify({"success": True, "checkins": checkins})


@app.route("/api/checkin", methods=["POST"])
@login_required
def api_checkin():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "message": "No se recibió un JSON válido."}), 400

    if not validate_payload(payload):
        return jsonify({"success": False, "message": "Formato de QR inválido. Asegurate de usar el QR del evento."}), 400

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


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
