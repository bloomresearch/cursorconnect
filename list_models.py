import os
from dotenv import load_dotenv
from cursorconnect import Cursor

load_dotenv()
api_key = os.environ.get("CURSOR_API_KEY")

models = Cursor.models.list(api_key=api_key)
for m in models:
    print(m.id)
