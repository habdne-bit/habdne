#!/usr/bin/env python3
"""Generate the Slice 7 closure evidence from a real test run.

Plan: `docs/gate/SLICE_7_PLAN.md` §6.4, with G7-19 decided in the review of
d04d5c8. Slice 7 has no STOP GATE; this document is **not** called one. As
Slice 6's generator does, it maps each mandatory test, red-team case and
review obligation to its bound test, and takes every status from a JUnit
report: by default the one committed with the clean-tree run,
`docs/gate/evidence/junit-run.xml`. Before any provenance is claimed,
`run_binding.check` must find the report's digest and counts to be the
recorded ones, no failed case, and the current tree's source fingerprint to
be the run's and the gate run's.

**G7-19, as decided:**
- (i) the event store's counts come from
  `docs/gate/evidence/SLICE7-EVENT-STORE-COUNTS.txt`, written by
  `slice7_event_store_counts.py` right after the run. The generator refuses
  it unless its run identifier, commit, source fingerprint and report sha256
  are the bound run's. They are shown as "a sample measured right after the
  run": never PASS;
- (ii) the writes to the four tables, by `INSERT`, `UPDATE` and `DELETE`,
  computed from the application's statements under `src/`, and each
  UPDATE's columns; any writer or column not decided is a problem. The
  module that holds an INSERT is told apart from the commands and scripts
  that call it. This is an inventory of the statements read here, **not a
  guarantee against a superuser's writes**;
- (iii) every limit listed, none given PASS.

**Never PASS here:** R-1 and Meta's verification; K06; retention; one
interaction per message beyond the service's paths; a link's validity after
its writing; the recovery's content; Slice 6's carried limits and the SALE
scope. Slice 5's and Slice 6's evidence stay their trees' records; this
generator reads neither.

Usage:
  db/gate/slice7_evidence.py [--junit PATH]           # write the document
  db/gate/slice7_evidence.py [--junit PATH] --check   # fail if stale or unproven
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

import run_binding
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_JUNIT = ROOT / "docs" / "gate" / "evidence" / "junit-run.xml"
GATE_RUN = ROOT / "docs" / "gate" / "evidence" / "gate-run.txt"
COUNTS = ROOT / "docs" / "gate" / "evidence" / "SLICE7-EVENT-STORE-COUNTS.txt"
CORRECTIONS = ROOT / "docs" / "contract" / "CONTRACT_CORRECTIONS.yaml"
OUT = ROOT / "docs" / "gate" / "SLICE_7_EVIDENCE.md"

M8 = "test_migration_0008_communication_records"
S2, S3, S4, S5 = (f"test_slice7_step{n}" for n in (2, 3, 4, 5))
C6, C78 = "test_correction_006", "test_correction_007_008"

#: §6.1: (number, the handoff's wording, tests). The end-to-end test first.
MANDATORY = (
    ("1", "repeated provider webhook creates one message",
     (f"{S5}::test_mandatory_1_the_same_envelope_twice_makes_one_event_one_message_one_interaction",
      f"{S5}::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction",
      f"{S5}::test_mandatory_1_a_failed_event_is_completed_by_the_redelivery_once",
      f"{S3}::test_mandatory_test_1_concurrent_deliveries_make_one_message",
      f"{S4}::test_iv_a_webhook_replay_and_an_ignored_event_write_no_interaction")),
    ("2", "same provider message id cannot be inserted into another thread",
     (f"{S5}::test_mandatory_2_staff_first_then_the_webhook_into_another_thread_writes_nothing",
      f"{S5}::test_mandatory_2_the_webhook_first_then_staff_into_another_thread_is_409",
      f"{S5}::test_mandatory_2_the_null_provider_path_is_refused_by_the_service_and_by_0008",
      f"{S2}::test_g7_4_a_recorded_reference_is_409_in_any_thread",
      f"{S3}::test_g7_4_mandatory_test_2_a_recorded_reference_is_ignored_in_any_thread",
      f"{M8}::test_a_a_reference_needs_a_provider",
      f"{M8}::test_a_the_global_identity_still_holds_across_threads")),
    ("3", "thread/opportunity links are checked by service invariant",
     (f"{S5}::test_mandatory_3_the_sellers_thread_about_the_buyers_opportunity_is_accepted_and_frozen",
      f"{S2}::test_rule_0_a_named_opportunity_must_be_a_sale",
      f"{S2}::test_rule_1_the_opportunitys_buyer_and_seller_are_accepted_with_its_own_links",
      f"{S2}::test_rule_1_a_link_the_opportunity_does_not_have_is_refused",
      f"{S2}::test_rule_2_a_request_without_an_opportunity_needs_its_own_party",
      f"{S2}::test_rule_3_a_property_without_an_opportunity_needs_one_of_its_offers_party",
      f"{S2}::test_rule_4_an_id_naming_no_row_is_refused_by_field",
      f"{S2}::test_the_links_are_frozen_after_creation",
      f"{M8}::test_d_a_named_parent_cannot_be_deleted")),
    ("4", "phone decision can be linked to later written confirmation observation",
     (f"{S5}::test_mandatory_4_over_http_the_decision_the_confirmation_the_link_and_the_timeline",
      f"{S4}::test_vii_mandatory_test_4_a_phone_decision_is_linked_to_a_later_written_confirmation")),
)

#: §6.2: (case, statement, tests).
RED_TEAM = (
    ("J01", "mandatory test 1",
     (f"{S5}::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction",)),
    ("J02", "mandatory test 2",
     (f"{S5}::test_mandatory_2_staff_first_then_the_webhook_into_another_thread_writes_nothing",
      f"{S5}::test_mandatory_2_the_webhook_first_then_staff_into_another_thread_is_409")),
    ("J03", "no content stored without a consent valid at write time, in messages, in the "
            "event store and in logs; retention not claimed",
     (f"{S5}::test_j03_content_reaches_the_timeline_only_under_the_consent",
      f"{S3}::test_g7_9_1_the_event_store_holds_the_allow_list_only",
      f"{S3}::test_j03_nothing_of_the_body_reaches_a_log_or_an_access_record",
      f"{S2}::test_g7_9_content_without_the_archive_consent_is_refused",
      f"{S2}::test_g7_11_the_content_never_reaches_the_audit_log_or_a_log",
      f"{S4}::test_vi_webhook_content_withheld_at_write_is_absent_for_every_role")),
    ("S41", "a wrong or missing relay signature is 401 before any write; it proves the "
            "relay's origin, not Meta's",
     (f"{S5}::test_s41_an_unsigned_or_missigned_delivery_writes_nothing",
      f"{S3}::test_ii_s41_a_missing_or_wrong_signature_is_401_writing_nothing")),
    ("S42", "a replay of a completed event is 200, with no duplicate",
     (f"{S5}::test_mandatory_1_the_same_envelope_twice_makes_one_event_one_message_one_interaction",
      f"{S3}::test_s42_a_replay_of_a_completed_event_is_200_and_writes_nothing")),
    ("G7-2 (iv)", "the four failure tests, and the answers whose result is not confirmed",
     (f"{S3}::test_iv_1_a_failure_in_processing_is_failed_with_its_code_and_answers_500",
      f"{S3}::test_iv_2_a_stop_after_t1_is_completed_by_a_redelivery",
      f"{S3}::test_iv_3_a_failure_of_the_status_update_loses_t2_whole",
      f"{S3}::test_iv_4_a_replay_while_t2_holds_the_claim_is_200_and_writes_nothing",
      f"{S3}::test_iv_t1_failing_before_its_commit_is_503_then_a_redelivery_completes_it",
      f"{S3}::test_iv_t1_whose_commit_answer_is_lost_is_503_then_a_redelivery_completes_it_once",
      f"{S3}::test_iv_t2_whose_commit_answer_is_lost_is_500_then_a_redelivery_is_a_replay")),
    ("K05", "each staff POST replays with its key; another body on the key is 409",
     (f"{S5}::test_k05_the_thread_command_replays_and_refuses_another_body_on_its_key",
      f"{S5}::test_k05_the_message_command_replays_and_refuses_another_body_on_its_key")),
)

#: K06: listed, never PASS. Trigger- and constraint-level refusals of 0008.
K06_TRIGGER_LEVEL = (
    f"{M8}::test_d_a_thread_never_changes_after_insert",
    f"{M8}::test_d_a_thread_cannot_be_deleted",
    f"{M8}::test_d_the_six_keys_are_restrict",
    f"{M8}::test_b_a_message_cannot_be_deleted",
    f"{M8}::test_b_delivery_status_transitions_are_exactly_the_decided_ones",
    f"{M8}::test_c_an_event_cannot_be_deleted",
    f"{M8}::test_c_processing_moves_only_from_received_or_failed",
)

#: §6.3.
AUTHORIZATION = (
    ("the two staff POSTs: ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER 403, "
     "recorded; anonymous 401",
     (f"{S2}::test_admin_and_operator_create_a_thread_and_a_message",
      f"{S2}::test_a_reviewer_and_a_customer_are_refused_both_writing_nothing",
      f"{S2}::test_an_anonymous_caller_is_refused_both",
      f"{S2}::test_an_unknown_thread_is_403_and_the_denial_is_recorded")),
    ("the webhook stays in the closed list of six, and reads no bearer",
     (f"{S3}::test_the_webhook_stays_in_the_closed_public_list_and_reads_no_bearer",)),
    ("the timeline's widened item, by exact key sets, for ADMIN, OPERATOR and REVIEWER",
     (f"{S4}::test_vi_an_unarchived_message_shows_no_content_to_any_role",
      f"{S4}::test_vi_archived_content_is_shown_to_every_role",
      f"{S4}::test_vi_any_other_interaction_keeps_slice_1s_exact_keys")),
)

#: What each review of Slice 7 asked to be proven: (review, obligation, tests).
OBLIGATIONS = (
    ("`0f423d2`", "G7-16 (iv): the thread locked before the insert, two concurrent "
                  "messages; no refusal carries an id or database text",
     (f"{S2}::test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later",
      f"{S2}::test_no_refusal_carries_an_id_or_database_text")),
    ("`f7e5297`", "R-S7-2-01: a binding in flight and a message, both orders, over HTTP",
     (f"{S2}::test_r_s7_2_01_a_message_holding_the_thread_makes_a_new_binding_wait",
      f"{S2}::test_r_s7_2_01_a_binding_in_flight_makes_the_message_wait_then_is_seen")),
    ("`bf1fe3d`", "a 503 when the secret is absent, with no event row",
     (f"{S3}::test_ii_a_missing_or_empty_secret_is_503_with_no_event_row",)),
    ("`3dfb717`", "T1 failing before its commit, T1's and T2's answers lost after it; "
                  "`archived_at` read and tested",
     (f"{S3}::test_iv_t1_failing_before_its_commit_is_503_then_a_redelivery_completes_it",
      f"{S3}::test_iv_t1_whose_commit_answer_is_lost_is_503_then_a_redelivery_completes_it_once",
      f"{S3}::test_iv_t2_whose_commit_answer_is_lost_is_500_then_a_redelivery_is_a_replay",
      f"{S3}::test_archived_at_alone_refuses_nothing")),
    ("`34d6122`", "a Content-Length too long for int(): 400 unread, writing nothing; long "
                  "leading zeros not refused",
     (f"{S3}::test_g7_15_the_declared_length_is_compared_without_an_unbounded_conversion",
      f"{S3}::test_g7_15_an_overlong_declared_length_is_400_unread_and_writes_nothing",
      f"{S3}::test_g7_15_a_small_body_under_an_odd_declared_length_is_processed")),
    ("`e18271a`", "the item's exact keys and the withholding for the three roles; the "
                  "link's refusals before any write or key; the backfill concurrent and "
                  "re-run",
     (f"{S4}::test_vi_an_unarchived_message_shows_no_content_to_any_role",
      f"{S4}::test_vii_a_links_metadata_must_be_exactly_its_two_uuids",
      f"{S4}::test_vii_the_observation_must_be_linkable",
      f"{S4}::test_v_two_backfills_at_once_write_each_interaction_once",
      f"{S4}::test_v_the_backfill_writes_one_interaction_per_earlier_message_and_a_rerun_none")),
    ("`a659587`", "R-S7-4-01: the backfill's actual level, on a REPEATABLE READ "
                  "connection; the concurrent pair and the re-run; the refusal",
     (f"{S4}::test_v_the_backfill_runs_read_committed_whatever_the_connections_default",
      f"{S4}::test_v_two_backfills_on_a_repeatable_read_default_write_each_interaction_once",
      f"{S4}::test_v_the_backfill_refuses_to_write_under_another_level")),
    ("`d04d5c8`", "the two gaps: mandatory test 1's interaction; K05's other body",
     (f"{S5}::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction",
      f"{S5}::test_k05_the_thread_command_replays_and_refuses_another_body_on_its_key",
      f"{S5}::test_k05_the_message_command_replays_and_refuses_another_body_on_its_key")),
)

#: Concurrency: (race, tests).
CONCURRENCY = (
    ("two threads with one WHATSAPP reference", (f"{M8}::test_e_two_concurrent_threads_with_one_reference_make_one",)),
    ("two messages on one thread", (f"{S2}::test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later",)),
    ("a revocation in flight", (f"{S2}::test_g7_9_a_revocation_in_flight_is_waited_for_then_seen",)),
    ("a webhook holding the thread, and a new binding", (f"{S3}::test_g7_16_iv_a_webhook_holding_the_thread_makes_a_new_binding_wait",)),
    ("a status change in flight", (f"{S3}::test_g7_5_a_status_change_in_flight_is_waited_for_then_seen",)),
    ("a replay during the claim", (f"{S3}::test_iv_4_a_replay_while_t2_holds_the_claim_is_200_and_writes_nothing",)),
    ("eight deliveries of one envelope", (f"{S5}::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction",)),
    ("two backfills; a backfill and a message", (f"{S4}::test_v_two_backfills_on_a_repeatable_read_default_write_each_interaction_once",
                                                 f"{S4}::test_v_a_backfill_concurrent_with_a_message_makes_no_duplicate")),
    ("an observation changed while a link reads it", (f"{S4}::test_vii_a_change_to_the_observation_in_flight_is_waited_for_then_seen",)),
)

#: G7-19 (iii): measured or stated limits, never PASS.
MEASURED_LIMITS = (
    ("the content-less recovery (G7-2 (v), accepted in the review of `58a0067`): the "
     "operator command recovers a message without its content",
     f"{S3}::test_iv_2_a_stop_after_t1_is_completed_by_the_recovery_without_content"),
    ("a confirmation link is valid at its writing only (G7-18 (vii)): the observation it "
     "names can still change afterwards; no legal value",
     f"{S4}::test_vii_the_link_is_valid_at_its_writing_only"),
    ("one interaction per message within the service's paths (G7-18 (iv)): not a database "
     "constraint; a row written outside the service has none",
     f"{S4}::test_ix_no_message_has_two_interactions_and_each_names_an_existing_message"),
)

#: G7-19 (ii): the decided writes, by kind, and each UPDATE's columns.
COMM, HOOK = "src/turab/services/communication.py", "src/turab/services/webhooks.py"
INTER = "src/turab/services/message_interactions.py"
OPP = "src/turab/services/opportunity_commands.py"
WRITES = {
    "communication_threads": {"INSERT": [COMM], "UPDATE": [COMM, HOOK], "DELETE": []},
    "communication_messages": {"INSERT": [COMM, HOOK], "UPDATE": [HOOK], "DELETE": []},
    "webhook_events": {"INSERT": [HOOK], "UPDATE": [HOOK], "DELETE": []},
    "interactions": {"INSERT": [INTER, OPP], "UPDATE": [], "DELETE": []},
}
UPDATE_COLUMNS = {
    "communication_threads": ["last_message_at"],
    "communication_messages": ["delivery_status"],
    "webhook_events": ["error_text", "processed_at", "processing_status"],
}
#: Who calls the message interaction's INSERT (`message_interactions.write`).
INTERACTION_CALLERS = {
    "write": [COMM, HOOK],
    "backfill": ["db/ops/backfill_message_interactions.py"],
}
OPERATIONS = ("postCommunicationThreads", "postCommunicationThreadsThreadIdMessages",
              "postWebhooksWhatsapp", "getPartiesPartyIdTimeline")
APPROVED = ("CORRECTION-006", "CORRECTION-007", "CORRECTION-008")
COUNT_FIELDS = {
    "sampled": r"^Sampled at        : (.+)$",
    "run_recorded": r"^Run recorded at   : (.+)$",
    "commit": r"^Run commit        : (\S+)$",
    "fingerprint": r"^Source fingerprint: ([0-9a-f]{64})$",
    "report_sha256": r"^Report sha256     : ([0-9a-f]{64})$",
    "database": r"^Test database     : (\S+)$",
}
STATUSES = ("RECEIVED", "PROCESSED", "IGNORED", "FAILED")


def mapped_names() -> set[str]:
    names = set(K06_TRIGGER_LEVEL) | {n for _, n in MEASURED_LIMITS}
    for group in (MANDATORY, RED_TEAM, OBLIGATIONS):
        for *_, tests in group:
            names.update(tests)
    for group in (AUTHORIZATION, CONCURRENCY):
        for _, tests in group:
            names.update(tests)
    return names


def _qualified(case: ET.Element) -> str:
    module = (case.get("classname") or "").rsplit(".", 1)[-1]
    return f"{module}::{(case.get('name') or '').split('[')[0]}"


def parse(junit: pathlib.Path) -> dict[str, str]:
    """module::name -> PASS / FAIL / ERROR / SKIP. A parametrised test is PASS
    only if every case passed."""
    results: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = _qualified(case)
        status = "PASS"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "FAIL", "error": "ERROR", "skipped": "SKIP"}[child.tag]
        if results.get(name, "PASS") == "PASS":
            results[name] = status
    return results


def _status(results, name, problems, where, shown="PASS"):
    status = results.get(name, "MISSING")
    if status != "PASS":
        problems.append(f"{where}: {name} is {status}")
        return f"**{status}**"
    return shown


_PATTERNS = {"INSERT": r"INSERT\s+INTO\s+turab\.{t}\b", "UPDATE": r"UPDATE\s+turab\.{t}\b",
             "DELETE": r"DELETE\s+FROM\s+turab\.{t}\b"}


def _sources(*dirs: str):
    for d in dirs:
        yield from sorted((ROOT / d).rglob("*.py"))


def _writers(kind: str, table: str, where: tuple[str, ...] = ("src",)) -> list[str]:
    pattern = re.compile(_PATTERNS[kind].format(t=table))
    return sorted(str(p.relative_to(ROOT)) for p in _sources(*where)
                  if pattern.search(p.read_text(encoding="utf-8")))


def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def _updated_columns(table: str) -> list[str]:
    """Every column any UPDATE of `table` under `src/` sets."""
    pattern = re.compile(rf"UPDATE\s+turab\.{table}\s+SET\s+(.*?)\s+WHERE\b", re.S)
    columns: set[str] = set()
    for path in _sources("src"):
        for assignments in pattern.findall(path.read_text(encoding="utf-8")):
            for part in _split_top(assignments):
                columns.add(part.split("=")[0].strip())
    return sorted(columns)


def _callers(function: str) -> list[str]:
    pattern = re.compile(rf"message_interactions\.{function}\(")
    return sorted(str(p.relative_to(ROOT)) for p in _sources("src", "db/ops")
                  if pattern.search(p.read_text(encoding="utf-8")))


def _routed() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "src" / "turab" / "api" / "routes").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        found.update(re.findall(r'operation_id="([A-Za-z]+)"', source))
        for const in re.findall(r"operation_id=([A-Z_]+)\b", source):
            found.update(re.findall(rf'^{const} = "([A-Za-z]+)"$', source, re.M))
    return found


def _counts(recorded: dict, provenance: str, problems: list[str]) -> list[str]:
    """G7-19 (i): the event store's sample, refused unless it names the bound run."""
    if not COUNTS.exists():
        problems.append(f"{COUNTS.relative_to(ROOT)} is absent: no sample of the event store")
        return ["**ABSENT**: no sample was taken after the run."]
    text = COUNTS.read_text(encoding="utf-8")
    fields = {k: (m.group(1).strip() if (m := re.search(p, text, re.M)) else None)
              for k, p in COUNT_FIELDS.items()}
    run_at = re.search(r"^Recorded    : (.+)$", provenance, re.M)
    expected = {"run_recorded": run_at.group(1).strip() if run_at else None,
                "commit": recorded.get("commit"), "fingerprint": recorded.get("fingerprint"),
                "report_sha256": recorded.get("report_sha256")}
    for key, value in expected.items():
        if fields.get(key) != value:
            problems.append(f"the event store's sample names {key} {fields.get(key)!r}, "
                            f"not the bound run's {value!r}")
    counts = {s: (m.group(1) if (m := re.search(rf"^  {s:<10} (\d+)$", text, re.M)) else None)
              for s in STATUSES}
    for s, v in counts.items():
        if v is None:
            problems.append(f"the event store's sample has no count for {s}")
    tail = text.split("FAILED, by error_text:\n", 1)
    failed = re.findall(r"^  (\S+)\s+(\d+)$", tail[1].split("\n\n", 1)[0], re.M) if len(tail) == 2 else []
    if len(tail) != 2:
        problems.append("the event store's sample has no FAILED by error_text")
    return [f"- **Sampled at** {fields['sampled']}, from the test database "
            f"`{fields['database']}`, for the run recorded at {fields['run_recorded']} "
            f"(commit `{fields['commit']}`, source fingerprint `{fields['fingerprint']}`, "
            f"report sha256 `{fields['report_sha256']}`), "
            f"from `{COUNTS.relative_to(ROOT)}`.", "",
            "| `processing_status` | Count |", "|---|---|",
            *[f"| {s} | {counts[s]} |" for s in STATUSES], "",
            "FAILED, by `error_text`: "
            + (", ".join(f"`{k}` {v}" for k, v in failed) or "none") + ".", "",
            "- **What this is, and is not:** a sample from the run's test database, taken "
            "after the run; not the state at the moment of the last test, and **never a "
            "PASS**. They are the suite's test events. **No reception of a real event, "
            "and no proof of Meta's path, is claimed.**"]


def render(results: dict[str, str], junit: pathlib.Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    bound = junit == DEFAULT_JUNIT.resolve()
    shown = junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit
    out = ["# Slice 7 — closure evidence", "",
           "**Generated** by `db/gate/slice7_evidence.py` from "
           f"`{shown}`. **Do not edit.**", "",
           "> Slice 7, Communication / WhatsApp Record (plan §6.4, G7-19). **Not a STOP "
           "GATE.** **R-1 is UNMET: no real event may be received.** **K06 UNPROVEN.** "
           "**SALE only.** The limits of §6 are never PASS.", ""]
    recorded: dict = {}
    provenance = ""
    if bound:
        recorded, binding = run_binding.check(ROOT)
        binding += run_binding.recorded_fingerprint_problems(GATE_RUN, ROOT)
        problems += binding
        provenance = (ROOT / run_binding.PROVENANCE).read_text()
        cases = run_binding.counted(junit)
        out += [f"- The JUnit run is recorded at commit `{recorded.get('commit')}`, source "
                f"fingerprint `{recorded.get('fingerprint')}`, report sha256 "
                f"`{recorded.get('report_sha256')}` "
                "(`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).",
                f"- Counted in the report: {cases.tests} test cases, {cases.failures} "
                f"failures, {cases.errors} errors, {cases.skipped} skipped.",
                "- Binding (`db/gate/run_binding.py`): "
                + ("the report's digest and counts are the recorded ones, and the current "
                   "tree's source fingerprint is the run's and the gate run's."
                   if not binding else "**FAILED**: " + "; ".join(binding) + ".")]
    else:
        out += ["- **UNBOUND RUN**: this report is not the committed clean-tree run, and "
                "no commit or fingerprint is claimed for it."]
        problems.append("the report is not the committed run; the document is not evidence")
    out += ["- Tests are named `module::name`.",
            "- These are our runs; nobody else has re-run them.", "",
            "## 1. The four mandatory tests (plan §6.1)", "",
            "The end-to-end test (`test_slice7_step5`, every business row made over HTTP) "
            "is listed first; the earlier steps' tests follow.", "",
            "| # | Handoff wording | Test | Status |", "|---|---|---|---|"]
    for num, wording, tests in MANDATORY:
        for name in tests:
            out.append(f"| {num} | {wording} | `{name}` | "
                       f"{_status(results, name, problems, 'mandatory ' + num)} |")
    out += ["", "## 2. Red-team cases (plan §6.2)", "",
            "| Case | Statement | Test | Status |", "|---|---|---|---|"]
    for case, what, tests in RED_TEAM:
        for name in tests:
            out.append(f"| {case} | {what} | `{name}` | {_status(results, name, problems, case)} |")
    out += ["", "**K06 — UNPROVEN.** The application role is a superuser and owns every "
            "table (EN-02). The refusals below are trigger- and constraint-level, and are "
            "never counted as K06:", ""]
    out += [f"- `{n}` {_status(results, n, problems, 'trigger-level', 'passes')} "
            "(trigger-level)" for n in K06_TRIGGER_LEVEL]
    out += ["", "## 3. Authorization (plan §6.3)", "",
            "| Rule | Test | Status |", "|---|---|---|"]
    for rule, tests in AUTHORIZATION:
        for name in tests:
            out.append(f"| {rule} | `{name}` | {_status(results, name, problems, rule)} |")
    out += ["", "## 4. What the reviews of Slice 7 asked to be proven", "",
            "| Review | Obligation | Test | Status |", "|---|---|---|---|"]
    for review, what, tests in OBLIGATIONS:
        for name in tests:
            out.append(f"| {review} | {what} | `{name}` | "
                       f"{_status(results, name, problems, 'review ' + review)} |")
    out += ["", "**Concurrency:**", "", "| Race | Test | Status |", "|---|---|---|"]
    for race, tests in CONCURRENCY:
        for name in tests:
            out.append(f"| {race} | `{name}` | {_status(results, name, problems, race)} |")

    out += ["", "## 5. The writes to the four tables, computed from the tree (plan §7 (9), "
            "G7-19 (ii))", "",
            "An inventory of the application's statements under `src/`, read by this "
            "generator. **It is not a guarantee against a superuser's writes** (K06).", "",
            "| Table | Kind | Decided | Found | |", "|---|---|---|---|---|"]
    for table, kinds in WRITES.items():
        for kind, approved in kinds.items():
            found = _writers(kind, table)
            if found != sorted(approved):
                problems.append(f"{table} {kind} by {found}, not {sorted(approved)}")
            out.append(f"| `{table}` | {kind} | "
                       f"{', '.join(f'`{f}`' for f in sorted(approved)) or 'none'} | "
                       f"{', '.join(f'`{f}`' for f in found) or 'none'} | "
                       f"{'as decided' if found == sorted(approved) else '**NOT DECIDED**'} |")
    out += ["", "**The columns each UPDATE sets:**", "",
            "| Table | Decided | Found |", "|---|---|---|"]
    for table, approved in UPDATE_COLUMNS.items():
        found = _updated_columns(table)
        if found != approved:
            problems.append(f"{table} UPDATE sets {found}, not {approved}")
        out.append(f"| `{table}` | {', '.join(f'`{c}`' for c in approved)} | "
                   f"{', '.join(f'`{c}`' for c in found) or 'none'} |")
    ops_writes = sorted({f for table in WRITES for kind in _PATTERNS
                         for f in _writers(kind, table, ("db/ops",))})
    if ops_writes:
        problems.append(f"an operator script writes one of the four tables itself: {ops_writes}")
    out += ["", "**The module that holds the INSERT, and who calls it** (`interactions`):", ""]
    for function, approved in INTERACTION_CALLERS.items():
        found = _callers(function)
        if found != sorted(approved):
            problems.append(f"message_interactions.{function} is called by {found}, "
                            f"not {sorted(approved)}")
        out.append(f"- `message_interactions.{function}` (its INSERT in "
                   f"`{INTER}`) is called by: "
                   + (", ".join(f"`{f}`" for f in found) or "nobody") + ".")
    out += [f"- `{OPP}` holds Slice 5's INSERT (share, close, revalidate with a note).",
            "- The operator scripts under `db/ops/` hold no statement on the four tables: "
            + ("none found." if not ops_writes else "**" + ", ".join(ops_writes) + "**."),
            "", "## 6. The event store: " + "a sample measured right after the run "
            "(G7-19 (i))", ""]
    if bound:
        out += _counts(recorded, provenance, problems)
    else:
        out += ["- Not shown: the run is not bound."]

    out += ["", "## 7. Limits (never PASS, G7-19 (iii))", "",
            "- **R-1 UNMET.** The relay is not built, and its seven duties are untested "
            "(G7-2 (ii), (a2) decided). **The relay's signature proves the relay's origin, "
            "not Meta's**: Meta's verification is never counted as done in this slice. No "
            "reception of a real event is claimed.",
            "- **K06 UNPROVEN** (EN-02): §2's refusals are trigger- and constraint-level.",
            "- **Retention is not claimed** (OQ7-1): content archived under a consent "
            "stays after its revocation.", ""]
    for what, name in MEASURED_LIMITS:
        out.append(f"- **{what}.** `{name}` "
                   f"{_status(results, name, problems, 'limit', 'measured')} (LIMIT)")
    out += ["- **Slice 6's carried limits:** SALE only (G4-5R open); K06; and its two "
            "stated limits (§5 of `docs/gate/SLICE_6_EVIDENCE.md`), named here, not "
            "re-measured.",
            "- **Slice 5's and Slice 6's evidence** (`SLICE_5_STOP_GATE_E.md`, "
            "`SLICE_6_EVIDENCE.md`) stay their trees' records; this generator reads "
            "neither."]

    corrections = yaml.safe_load(CORRECTIONS.read_text(encoding="utf-8"))
    entries = {e["id"]: e for section in corrections.values() if isinstance(section, list)
               for e in section if isinstance(e, dict) and "id" in e}
    out += ["", "## 8. The contract's corrections (plan §7 (1)) and the operations", ""]
    for cid in APPROVED:
        approved = (entries.get(cid) or {}).get("approved")
        if not approved:
            problems.append(f"{cid} carries no approval date")
        out.append(f"- **{cid}:** " + (f"approved {approved}." if approved
                                       else "**NOT APPROVED**."))
    ops = _routed()
    missing = [o for o in OPERATIONS if o not in ops]
    if missing:
        problems.append(f"Slice 7 operations without a route: {missing}")
    out += ["- **The operations:** " + ", ".join(
        f"`{o}`" + (" routed" if o in ops else " **NOT ROUTED**") for o in OPERATIONS) + ".",
            "- The remaining conditions are argued in the steps' delivery notes, which "
            "this document does not replace."]
    return "\n".join(out) + "\n", problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=pathlib.Path, default=DEFAULT_JUNIT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    junit = args.junit.resolve()
    body, problems = render(parse(junit), junit)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != body:
            problems.append(f"{OUT.relative_to(ROOT)} is stale; regenerate it")
    else:
        OUT.write_text(body, encoding="utf-8")
        print(f"wrote {OUT}")
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
