"""
SavedQuery Model
=================
Stores user-saved routing queries in parametrised form (start/end coords + weights).
Optionally stores exact polyline geometry for deterministic recall.

Design Decision (see ADR-014):
    - Default: Parametrised (Option A) — re-calculates from coords + weights
    - Optional: route_geometry stores [[lat, lon], ...] for exact physical recall
"""

from datetime import datetime, timezone

from app.extensions import db


class SavedQuery(db.Model):
    """A user-saved routing query."""

    __tablename__ = 'saved_queries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False, default='Untitled Query')

    # Parametrised route definition (Option A)
    start_lat = db.Column(db.Float, nullable=False)
    start_lon = db.Column(db.Float, nullable=False)
    end_lat = db.Column(db.Float, nullable=True)   # Nullable for loop routes (same as start)
    end_lon = db.Column(db.Float, nullable=True)

    # Full slider/preference snapshot at time of save
    weights_json = db.Column(db.JSON, nullable=True)

    # Optional deterministic geometry: [[lat, lon], [lat, lon], ...]
    # Only populated when user explicitly "pins" a specific route result
    route_geometry = db.Column(db.JSON, nullable=True)

    # Metadata
    distance_km = db.Column(db.Float, nullable=True)
    is_loop = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'start_lat': self.start_lat,
            'start_lon': self.start_lon,
            'end_lat': self.end_lat,
            'end_lon': self.end_lon,
            'weights': self.weights_json,
            'has_geometry': self.route_geometry is not None,
            'distance_km': self.distance_km,
            'is_loop': self.is_loop,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        route_type = 'Loop' if self.is_loop else 'A→B'
        return f'<SavedQuery "{self.name}" ({route_type})>'
