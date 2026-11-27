"""Write per-batch data-quality reports (markdown + JSON). Import is a no-op."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from signal_data.paths import REPORTS_DIR
from signal_data.schema import DataQualityReport


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def reports_to_payload(batch: str, reports: Iterable[DataQualityReport], *, notes: list[str] | None = None) -> dict:
    items = []
    for r in reports:
        items.append(
            {
                "symbol": r.symbol,
                "asset_class": r.asset_class,
                "timeframe": r.timeframe,
                "source": r.source,
                "n_bars": r.n_bars,
                "first_open": _iso(r.start),
                "last_close": _iso(r.end),
                "n_duplicates_removed": r.n_duplicates_removed,
                "n_bad_ticks_dropped": r.n_bad_ticks_dropped,
                "n_outliers_flagged": r.n_outliers_flagged,
                "n_zero_volume": r.n_zero_volume,
                "n_stale_bars": r.n_stale_bars,
                "n_stale_runs_gt_3": r.n_stale_runs_gt_3,
                "n_off_grid_dropped": r.n_off_grid_dropped,
                "off_grid_times": [_iso(x) for x in r.off_grid_times],
                "n_gaps_unexpected": r.n_gaps_unexpected,
                "n_gaps_calendar": r.n_gaps_calendar,
                "n_gaps_gt_3x": r.n_gaps_gt_3x,
                "missing_pct_estimate": r.missing_pct_estimate,
                "dropped_forming_bars": r.dropped_forming_bars,
                "history_limitations": r.history_limitations,
                "warnings": r.warnings,
                "errors": r.errors,
                "fetch_attempts": [a.model_dump() for a in r.fetch_attempts],
                "ok": r.n_bars > 0 and not r.errors,
            }
        )
    ok = [i for i in items if i["ok"]]
    failed = [i for i in items if not i["ok"]]
    return {
        "batch": batch,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_series_requested": len(items),
        "n_series_ok": len(ok),
        "n_series_failed": len(failed),
        "notes": list(notes or []),
        "series": items,
    }


def write_batch_reports(batch: str, reports: Iterable[DataQualityReport], *, notes: list[str] | None = None, dest: Path | None = None) -> tuple[Path, Path]:
    dest = dest or REPORTS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    payload = reports_to_payload(batch, reports, notes=notes)
    json_path = dest / f"data_quality_{batch}.json"
    md_path = dest / f"data_quality_{batch}.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    md_path.write_text(_to_markdown(payload))
    return json_path, md_path


def _to_markdown(payload: dict) -> str:
    lines = [
        f"# Data quality — {payload['batch']}",
        "",
        f"Generated at {payload['generated_at']} (UTC).",
        "",
        f"- Series requested: **{payload['n_series_requested']}**",
        f"- Succeeded: **{payload['n_series_ok']}**",
        f"- Failed: **{payload['n_series_failed']}**",
        "",
        "Prices are from real free APIs. Empty or failed series are recorded honestly; no bars were synthesized.",
        "",
    ]
    if payload.get("notes"):
        lines.append("## Notes")
        lines.append("")
        for n in payload["notes"]:
            lines.append(f"- {n}")
        lines.append("")
    lines += [
        "## Series",
        "",
        "| Symbol | TF | Source | Bars | First open (UTC) | Last close (UTC) | Unexpected gaps | Gaps >3x | Stale bars | Stale runs >3 | Off-grid dropped | Bad ticks | Outliers | Status |",
        "|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for s in payload["series"]:
        status = "ok" if s["ok"] else "FAILED"
        lines.append(
            "| {symbol} | {timeframe} | {source} | {n_bars} | {first_open} | {last_close} | {n_gaps_unexpected} | {n_gaps_gt_3x} | {n_stale_bars} | {n_stale_runs_gt_3} | {n_off_grid_dropped} | {n_bad_ticks_dropped} | {n_outliers_flagged} | {status} |".format(
                symbol=s["symbol"],
                timeframe=s["timeframe"],
                source=s["source"] or "—",
                n_bars=s["n_bars"],
                first_open=s["first_open"] or "—",
                last_close=s["last_close"] or "—",
                n_gaps_unexpected=s["n_gaps_unexpected"],
                n_gaps_gt_3x=s["n_gaps_gt_3x"],
                n_stale_bars=s["n_stale_bars"],
                n_stale_runs_gt_3=s.get("n_stale_runs_gt_3", 0),
                n_off_grid_dropped=s.get("n_off_grid_dropped", 0),
                n_bad_ticks_dropped=s["n_bad_ticks_dropped"],
                n_outliers_flagged=s["n_outliers_flagged"],
                status=status,
            )
        )
    lines += ["", "## Details", ""]
    for s in payload["series"]:
        lines.append(f"### {s['symbol']} {s['timeframe']}")
        lines.append("")
        if s["errors"]:
            lines.append("**Errors:**")
            for e in s["errors"]:
                lines.append(f"- {e}")
            lines.append("")
        if s["warnings"]:
            lines.append("**Warnings / flags:**")
            for w in s["warnings"]:
                lines.append(f"- {w}")
            lines.append("")
        if s["history_limitations"]:
            lines.append("**Source history limitations (not fabricated coverage):**")
            for h in s["history_limitations"]:
                lines.append(f"- {h}")
            lines.append("")
        if s["fetch_attempts"]:
            lines.append("**Fetch attempts:**")
            for a in s["fetch_attempts"]:
                mark = "ok" if a["ok"] else "failed"
                err = f" — {a['error']}" if a.get("error") else ""
                notes = f" ({'; '.join(a['notes'])})" if a.get("notes") else ""
                lines.append(f"- `{a['source']}` {mark}, bars={a['bars']}{err}{notes}")
            lines.append("")
        if s["n_gaps_calendar"] or s["n_zero_volume"] or s["dropped_forming_bars"]:
            lines.append(
                f"Calendar gaps: {s['n_gaps_calendar']}; gaps >3x interval: {s.get('n_gaps_gt_3x', 0)}; stale bars kept: {s.get('n_stale_bars', 0)}; stale runs >3: {s.get('n_stale_runs_gt_3', 0)}; off-grid dropped: {s.get('n_off_grid_dropped', 0)}; zero-volume (non-stale): {s['n_zero_volume']}; "
                f"forming bars dropped: {s['dropped_forming_bars']}; missing_pct_estimate: {s['missing_pct_estimate']:.4f}."
            )
            lines.append("")
    return "\n".join(lines) + "\n"


def reports_from_store(*, data_dir=None) -> list[DataQualityReport]:
    """Build a quality report from every Parquet file currently in the store.

    The alignment check FAILS a series (``errors`` is non-empty, ``ok`` is
    false) if any off-boundary ``open_time`` remains in the file. Off-grid
    bars must already have been dropped; this path does not rewrite the store.
    """
    from signal_data.alignment import off_grid_mask
    from signal_data.cleaning import clean_ohlcv
    from signal_data.paths import get_store_dir
    from signal_data.storage import read_parquet
    from signal_data.timeutil import now_utc

    root = get_store_dir(data_dir)
    reports: list[DataQualityReport] = []
    for path in sorted(root.glob("*/*/*.parquet")):
        asset_class = path.parent.parent.name
        symbol = path.parent.name
        timeframe = path.stem
        df = read_parquet(path)
        remaining = off_grid_mask(df, timeframe, asset_class)
        source = None
        if not df.empty and "source" in df.columns:
            vc = df["source"].astype(str).value_counts()
            source = ",".join(f"{k}:{int(v)}" for k, v in vc.items())
        cleaned, report = clean_ohlcv(
            df,
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            source=source,
            as_of=now_utc(),
        )
        if bool(remaining.any()):
            sample = [str(t) for t in df.loc[remaining, "open_time"].head(5).tolist()]
            report.errors.append(
                f"FAIL: {int(remaining.sum())} off-boundary open_time(s) remain in "
                f"{path}; examples: {sample}. Off-grid bars must be dropped, never snapped."
            )
        reports.append(report)
    return reports
