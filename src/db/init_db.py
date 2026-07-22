import os
import sys

# Allow running directly from project root or from src/db/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.db.db import engine
from src.db.models import Base


def init_db():
    print("Initializing SQLite database...")
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    print("Database initialization complete. Tables:")
    for table_name in Base.metadata.tables.keys():
        print(f"  [OK] {table_name}")


if __name__ == "__main__":
    init_db()
