"""DuckDB catalog over the locked Parquet store.

Paths are not Hive `key=value` partitions, so asset_class / symbol / timeframe
are parsed from the filename and exposed as columns on the `ohlcv` view.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from signal_data.paths import CATALOG_DB, CATALOG_DIR, STORE_DIR


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path or CATALOG_DB))


def refresh_catalog(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    own = con is None
    con = con or connect()
    store = str(STORE_DIR).replace("'", "''")
    # filename=true gives the full path so we can parse layout components.
    con.execute("DROP VIEW IF EXISTS ohlcv")
    con.execute("DROP VIEW IF EXISTS series_catalog")
    # read_parquet on an empty glob raises; guard it.
    files = list(STORE_DIR.glob("*/*/*.parquet"))
    if not files:
        con.execute(
            """
            CREATE VIEW ohlcv AS
            SELECT
                CAST(NULL AS VARCHAR) AS asset_class,
                CAST(NULL AS VARCHAR) AS symbol,
                CAST(NULL AS VARCHAR) AS timeframe,
                CAST(NULL AS TIMESTAMP WITH TIME ZONE) AS open_time,
                CAST(NULL AS TIMESTAMP WITH TIME ZONE) AS close_time,
                CAST(NULL AS DOUBLE) AS open,
                CAST(NULL AS DOUBLE) AS high,
                CAST(NULL AS DOUBLE) AS low,
                CAST(NULL AS DOUBLE) AS close,
                CAST(NULL AS DOUBLE) AS volume,
                CAST(NULL AS VARCHAR) AS source
            WHERE 1 = 0
            """
        )
        con.execute(
            """
            CREATE VIEW series_catalog AS
            SELECT * FROM ohlcv LIMIT 0
            """
        )
        return con
    con.execute(
        f"""
        CREATE VIEW ohlcv AS
        SELECT
            regexp_extract(filename, '/store/([^/]+)/([^/]+)/([^/]+)\\.parquet$', 1) AS asset_class,
            regexp_extract(filename, '/store/([^/]+)/([^/]+)/([^/]+)\\.parquet$', 2) AS symbol,
            regexp_extract(filename, '/store/([^/]+)/([^/]+)/([^/]+)\\.parquet$', 3) AS timeframe,
            open_time,
            close_time,
            open,
            high,
            low,
            close,
            volume,
            source
        FROM read_parquet('{store}/*/*/*.parquet', filename=true, union_by_name=true)
        """
    )
    con.execute(
        """
        CREATE VIEW series_catalog AS
        SELECT
            asset_class,
            symbol,
            timeframe,
            min(open_time) AS start_time,
            max(close_time) AS end_time,
            count(*) AS n_bars,
            any_value(source) AS source
        FROM ohlcv
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """
    )
    return con
