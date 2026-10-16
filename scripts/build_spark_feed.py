"""Build a small, verifiable, public SPARK feed for REACH Scout.

Usage (from the root of PART-WPO/SPARK):
    python scripts/build_spark_feed.py

Reads the published SPARK CSV. Does NOT change it or the live SPARK website.
Writes only to agent-data/. Python 3.10+; standard library only.
"""

import csv
import hashlib
import io
import json
import re
import shutil
from collections import Counter
from pathlib import Path

SOURCE = Path("SPARK Report - SPARK Report.csv")
DEST = Path("agent-data")
MAX_BYTES = 48 * 1024

REQUIRED_COLUMNS = {
    "Project Title", "Managing WPO Program", "Award Number(s)",
    "Project Goal", "Project Description", "Year Funded",
}

INDEX_COLUMNS = [
    "Record ID", "Project Fingerprint", "Primary", "Project Title",
    "Managing WPO Program", "Award Number(s)", "Parsed NOAA Awards",
    "Umbrella Award Roots", "Principal Investigator", "Year Funded",
    "Project Status", "Research Keywords", "Project Team Affiliations",
    "Detail File",
]

AWARD_COLUMNS = [
    "Award Number", "Umbrella Award Root", "Match Basis", "Record ID",
    "Project Fingerprint", "Project Title", "Managing WPO Program",
    "Year Funded", "Detail File",
]

# Preserve the full NOAA award plus optional hyphenated subaward segments.
# The root identifies a possible umbrella relationship, NOT project attribution.
NOAA_AWARD = re.compile(r"\b(NA\d{2}[A-Z]{3}\d{7})(?:-[A-Z0-9]+)*\b", re.I)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(values):
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerow(values)
    return buffer.getvalue().encode("utf-8")


def award_identifiers(raw):
    """Return (exact tokens, possible CI/umbrella roots, match provenance).

    Unrecognized identifiers are retained as literal tokens for investigation,
    never silently discarded or treated as a confirmed NOAA award.
    """
    raw = raw or ""
    exact = []
    roots = []
    matches = list(NOAA_AWARD.finditer(raw.upper()))
    for m in matches:
        full = m.group(0).upper()
        root = m.group(1).upper()
        if full not in exact:
            exact.append(full)
        if root not in roots:
            roots.append(root)

    # Retain unknown formats as raw lookup values, but mark them unparsed.
    # Only recognize list separators known to occur in SPARK award fields.
    unknown = []
    for item in re.split(r"[,;\r\n]+", raw):
        clean = " ".join(item.upper().split()).strip()
        if clean and not NOAA_AWARD.search(clean) and clean not in exact:
            unknown.append(clean)

    return exact, roots, list(dict.fromkeys(unknown))


def fingerprint(row):
    """Cross-snapshot grouping aid; may change if identifying fields change."""
    parts = [
        row.get("Project Title", ""), row.get("Managing WPO Program", ""),
        row.get("Award Number(s)", ""), row.get("Year Funded", ""),
        row.get("Principal Investigator", ""),
    ]
    text = "|".join(" ".join((x or "").lower().split()) for x in parts)
    return "sparkfp-" + sha256(text.encode("utf-8"))[:20]


def write_shards(rows, columns, folder):
    """Return (manifest shard list, record-id -> relative file path)."""
    folder.mkdir(parents=True, exist_ok=True)
    header = csv_bytes(columns)
    shards = []
    row_paths = {}
    pending = []
    pending_size = len(header)

    def flush():
        nonlocal pending, pending_size
        if not pending:
            return
        path = folder / f"part-{len(shards) + 1:03d}.csv"
        content = header + b"".join(blob for _, blob in pending)
        if len(content) > MAX_BYTES:
            raise ValueError(f"Shard too large: {path}")
        path.write_bytes(content)
        for record_id, _ in pending:
            row_paths[record_id] = path.as_posix()
        shards.append({
            "path": path.as_posix(), "rows": len(pending),
            "bytes": len(content), "sha256": sha256(content),
        })
        pending = []
        pending_size = len(header)

    for row in rows:
        data = csv_bytes([row.get(column, "") or "" for column in columns])
        if len(header) + len(data) > MAX_BYTES:
            raise ValueError(
                f"Individual row {row.get('Record ID')} is larger than 48 KiB "
                f"for {folder}; investigate before publishing."
            )
        if pending and pending_size + len(data) > MAX_BYTES:
            flush()
        pending.append((row["Record ID"], data))
        pending_size += len(data)
    flush()
    return shards, row_paths


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"SPARK source CSV is missing: {SOURCE}")
    source = SOURCE.read_bytes()
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise ValueError("Source CSV has duplicate column names")
        missing = REQUIRED_COLUMNS - set(columns)
        if missing:
            raise ValueError(f"Source CSV missing expected columns: {sorted(missing)}")
        records = list(reader)

    if not records:
        raise ValueError("Source CSV is empty; refusing to create an empty feed")
    for pos, row in enumerate(records, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Malformed CSV record at position {pos}")

    # Generate complete detail records first. Project IDs are snapshot locators.
    details = []
    for pos, row in enumerate(records, 1):
        details.append({
            "Record ID": f"spark-{pos:06d}",
            "Project Fingerprint": fingerprint(row),
            **row,
        })

    # Remove stale shards in only these generated folders. No source file changes.
    for folder in (DEST / "index", DEST / "details", DEST / "awards"):
        if folder.exists():
            shutil.rmtree(folder)

    detail_columns = ["Record ID", "Project Fingerprint"] + columns
    detail_files, detail_paths = write_shards(details, detail_columns, DEST / "details")

    index = []
    award_map = []
    unknown_tokens_count = 0
    projects_without_awards = 0
    for project in details:
        full, roots, unknown = award_identifiers(project.get("Award Number(s)", ""))
        if not full and not unknown:
            projects_without_awards += 1
        unknown_tokens_count += len(unknown)
        common = {
            "Record ID": project["Record ID"],
            "Project Fingerprint": project["Project Fingerprint"],
            "Project Title": project["Project Title"],
            "Managing WPO Program": project["Managing WPO Program"],
            "Year Funded": project.get("Year Funded", ""),
            "Detail File": detail_paths[project["Record ID"]],
        }
        index.append({
            **{name: project.get(name, "") for name in INDEX_COLUMNS},
            **common,
            "Parsed NOAA Awards": "; ".join(full),
            "Umbrella Award Roots": "; ".join(roots),
        })
        for award in full:
            root_match = NOAA_AWARD.match(award)
            award_map.append({
                **common, "Award Number": award,
                "Umbrella Award Root": root_match.group(1).upper() if root_match else "",
                "Match Basis": "parsed_noaa_award",
            })
        for token in unknown:
            award_map.append({
                **common, "Award Number": token,
                "Umbrella Award Root": "", "Match Basis": "unparsed_raw_identifier",
            })

    index_files, _ = write_shards(index, INDEX_COLUMNS, DEST / "index")
    awards_files, _ = write_shards(award_map, AWARD_COLUMNS, DEST / "awards")
    assert sum(item["rows"] for item in detail_files) == len(details)
    assert sum(item["rows"] for item in index_files) == len(details)
    assert sum(item["rows"] for item in awards_files) == len(award_map)
    assert len(detail_paths) == len(details)
    # The generator is read-only with respect to the source CSV.
    assert SOURCE.read_bytes() == source

    duplicates = Counter(item["Project Fingerprint"] for item in details)
    manifest = {
        "feed": "spark-agent-feed",
        "schema_version": 1,
        "source": {
            "path": SOURCE.as_posix(), "bytes": len(source),
            "sha256": sha256(source), "rows": len(records),
        },
        "index": {"columns": INDEX_COLUMNS, "files": index_files},
        "awards": {"columns": AWARD_COLUMNS, "rows": len(award_map), "files": awards_files},
        "details": {"columns": detail_columns, "files": detail_files},
        "quality_notes": {
            "projects_without_award_tokens": projects_without_awards,
            "unparsed_award_tokens": unknown_tokens_count,
            "duplicate_project_fingerprint_groups": sum(v > 1 for v in duplicates.values()),
        },
        "identity_note": (
            "Record ID is a location within this snapshot, NOT a permanent SPARK project ID. "
            "Project Fingerprint aids cross-run matching but may change when source fields change."
        ),
        "attribution_warning": (
            "Umbrella Award Root is a DISCOVERY grouping only. A shared cooperative "
            "institute award NEVER proves that an output belongs to any specific WPO "
            "project. Inspect the linked SPARK project and primary funding evidence."
        ),
        "retrieval_note": (
            "Load all index/ and awards/ shards for portfolio coverage and "
            "award matching; fetch details/ files for specific projects. "
            "Verify row counts and SHA-256 before concluding a record is absent."
        ),
    }
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"SPARK feed created from {len(details):,} project records")
    print(f"Index files: {len(index_files)}; award-lookup files: {len(awards_files)}; "
          f"detail files: {len(detail_files)}")
    print(f"Award-map entries: {len(award_map):,}; "
          f"unparsed award tokens: {unknown_tokens_count}")
    print(f"Every generated CSV shard <= {MAX_BYTES:,} bytes")
    print("Original SPARK CSV unchanged. Manifest: agent-data/manifest.json")


if __name__ == "__main__":
    main()
