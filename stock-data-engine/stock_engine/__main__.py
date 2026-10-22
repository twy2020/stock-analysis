import os
from waitress import serve
from .app import create_app

serve(create_app(),host=os.getenv('STOCK_ENGINE_HOST','127.0.0.1'),port=int(os.getenv('STOCK_ENGINE_PORT','18310')),threads=8)
