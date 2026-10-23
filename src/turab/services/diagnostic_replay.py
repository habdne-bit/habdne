"""The replay of a format-2 diagnostic (Slice 6 step 3, G6-11).

Ref: `docs/gate/SLICE_6_PLAN.md` G6-11 (revision 3, review of 1fd7bdf);
`matching/diagnostic.py`.

Two checks, kept apart, and a failure names which:
- **(R) the recorded facts are verified, not re-derived.** `evaluated` and
  `stored` are what the run recorded; a reused match may have been
  committed by a concurrent run (Slice 4, D5). Only their consistency with
  the stored rows is checked: every listed match exists, is of the
  diagnostic's request, and has the entry's `input_hash`, `property_id` and
  `offer_id` (the last three since the review of 220573a); and an entry NEW
  was evaluated at the diagnostic's `run_at`. Nothing is inferred from an
  EXISTING entry's timestamps.
- **(D) the decisions are recomputed from the inputs:** the matches
  `evaluated` names, by id and in that order, and the stored location
  chains, under the versions the row RECORDS (review of 220573a). `compute`
  re-derives `suggested_actions`, `relaxation_scenarios` and the computed
  parts of the summary, `excluded_counts` included, and each is compared. The
  evaluated matches are never inferred from `evaluated_at` (F6-11), and
  `tasks` is never read (G6-4 (iii)).

Reads only. Since step 4 the run writes format-2 rows, and the tests replay
those rows as the database holds them. **A stated limit** (review of
0fae42c; plan §5.4): the diagnostic row's own `input_hash`
(`turab.diagnostic-input/2`) is neither recomputed nor compared, so a replay
with no problem is not a proof that every input of that hash is sound.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy import text

from turab.matching import snapshots
from turab.matching.registry import UnknownRuleVersion
from turab.matching.diagnostic import (COMPUTED_SUMMARY_KEYS, SUMMARY_FORMAT,
                                       candidate_record, compute)
from turab.services.matching_run import match_view


def replay(conn: Any, diagnostic: Mapping[str, Any]) -> dict[str, list[str]]:
    """Both checks of G6-11 on one diagnostic row (`run_at`, `request_id`,
    `blocker_summary`, `suggested_actions`, `relaxation_scenarios`).
    Returns `{"R": [...], "D": [...]}`; empty lists mean it replays. Reads
    `match_candidates` and `match_criterion_results` only, never `tasks`."""
    stored = snapshots.stored_form(dict(diagnostic))
    summary = stored["blocker_summary"]
    if summary.get("format") != SUMMARY_FORMAT:
        return {"R": [f"blocker_summary format {summary.get('format')!r} records no "
                      "evaluated matches; only format 2 is replayed"], "D": []}
    problems: dict[str, list[str]] = {"R": [], "D": []}
    records = []
    for position, entry in enumerate(summary["evaluated"]):
        # The instants are compared as timestamps, in SQL: their text forms
        # differ between a JSON document and a row.
        row = conn.execute(text("""
            SELECT input_hash, evaluated_at = CAST(:at AS timestamptz) AS at_run,
                   request_id::text AS request_id, property_id::text AS property_id,
                   evaluated_offer_id::text AS offer_id
              FROM turab.match_candidates WHERE match_id = :m"""),
            {"m": uuid.UUID(entry["match_id"]), "at": stored["run_at"]}).mappings().first()
        if row is None:
            problems["R"].append(f"evaluated[{position}]: no match {entry['match_id']}")
            continue
        # The ids the entry records are the match's, and the match is of this
        # diagnostic's request (review of 220573a).
        if row["request_id"] != str(stored["request_id"]):
            problems["R"].append(f"evaluated[{position}]: the match is of another request")
        for field in ("property_id", "offer_id"):
            if row[field] != (None if entry.get(field) is None else str(entry[field])):
                problems["R"].append(f"evaluated[{position}]: {field} differs from the "
                                     "match's")
        if row["input_hash"] != entry["input_hash"]:
            problems["R"].append(f"evaluated[{position}]: input_hash differs from the match's")
        if entry["stored"] == "NEW" and not row["at_run"]:
            problems["R"].append(f"evaluated[{position}]: NEW, but evaluated at another "
                                 "instant than the run")
        if entry["stored"] not in ("NEW", "EXISTING"):
            problems["R"].append(f"evaluated[{position}]: stored is neither NEW nor EXISTING")
        records.append(candidate_record(match_view(conn, uuid.UUID(entry["match_id"]))))
    if problems["R"]:
        return problems
    # The versions the row RECORDS, never the current ones (review of 220573a).
    versions = summary.get("versions")
    if not isinstance(versions, dict) or set(versions) != {"value", "actions", "relaxation"}:
        problems["D"].append("blocker_summary.versions does not name the three functions")
        return problems
    try:
        again = compute(stored["request_id"], records,
                        location_chains=summary["requested_location_chains"],
                        evaluated=summary["evaluated"], excluded=summary["excluded"],
                        versions=versions)
    except UnknownRuleVersion as exc:
        problems["D"].append(f"a recorded version is not implemented: {exc}")
        return problems
    for part in ("suggested_actions", "relaxation_scenarios"):
        if again[part] != stored[part]:
            problems["D"].append(f"{part} differs from what the stored inputs give")
    for key in COMPUTED_SUMMARY_KEYS:
        if again["blocker_summary"].get(key) != summary.get(key):
            problems["D"].append(f"blocker_summary.{key} differs from what the stored "
                                 "inputs give")
    return problems
