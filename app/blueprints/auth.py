"""
Authentication Blueprint
========================
Provides registration, login, logout, and session-check endpoints.
All passwords are hashed with werkzeug.security before storage.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user account.

    Expects JSON: {"email": "...", "password": "..."}
    Returns 201 on success, 400/409 on validation error.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    # ── Validation ────────────────────────────────────────────────────
    if not email or '@' not in email:
        return jsonify({'error': 'A valid email address is required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    # ── Uniqueness check ──────────────────────────────────────────────
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists'}), 409

    # ── Create user ───────────────────────────────────────────────────
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({'message': 'Account created', 'user': user.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate and create a session.

    Expects JSON: {"email": "...", "password": "..."}
    Returns 200 on success, 401 on bad credentials.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    login_user(user, remember=data.get('remember', False))
    return jsonify({'message': 'Logged in', 'user': user.to_dict()}), 200


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Clear the current session."""
    logout_user()
    return jsonify({'message': 'Logged out'}), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    """Return the currently authenticated user's profile."""
    return jsonify({'user': current_user.to_dict()}), 200
