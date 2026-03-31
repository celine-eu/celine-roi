import os
from pathlib import Path
DOTENV_PATH: str = ".env"
from dotenv import load_dotenv
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text

dotenv_path = Path(DOTENV_PATH).resolve()
if not dotenv_path.exists():
    raise FileNotFoundError(f".env file not found: {dotenv_path}")
load_dotenv(dotenv_path)

def build_db_url(
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> str:
    """Build a PostgreSQL connection URL from args or environment variables."""
    host = host or os.getenv("POSTGRES_HOST", "localhost")
    port = port or int(os.getenv("POSTGRES_PORT", "15432"))
    user = user or os.getenv("POSTGRES_USER", "postgres")
    password = password or os.getenv("POSTGRES_PASSWORD", "postgres")
    database = database or os.getenv("POSTGRES_DB", "datasets")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}"
    )


DB_URL = build_db_url()
engine = create_engine(DB_URL)
print(f"Connected to {os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}")


import pandas as pd
import numpy as np
from pathlib import Path
import pytz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOCAL_TZ = pytz.timezone("Europe/Rome")
RANDOM_SEED = 42

import pandas as pd
df_meters_raw = pd.read_sql("""
      SELECT device_id, cf_type, ts, consumption_kw, production_kw, meter_type
      FROM ds_dev_silver.meters_data
      ORDER BY device_id, ts
  """, engine)
df_meters_raw['ts'] = pd.to_datetime(df_meters_raw['ts'], utc=True)
logger.info(f"Loaded meter data: {df_meters_raw.shape}")
logger.info(f"Date range: {df_meters_raw['ts'].min()} to {df_meters_raw['ts'].max()}")
logger.info(f"Devices: {df_meters_raw['device_id'].nunique()}")
logger.info(f"Meter types: {df_meters_raw['meter_type'].unique().tolist()}")