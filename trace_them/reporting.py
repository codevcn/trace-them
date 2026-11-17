"""Canonical versioned reports and evidence-preserving, safe exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from trace_them import __version__
from trace_them.models import utc_now

SCHEMA_VERSION = "1.0"
FIELDS = ["record_type", "input_type", "input_value", "platform", "username", "profile_url",
          "status", "reason", "association", "origin", "identifier", "observed_at",
          "http_status", "query_time", "evidence", "association_evidence", "run_metadata"]


def make_report(input_type, value, findings, *, resolutions=None, candidates=None,
                budget=None, manifest=None, warnings=None):
    serialized = [finding.to_dict() if hasattr(finding, "to_dict") else finding
                  for finding in findings]
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "Trace Them", "version": __version__},
        "observed_at": utc_now(),
        "input": {"type": input_type, "value": value},
        "manifest": {"source": getattr(manifest, "source", None),
                     "selected_sites": sorted(getattr(manifest, "sites", {})),
                     "skipped": getattr(manifest, "skipped", {})},
        "request_budget": {"limit": budget.limit, "used": budget.used,
                           "remaining": budget.remaining} if budget is not None else None,
        "summary": dict(Counter(item["status"] for item in serialized)),
        "findings": serialized,
        "resolutions": [item.to_dict() if hasattr(item, "to_dict") else item
                        for item in (resolutions or [])],
        "candidates": [asdict(item) if hasattr(item, "__dataclass_fields__") else item
                       for item in (candidates or [])],
        "warnings": list(warnings or []),
    }


def safe_filename(value: str) -> str:
    """Contain untrusted identifiers and distinguish normalization collisions."""
    value = str(value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip(". _")[:70] or "report"
    if stem.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6",
        "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7",
        "LPT8", "LPT9",
    }:
        stem = "report_" + stem
    return f"{stem}-{digest}"


def _literal(value) -> str:
    value = "" if value is None else str(value)
    prefix = value
    while prefix and (prefix[0].isspace() or ord(prefix[0]) < 32):
        prefix = prefix[1:]
    if prefix.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _rows(report):
    metadata = json.dumps({key: value for key, value in report.items()
                           if key not in ("findings", "resolutions", "candidates")},
                          ensure_ascii=False)
    common = {"input_type": report["input"]["type"],
              "input_value": json.dumps(report["input"]["value"], ensure_ascii=False),
              "run_metadata": metadata}
    for item in report["findings"]:
        row = {**common, **{key: item.get(key) for key in FIELDS if key in item},
               "record_type": "finding", "origin": item.get("origin", "input")}
        for key in ("evidence", "association_evidence"):
            row[key] = json.dumps(item.get(key, []), ensure_ascii=False)
        yield row
    for item in report["resolutions"]:
        yield {**common, "record_type": "resolution", "platform": item["provider"],
               "status": item["status"], "reason": item["reason"],
               "evidence": json.dumps(item.get("evidence", []), ensure_ascii=False)}
    for item in report["candidates"]:
        yield {**common, "record_type": "candidate", "platform": item.get("platform"),
               "username": item["username"], "origin": item["origin"],
               "association": "unverified",
               "evidence": json.dumps(item.get("evidence", []), ensure_ascii=False)}
    if not any(report.get(key) for key in ("findings", "resolutions", "candidates")):
        yield {**common, "record_type": "run"}


def _atomic_write(path: Path, data: bytes):
    descriptor, name = tempfile.mkstemp(prefix=".trace-them-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def write_reports(report, output_dir, formats, stem=None) -> list[Path]:
    """All formats preserve candidate origins and source-scoped associations."""
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(stem if stem is not None else report["input"]["value"])
    formats = list(dict.fromkeys(formats))
    if any(value not in ("json", "txt", "csv", "xlsx") for value in formats):
        raise ValueError("Unknown export format.")
    paths = []
    for fmt in formats:
        path = directory / f"{stem}.{fmt}"
        if fmt == "json":
            write_json(report, path)
        elif fmt == "txt":
            lines = ["Trace Them — public profile observations",
                     "Account existence and association with the input are separate observations."]
            for item in report["findings"]:
                lines.append(f"{item['platform']} / {item['username']}: {item['status']} | "
                             f"association={item['association']} | {item['profile_url']}")
            lines += ["", "Evidence and provenance (canonical report):",
                      json.dumps(report, indent=2, ensure_ascii=False)]
            _atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))
        elif fmt == "csv":
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for row in _rows(report):
                writer.writerow({key: _literal(row.get(key)) for key in FIELDS})
            _atomic_write(path, stream.getvalue().encode("utf-8-sig"))
        else:
            from openpyxl import Workbook
            from openpyxl.cell import WriteOnlyCell

            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet("Observations")
            sheet.append(FIELDS)
            for row in _rows(report):
                cells = []
                for key in FIELDS:
                    # Explicit string cells cannot become formulas or hyperlinks.
                    text = "" if row.get(key) is None else str(row[key])
                    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
                    if len(text) > 32767:
                        raise ValueError("XLSX cell exceeds 32767 characters; use JSON to preserve evidence.")
                    cell = WriteOnlyCell(sheet, value=text)
                    cell.data_type = "s"
                    cells.append(cell)
                sheet.append(cells)
            data = io.BytesIO()
            workbook.save(data)
            workbook.close()
            _atomic_write(path, data.getvalue())
        paths.append(path)
    return paths
