"""
User Data Blueprint
===================
CRUD endpoints for saved pins and saved queries.
All endpoints require authentication (@login_required).

Cross-domain aggregation note:
    SQLAlchemy cannot JOIN across different database binds.
    Any logic comparing user pins/queries against routing_db spatial data
    must be done in the Python application layer.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.saved_pin import SavedPin
from app.models.saved_query import SavedQuery

user_data_bp = Blueprint('user_data', __name__, url_prefix='/api')


# ═══════════════════════════════════════════════════════════════════════
#  SAVED PINS
# ═══════════════════════════════════════════════════════════════════════

@user_data_bp.route('/pins', methods=['GET'])
@login_required
def list_pins():
    """Return all saved pins for the current user."""
    pins = SavedPin.query.filter_by(user_id=current_user.id).order_by(
        SavedPin.created_at.desc()
    ).all()
    return jsonify({'pins': [p.to_dict() for p in pins]}), 200


@user_data_bp.route('/pins', methods=['POST'])
@login_required
def create_pin():
    """
    Save a new map pin.

    Expects JSON: {"label": "...", "latitude": float, "longitude": float}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    lat = data.get('latitude')
    lon = data.get('longitude')
    if lat is None or lon is None:
        return jsonify({'error': 'latitude and longitude are required'}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return jsonify({'error': 'latitude and longitude must be numbers'}), 400

    pin = SavedPin(
        user_id=current_user.id,
        label=data.get('label', 'Untitled Pin')[:100],
        latitude=lat,
        longitude=lon,
    )
    db.session.add(pin)
    db.session.commit()
    return jsonify({'pin': pin.to_dict()}), 201


@user_data_bp.route('/pins/<int:pin_id>', methods=['PATCH'])
@login_required
def update_pin(pin_id: int):
    """Update a saved pin (currently only the label)."""
    pin = SavedPin.query.filter_by(id=pin_id, user_id=current_user.id).first()
    if not pin:
        return jsonify({'error': 'Pin not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    label = data.get('label')
    if label is not None:
        pin.label = str(label).strip()[:100] or pin.label

    db.session.commit()
    return jsonify({'pin': pin.to_dict()}), 200

@user_data_bp.route('/pins/<int:pin_id>', methods=['DELETE'])
@login_required
def delete_pin(pin_id: int):
    """Delete a saved pin. Only the owning user may delete."""
    pin = SavedPin.query.filter_by(id=pin_id, user_id=current_user.id).first()
    if not pin:
        return jsonify({'error': 'Pin not found'}), 404

    db.session.delete(pin)
    db.session.commit()
    return jsonify({'message': 'Pin deleted'}), 200


# ═══════════════════════════════════════════════════════════════════════
#  SAVED QUERIES
# ═══════════════════════════════════════════════════════════════════════

@user_data_bp.route('/queries', methods=['GET'])
@login_required
def list_queries():
    """Return all saved queries for the current user."""
    queries = SavedQuery.query.filter_by(user_id=current_user.id).order_by(
        SavedQuery.created_at.desc()
    ).all()
    return jsonify({'queries': [q.to_dict() for q in queries]}), 200


@user_data_bp.route('/queries', methods=['POST'])
@login_required
def create_query():
    """
    Save a new routing query.

    Expects JSON: {
        "name": "My Evening Walk",
        "start_lat": 51.454, "start_lon": -2.627,
        "end_lat": 51.449, "end_lon": -2.580,    // optional for loops
        "weights": {"distance": 1, "greenness": 3, ...},
        "route_geometry": [[lat, lon], ...],       // optional
        "distance_km": 4.2,
        "is_loop": false
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    start_lat = data.get('start_lat')
    start_lon = data.get('start_lon')
    if start_lat is None or start_lon is None:
        return jsonify({'error': 'start_lat and start_lon are required'}), 400

    try:
        start_lat = float(start_lat)
        start_lon = float(start_lon)
    except (TypeError, ValueError):
        return jsonify({'error': 'Coordinates must be numbers'}), 400

    query = SavedQuery(
        user_id=current_user.id,
        name=(data.get('name') or 'Untitled Query')[:100],
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=float(data['end_lat']) if data.get('end_lat') is not None else None,
        end_lon=float(data['end_lon']) if data.get('end_lon') is not None else None,
        weights_json=data.get('weights'),
        route_geometry=data.get('route_geometry'),
        distance_km=float(data['distance_km']) if data.get('distance_km') is not None else None,
        is_loop=bool(data.get('is_loop', False)),
    )
    db.session.add(query)
    db.session.commit()
    return jsonify({'query': query.to_dict()}), 201


@user_data_bp.route('/queries/<int:query_id>', methods=['PATCH'])
@login_required
def update_query(query_id: int):
    """Update a saved query (currently only the name)."""
    query = SavedQuery.query.filter_by(
        id=query_id, user_id=current_user.id
    ).first()
    if not query:
        return jsonify({'error': 'Query not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    name = data.get('name')
    if name is not None:
        query.name = str(name).strip()[:100] or query.name

    db.session.commit()
    return jsonify({'query': query.to_dict()}), 200


@user_data_bp.route('/queries/<int:query_id>', methods=['DELETE'])
@login_required
def delete_query(query_id: int):
    """Delete a saved query. Only the owning user may delete."""
    query = SavedQuery.query.filter_by(
        id=query_id, user_id=current_user.id
    ).first()
    if not query:
        return jsonify({'error': 'Query not found'}), 404

    db.session.delete(query)
    db.session.commit()
    return jsonify({'message': 'Query deleted'}), 200
