from datetime import date
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from engine import (
    Assignment,  # your dataclass
    parse_date,
    rank_assignments_by_danger,
    hours_next_days,
    workload_text_bars,
    dashboard_summary,
    gpa_impact_estimate
)

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Allow web + iOS clients later (lock down origins later if you want)
CORS(app, resources={r"/api/*": {"origins": "*"}})

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])


# ----------------------------
# DB MODELS
# ----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class AssignmentRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(200), nullable=False)
    weight_percent = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.String(10), nullable=False)  # store YYYY-MM-DD
    confidence = db.Column(db.Integer, nullable=False)
    estimated_hours = db.Column(db.Float, nullable=False)


with app.app_context():
    db.create_all()


# ----------------------------
# HELPERS
# ----------------------------
def row_to_assignment(r: AssignmentRow) -> Assignment:
    return Assignment(
        name=r.name,
        weight_percent=r.weight_percent,
        due_date=parse_date(r.due_date),
        confidence=r.confidence,
        estimated_hours=r.estimated_hours
    )


def get_user_assignments(user_id: int):
    rows = AssignmentRow.query.filter_by(user_id=user_id).all()
    return [row_to_assignment(r) for r in rows]


# ----------------------------
# AUTH
# ----------------------------
@app.post("/api/register")
@limiter.limit("10 per hour")
def register():
    data = request.get_json(force=True)

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    u = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.commit()

    return jsonify({"ok": True})


@app.post("/api/login")
@limiter.limit("20 per hour")
def login():
    data = request.get_json(force=True)
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    u = User.query.filter_by(email=email).first()
    if not u or not check_password_hash(u.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=u.id)
    return jsonify({"access_token": token})


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


# ----------------------------
# APP API (per-user)
# ----------------------------
@app.get("/api/dashboard")
@jwt_required()
def api_dashboard():
    user_id = int(get_jwt_identity())
    today = date.today()

    assignments = get_user_assignments(user_id)
    danger_list = rank_assignments_by_danger(assignments, today) if assignments else []

    return jsonify({
        "today": today.isoformat(),
        "summary": dashboard_summary(assignments, today) if assignments else None,
        "danger_list": danger_list,
        "hours3": hours_next_days(assignments, today, window_days=3) if assignments else None,
        "bars": workload_text_bars(assignments, today, days=3) if assignments else []
    })


@app.post("/api/assignments")
@jwt_required()
@limiter.limit("60 per hour")
def api_add_assignment():
    user_id = int(get_jwt_identity())
    data = request.get_json(force=True)

    # basic validation
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    weight_percent = float(data.get("weight_percent", 0))
    confidence = int(data.get("confidence", 3))
    estimated_hours = float(data.get("estimated_hours", 1))
    due_date_str = str(data.get("due_date", "")).strip()

    if weight_percent <= 0 or weight_percent > 100:
        return jsonify({"error": "weight_percent must be 1..100"}), 400
    if confidence < 1 or confidence > 5:
        return jsonify({"error": "confidence must be 1..5"}), 400
    if estimated_hours <= 0:
        return jsonify({"error": "estimated_hours must be > 0"}), 400
    try:
        parse_date(due_date_str)
    except Exception:
        return jsonify({"error": "due_date must be YYYY-MM-DD"}), 400

    r = AssignmentRow(
        user_id=user_id,
        name=name,
        weight_percent=weight_percent,
        due_date=due_date_str,
        confidence=confidence,
        estimated_hours=estimated_hours
    )
    db.session.add(r)
    db.session.commit()

    return jsonify({"ok": True})


@app.delete("/api/assignments/<int:assignment_id>")
@jwt_required()
@limiter.limit("60 per hour")
def api_delete_assignment(assignment_id: int):
    user_id = int(get_jwt_identity())
    r = AssignmentRow.query.filter_by(id=assignment_id, user_id=user_id).first()
    if not r:
        return jsonify({"error": "not found"}), 404

    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True})


@app.get("/api/gpa-impact")
@jwt_required()
def api_gpa_impact():
    user_id = int(get_jwt_identity())
    current_grade = request.args.get("current_grade", "").strip()
    try:
        cg = float(current_grade)
    except ValueError:
        return jsonify({"error": "current_grade must be a number"}), 400

    assignments = get_user_assignments(user_id)
    impacts = [gpa_impact_estimate(a, cg) for a in assignments]
    return jsonify({"impacts": impacts})