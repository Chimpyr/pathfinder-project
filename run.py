import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Bind to 0.0.0.0 in containers, 127.0.0.1 locally
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(host=host, port=port, debug=True)

