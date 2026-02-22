"""
Database Bootstrap Script
=========================
Pre-flight script that ensures the `user_db` database exists on the
PostGIS container before the Flask application starts.

Uses a raw psycopg2 connection to the default `postgres` database with
autocommit=True (PostgreSQL forbids CREATE DATABASE inside a transaction).

Called from the Flask application factory (create_app) before SQLAlchemy
binds to the user database.
"""

import os
import logging

logger = logging.getLogger(__name__)


def ensure_user_db():
    """
    Check if the user database exists and create it if missing.
    
    Reads connection details from environment variables:
        POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB_HOST, USER_DB_NAME
    
    Falls back gracefully if psycopg2 is not installed or the database
    server is unreachable (e.g., running locally without Docker).
    """
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        logger.warning(
            "psycopg2 not installed — skipping user_db bootstrap. "
            "Install psycopg2-binary to enable persistent user data."
        )
        return False

    db_user = os.environ.get('POSTGRES_USER', 'scenic')
    db_password = os.environ.get('POSTGRES_PASSWORD', 'scenicpassword')
    db_host = os.environ.get('POSTGRES_DB_HOST', 'localhost')
    db_port = os.environ.get('POSTGRES_DB_PORT', '5432')
    user_db_name = os.environ.get('USER_DB_NAME', 'user_db')

    try:
        # Connect to the default 'postgres' maintenance database
        conn = psycopg2.connect(
            dbname='postgres',
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if user_db already exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (user_db_name,)
        )
        exists = cursor.fetchone()

        if not exists:
            # Safe: user_db_name comes from our own env var, not user input
            cursor.execute(f'CREATE DATABASE "{user_db_name}"')
            logger.info(f"Created database '{user_db_name}' successfully.")
        else:
            logger.info(f"Database '{user_db_name}' already exists — skipping creation.")

        cursor.close()
        conn.close()
        return True

    except psycopg2.OperationalError as e:
        logger.warning(
            f"Could not connect to PostgreSQL for bootstrap: {e}. "
            "User persistence features will be unavailable."
        )
        return False
