"""
SavedPin Model
==============
Stores user-saved map locations (favourites / bookmarks).
Uses plain float columns for lat/lon — no PostGIS geometry overhead.
"""

from datetime import datetime, timezone

from app.extensions import db


class SavedPin(db.Model):
    """A user-saved map location (bookmark)."""

    __tablename__ = 'saved_pins'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    label = db.Column(db.String(100), nullable=False, default='Untitled Pin')
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'label': self.label,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f'<SavedPin {self.label} ({self.latitude}, {self.longitude})>'
