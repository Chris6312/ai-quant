from sqlalchemy import create_engine, text

from app.config.settings import get_settings

settings = get_settings()
database_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")

engine = create_engine(database_url)

with engine.begin() as conn:
    result = conn.execute(text("DELETE FROM candles WHERE usage = 'ml'"))

print(f"Deleted {result.rowcount} ML candles. Trading candles preserved.")