"""
User Model
==========
Stores registered user accounts with hashed passwords.
Implements Flask-Login's UserMixin for session integration.
"""

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    """Registered application user."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships (cascade delete orphan pins/queries when user is removed)
    saved_pins = db.relationship(
        'SavedPin', backref='owner', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    saved_queries = db.relationship(
        'SavedQuery', backref='owner', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    # ── Password helpers ──────────────────────────────────────────────

    def set_password(self, password: str) -> None:
        """Hash and store the password. Plain text never touches the DB."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a candidate password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    # ── Representation ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Public-safe serialisation (no password hash)."""
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f'<User {self.email}>'
