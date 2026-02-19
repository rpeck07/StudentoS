# app.py
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
import bcrypt
import os
import json
import time
from uuid import uuid4
from datetime import date, timedelta

ENGINE_OK = True
try:
    from engine import (
        Assignment,
        parse_date,
        load_assignments,
        rank_assignments_by_danger,
        hours_next_days,
        workload_text_bars,
        gpa_impact_estimates,
        dashboard_summary,
    )
except Exception as e:
    ENGINE_OK = False
    ENGINE_IMPORT_ERROR = str(e)

BASE_DIR = os.path.dirname(__file__)
USERS_FILE = os.path.join(BASE_DIR, "users.json")

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=30)

jwt = JWTManager(app)

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "DELETE", "OPTIONS"],
)


# ----------------------------
# Helpers
# ----------------------------

def _read_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_users(users: dict) -> None:
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _user_data_file(username: str) -> str:
    safe = username.replace("/", "_").replace("..", "").replace(" ", "_")
    return os.path.join(BASE_DIR, f"data_{safe}.json")


def _read_json_file(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _write_json_file(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _load_user_assignments(username: str):
    """Load a user's assignments from JSON and convert to engine Assignment objects."""
    raw = _read_json_file(_user_data_file(username))
    assignments = []
    for x in raw:
        try:
            assignments.append(Assignment(
                name=str(x["name"]),
                weight_percent=float(x["weightPercent"]),
                due_date=parse_date(str(x["dueDate"])),
                confidence=int(x["confidence"]),
                estimated_hours=float(x["estHours"]),
            ))
        except Exception:
            pass
    return assignments


# ----------------------------
# Health + home
# ----------------------------

@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "engine_ok": ENGINE_OK,
    }), 200


@app.get("/")
def home():
    today = date.today()

    if not ENGINE_OK:
        return (
            f"<h1>StudentOS is running ✅</h1>"
            f"<p>Engine import failed:</p>"
            f"<pre>{ENGINE_IMPORT_ERROR}</pre>",
            200,
        )

    try:
        assignments = load_assignments(os.path.join(BASE_DIR, "assignments.json"))
    except Exception:
        assignments = []

    danger_rows = rank_assignments_by_danger(assignments, today) if assignments else []

    try:
        bars = workload_text_bars(assignments, today, window_days=3) if assignments else []
        nxt = hours_next_days(assignments, today, window_days=3) if assignments else []
        total_next_3 = round(sum(d["hours"] for d in nxt), 2)
    except Exception:
        bars = []
        total_next_3 = 0

    return render_template(
        "index.html",
        engine_ok=True,
        load_error=None,
        assignments_count=len(assignments),
        danger_rows=danger_rows,
        bars=bars,
        total_next_3=total_next_3,
        impacts=[],
    )


# ----------------------------
# Auth
# ----------------------------

@app.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip().lower()
    password = (body.get("password") or "")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if len(username) < 3:
        return jsonify({"error": "username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    users = _read_users()
    if username in users:
        return jsonify({"error": "username already taken"}), 409

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users[username] = hashed.decode("utf-8")
    _write_users(users)

    access_token = create_access_token(identity=username)
    return jsonify({"access_token": access_token}), 200


@app.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip().lower()
    password = (body.get("password") or "")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    users = _read_users()
    if username not in users:
        return jsonify({"error": "invalid username or password"}), 401

    stored_hash = users[username].encode("utf-8")
    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        return jsonify({"error": "invalid username or password"}), 401

    access_token = create_access_token(identity=username)
    return jsonify({"access_token": access_token}), 200


# ----------------------------
# Dashboard (NEW)
# ----------------------------

@app.get("/dashboard")
@jwt_required()
def get_dashboard():
    if not ENGINE_OK:
        return jsonify({"error": "engine not available"}), 500

    username = get_jwt_identity()
    today = date.today()

    assignments = _load_user_assignments(username)

    if not assignments:
        return jsonify({
            "has_assignments": False,
            "top": [],
            "headlines": [],
            "stress_forecast": {
                "high_risk_count": 0,
                "message": "No assignments yet.",
                "window_days": 5,
                "high_risk_names": []
            },
            "gpa_impacts": [],
            "workload_next_3_days": [],
        }), 200

    summary = dashboard_summary(assignments, today)
    gpa = gpa_impact_estimates(assignments, current_grade=85.0)
    workload = hours_next_days(assignments, today, window_days=3)

    return jsonify({
        "has_assignments": True,
        "top": summary["top"],
        "headlines": summary["headlines"],
        "stress_forecast": summary["stress_forecast"],
        "gpa_impacts": gpa,
        "workload_next_3_days": workload,
    }), 200


# ----------------------------
# Assignments API
# ----------------------------

@app.get("/assignments")
@jwt_required()
def get_assignments():
    username = get_jwt_identity()
    items = _read_json_file(_user_data_file(username))
    return jsonify(items), 200


@app.post("/assignments")
@jwt_required()
def create_assignment():
    username = get_jwt_identity()
    body = request.get_json(silent=True) or {}

    name = str(body.get("name", "")).strip()
    weightPercent = body.get("weightPercent")
    dueDate = body.get("dueDate")
    confidence = body.get("confidence")
    estHours = body.get("estHours")

    if not name:
        return jsonify({"error": "name required"}), 400

    item = {
        "id": str(uuid4()),
        "name": name,
        "weightPercent": float(weightPercent or 0),
        "dueDate": str(dueDate or ""),
        "confidence": int(confidence or 3),
        "estHours": float(estHours or 0),
        "createdAt": int(time.time() * 1000),
    }

    path = _user_data_file(username)
    items = _read_json_file(path)
    items.append(item)
    _write_json_file(path, items)

    return jsonify(item), 200


@app.delete("/assignments/<id>")
@jwt_required()
def delete_assignment(id):
    username = get_jwt_identity()
    path = _user_data_file(username)
    items = _read_json_file(path)
    new_items = [x for x in items if str(x.get("id")) != str(id)]
    _write_json_file(path, new_items)
    return "", 204


@app.post("/debug")
def debug():
    return jsonify({
        "ok": True,
        "headers": dict(request.headers),
        "json": request.get_json(silent=True),
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)