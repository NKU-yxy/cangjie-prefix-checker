#!/usr/bin/env python3
"""Independently recompute the locked G1 scale gate from raw harness trials.

Only ``runs`` and the raw case/document metadata emitted by ``audit_harness.py``
are used.  Stored harness summaries are deliberately ignored.  The analyzer is
read-only: it never launches a solution or changes either audited checkout.

Exit status is 0 for SCALE_GATE_PASS, 1 for a completed recomputation with one
or more failed gates, and 2 for an unreadable/malformed input document.  A scale
PASS is not, by itself, the final competition acceptance verdict.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence


CONTROL_SHA = "68d780d54c25883b4e05c3f3562b315750b38af0"
CANDIDATE_SHA = "499c9c787fdbd8140307c5b5f472e9aee0c9342c"
OFFICIAL_SHA = "88336c400e7a4a671424e3e6c46c0866c8c0af93"
OFFICIAL_REGISTRY_SHA256 = (
    "2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2"
)

PROTOCOLS = ("default", "competition")
ROLES = ("control", "candidate")
LOCAL_COUNTS = (0, 1, 2, 10, 25, 50, 100, 150, 200, 250, 300, 500)
POWER_COUNTS = (50, 100, 150, 200, 250, 300, 500)
IDENTIFIER_CASE = "four-kilobyte-identifier"
OTHER_SCALE_CASES = (
    "eight-kilobyte-string",
    "eighty-top-level-functions",
    "ninety-six-nested-blocks",
    "sixty-four-nested-comments",
    "three-hundred-element-array",
    "two-hundred-crlf-lines",
    "late-error-after-250-declarations",
)
ALL_NONLOCAL_CASES = OTHER_SCALE_CASES + (IDENTIFIER_CASE,)

REPETITIONS = 3
CONTROL_300_REPETITIONS = 1
CONTROL_300_TIMEOUT_NS = 35_000_000_000
LOCAL_CANDIDATE_LIMIT_NS = 2_000_000_000
MIN_CONTROL_300_SPEEDUP = 10.0
MAX_OTHER_TIME_RATIO = 1.10
MAX_RSS_RATIO = 1.25
MIN_IDENTIFIER_COMMON_PREFIX = 80
MAX_IDENTIFIER_PREFIX_TIME_RATIO = 1.10
MAX_POWER_EXPONENT = 2.0


class InputError(ValueError):
    """The JSON cannot support an independent scale recomputation."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_number(value: Any) -> float | None:
    if not _is_number(value):
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0.0 else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _median(values: Iterable[int | float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else statistics.median(present)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _decode_b64(value: Any, location: str, issues: list[str]) -> bytes | None:
    if not isinstance(value, str):
        issues.append(f"{location}: missing/non-string base64 payload")
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as error:
        issues.append(f"{location}: invalid base64 ({type(error).__name__}: {error})")
        return None


def _check_digest(
    payload: bytes | None,
    value: Any,
    location: str,
    issues: list[str],
    *,
    required: bool = True,
) -> None:
    if payload is None:
        return
    if value is None and not required:
        return
    if not isinstance(value, str) or value != _sha256(payload):
        issues.append(f"{location}: SHA-256 missing or does not match raw bytes")


def _strict_bits(raw: bytes | None, location: str, issues: list[str]) -> list[str]:
    if raw is None:
        return []
    records = raw.splitlines(keepends=True)
    bits: list[str] = []
    for index, record in enumerate(records):
        if record == b"0\n":
            bits.append("0")
        elif record == b"1\n":
            bits.append("1")
        else:
            issues.append(
                f"{location}: stdout record {index} is not exactly b'0\\n' or b'1\\n'"
            )
    if raw and not records:
        issues.append(f"{location}: nonempty stdout did not contain a record")
    return bits


def _continue_bit(protocol: str) -> str:
    return "1" if protocol == "competition" else "0"


def _reject_bit(protocol: str) -> str:
    return "0" if protocol == "competition" else "1"


def _normal_bits(bits: Sequence[str], protocol: str) -> list[bool]:
    """Normalize protocol output to True=continue, False=reject."""
    continue_bit = _continue_bit(protocol)
    return [bit == continue_bit for bit in bits]


def _case_expected(name: str) -> str:
    return "reject" if name == "late-error-after-250-declarations" else "accept"


def _local_name(count: int) -> str:
    return f"locals-{count}"


def _all_expected_cases() -> tuple[str, ...]:
    return tuple(_local_name(count) for count in LOCAL_COUNTS) + ALL_NONLOCAL_CASES


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{location}: expected JSON object")
    return value


def load_document(path: Path, index: int) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    try:
        root = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InputError(f"invalid UTF-8 JSON in {path}: {error}") from error
    root = _mapping(root, str(path))
    if root.get("kind") != "scale":
        raise InputError(f"{path}: kind is {root.get('kind')!r}, expected 'scale'")
    if not isinstance(root.get("runs"), list):
        raise InputError(f"{path}: runs must be an array")
    if not isinstance(root.get("cases"), list):
        raise InputError(f"{path}: cases must be an array")
    return {
        "index": index,
        "path": str(path.resolve()),
        "sha256": _sha256(payload),
        "root": root,
    }


def _get_nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _document_audit(document: Mapping[str, Any]) -> dict[str, Any]:
    root = document["root"]
    issues: list[str] = []
    schema = root.get("schema")
    if not isinstance(schema, str) or not schema.startswith("g1-independent-audit-raw-"):
        issues.append(f"unrecognized raw schema {schema!r}")
    if root.get("status") != "complete":
        issues.append(f"report status is {root.get('status')!r}, expected 'complete'")

    locked = root.get("locked_values")
    if not isinstance(locked, dict):
        issues.append("locked_values is missing")
    else:
        expected_locked = {
            "control_sha": CONTROL_SHA,
            "candidate_sha": CANDIDATE_SHA,
            "official_sha": OFFICIAL_SHA,
            "official_registry_sha256": OFFICIAL_REGISTRY_SHA256,
        }
        for key, expected in expected_locked.items():
            if locked.get(key) != expected:
                issues.append(f"locked_values.{key}={locked.get(key)!r}, expected {expected!r}")

    environment = root.get("environment")
    if not isinstance(environment, dict) or environment.get("strict_linux_aarch64") is not True:
        issues.append("environment is not the locked Linux AArch64 environment")

    arguments = root.get("arguments")
    if not isinstance(arguments, dict):
        issues.append("arguments object is missing")
    elif arguments.get("protocol") != "both":
        issues.append(f"arguments.protocol={arguments.get('protocol')!r}, expected 'both'")

    expected_heads = {
        "control": CONTROL_SHA,
        "candidate": CANDIDATE_SHA,
        "official": OFFICIAL_SHA,
    }
    for role, expected in expected_heads.items():
        head = _get_nested(root, "artifacts", "repositories", role, "head")
        if head != expected:
            issues.append(f"artifacts.repositories.{role}.head={head!r}, expected {expected!r}")

    registry_sha = _get_nested(root, "official_registry", "sha256")
    if registry_sha != OFFICIAL_REGISTRY_SHA256:
        issues.append(
            f"official_registry.sha256={registry_sha!r}, expected {OFFICIAL_REGISTRY_SHA256!r}"
        )

    trial_exceptions = root.get("trial_exceptions", [])
    if not isinstance(trial_exceptions, list):
        issues.append("trial_exceptions is not an array")
        trial_exceptions = [{"malformed_trial_exceptions": repr(trial_exceptions)}]
    elif trial_exceptions:
        issues.append(f"raw harness recorded {len(trial_exceptions)} trial exception(s)")

    return {
        "path": document["path"],
        "sha256": document["sha256"],
        "schema": schema,
        "status": root.get("status"),
        "run_count": len(root["runs"]),
        "case_count": len(root["cases"]),
        "section": arguments.get("section") if isinstance(arguments, dict) else None,
        "issues": issues,
        "trial_exceptions": trial_exceptions,
        "control_solution_sha256": _get_nested(root, "artifacts", "solutions", "control", "sha256"),
        "candidate_solution_sha256": _get_nested(root, "artifacts", "solutions", "candidate", "sha256"),
    }


def _event_data(run: Mapping[str, Any], issues: list[str]) -> tuple[list[Mapping[str, Any]], str]:
    for key in ("deadline_response_events", "response_events_at_deadline", "response_events"):
        value = run.get(key)
        if isinstance(value, list):
            if not all(isinstance(item, dict) for item in value):
                issues.append(f"{key}: contains a non-object event")
                return [], key
            return value, key
    issues.append("response_events: no deadline-capable event array is present")
    return [], "missing"


def _deadline_stdout(
    run: Mapping[str, Any],
    full_stdout: bytes | None,
    events: Sequence[Mapping[str, Any]],
    deadline_answer_count: int | None,
    issues: list[str],
) -> tuple[bytes | None, str]:
    direct = run.get("deadline_stdout_raw_b64")
    if direct is not None:
        payload = _decode_b64(direct, "deadline_stdout_raw_b64", issues)
        _check_digest(
            payload,
            run.get("deadline_stdout_sha256"),
            "deadline_stdout_sha256",
            issues,
            required=False,
        )
        return payload, "deadline_stdout_raw_b64"

    byte_count = _nonnegative_int(run.get("deadline_stdout_byte_count"))
    if byte_count is not None:
        if full_stdout is None or byte_count > len(full_stdout):
            issues.append("deadline_stdout_byte_count exceeds/misses full stdout")
            return None, "deadline_stdout_byte_count_invalid"
        return full_stdout[:byte_count], "stdout_raw_b64[:deadline_stdout_byte_count]"

    if deadline_answer_count is not None and len(events) >= deadline_answer_count:
        records: list[bytes] = []
        for index, event in enumerate(events[:deadline_answer_count]):
            raw = _decode_b64(event.get("raw_b64"), f"response_events[{index}].raw_b64", issues)
            if raw is None:
                return None, "response_events_invalid"
            records.append(raw)
        return b"".join(records), "response_events fallback"

    issues.append("cannot reconstruct stdout as observed at the deadline")
    return None, "missing"


def _rss_gate_value(run: Mapping[str, Any], timed_out: bool, issues: list[str]) -> tuple[float | None, str]:
    rss = run.get("rss")
    if not isinstance(rss, dict):
        issues.append("rss: missing/non-object")
        return None, "missing"

    priorities: list[tuple[str, Any]] = [
        ("gate_peak_vmhwm_kib", rss.get("gate_peak_vmhwm_kib")),
    ]
    if timed_out:
        priorities.append(("deadline_snapshot_vmhwm_kib", rss.get("deadline_snapshot_vmhwm_kib")))
    priorities.append(("peak_vmhwm_kib", rss.get("peak_vmhwm_kib")))
    for key, value in priorities:
        parsed = _positive_number(value)
        if parsed is not None:
            return parsed, f"rss.{key}"

    issues.append("rss: no positive VmHWM gate value (missing RSS fails the gate)")
    return None, "missing"


def _timeout_lower_bound(run: Mapping[str, Any]) -> tuple[float | None, str]:
    explicit = _positive_number(run.get("configured_timeout_lower_bound_ns"))
    if explicit is not None:
        return explicit, "configured_timeout_lower_bound_ns"
    seconds = _positive_number(run.get("timeout_seconds"))
    if seconds is not None:
        return seconds * 1_000_000_000.0, "timeout_seconds fallback"
    return None, "missing"


def audit_trial(run_value: Any, source: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(run_value, dict):
        return {
            "trial_key": f"doc{source['index']}:ordinal{ordinal}",
            "source_path": source["path"],
            "case_name": None,
            "protocol": None,
            "role": None,
            "role_repetition": None,
            "issues": ["run is not a JSON object"],
            "full_success": False,
            "clean_timeout_prefix": False,
            "naturally_completed_for_timing": False,
            "process_total_ns": None,
            "deadline_answer_count": None,
            "gate_vmhwm_kib": None,
        }
    run = run_value
    run_id = run.get("run_id")
    trial_key = f"doc{source['index']}:run{run_id if run_id is not None else 'ordinal' + str(ordinal)}"
    case_name = run.get("case_name")
    protocol = run.get("protocol")
    role = run.get("role")
    role_repetition = _nonnegative_int(run.get("role_repetition"))
    if not isinstance(case_name, str) or not case_name:
        issues.append("case_name is missing/invalid")
    if protocol not in PROTOCOLS:
        issues.append(f"protocol={protocol!r}, expected default or competition")
    if role not in ROLES:
        issues.append(f"role={role!r}, expected control or candidate")
    if role_repetition is None or role_repetition < 1:
        issues.append("role_repetition is missing or less than one")

    expected = _case_expected(case_name) if isinstance(case_name, str) else "accept"
    if run.get("case_expected") != expected:
        issues.append(f"case_expected={run.get('case_expected')!r}, independently expected {expected!r}")

    full_stdout = _decode_b64(run.get("stdout_raw_b64"), "stdout_raw_b64", issues)
    _check_digest(full_stdout, run.get("stdout_sha256"), "stdout_sha256", issues)
    full_bits = _strict_bits(full_stdout, "full stdout", issues)

    full_stderr = _decode_b64(run.get("stderr_raw_b64"), "stderr_raw_b64", issues)
    _check_digest(full_stderr, run.get("stderr_sha256"), "stderr_sha256", issues)
    profile = run.get("profile_stderr")
    if isinstance(profile, dict):
        stripped_stderr = _decode_b64(
            profile.get("stderr_without_profile_raw_b64"),
            "profile_stderr.stderr_without_profile_raw_b64",
            issues,
        )
        _check_digest(
            stripped_stderr,
            profile.get("stderr_without_profile_sha256"),
            "profile_stderr.stderr_without_profile_sha256",
            issues,
        )
        parse_errors = profile.get("parse_errors")
        if not isinstance(parse_errors, list):
            issues.append("profile_stderr.parse_errors is not an array")
        elif parse_errors:
            issues.append(f"profile stderr parse errors: {parse_errors!r}")
    else:
        stripped_stderr = full_stderr
    if stripped_stderr not in (None, b""):
        issues.append("non-profile stderr is not empty")

    trailing_stdout = _decode_b64(
        run.get("trailing_stdout_raw_b64"), "trailing_stdout_raw_b64", issues
    )
    _check_digest(
        trailing_stdout,
        run.get("trailing_stdout_sha256"),
        "trailing_stdout_sha256",
        issues,
    )

    cleanup_stdout: bytes | None = b""
    if run.get("cleanup_stdout_raw_b64") is not None:
        cleanup_stdout = _decode_b64(
            run.get("cleanup_stdout_raw_b64"), "cleanup_stdout_raw_b64", issues
        )
        _check_digest(
            cleanup_stdout,
            run.get("cleanup_stdout_sha256"),
            "cleanup_stdout_sha256",
            issues,
            required=False,
        )
    cleanup_bits = _strict_bits(cleanup_stdout, "cleanup stdout", issues)

    reported_answer_count = _nonnegative_int(run.get("answer_count"))
    if reported_answer_count is None:
        issues.append("answer_count is missing/invalid")
    explicit_deadline_count = _nonnegative_int(run.get("deadline_answer_count"))
    if run.get("deadline_answer_count") is not None and explicit_deadline_count is None:
        issues.append("deadline_answer_count is invalid")
    if explicit_deadline_count is not None:
        deadline_answer_count = explicit_deadline_count
        deadline_count_source = "deadline_answer_count"
    else:
        deadline_answer_count = reported_answer_count
        deadline_count_source = "answer_count fallback"

    events, events_source = _event_data(run, issues)
    deadline_stdout, deadline_stdout_source = _deadline_stdout(
        run, full_stdout, events, deadline_answer_count, issues
    )
    deadline_bits = _strict_bits(deadline_stdout, "deadline stdout", issues)
    if deadline_answer_count is not None and len(deadline_bits) != deadline_answer_count:
        issues.append(
            f"deadline answer count {deadline_answer_count} != strict deadline records {len(deadline_bits)}"
        )

    event_times_ns: list[float | None] = []
    previous_time = -1.0
    for index, event in enumerate(events[: len(deadline_bits)]):
        elapsed = _positive_number(event.get("response_elapsed_ns"))
        event_times_ns.append(elapsed)
        if elapsed is None:
            issues.append(f"{events_source}[{index}].response_elapsed_ns missing/invalid")
        elif elapsed < previous_time:
            issues.append(f"{events_source}: response times are not monotonic")
        else:
            previous_time = elapsed
        strict_bit = event.get("strict_bit")
        if strict_bit is not None and strict_bit != deadline_bits[index]:
            issues.append(f"{events_source}[{index}].strict_bit disagrees with raw deadline stdout")
    if len(events) < len(deadline_bits):
        issues.append("fewer response events than deadline answers; prefix timing is incomplete")

    timed_out = run.get("timed_out")
    if not isinstance(timed_out, bool):
        issues.append("timed_out is not boolean")
        timed_out = False
    process_total_ns = _positive_number(run.get("process_total_ns"))
    if process_total_ns is None:
        issues.append("process_total_ns is missing/nonpositive")
    interaction_elapsed_ns = _positive_number(run.get("interaction_elapsed_ns"))
    deadline_elapsed_ns = _positive_number(run.get("deadline_elapsed_ns"))
    cleanup_elapsed_ns = _positive_number(run.get("cleanup_elapsed_ns"))
    timeout_lower_bound_ns, timeout_lower_bound_source = _timeout_lower_bound(run)

    returncode = run.get("returncode")
    if returncode is not None and (isinstance(returncode, bool) or not isinstance(returncode, int)):
        issues.append("returncode is neither integer nor null")
    spawn_exception = run.get("spawn_exception")
    protocol_error = run.get("protocol_error")
    if spawn_exception is not None:
        issues.append(f"spawn_exception is present: {spawn_exception!r}")
    if protocol_error is not None:
        issues.append(f"protocol_error is present: {protocol_error!r}")

    token_count = _nonnegative_int(run.get("token_count_available"))
    tokens_sent = _nonnegative_int(run.get("tokens_sent"))
    if token_count is None:
        issues.append("token_count_available is missing/invalid")
    if tokens_sent is None:
        issues.append("tokens_sent is missing/invalid")
    if deadline_answer_count is not None and tokens_sent is not None and deadline_answer_count > tokens_sent:
        issues.append("deadline answers exceed tokens sent")
    if len(full_bits) and tokens_sent is not None and len(full_bits) > tokens_sent:
        issues.append("full stdout records exceed tokens sent")

    if protocol in PROTOCOLS:
        continue_bit = _continue_bit(protocol)
        reject_bit = _reject_bit(protocol)
        if expected == "accept":
            if any(bit != continue_bit for bit in full_bits):
                issues.append("accept case emitted a reject or invalid protocol bit")
            transcript_complete = (
                token_count is not None
                and len(full_bits) == token_count
                and tokens_sent == token_count
            )
        else:
            transcript_complete = bool(full_bits) and full_bits[-1] == reject_bit and all(
                bit == continue_bit for bit in full_bits[:-1]
            )
            if not transcript_complete:
                issues.append("reject case transcript is not continue* followed by one reject")
        if any(bit != continue_bit for bit in deadline_bits[:-1] if expected == "reject"):
            issues.append("deadline transcript has a non-continuation before final reject")
        if expected == "accept" and any(bit != continue_bit for bit in deadline_bits):
            issues.append("deadline transcript for accept case is not all-continuation")
        if cleanup_bits and any(bit != continue_bit for bit in cleanup_bits):
            issues.append("post-deadline cleanup stdout contains a non-continuation response")
    else:
        transcript_complete = False

    termination = run.get("termination")
    naturally_completed_for_timing = (
        not timed_out
        and process_total_ns is not None
        and returncode is not None
        and spawn_exception is None
    )
    base_clean = not issues
    full_success = all(
        (
            base_clean,
            not timed_out,
            returncode == 0,
            termination == "natural",
            trailing_stdout == b"",
            transcript_complete,
        )
    )
    clean_timeout_prefix = all(
        (
            base_clean,
            timed_out,
            timeout_lower_bound_ns is not None,
            bool(deadline_bits),
        )
    )

    gate_vmhwm_kib, rss_source = _rss_gate_value(run, timed_out, issues)
    # RSS is a required independent observation, so recompute cleanliness after
    # adding a possible missing-VmHWM issue.
    base_clean = not issues
    full_success = full_success and base_clean
    clean_timeout_prefix = clean_timeout_prefix and base_clean

    stored_bits = run.get("response_bits")
    if isinstance(stored_bits, list):
        compare_count = min(len(stored_bits), len(deadline_bits))
        if stored_bits[:compare_count] != deadline_bits[:compare_count]:
            issues.append("stored response_bits disagree with raw deadline transcript")
            full_success = False
            clean_timeout_prefix = False

    case_ok_reported = run.get("case_ok")
    if not timed_out and case_ok_reported is not None:
        if not isinstance(case_ok_reported, bool) or case_ok_reported != full_success:
            issues.append(
                f"stored case_ok={case_ok_reported!r} disagrees with independent full_success={full_success}"
            )
            full_success = False

    normalized_deadline = _normal_bits(deadline_bits, protocol) if protocol in PROTOCOLS else []
    normalized_full = _normal_bits(full_bits, protocol) if protocol in PROTOCOLS else []
    return {
        "trial_key": trial_key,
        "source_path": source["path"],
        "source_document_index": source["index"],
        "run_id": run_id,
        "ordinal": ordinal,
        "case_name": case_name,
        "protocol": protocol,
        "role": role,
        "role_repetition": role_repetition,
        "schedule_key": run.get("schedule_key"),
        "timed_out": timed_out,
        "timeout_phase": run.get("timeout_phase"),
        "termination": termination,
        "returncode": returncode,
        "process_total_ns": process_total_ns,
        "process_total_ms": None if process_total_ns is None else process_total_ns / 1e6,
        "naturally_completed_for_timing": naturally_completed_for_timing,
        "interaction_elapsed_ns": interaction_elapsed_ns,
        "deadline_elapsed_ns": deadline_elapsed_ns,
        "cleanup_elapsed_ns": cleanup_elapsed_ns,
        "timeout_lower_bound_ns": timeout_lower_bound_ns,
        "timeout_lower_bound_source": timeout_lower_bound_source,
        "reported_answer_count": reported_answer_count,
        "deadline_answer_count": deadline_answer_count,
        "deadline_answer_count_source": deadline_count_source,
        "deadline_stdout_source": deadline_stdout_source,
        "deadline_stdout_sha256": None if deadline_stdout is None else _sha256(deadline_stdout),
        "full_stdout_sha256_recomputed": None if full_stdout is None else _sha256(full_stdout),
        "full_stderr_sha256_recomputed": None if full_stderr is None else _sha256(full_stderr),
        "trailing_stdout_bytes": None if trailing_stdout is None else len(trailing_stdout),
        "cleanup_stdout_bytes": None if cleanup_stdout is None else len(cleanup_stdout),
        "deadline_bits": deadline_bits,
        "normalized_deadline_transcript": normalized_deadline,
        "normalized_full_transcript": normalized_full,
        "deadline_transcript_sha256": _sha256(bytes(normalized_deadline)),
        "full_transcript_sha256": _sha256(bytes(normalized_full)),
        "deadline_response_elapsed_ns": event_times_ns,
        "response_events_source": events_source,
        "gate_vmhwm_kib": gate_vmhwm_kib,
        "gate_vmhwm_source": rss_source,
        "full_success": full_success,
        "clean_timeout_prefix": clean_timeout_prefix,
        "issues": issues,
    }


def _expected_count(case_name: str, protocol: str, role: str, trials: Sequence[Mapping[str, Any]]) -> int:
    if case_name.startswith("locals-"):
        try:
            count = int(case_name.split("-", 1)[1])
        except ValueError:
            return 0
        if role == "candidate":
            return REPETITIONS
        if count <= 250:
            return REPETITIONS
        if count == 300:
            return CONTROL_300_REPETITIONS
        if count == 500:
            matching_300 = [
                trial
                for trial in trials
                if trial["case_name"] == "locals-300"
                and trial["protocol"] == protocol
                and trial["role"] == "control"
            ]
            return 0 if len(matching_300) == 1 and matching_300[0]["timed_out"] else 1
        return 0
    if case_name in ALL_NONLOCAL_CASES:
        return REPETITIONS
    return 0


def _trial_acceptable(trial: Mapping[str, Any], case_name: str, role: str) -> bool:
    if trial["full_success"]:
        return True
    if case_name == IDENTIFIER_CASE and trial["clean_timeout_prefix"]:
        return True
    if case_name == "locals-300" and role == "control" and trial["clean_timeout_prefix"]:
        return True
    return False


def _group_summary(
    case_name: str,
    protocol: str,
    role: str,
    trials: Sequence[Mapping[str, Any]],
    expected_count: int,
) -> dict[str, Any]:
    group = [
        trial
        for trial in trials
        if trial["case_name"] == case_name
        and trial["protocol"] == protocol
        and trial["role"] == role
    ]
    completed_timing = [
        trial["process_total_ns"]
        for trial in group
        if trial["naturally_completed_for_timing"]
    ]
    rss_values = [trial["gate_vmhwm_kib"] for trial in group]
    repetitions = [trial["role_repetition"] for trial in group]
    expected_repetitions = list(range(1, expected_count + 1))
    acceptable = [_trial_acceptable(trial, case_name, role) for trial in group]
    count_ok = len(group) == expected_count and sorted(repetitions) == expected_repetitions
    passed = count_ok and all(acceptable) and all(value is not None for value in rss_values)
    if expected_count == 0:
        passed = not group
    return {
        "case_name": case_name,
        "protocol": protocol,
        "role": role,
        "expected_trial_count": expected_count,
        "observed_trial_count": len(group),
        "role_repetitions_observed": repetitions,
        "required_count_and_repetitions_exact": count_ok,
        "naturally_completed_trial_count": len(completed_timing),
        "timed_out_trial_count": sum(bool(trial["timed_out"]) for trial in group),
        "acceptable_trial_count": sum(acceptable),
        "process_total_completed_samples_ns": completed_timing,
        "process_total_completed_median_ns": _median(completed_timing),
        "process_total_completed_median_ms": (
            None if not completed_timing else _median(completed_timing) / 1e6
        ),
        "deadline_answer_counts": [trial["deadline_answer_count"] for trial in group],
        "gate_vmhwm_kib_samples": rss_values,
        "gate_vmhwm_kib_median": _median(rss_values),
        "stdout_sha256_by_trial": [trial["full_stdout_sha256_recomputed"] for trial in group],
        "stderr_sha256_by_trial": [trial["full_stderr_sha256_recomputed"] for trial in group],
        "returncodes_by_trial": [trial["returncode"] for trial in group],
        "deadline_transcript_sha256_by_trial": [trial["deadline_transcript_sha256"] for trial in group],
        "full_transcript_sha256_by_trial": [trial["full_transcript_sha256"] for trial in group],
        "failed_or_anomalous_trials": [
            {
                "trial_key": trial["trial_key"],
                "acceptable": acceptable[index],
                "issues": trial["issues"],
            }
            for index, trial in enumerate(group)
            if not acceptable[index] or trial["issues"]
        ],
        "passed": passed,
    }


def _comparison(
    case_name: str,
    protocol: str,
    trials: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_role = {
        role: [
            trial
            for trial in trials
            if trial["case_name"] == case_name
            and trial["protocol"] == protocol
            and trial["role"] == role
        ]
        for role in ROLES
    }
    all_trials = by_role["control"] + by_role["candidate"]
    counts = [trial["deadline_answer_count"] for trial in all_trials]
    valid_counts = [count for count in counts if count is not None]
    common_count = min(valid_counts) if len(valid_counts) == len(counts) and counts else 0
    prefix_equal = True
    common_prefix: list[bool] = []
    for index in range(common_count):
        values = [trial["normalized_deadline_transcript"][index] for trial in all_trials]
        if len(set(values)) != 1:
            prefix_equal = False
            break
        common_prefix.append(values[0])
    if len(common_prefix) != common_count:
        prefix_equal = False

    all_full = bool(all_trials) and all(trial["full_success"] for trial in all_trials)
    full_transcripts = [trial["normalized_full_transcript"] for trial in all_trials]
    full_raw_hashes = [trial["full_stdout_sha256_recomputed"] for trial in all_trials]
    exact_full_equal = all_full and len({tuple(value) for value in full_transcripts}) == 1
    exact_stdout_equal = all_full and len(set(full_raw_hashes)) == 1
    return {
        "case_name": case_name,
        "protocol": protocol,
        "common_deadline_prefix_count": common_count,
        "control_candidate_prefix_equal": prefix_equal,
        "all_trials_fully_completed": all_full,
        "exact_normalized_full_transcript_equal": exact_full_equal,
        "exact_raw_stdout_equal": exact_stdout_equal,
        "comparison_passed": (
            prefix_equal
            and (
                case_name == IDENTIFIER_CASE
                or not all_full
                or (exact_full_equal and exact_stdout_equal)
            )
        ),
    }


def _protocol_equivalence(case_name: str, role: str, trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = {
        protocol: [
            trial
            for trial in trials
            if trial["case_name"] == case_name
            and trial["protocol"] == protocol
            and trial["role"] == role
        ]
        for protocol in PROTOCOLS
    }
    flat = groups["default"] + groups["competition"]
    if not flat:
        if case_name == "locals-500" and role == "control":
            return {
                "case_name": case_name,
                "role": role,
                "passed": True,
                "reason": "not applicable: locked control-500 skip after both control-300 timeouts",
            }
        return {"case_name": case_name, "role": role, "passed": False, "reason": "no trials"}
    if case_name == IDENTIFIER_CASE or any(trial["timed_out"] for trial in flat):
        min_count = min(
            (len(trial["normalized_deadline_transcript"]) for trial in flat),
            default=0,
        )
        prefixes = [tuple(trial["normalized_deadline_transcript"][:min_count]) for trial in flat]
        passed = min_count > 0 and len(set(prefixes)) == 1
        reason = f"normalized common prefix of {min_count} responses"
    else:
        transcripts = [tuple(trial["normalized_full_transcript"]) for trial in flat]
        passed = bool(transcripts) and len(set(transcripts)) == 1
        reason = "exact normalized full transcript"
    return {"case_name": case_name, "role": role, "passed": passed, "reason": reason}


def _check(check_id: str, observed: Any, rule: str, passed: bool) -> dict[str, Any]:
    return {"id": check_id, "observed": observed, "rule": rule, "passed": bool(passed)}


def _fit_log_slope(points: Sequence[tuple[int, float]]) -> float | None:
    if len(points) < 2 or any(n <= 0 or t <= 0.0 for n, t in points):
        return None
    xs = [math.log(float(n)) for n, _ in points]
    ys = [math.log(float(t)) for _, t in points]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    denominator = math.fsum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0.0:
        return None
    return math.fsum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
    ) / denominator


def _power_diagnostic(protocol: str, group_map: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> dict[str, Any]:
    points: list[tuple[int, float]] = []
    for count in POWER_COUNTS:
        value = group_map[(_local_name(count), protocol, "candidate")][
            "process_total_completed_median_ns"
        ]
        if value is not None:
            points.append((count, value))
    local_exponents: list[dict[str, Any]] = []
    for (n1, t1), (n2, t2) in zip(points, points[1:]):
        exponent = math.log(t2 / t1) / math.log(n2 / n1) if t1 > 0.0 and t2 > 0.0 else None
        local_exponents.append(
            {"from_n": n1, "to_n": n2, "time_ratio": t2 / t1, "log_log_exponent": exponent}
        )
    point_map = dict(points)
    endpoint_ratio = _ratio(point_map.get(500), point_map.get(50))
    endpoint_exponent = (
        None if endpoint_ratio is None else math.log(endpoint_ratio) / math.log(500.0 / 50.0)
    )
    fit = _fit_log_slope(points) if len(points) == len(POWER_COUNTS) else None
    endpoint_pass = endpoint_ratio is not None and endpoint_ratio < (500.0 / 50.0) ** MAX_POWER_EXPONENT
    fit_pass = fit is not None and fit < MAX_POWER_EXPONENT
    return {
        "protocol": protocol,
        "points_n_process_total_median_ns": [[n, t] for n, t in points],
        "local_log_log_exponents": local_exponents,
        "endpoint_50_to_500_time_ratio": endpoint_ratio,
        "endpoint_50_to_500_log_log_exponent": endpoint_exponent,
        "overall_ols_log_log_exponent": fit,
        "endpoint_rule": "t500/t50 < (500/50)^2 = 100",
        "fit_rule": "OLS log(time)~log(n) exponent < 2",
        "interpretation": (
            "clearly not near O(n^3): both conservative subquadratic diagnostics pass"
            if endpoint_pass and fit_pass
            else "not proven non-cubic: one or both conservative subquadratic diagnostics fail"
        ),
        "passed": endpoint_pass and fit_pass,
    }


def _prefix_time(trial: Mapping[str, Any], count: int) -> float | None:
    values = trial["deadline_response_elapsed_ns"]
    if count < 1 or len(values) < count:
        return None
    return values[count - 1]


def analyze(documents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    document_audits = [_document_audit(document) for document in documents]
    document_issues = [
        {"path": item["path"], "issue": issue}
        for item in document_audits
        for issue in item["issues"]
    ]

    section_layout_issues: list[str] = []
    sections = [item["section"] for item in document_audits]
    if sections == ["all"]:
        pass
    elif len(sections) == 2 and collections.Counter(sections) == collections.Counter(("locals", "other")):
        pass
    else:
        section_layout_issues.append(
            f"expected one section=all document or exactly one locals plus one other document; got {sections!r}"
        )
    expected_locals = {_local_name(count) for count in LOCAL_COUNTS}
    expected_other = set(ALL_NONLOCAL_CASES)
    for document, audit in zip(documents, document_audits):
        section = audit["section"]
        expected_for_section = (
            expected_locals | expected_other
            if section == "all"
            else expected_locals
            if section == "locals"
            else expected_other
            if section == "other"
            else set()
        )
        case_names = {
            value.get("name")
            for value in document["root"]["cases"]
            if isinstance(value, dict) and isinstance(value.get("name"), str)
        }
        run_names = {
            value.get("case_name")
            for value in document["root"]["runs"]
            if isinstance(value, dict) and isinstance(value.get("case_name"), str)
        }
        if expected_for_section and case_names != expected_for_section:
            section_layout_issues.append(
                f"{document['path']}: section={section} case set mismatch; "
                f"missing={sorted(expected_for_section - case_names)}, extra={sorted(case_names - expected_for_section)}"
            )
        if expected_for_section and not run_names.issubset(expected_for_section):
            section_layout_issues.append(
                f"{document['path']}: section={section} contains out-of-section run cases "
                f"{sorted(run_names - expected_for_section)}"
            )
    document_issues.extend(
        {"path": "<section-layout>", "issue": issue} for issue in section_layout_issues
    )

    solution_pairs = {
        (item["control_solution_sha256"], item["candidate_solution_sha256"])
        for item in document_audits
    }
    if len(solution_pairs) != 1:
        document_issues.append(
            {"path": "<combined>", "issue": "input documents use inconsistent solution hashes"}
        )
    if any(None in pair for pair in solution_pairs):
        document_issues.append(
            {"path": "<combined>", "issue": "one or more solution SHA-256 values are missing"}
        )

    case_records: dict[str, dict[str, Any]] = {}
    case_metadata_issues: list[str] = []
    for document in documents:
        for index, value in enumerate(document["root"]["cases"]):
            if not isinstance(value, dict):
                case_metadata_issues.append(f"{document['path']}: cases[{index}] is not an object")
                continue
            name = value.get("name")
            if not isinstance(name, str):
                case_metadata_issues.append(f"{document['path']}: cases[{index}].name is invalid")
                continue
            expected = _case_expected(name)
            if value.get("expected") != expected:
                case_metadata_issues.append(
                    f"{name}: metadata expected={value.get('expected')!r}, independently expected {expected!r}"
                )
            token_count = _nonnegative_int(value.get("token_count"))
            if token_count is None or token_count < 1:
                case_metadata_issues.append(f"{name}: token_count is missing/nonpositive")
            digest = value.get("source_sha256")
            signature = {"expected": value.get("expected"), "token_count": token_count, "source_sha256": digest}
            previous = case_records.get(name)
            if previous is not None and previous != signature:
                case_metadata_issues.append(f"{name}: inconsistent case metadata across raw documents")
            else:
                case_records[name] = signature

    expected_case_set = set(_all_expected_cases())
    observed_case_set = set(case_records)
    missing_cases = sorted(expected_case_set - observed_case_set)
    extra_cases = sorted(observed_case_set - expected_case_set)
    if missing_cases:
        case_metadata_issues.append(f"missing expected scale case metadata: {missing_cases}")
    if extra_cases:
        case_metadata_issues.append(f"unexpected scale case metadata: {extra_cases}")

    trials: list[dict[str, Any]] = []
    for document in documents:
        for ordinal, run in enumerate(document["root"]["runs"]):
            trials.append(audit_trial(run, document, ordinal))

    trial_keys = [trial["trial_key"] for trial in trials]
    duplicate_trial_keys = sorted(
        key for key, count in collections.Counter(trial_keys).items() if count > 1
    )
    unknown_trials = [
        trial["trial_key"]
        for trial in trials
        if trial["case_name"] not in expected_case_set
        or trial["protocol"] not in PROTOCOLS
        or trial["role"] not in ROLES
    ]

    group_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case_name in _all_expected_cases():
        for protocol in PROTOCOLS:
            for role in ROLES:
                expected_count = _expected_count(case_name, protocol, role, trials)
                group_map[(case_name, protocol, role)] = _group_summary(
                    case_name, protocol, role, trials, expected_count
                )
    group_rows = list(group_map.values())
    all_groups_pass = all(row["passed"] for row in group_rows)

    comparisons = [
        _comparison(case_name, protocol, trials)
        for case_name in _all_expected_cases()
        for protocol in PROTOCOLS
    ]
    comparison_map = {(row["case_name"], row["protocol"]): row for row in comparisons}
    protocol_equivalence = [
        _protocol_equivalence(case_name, role, trials)
        for case_name in _all_expected_cases()
        for role in ROLES
    ]

    locals_rows: list[dict[str, Any]] = []
    local_checks: list[dict[str, Any]] = []
    for protocol in PROTOCOLS:
        for count in LOCAL_COUNTS:
            case_name = _local_name(count)
            control = group_map[(case_name, protocol, "control")]
            candidate = group_map[(case_name, protocol, "candidate")]
            control_time = control["process_total_completed_median_ns"]
            candidate_time = candidate["process_total_completed_median_ns"]
            time_ratio = _ratio(candidate_time, control_time)
            control_rss = control["gate_vmhwm_kib_median"]
            rss_reference_case = case_name
            rss_fallback = False
            if count == 500 and control["expected_trial_count"] == 0:
                control_rss = group_map[("locals-300", protocol, "control")]["gate_vmhwm_kib_median"]
                rss_reference_case = "locals-300"
                rss_fallback = True
            candidate_rss = candidate["gate_vmhwm_kib_median"]
            rss_ratio = _ratio(candidate_rss, control_rss)
            rss_pass = rss_ratio is not None and rss_ratio <= MAX_RSS_RATIO
            transcript_pass = comparison_map[(case_name, protocol)]["comparison_passed"]
            locals_rows.append(
                {
                    "locals": count,
                    "protocol": protocol,
                    "control_completed_median_ms": None if control_time is None else control_time / 1e6,
                    "candidate_completed_median_ms": None if candidate_time is None else candidate_time / 1e6,
                    "candidate_control_time_ratio": time_ratio,
                    "control_timed_out_trials": control["timed_out_trial_count"],
                    "candidate_timed_out_trials": candidate["timed_out_trial_count"],
                    "control_deadline_answer_counts": control["deadline_answer_counts"],
                    "candidate_deadline_answer_counts": candidate["deadline_answer_counts"],
                    "control_gate_vmhwm_kib_median": control_rss,
                    "candidate_gate_vmhwm_kib_median": candidate_rss,
                    "candidate_control_rss_ratio": rss_ratio,
                    "rss_reference_case": rss_reference_case,
                    "rss_reference_is_conservative_300_timeout_fallback": rss_fallback,
                    "rss_passed": rss_pass,
                    "transcript_passed": transcript_pass,
                    "control_group_passed": control["passed"],
                    "candidate_group_passed": candidate["passed"],
                }
            )
            local_checks.append(
                _check(
                    f"locals_{count}_{protocol}_rss",
                    rss_ratio,
                    "candidate median gate VmHWM <= 1.25 * control reference median; no missing trial VmHWM",
                    rss_pass,
                )
            )
            local_checks.append(
                _check(
                    f"locals_{count}_{protocol}_transcript",
                    transcript_pass,
                    "all completed transcripts exact, or candidate extends a correct control-timeout prefix",
                    transcript_pass,
                )
            )

        for count in (300, 500):
            candidate = group_map[(_local_name(count), protocol, "candidate")]
            value = candidate["process_total_completed_median_ns"]
            local_checks.append(
                _check(
                    f"locals_{count}_{protocol}_candidate_complete_under_2s",
                    None if value is None else value / 1e9,
                    "3/3 candidate trials complete correctly and median process_total <= 2 seconds",
                    candidate["passed"]
                    and candidate["naturally_completed_trial_count"] == REPETITIONS
                    and value is not None
                    and value <= LOCAL_CANDIDATE_LIMIT_NS,
                )
            )

        control_300_trials = [
            trial
            for trial in trials
            if trial["case_name"] == "locals-300"
            and trial["protocol"] == protocol
            and trial["role"] == "control"
        ]
        candidate_300 = group_map[("locals-300", protocol, "candidate")]
        candidate_300_time = candidate_300["process_total_completed_median_ns"]
        control_300 = group_map[("locals-300", protocol, "control")]
        if control_300["process_total_completed_median_ns"] is not None:
            control_basis_ns = control_300["process_total_completed_median_ns"]
            control_basis = "completed control process_total median"
            control_basis_valid = control_300["passed"]
        elif len(control_300_trials) == 1 and control_300_trials[0]["clean_timeout_prefix"]:
            control_basis_ns = control_300_trials[0]["timeout_lower_bound_ns"]
            control_basis = control_300_trials[0]["timeout_lower_bound_source"]
            control_basis_valid = (
                control_basis_ns is not None and control_basis_ns >= CONTROL_300_TIMEOUT_NS
            )
        else:
            control_basis_ns = None
            control_basis = "unusable control trial"
            control_basis_valid = False
        speedup = _ratio(control_basis_ns, candidate_300_time)
        local_checks.append(
            _check(
                f"locals_300_{protocol}_control_speedup_at_least_10x",
                {"speedup": speedup, "control_basis": control_basis, "control_basis_ns": control_basis_ns},
                "control completed time or configured 35 s timeout lower bound divided by candidate median >= 10",
                control_basis_valid
                and candidate_300["passed"]
                and speedup is not None
                and speedup >= MIN_CONTROL_300_SPEEDUP,
            )
        )

    power = [_power_diagnostic(protocol, group_map) for protocol in PROTOCOLS]
    for item in power:
        local_checks.append(
            _check(
                f"locals_50_to_500_{item['protocol']}_not_near_cubic",
                {
                    "endpoint_exponent": item["endpoint_50_to_500_log_log_exponent"],
                    "ols_exponent": item["overall_ols_log_log_exponent"],
                    "time_ratio": item["endpoint_50_to_500_time_ratio"],
                },
                "both t500/t50 < 100 and OLS log-log exponent < 2",
                item["passed"],
            )
        )

    local_group_pass = all(
        group_map[(_local_name(count), protocol, "candidate")]["passed"]
        and (
            group_map[(_local_name(count), protocol, "control")]["passed"]
            or (
                count == 500
                and group_map[(_local_name(count), protocol, "control")]["expected_trial_count"] == 0
            )
        )
        for count in LOCAL_COUNTS
        for protocol in PROTOCOLS
    )
    local_checks.insert(
        0,
        _check(
            "all_required_local_trials_valid",
            local_group_pass,
            "all required trials/counts/protocol output/exit/stderr/transcript/VmHWM valid; prescribed control timeouts/skips only",
            local_group_pass,
        ),
    )
    locals_pass = all(check["passed"] for check in local_checks)

    other_rows: list[dict[str, Any]] = []
    other_checks: list[dict[str, Any]] = []
    for case_name in OTHER_SCALE_CASES:
        for protocol in PROTOCOLS:
            control = group_map[(case_name, protocol, "control")]
            candidate = group_map[(case_name, protocol, "candidate")]
            control_time = control["process_total_completed_median_ns"]
            candidate_time = candidate["process_total_completed_median_ns"]
            time_ratio = _ratio(candidate_time, control_time)
            time_delta_ms = (
                None
                if control_time is None or candidate_time is None
                else (candidate_time - control_time) / 1e6
            )
            rss_ratio = _ratio(
                candidate["gate_vmhwm_kib_median"], control["gate_vmhwm_kib_median"]
            )
            transcript_pass = (
                comparison_map[(case_name, protocol)]["exact_normalized_full_transcript_equal"]
                and comparison_map[(case_name, protocol)]["exact_raw_stdout_equal"]
            )
            row_pass = all(
                (
                    control["passed"],
                    candidate["passed"],
                    control["naturally_completed_trial_count"] == REPETITIONS,
                    candidate["naturally_completed_trial_count"] == REPETITIONS,
                    time_ratio is not None and time_ratio <= MAX_OTHER_TIME_RATIO,
                    rss_ratio is not None and rss_ratio <= MAX_RSS_RATIO,
                    transcript_pass,
                )
            )
            other_rows.append(
                {
                    "case_name": case_name,
                    "protocol": protocol,
                    "control_process_total_median_ms": None if control_time is None else control_time / 1e6,
                    "candidate_process_total_median_ms": None if candidate_time is None else candidate_time / 1e6,
                    "candidate_control_time_ratio": time_ratio,
                    "absolute_time_delta_ms": time_delta_ms,
                    "control_gate_vmhwm_kib_median": control["gate_vmhwm_kib_median"],
                    "candidate_gate_vmhwm_kib_median": candidate["gate_vmhwm_kib_median"],
                    "candidate_control_rss_ratio": rss_ratio,
                    "transcript_exact": transcript_pass,
                    "passed": row_pass,
                }
            )
            other_checks.append(
                _check(
                    f"other_{case_name}_{protocol}",
                    {
                        "time_ratio": time_ratio,
                        "absolute_delta_ms": time_delta_ms,
                        "rss_ratio": rss_ratio,
                        "transcript_exact": transcript_pass,
                    },
                    "3/3 each role complete; candidate time median <= 1.10x, VmHWM median <= 1.25x, exact stdout/transcript/exit/stderr",
                    row_pass,
                )
            )
    other_pass = all(check["passed"] for check in other_checks)

    identifier_rows: list[dict[str, Any]] = []
    identifier_checks: list[dict[str, Any]] = []
    identifier_any_timeout = False
    for protocol in PROTOCOLS:
        by_role = {
            role: [
                trial
                for trial in trials
                if trial["case_name"] == IDENTIFIER_CASE
                and trial["protocol"] == protocol
                and trial["role"] == role
            ]
            for role in ROLES
        }
        flat = by_role["control"] + by_role["candidate"]
        identifier_any_timeout = identifier_any_timeout or any(trial["timed_out"] for trial in flat)
        counts = [trial["deadline_answer_count"] for trial in flat]
        common_correct = 0
        if len(flat) == 2 * REPETITIONS and all(count is not None for count in counts):
            minimum = min(counts)
            for index in range(minimum):
                values = [trial["normalized_deadline_transcript"][index] for trial in flat]
                if any(value is not True for value in values) or len(set(values)) != 1:
                    break
                common_correct += 1
        answer_medians = {
            role: _median(trial["deadline_answer_count"] for trial in role_trials)
            for role, role_trials in by_role.items()
        }
        allowed_shortfall = (
            None
            if answer_medians["control"] is None
            else max(2.0, answer_medians["control"] * 0.02)
        )
        answer_pass = all(
            (
                answer_medians["control"] is not None,
                answer_medians["candidate"] is not None,
                allowed_shortfall is not None,
                answer_medians["candidate"] is not None
                and answer_medians["control"] is not None
                and allowed_shortfall is not None
                and answer_medians["candidate"] >= answer_medians["control"] - allowed_shortfall,
            )
        )
        prefix_samples = {
            role: [_prefix_time(trial, common_correct) for trial in role_trials]
            for role, role_trials in by_role.items()
        }
        prefix_medians = {role: _median(values) for role, values in prefix_samples.items()}
        prefix_ratio = _ratio(prefix_medians["candidate"], prefix_medians["control"])
        prefix_pass = all(
            (
                common_correct >= MIN_IDENTIFIER_COMMON_PREFIX,
                all(value is not None for values in prefix_samples.values() for value in values),
                prefix_ratio is not None and prefix_ratio <= MAX_IDENTIFIER_PREFIX_TIME_RATIO,
            )
        )
        groups_valid = all(
            group_map[(IDENTIFIER_CASE, protocol, role)]["passed"] for role in ROLES
        )
        candidate_clean = all(
            _trial_acceptable(trial, IDENTIFIER_CASE, "candidate")
            for trial in by_role["candidate"]
        ) and len(by_role["candidate"]) == REPETITIONS
        control_comparator_clean = all(
            _trial_acceptable(trial, IDENTIFIER_CASE, "control")
            for trial in by_role["control"]
        ) and len(by_role["control"]) == REPETITIONS
        no_new_errors = groups_valid and candidate_clean and control_comparator_clean
        control_rss = group_map[(IDENTIFIER_CASE, protocol, "control")]["gate_vmhwm_kib_median"]
        candidate_rss = group_map[(IDENTIFIER_CASE, protocol, "candidate")]["gate_vmhwm_kib_median"]
        rss_ratio = _ratio(candidate_rss, control_rss)
        rss_pass = rss_ratio is not None and rss_ratio <= MAX_RSS_RATIO
        row_pass = answer_pass and prefix_pass and rss_pass and no_new_errors
        identifier_rows.append(
            {
                "protocol": protocol,
                "deadline_answer_count_samples": {
                    role: [trial["deadline_answer_count"] for trial in role_trials]
                    for role, role_trials in by_role.items()
                },
                "deadline_answer_count_medians": answer_medians,
                "allowed_candidate_shortfall": allowed_shortfall,
                "answer_shortfall_passed": answer_pass,
                "selected_common_correct_prefix_count": common_correct,
                "required_common_correct_prefix_count": MIN_IDENTIFIER_COMMON_PREFIX,
                "selected_prefix_elapsed_ns_samples": prefix_samples,
                "selected_prefix_elapsed_ns_medians": prefix_medians,
                "candidate_control_prefix_time_ratio": prefix_ratio,
                "prefix_time_passed": prefix_pass,
                "control_gate_vmhwm_kib_median": control_rss,
                "candidate_gate_vmhwm_kib_median": candidate_rss,
                "candidate_control_rss_ratio": rss_ratio,
                "rss_passed": rss_pass,
                "no_new_error_output_exception_or_premature_exit": no_new_errors,
                "passed": row_pass,
            }
        )
        identifier_checks.append(
            _check(
                f"identifier_{protocol}_answer_shortfall",
                {
                    "medians": answer_medians,
                    "allowed_shortfall": allowed_shortfall,
                },
                "candidate deadline answer-count median shortfall <= max(2, 2% of control median)",
                answer_pass,
            )
        )
        identifier_checks.append(
            _check(
                f"identifier_{protocol}_common_prefix_time",
                {"common_correct": common_correct, "time_ratio": prefix_ratio},
                "common correct prefix >= 80 and candidate median elapsed time to that prefix <= 1.10x control",
                prefix_pass,
            )
        )
        identifier_checks.append(
            _check(
                f"identifier_{protocol}_rss_and_errors",
                {"rss_ratio": rss_ratio, "no_new_errors": no_new_errors},
                "candidate median gate VmHWM <= 1.25x control, all VmHWM present, no new output/error/exception/early exit",
                rss_pass and no_new_errors,
            )
        )
    identifier_pass = all(check["passed"] for check in identifier_checks)

    coverage_checks = [
        _check(
            "documents_locked_complete_linux_aarch64",
            document_issues,
            "all raw documents complete, locked, Linux AArch64, same independently-built solution hashes, no trial exceptions",
            not document_issues,
        ),
        _check(
            "case_metadata_exact",
            case_metadata_issues,
            "exact 12 generated locals plus locked identifier and seven other scale cases",
            not case_metadata_issues,
        ),
        _check(
            "all_group_trial_counts_and_trials_valid",
            {
                "groups": len(group_rows),
                "failed_groups": [
                    [row["case_name"], row["protocol"], row["role"]]
                    for row in group_rows
                    if not row["passed"]
                ],
            },
            "every required case/protocol/role has exact repetitions and every required trial is acceptable",
            all_groups_pass,
        ),
        _check(
            "no_unknown_or_duplicate_trials",
            {"unknown": unknown_trials, "duplicate_keys": duplicate_trial_keys},
            "no raw trial is discarded, duplicated, or outside the locked matrix",
            not unknown_trials and not duplicate_trial_keys,
        ),
        _check(
            "protocol_transcripts_equivalent",
            [
                [row["case_name"], row["role"]]
                for row in protocol_equivalence
                if not row["passed"]
            ],
            "default and competition transcripts normalize to the same per-token decisions",
            all(row["passed"] for row in protocol_equivalence),
        ),
    ]

    all_checks = coverage_checks + local_checks + other_checks + identifier_checks
    failed_ids = [check["id"] for check in all_checks if not check["passed"]]
    overall_pass = not failed_ids
    anomalous_trials = [
        {
            "trial_key": trial["trial_key"],
            "case_name": trial["case_name"],
            "protocol": trial["protocol"],
            "role": trial["role"],
            "role_repetition": trial["role_repetition"],
            "issues": trial["issues"],
            "full_success": trial["full_success"],
            "clean_timeout_prefix": trial["clean_timeout_prefix"],
        }
        for trial in trials
        if trial["issues"]
        or not _trial_acceptable(trial, str(trial["case_name"]), str(trial["role"]))
    ]

    return {
        "analysis": "independent G1 scale raw-trial recomputation",
        "analysis_policy": {
            "source": "raw runs only; all stored harness summaries ignored",
            "trial_retention": "every observed trial and exception retained; no outlier deletion",
            "timing_median": "process_total_ns from naturally completed trials only",
            "failed_trial_rule": "any failed required trial fails its group even when a completed timing median exists",
            "timeout_timing": "configured timeout lower bound only; cleanup-inclusive process_total is never a speedup basis",
            "rss": "per-trial VmHWM gate value; missing any required value fails; ratios use role medians",
            "complexity": "both 50->500 endpoint exponent and seven-point OLS log-log exponent must be <2",
            "scope": "SCALE_GATE_PASS is not an overall competition verdict",
        },
        "inputs": document_audits,
        "case_metadata_issues": case_metadata_issues,
        "trial_count": len(trials),
        "trial_audits": trials,
        "anomalous_or_failed_trials": anomalous_trials,
        "group_rows": group_rows,
        "control_candidate_transcript_comparisons": comparisons,
        "protocol_equivalence": protocol_equivalence,
        "locals": {
            "rows": locals_rows,
            "power_diagnostics": power,
            "checks": local_checks,
            "passed": locals_pass,
        },
        "other_seven_scale_cases": {
            "rows": other_rows,
            "checks": other_checks,
            "passed": other_pass,
        },
        "four_kilobyte_identifier": {
            "rows": identifier_rows,
            "checks": identifier_checks,
            "passed": identifier_pass,
            "any_timeout_observed": identifier_any_timeout,
            "scope_statement": (
                "G1 did not solve the 4KB identifier; it still requires a separate G4 lexer/state-machine project."
                if identifier_any_timeout
                else "Identifier trials completed, but this G1 audit does not claim an identifier optimization."
            ),
        },
        "coverage_checks": coverage_checks,
        "all_threshold_checks": all_checks,
        "gate_failure_ids": failed_ids,
        "overall_pass": overall_pass,
        "gate": "SCALE_GATE_PASS" if overall_pass else "SCALE_GATE_FAIL",
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# Independent G1 scale raw recomputation",
        "",
        f"**Scale gate: {result['gate']}**",
        "",
        "This covers only the scale gate; it is not the final competition verdict. Harness summaries were ignored, and no raw trial or anomaly was deleted.",
        "",
        "## Inputs and coverage",
        "",
        "| JSON | SHA-256 | Runs | Status | Issues |",
        "|---|---|---:|---|---|",
    ]
    for item in result["inputs"]:
        issue_text = "; ".join(item["issues"]) or "none"
        lines.append(
            f"| `{item['path']}` | `{item['sha256']}` | {item['run_count']} | {item['status']} | {issue_text} |"
        )
    lines.extend(
        [
            "",
            "## Locals 0–500",
            "",
            "| Locals | Protocol | Control median ms | Candidate median ms | Candidate/control | Control deadline answers | Candidate deadline answers | Control VmHWM KiB | Candidate VmHWM KiB | RSS ratio | RSS ref | Status |",
            "|---:|---|---:|---:|---:|---|---|---:|---:|---:|---|---|",
        ]
    )
    for row in result["locals"]["rows"]:
        status = "PASS" if row["rss_passed"] and row["transcript_passed"] and row["candidate_group_passed"] else "FAIL"
        lines.append(
            f"| {row['locals']} | {row['protocol']} | {_fmt(row['control_completed_median_ms'])} | "
            f"{_fmt(row['candidate_completed_median_ms'])} | {_fmt(row['candidate_control_time_ratio'])} | "
            f"{row['control_deadline_answer_counts']} | {row['candidate_deadline_answer_counts']} | "
            f"{_fmt(row['control_gate_vmhwm_kib_median'])} | {_fmt(row['candidate_gate_vmhwm_kib_median'])} | "
            f"{_fmt(row['candidate_control_rss_ratio'])} | {row['rss_reference_case']} | {status} |"
        )
    lines.extend(["", "Complexity diagnostics:", ""])
    for item in result["locals"]["power_diagnostics"]:
        lines.append(
            f"- {item['protocol']}: t500/t50={_fmt(item['endpoint_50_to_500_time_ratio'])}, "
            f"endpoint p={_fmt(item['endpoint_50_to_500_log_log_exponent'])}, "
            f"OLS p={_fmt(item['overall_ols_log_log_exponent'])} — "
            f"{'PASS' if item['passed'] else 'FAIL'}; {item['interpretation']}."
        )

    lines.extend(
        [
            "",
            "## Other seven scale cases",
            "",
            "| Case | Protocol | Control ms | Candidate ms | Ratio | Delta ms | Control VmHWM | Candidate VmHWM | RSS ratio | Transcript | Status |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in result["other_seven_scale_cases"]["rows"]:
        lines.append(
            f"| `{row['case_name']}` | {row['protocol']} | {_fmt(row['control_process_total_median_ms'])} | "
            f"{_fmt(row['candidate_process_total_median_ms'])} | {_fmt(row['candidate_control_time_ratio'])} | "
            f"{_fmt(row['absolute_time_delta_ms'])} | {_fmt(row['control_gate_vmhwm_kib_median'])} | "
            f"{_fmt(row['candidate_gate_vmhwm_kib_median'])} | {_fmt(row['candidate_control_rss_ratio'])} | "
            f"{'exact' if row['transcript_exact'] else 'DIFF'} | {'PASS' if row['passed'] else 'FAIL'} |"
        )

    lines.extend(
        [
            "",
            "## 4KB identifier non-regression",
            "",
            "| Protocol | Deadline answers C/Cand | Allowed shortfall | Common correct prefix | Prefix-time ratio | VmHWM ratio | No new error | Status |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in result["four_kilobyte_identifier"]["rows"]:
        medians = row["deadline_answer_count_medians"]
        lines.append(
            f"| {row['protocol']} | {_fmt(medians['control'])}/{_fmt(medians['candidate'])} | "
            f"{_fmt(row['allowed_candidate_shortfall'])} | {row['selected_common_correct_prefix_count']} | "
            f"{_fmt(row['candidate_control_prefix_time_ratio'])} | {_fmt(row['candidate_control_rss_ratio'])} | "
            f"{'yes' if row['no_new_error_output_exception_or_premature_exit'] else 'NO'} | "
            f"{'PASS' if row['passed'] else 'FAIL'} |"
        )
    lines.extend(["", result["four_kilobyte_identifier"]["scope_statement"], ""])

    failed = result["gate_failure_ids"]
    if failed:
        lines.extend(["## Failed checks", ""])
        lines.extend(f"- `{item}`" for item in failed)
        lines.append("")
    anomalies = result["anomalous_or_failed_trials"]
    if anomalies:
        lines.extend(["## Failed/anomalous raw trials (none removed)", ""])
        for item in anomalies:
            details = "; ".join(item["issues"]) or "required trial did not reach an acceptable state"
            lines.append(
                f"- `{item['trial_key']}` {item['case_name']}/{item['protocol']}/{item['role']} "
                f"rep={item['role_repetition']}: {details}"
            )
        lines.append("")
    return "\n".join(lines)


def _raw_payload(bits: Sequence[str]) -> bytes:
    return "".join(f"{bit}\n" for bit in bits).encode("ascii")


def _synthetic_run(
    *,
    run_id: int,
    case_name: str,
    protocol: str,
    role: str,
    repetition: int,
    process_ns: int,
    rss_kib: int,
    token_count: int,
    answer_count: int | None = None,
    timed_out: bool = False,
) -> dict[str, Any]:
    expected = _case_expected(case_name)
    continue_bit = _continue_bit(protocol)
    reject_bit = _reject_bit(protocol)
    if answer_count is None:
        answer_count = token_count if expected == "accept" else min(4, token_count)
    if expected == "reject" and not timed_out:
        bits = [continue_bit] * (answer_count - 1) + [reject_bit]
    else:
        bits = [continue_bit] * answer_count
    stdout = _raw_payload(bits)
    empty = b""
    events = [
        {
            "token_index": index,
            "raw_b64": base64.b64encode(f"{bit}\n".encode("ascii")).decode("ascii"),
            "strict_bit": bit,
            "response_elapsed_ns": int((index + 1) * process_ns / max(answer_count, 1) * 0.90),
        }
        for index, bit in enumerate(bits)
    ]
    return {
        "run_id": run_id,
        "case_name": case_name,
        "case_expected": expected,
        "protocol": protocol,
        "role": role,
        "role_repetition": repetition,
        "schedule_key": f"synthetic:{case_name}:{protocol}",
        "timed_out": timed_out,
        "timeout_phase": "waiting_for_response" if timed_out else None,
        "termination": "sigterm-after-timeout" if timed_out else "natural",
        "returncode": -15 if timed_out else 0,
        "spawn_exception": None,
        "protocol_error": None,
        "timeout_seconds": 35.0 if case_name == "locals-300" else 30.0,
        "configured_timeout_lower_bound_ns": (
            35_000_000_000 if case_name == "locals-300" else 30_000_000_000
        ),
        "deadline_elapsed_ns": process_ns if not timed_out else (
            35_000_000_000 if case_name == "locals-300" else 30_000_000_000
        ),
        "interaction_elapsed_ns": process_ns if not timed_out else (
            35_000_000_000 if case_name == "locals-300" else 30_000_000_000
        ),
        "cleanup_elapsed_ns": 0 if not timed_out else 50_000_000,
        "process_total_ns": process_ns,
        "token_count_available": token_count,
        "tokens_sent": answer_count if timed_out else token_count,
        "answer_count": answer_count,
        "deadline_answer_count": answer_count,
        "deadline_stdout_byte_count": len(stdout),
        "response_bits": bits,
        "response_events": events,
        "stdout_raw_b64": base64.b64encode(stdout).decode("ascii"),
        "stdout_sha256": _sha256(stdout),
        "stderr_raw_b64": base64.b64encode(empty).decode("ascii"),
        "stderr_sha256": _sha256(empty),
        "trailing_stdout_raw_b64": base64.b64encode(empty).decode("ascii"),
        "trailing_stdout_sha256": _sha256(empty),
        "cleanup_stdout_raw_b64": base64.b64encode(empty).decode("ascii"),
        "cleanup_stdout_sha256": _sha256(empty),
        "profile_stderr": {
            "parse_errors": [],
            "stderr_without_profile_raw_b64": base64.b64encode(empty).decode("ascii"),
            "stderr_without_profile_sha256": _sha256(empty),
        },
        "rss": {
            "gate_peak_vmhwm_kib": rss_kib,
            "deadline_snapshot_vmhwm_kib": rss_kib,
            "peak_vmhwm_kib": rss_kib,
        },
        "case_ok": False if timed_out else True,
    }


def _synthetic_document() -> dict[str, Any]:
    cases = []
    for name in _all_expected_cases():
        cases.append(
            {
                "name": name,
                "expected": _case_expected(name),
                "token_count": 200 if name == IDENTIFIER_CASE else 6,
                "source_sha256": _sha256(name.encode("utf-8")),
            }
        )
    runs: list[dict[str, Any]] = []
    run_id = 0
    for count in LOCAL_COUNTS:
        name = _local_name(count)
        for protocol in PROTOCOLS:
            control_300_timeout = count == 300
            role_counts = {"candidate": 3, "control": 0 if count == 500 else (1 if count == 300 else 3)}
            for role in ROLES:
                for repetition in range(1, role_counts[role] + 1):
                    timed_out = role == "control" and control_300_timeout
                    candidate_ns = int((80.0 + count) * 1e6 + repetition * 100_000)
                    process_ns = (
                        35_050_000_000
                        if timed_out
                        else int(candidate_ns * (1.08 if role == "control" else 1.0))
                    )
                    runs.append(
                        _synthetic_run(
                            run_id=run_id,
                            case_name=name,
                            protocol=protocol,
                            role=role,
                            repetition=repetition,
                            process_ns=process_ns,
                            rss_kib=160_000 + count * 10 + (0 if role == "control" else -5_000),
                            token_count=6,
                            answer_count=4 if timed_out else None,
                            timed_out=timed_out,
                        )
                    )
                    run_id += 1
    for name in OTHER_SCALE_CASES:
        for protocol in PROTOCOLS:
            for role in ROLES:
                for repetition in range(1, REPETITIONS + 1):
                    base_ns = 100_000_000 + OTHER_SCALE_CASES.index(name) * 10_000_000
                    process_ns = int(base_ns * (1.05 if role == "candidate" else 1.0)) + repetition * 100_000
                    runs.append(
                        _synthetic_run(
                            run_id=run_id,
                            case_name=name,
                            protocol=protocol,
                            role=role,
                            repetition=repetition,
                            process_ns=process_ns,
                            rss_kib=180_000 if role == "control" else 190_000,
                            token_count=6,
                        )
                    )
                    run_id += 1
    for protocol in PROTOCOLS:
        for role in ROLES:
            for repetition in range(1, REPETITIONS + 1):
                answer_count = 100 if role == "control" else 99
                process_ns = 30_050_000_000
                run = _synthetic_run(
                    run_id=run_id,
                    case_name=IDENTIFIER_CASE,
                    protocol=protocol,
                    role=role,
                    repetition=repetition,
                    process_ns=process_ns,
                    rss_kib=200_000 if role == "control" else 210_000,
                    token_count=200,
                    answer_count=answer_count,
                    timed_out=True,
                )
                # Candidate reaches the common prefix 5% later, within the 10% guard.
                factor = 1.05 if role == "candidate" else 1.0
                for event in run["response_events"]:
                    event["response_elapsed_ns"] = int(event["response_elapsed_ns"] * factor)
                runs.append(run)
                run_id += 1
    return {
        "schema": "g1-independent-audit-raw-v1",
        "kind": "scale",
        "status": "complete",
        "locked_values": {
            "control_sha": CONTROL_SHA,
            "candidate_sha": CANDIDATE_SHA,
            "official_sha": OFFICIAL_SHA,
            "official_registry_sha256": OFFICIAL_REGISTRY_SHA256,
        },
        "environment": {"strict_linux_aarch64": True},
        "arguments": {"protocol": "both", "section": "all"},
        "artifacts": {
            "repositories": {
                "control": {"head": CONTROL_SHA},
                "candidate": {"head": CANDIDATE_SHA},
                "official": {"head": OFFICIAL_SHA},
            },
            "solutions": {
                "control": {"sha256": "synthetic-control"},
                "candidate": {"sha256": "synthetic-candidate"},
            },
        },
        "official_registry": {"sha256": OFFICIAL_REGISTRY_SHA256},
        "cases": cases,
        "runs": runs,
        "trial_exceptions": [],
        "summaries": {"deliberately_bogus": True},
    }


def self_test() -> None:
    import copy

    root = _synthetic_document()
    document = {
        "index": 0,
        "path": "synthetic.json",
        "sha256": "synthetic",
        "root": root,
    }
    passing = analyze([document])
    if passing["gate"] != "SCALE_GATE_PASS":
        raise AssertionError(f"passing synthetic matrix failed: {passing['gate_failure_ids']}")
    if not all(item["passed"] for item in passing["locals"]["power_diagnostics"]):
        raise AssertionError("linear/subquadratic synthetic locals failed complexity gate")
    if passing["four_kilobyte_identifier"]["rows"][0]["selected_common_correct_prefix_count"] != 99:
        raise AssertionError("identifier common deadline prefix was not independently recomputed")
    json.dumps(passing, allow_nan=False)

    locals_root = copy.deepcopy(root)
    locals_names = {_local_name(count) for count in LOCAL_COUNTS}
    locals_root["arguments"]["section"] = "locals"
    locals_root["cases"] = [case for case in locals_root["cases"] if case["name"] in locals_names]
    locals_root["runs"] = [run for run in locals_root["runs"] if run["case_name"] in locals_names]
    other_root = copy.deepcopy(root)
    other_root["arguments"]["section"] = "other"
    other_root["cases"] = [case for case in other_root["cases"] if case["name"] in ALL_NONLOCAL_CASES]
    other_root["runs"] = [run for run in other_root["runs"] if run["case_name"] in ALL_NONLOCAL_CASES]
    split = analyze(
        [
            {**document, "index": 0, "path": "locals.synthetic.json", "root": locals_root},
            {**document, "index": 1, "path": "other.synthetic.json", "root": other_root},
        ]
    )
    if split["gate"] != "SCALE_GATE_PASS":
        raise AssertionError(f"locals+other two-document merge failed: {split['gate_failure_ids']}")

    failed_rss_root = copy.deepcopy(root)
    victim = next(
        run
        for run in failed_rss_root["runs"]
        if run["case_name"] == "eight-kilobyte-string"
        and run["protocol"] == "default"
        and run["role"] == "candidate"
    )
    victim["rss"] = {"gate_peak_vmhwm_kib": None, "peak_vmhwm_kib": None}
    failed_rss = analyze([{**document, "root": failed_rss_root}])
    if failed_rss["overall_pass"]:
        raise AssertionError("missing required VmHWM did not fail")

    failed_trial_root = copy.deepcopy(root)
    victim = next(
        run
        for run in failed_trial_root["runs"]
        if run["case_name"] == "eighty-top-level-functions"
        and run["protocol"] == "competition"
        and run["role"] == "candidate"
        and run["role_repetition"] == 2
    )
    victim["stderr_raw_b64"] = base64.b64encode(b"synthetic error\n").decode("ascii")
    victim["stderr_sha256"] = _sha256(b"synthetic error\n")
    victim["profile_stderr"]["stderr_without_profile_raw_b64"] = victim["stderr_raw_b64"]
    victim["profile_stderr"]["stderr_without_profile_sha256"] = victim["stderr_sha256"]
    failed_trial = analyze([{**document, "root": failed_trial_root}])
    if failed_trial["overall_pass"] or not failed_trial["anomalous_or_failed_trials"]:
        raise AssertionError("failed required trial was deleted or did not fail the gate")

    failed_identifier_root = copy.deepcopy(root)
    for run in failed_identifier_root["runs"]:
        if run["case_name"] == IDENTIFIER_CASE and run["role"] == "candidate":
            keep = 90
            bits = run["response_bits"][:keep]
            stdout = _raw_payload(bits)
            run["response_bits"] = bits
            run["response_events"] = run["response_events"][:keep]
            run["answer_count"] = keep
            run["deadline_answer_count"] = keep
            run["deadline_stdout_byte_count"] = len(stdout)
            run["stdout_raw_b64"] = base64.b64encode(stdout).decode("ascii")
            run["stdout_sha256"] = _sha256(stdout)
    failed_identifier = analyze([{**document, "root": failed_identifier_root}])
    if failed_identifier["four_kilobyte_identifier"]["passed"]:
        raise AssertionError("identifier answer-count shortfall did not fail")

    # Old-schema compatibility: explicit deadline/RSS gate fields may be absent;
    # paired answer_count/events and peak_vmhwm_kib remain conservative fallbacks.
    fallback_root = copy.deepcopy(root)
    for run in fallback_root["runs"]:
        run.pop("deadline_answer_count", None)
        run.pop("deadline_stdout_byte_count", None)
        run["rss"].pop("gate_peak_vmhwm_kib", None)
        run["rss"].pop("deadline_snapshot_vmhwm_kib", None)
    fallback = analyze([{**document, "root": fallback_root}])
    if fallback["gate"] != "SCALE_GATE_PASS":
        raise AssertionError(f"old-field fallback compatibility failed: {fallback['gate_failure_ids']}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute the G1 scale thresholds strictly from audit_harness raw runs."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="one full scale JSON, or non-overlapping staged locals/other raw JSON files",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic in-memory tests only; never launches a benchmark",
    )
    args = parser.parse_args(argv)
    if not args.self_test and not args.inputs:
        parser.error("at least one raw scale JSON is required")
    if len({str(path.resolve()) for path in args.inputs}) != len(args.inputs):
        parser.error("the same input path was supplied more than once")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        print(
            "SELF-TEST PASS: complete matrix, raw medians, censored 35s lower bound, "
            "VmHWM missing-data failure, complexity, transcript, and identifier gates"
        )
        return 0
    try:
        documents = [load_document(path, index) for index, path in enumerate(args.inputs)]
        result = analyze(documents)
    except InputError as error:
        print(f"INPUT ERROR: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(render_markdown(result), end="")
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
