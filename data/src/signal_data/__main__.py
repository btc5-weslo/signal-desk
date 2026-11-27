"""python -m signal_data  ->  CLI help. Does not ingest or touch the network by itself."""

from signal_data.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
