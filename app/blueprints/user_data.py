"""
User Data Blueprint
===================
CRUD endpoints for saved pins and saved routes.
All endpoints require authentication (@login_required).

Cross-domain aggregation note:
    SQLAlchemy cannot JOIN across different database binds.
    Any logic comparing user pins/routes against routing_db spatial data
    must be done in the Python application layer.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.saved_pin import SavedPin
from app.models.saved_route import SavedRoute

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
#  SAVED ROUTES
# ═══════════════════════════════════════════════════════════════════════

@user_data_bp.route('/routes', methods=['GET'])
@login_required
def list_routes():
    """Return all saved routes for the current user."""
    routes = SavedRoute.query.filter_by(user_id=current_user.id).order_by(
        SavedRoute.created_at.desc()
    ).all()
    return jsonify({'routes': [r.to_dict() for r in routes]}), 200


@user_data_bp.route('/routes', methods=['POST'])
@login_required
def create_route():
    """
    Save a new route configuration.

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

    route = SavedRoute(
        user_id=current_user.id,
        name=(data.get('name') or 'Untitled Route')[:100],
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=float(data['end_lat']) if data.get('end_lat') is not None else None,
        end_lon=float(data['end_lon']) if data.get('end_lon') is not None else None,
        weights_json=data.get('weights'),
        route_geometry=data.get('route_geometry'),
        distance_km=float(data['distance_km']) if data.get('distance_km') is not None else None,
        is_loop=bool(data.get('is_loop', False)),
    )
    db.session.add(route)
    db.session.commit()
    return jsonify({'route': route.to_dict()}), 201


@user_data_bp.route('/routes/<int:route_id>', methods=['DELETE'])
@login_required
def delete_route(route_id: int):
    """Delete a saved route. Only the owning user may delete."""
    route = SavedRoute.query.filter_by(
        id=route_id, user_id=current_user.id
    ).first()
    if not route:
        return jsonify({'error': 'Route not found'}), 404

    db.session.delete(route)
    db.session.commit()
    return jsonify({'message': 'Route deleted'}), 200
