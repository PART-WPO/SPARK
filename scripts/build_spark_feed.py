"""Build a small, verifiable, public SPARK feed for REACH Scout.

Run from the root of PART-WPO/SPARK:
    python scripts/build_spark_feed.py

Reads the published SPARK CSV. Does NOT change it or the SPARK website.
Writes only to agent-data/. Python 3.10+; standard library only.

Version 1.2 identifies likely Cooperative Institute (CI) awards by the base
identifier NAyyOAR432xxxx or NAyyOAR405xxxx, including subaward suffixes and
single-letter extensions. Classification is a screening rule, NOT proof that
a research output belongs to a specific WPO-funded project. Related awards
remain discovery leads, not funding attribution.
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
    "Related Award Number(s)", "Project Goal", "Project Description",
    "Year Funded",
}

INDEX_COLUMNS = [
    "Record ID", "Project Fingerprint", "Primary", "Project Title",
    "Managing WPO Program", "Award Number(s)", "Parsed NOAA Awards",
    "Related Award Number(s)", "Parsed Related NOAA Awards",
    "Umbrella Award Roots", "Principal Investigator", "Year Funded",
    "Project Status", "Research Keywords", "Project Team Affiliations",
    "Has Primary CI Award", "Primary CI Awards",
    "Has Related CI Award", "Related CI Awards", "Detail File",
]

AWARD_COLUMNS = [
    "Award Number", "Umbrella Award Root", "Match Basis", "Record ID",
    "Project Fingerprint", "Project Title", "Managing WPO Program",
    "Year Funded", "Is CI Award", "CI Base Award",
    "CI Identifier Note", "Detail File",
]

# Legacy NOAA awards: keep any hyphenated subaward suffixes. Newer NOAA
# identifier formats and non-NOAA internal project codes are also retained
# as raw lookup values, never silently discarded or presumed equivalent.
NOAA_AWARD = re.compile(r"\b(NA\d{2}[A-Z]{3}\d{7})(?:-[A-Z0-9]+)*\b", re.I)
# The user-specified WPO convention: OAR432 and OAR405 identify CI awards.
# Allow one trailing letter (e.g., NA23OAR4050503I) and hyphenated subaward
# components; a trailing letter remains "unparsed" under the generic parser.
CI_AWARD = re.compile(
    r"^(NA\d{2}OAR(?:432|405)\d{4})(?:[A-Z])?(?:-[A-Z0-9]+)*$", re.I
)
EMPTY_IDENTIFIERS = {"N/A", "NA", "NONE", "NOT APPLICABLE", "UNKNOWN", "TBD", "-"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(values):
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerow(values)
    return buffer.getvalue().encode("utf-8")


def award_identifiers(raw):
    """Extract recognized NOAA awards and preserve other reference formats.

    Returns (exact NOAA tokens, potential umbrella roots, unmatched tokens).
    'Root' indicates textual ancestry, never evidence of project attribution.
    """
    raw = raw or ""
    full = []
    roots = []
    for match in NOAA_AWARD.finditer(raw.upper()):
        token = match.group(0).upper()
        root = match.group(1).upper()
        if token not in full:
            full.append(token)
        if root not in roots:
            roots.append(root)

    unknown = []
    # Preserve any other identifiers even when mixed with NOAA awards.
    for fragment in re.split(r"[,;\r\n]+", raw.upper()):
        remaining = NOAA_AWARD.sub(" ", fragment)
        token = " ".join(remaining.split()).strip(" .:()[]")
        if token and token not in EMPTY_IDENTIFIERS and token not in unknown:
            unknown.append(token)
    return full, roots, unknown


def ci_classification(award):
    """(CI indicator, base grant, explanatory note), never project attribution.

    A CI-formatted award in a related-award column is still ONLY a lead.
    Leave extended identifier forms as unparsed in the existing award lookup.
    """
    token = (award or "").strip().upper()
    match = CI_AWARD.fullmatch(token)
    if not match:
        return "No", "", ""
    base = match.group(1).upper()
    if NOAA_AWARD.fullmatch(token):
        return "Yes", base, "CI pattern in recognized NOAA award format"
    return "Yes", base, "CI prefix matched; extended suffix, verify exact identifier"


def fingerprint(row):
    """Cross-snapshot grouping aid; not a permanent project identifier."""
    fields = (
        "Project Title", "Managing WPO Program", "Award Number(s)",
        "Year Funded", "Principal Investigator",
    )
    normalized = "|".join(
        " ".join((row.get(key) or "").lower().split()) for key in fields
    )
    return "sparkfp-" + sha256(normalized.encode("utf-8"))[:20]


def write_shards(rows, columns, folder):
    """Create byte-limited CSV shards and per-record detail-file pointers."""
    folder.mkdir(parents=True, exist_ok=True)
    header = csv_bytes(columns)
    shards, paths = [], {}
    pending, current_bytes = [], len(header)

    def flush():
        nonlocal pending, current_bytes
        if not pending:
            return
        path = folder / f"part-{len(shards) + 1:03d}.csv"
        data = header + b"".join(blob for _, blob in pending)
        if len(data) > MAX_BYTES:
            raise ValueError(f"Oversized shard: {path}")
        path.write_bytes(data)
        for record_id, _ in pending:
            paths[record_id] = path.as_posix()
        shards.append({
            "path": path.as_posix(), "rows": len(pending),
            "bytes": len(data), "sha256": sha256(data),
        })
        pending, current_bytes = [], len(header)

    for row in rows:
        blob = csv_bytes([row.get(col, "") or "" for col in columns])
        if len(header) + len(blob) > MAX_BYTES:
            raise ValueError(
                f"Row {row.get('Record ID')} is too large for {folder}; "
                "review this source record before publishing."
            )
        if pending and current_bytes + len(blob) > MAX_BYTES:
            flush()
        pending.append((row["Record ID"], blob))
        current_bytes += len(blob)
    flush()
    return shards, paths


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"SPARK CSV missing: {SOURCE}")
    original = SOURCE.read_bytes()
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise ValueError("SPARK CSV has duplicate column names")
        missing = REQUIRED_COLUMNS - set(columns)
        if missing:
            raise ValueError(f"Missing expected columns: {sorted(missing)}")
        source_rows = list(reader)

    if not source_rows:
        raise ValueError("Empty SPARK CSV; refusing to generate empty feed")
    for i, row in enumerate(source_rows, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Malformed CSV row {i}")

    details = [
        {"Record ID": f"spark-{i:06d}", "Project Fingerprint": fingerprint(row), **row}
        for i, row in enumerate(source_rows, start=1)
    ]

    for folder in (DEST / "index", DEST / "details", DEST / "awards"):
        if folder.exists():
            shutil.rmtree(folder)

    detail_columns = ["Record ID", "Project Fingerprint"] + columns
    detail_files, detail_paths = write_shards(details, detail_columns, DEST / "details")

    index_rows, award_rows = [], []
    no_primary_ids, unparsed_primary, unparsed_related = 0, 0, 0
    related_project_count = 0
    ci_primary_projects, ci_related_projects, ci_award_rows = 0, 0, 0
    ci_extended_suffix_rows = 0
    for project in details:
        primary, primary_roots, primary_other = award_identifiers(project.get("Award Number(s)"))
        related, related_roots, related_other = award_identifiers(project.get("Related Award Number(s)"))
        if not primary and not primary_other:
            no_primary_ids += 1
        if related or related_other:
            related_project_count += 1
        unparsed_primary += len(primary_other)
        unparsed_related += len(related_other)
        primary_ci = [token for token in primary + primary_other
                      if ci_classification(token)[0] == "Yes"]
        related_ci = [token for token in related + related_other
                      if ci_classification(token)[0] == "Yes"]
        ci_primary_projects += bool(primary_ci)
        ci_related_projects += bool(related_ci)

        common = {
            "Record ID": project["Record ID"],
            "Project Fingerprint": project["Project Fingerprint"],
            "Project Title": project.get("Project Title", ""),
            "Managing WPO Program": project.get("Managing WPO Program", ""),
            "Year Funded": project.get("Year Funded", ""),
            "Detail File": detail_paths[project["Record ID"]],
        }
        index_rows.append({
            **{name: project.get(name, "") for name in INDEX_COLUMNS},
            **common,
            "Parsed NOAA Awards": "; ".join(primary),
            "Parsed Related NOAA Awards": "; ".join(related),
            "Umbrella Award Roots": "; ".join(dict.fromkeys(primary_roots + related_roots)),
            "Has Primary CI Award": "Yes" if primary_ci else "No",
            "Primary CI Awards": "; ".join(primary_ci),
            "Has Related CI Award": "Yes" if related_ci else "No",
            "Related CI Awards": "; ".join(related_ci),
        })

        for identifiers, basis in [
            (primary, "primary_noaa_award"),
            (primary_other, "primary_unparsed_identifier"),
            (related, "related_noaa_award"),
            (related_other, "related_unparsed_identifier"),
        ]:
            for identifier in identifiers:
                match = NOAA_AWARD.fullmatch(identifier)
                ci_flag, ci_root, ci_note = ci_classification(identifier)
                if ci_flag == "Yes":
                    ci_award_rows += 1
                    if not match:
                        ci_extended_suffix_rows += 1
                award_rows.append({
                    **common,
                    "Award Number": identifier,
                    "Umbrella Award Root": match.group(1).upper() if match else "",
                    "Match Basis": basis,
                    "Is CI Award": ci_flag,
                    "CI Base Award": ci_root,
                    "CI Identifier Note": ci_note,
                })

    index_files, _ = write_shards(index_rows, INDEX_COLUMNS, DEST / "index")
    awards_files, _ = write_shards(award_rows, AWARD_COLUMNS, DEST / "awards")

    assert sum(x["rows"] for x in detail_files) == len(details)
    assert sum(x["rows"] for x in index_files) == len(details)
    assert sum(x["rows"] for x in awards_files) == len(award_rows)
    assert len(detail_paths) == len(details)
    assert SOURCE.read_bytes() == original, "Source CSV unexpectedly modified"

    duplicates = Counter(x["Project Fingerprint"] for x in details)
    manifest = {
        "feed": "spark-agent-feed", "schema_version": 3,
        "source": {
            "path": SOURCE.as_posix(), "bytes": len(original),
            "sha256": sha256(original), "rows": len(source_rows),
        },
        "index": {"columns": INDEX_COLUMNS, "files": index_files},
        "awards": {"columns": AWARD_COLUMNS, "rows": len(award_rows), "files": awards_files},
        "details": {"columns": detail_columns, "files": detail_files},
        "quality_notes": {
            "projects_without_primary_award_tokens": no_primary_ids,
            "projects_with_related_award_identifiers": related_project_count,
            "projects_with_primary_ci_awards": ci_primary_projects,
            "projects_with_related_ci_awards": ci_related_projects,
            "ci_award_lookup_entries": ci_award_rows,
            "ci_entries_with_extended_suffixes": ci_extended_suffix_rows,
            "unparsed_primary_award_tokens": unparsed_primary,
            "unparsed_related_award_tokens": unparsed_related,
            "duplicate_project_fingerprint_groups": sum(v > 1 for v in duplicates.values()),
        },
        "ci_identification": {
            "rule": "Base award matches NAyyOAR432xxxx or NAyyOAR405xxxx",
            "subaward_suffixes": "Recognized, and one-letter extensions flagged for manual format verification",
            "scope": "identifier screening only; NOT proof of funding for any WPO project",
            "crosswalk": "Treat primary and related CI awards as distinct match types",
        },
        "identity_note": (
            "Record ID identifies a row in this snapshot only. Project Fingerprint "
            "is a matching aid that may change when source metadata changes."
        ),
        "attribution_warning": (
            "Primary awards, related awards, and CI award classification are DISTINCT evidence "
            "types. Related-award and umbrella-root matches are DISCOVERY LEADS, not "
            "proof that an output belongs to a specific WPO-funded project. "
            "Verify the linked SPARK workstream and primary funding evidence."
        ),
        "retrieval_note": (
            "Read ALL index and award shards for global coverage; inspect Match Basis "
            "before interpreting any award relationship. Fetch details only for "
            "specific projects. Verify row counts and SHA-256 before declaring "
            "any record absent."
        ),
    }
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"SPARK feed created from {len(details):,} project records")
    print(f"Index files: {len(index_files)}; award lookup files: {len(awards_files)}; "
          f"detail files: {len(detail_files)}")
    print(f"Award references: {len(award_rows)}; projects with related awards: {related_project_count}")
    print(f"CI references: {ci_award_rows}; primary-CI projects: {ci_primary_projects}; "
          f"related-CI projects: {ci_related_projects}; extended CI suffixes: {ci_extended_suffix_rows}")
    print(f"All generated CSV shards <= {MAX_BYTES:,} bytes")
    print("Original SPARK CSV unchanged. Manifest: agent-data/manifest.json")


if __name__ == "__main__":
    main()
