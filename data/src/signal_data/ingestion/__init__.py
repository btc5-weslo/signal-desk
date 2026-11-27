"""Pluggable market-data sources. All paths return real API data or an explicit failure."""

from signal_data.ingestion.pipeline import ingest_series, ingest_many

__all__ = ["ingest_series", "ingest_many"]
