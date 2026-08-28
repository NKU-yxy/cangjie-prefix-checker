#!/usr/bin/env python3
"""Independent raw-data harness for the locked G1 correctness/scale audit.

This file intentionally lives outside both audited repositories.  It never
builds or edits a checkout.  It drives already-built ``solution`` binaries one
token at a time, retains exact subprocess transcripts, and checkpoints raw
JSON after every trial.  It is only a raw collector for official-50 and scale;
it does not replace the independent logs for the remaining gates and does not
issue the competition verdict.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import statistics
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


CONTROL_SHA = "68d780d54c25883b4e05c3f3562b315750b38af0"
CANDIDATE_SHA = "499c9c787fdbd8140307c5b5f472e9aee0c9342c"
OFFICIAL_SHA = "88336c400e7a4a671424e3e6c46c0866c8c0af93"
OFFICIAL_REGISTRY_SHA256 = (
    "2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2"
)
OFFICIAL_CASE_COUNT = 50
SCALE_FAMILY_COUNT = 9
LOCAL_COUNTS = (0, 1, 2, 10, 25, 50, 100, 150, 200, 250, 300, 500)
SCALE_REPETITIONS = 3
CONTROL_300_TIMEOUT_SECONDS = 35.0
IDENTIFIER_TIMEOUT_SECONDS = 30.0
IDENTIFIER_MIN_COMMON_PREFIX = 80
LOCAL_MANIFEST_NAME = "three-hundred-local-declarations"
IDENTIFIER_MANIFEST_NAME = "four-kilobyte-identifier"
PHASE_PROFILE_MARKER = b"CANGJIE_PHASE_PROFILE "
COUNTER_PROFILE_MARKER = b"CANGJIE_PROFILE "


class HarnessError(RuntimeError):
    """An audit precondition or harness invariant failed."""


@dataclass(frozen=True)
class InputCase:
    name: str
    family: str
    expected: str
    source: str
    source_path: str
    source_sha256: str
    origin: str
    manifest_item: dict[str, Any] | None = None
    official_first_error_token_index: int | None = None


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _lossy(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")


def _is_beneath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _resolve_beneath(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise HarnessError(f"{label} must be relative: {relative!r}")
    resolved = (root / candidate).resolve()
    if not _is_beneath(resolved, root):
        raise HarnessError(f"{label} escapes root {root}: {relative!r}")
    return resolved


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise HarnessError(
            f"git -C {root} {' '.join(args)} failed ({proc.returncode}): "
            f"{_lossy(proc.stderr).strip()}"
        )
    return proc.stdout if binary else proc.stdout.decode("utf-8", errors="strict").strip()


def _git_path(root: Path, expression: str) -> Path:
    raw = Path(str(_git(root, "rev-parse", expression)))
    return (raw if raw.is_absolute() else root / raw).resolve()


def _status_entries(root: Path) -> list[dict[str, Any]]:
    raw = bytes(
        _git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            binary=True,
        )
    )
    parts = raw.split(b"\0")
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise HarnessError(f"cannot parse git porcelain record: {record!r}")
        status = record[:2].decode("ascii", errors="replace")
        path = record[3:].decode("utf-8", errors="replace")
        original_path = None
        if "R" in status or "C" in status:
            if index >= len(parts) or not parts[index]:
                raise HarnessError(f"missing source path for git status {status} {path!r}")
            original_path = parts[index].decode("utf-8", errors="replace")
            index += 1
        entries.append(
            {
                "status": status,
                "path": path,
                "original_path": original_path,
                "staged": status[0] not in {" ", "?", "!"},
                "worktree": status[1] not in {" ", "?", "!"},
                "untracked": status == "??",
            }
        )
    return entries


def _is_allowed_build_artifact(path: str) -> bool:
    return path in {"solution", "solution_profile"} or path.startswith("generated/")


def _verify_locked_repo(
    root: Path,
    expected_sha: str,
    label: str,
    *,
    allow_build_artifacts: bool = False,
    require_no_alternates: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise HarnessError(f"{label} root does not exist: {root}")
    head = str(_git(root, "rev-parse", "HEAD"))
    if head != expected_sha:
        raise HarnessError(f"{label} HEAD is {head}, expected locked {expected_sha}")
    status_entries = _status_entries(root)
    for entry in status_entries:
        entry["allowed_build_artifact"] = bool(
            allow_build_artifacts
            and _is_allowed_build_artifact(entry["path"])
            and entry["original_path"] is None
        )
    forbidden = [
        entry for entry in status_entries if not entry["allowed_build_artifact"]
    ]
    if forbidden:
        raise HarnessError(
            f"{label} has staged/worktree/untracked changes outside the explicit "
            f"solution, solution_profile, and generated/ build artifacts: {forbidden}"
        )
    git_dir = _git_path(root, "--absolute-git-dir")
    common_dir = _git_path(root, "--git-common-dir")
    objects_dir = (common_dir / "objects").resolve()
    if not objects_dir.is_dir():
        raise HarnessError(f"{label} git objects directory is missing: {objects_dir}")
    alternates = objects_dir / "info" / "alternates"
    if require_no_alternates and alternates.exists():
        raise HarnessError(
            f"{label} clone has {alternates}; independent clone --no-local evidence requires it absent"
        )
    objects_stat = objects_dir.stat()
    return {
        "root": str(root),
        "root_realpath": str(root.resolve()),
        "head": head,
        "status_porcelain_entries": status_entries,
        "status_entry_count": len(status_entries),
        "allowed_build_artifacts_only": not forbidden,
        "git_dir_realpath": str(git_dir),
        "git_common_dir_realpath": str(common_dir),
        "objects_dir_realpath": str(objects_dir),
        "objects_dir_device": objects_stat.st_dev,
        "objects_dir_inode": objects_stat.st_ino,
        "alternates_path": str(alternates),
        "alternates_exists": alternates.exists(),
        "no_local_clone_evidence": (
            "objects directory is clone-local and objects/info/alternates is absent; "
            "this is necessary evidence but cannot reconstruct the historical clone command"
        ),
    }


def _verify_solution(
    path: Path,
    root: Path,
    label: str,
    *,
    allow_profile_override: bool,
) -> dict[str, Any]:
    path = path.resolve()
    root = root.resolve()
    default = (root / "solution").resolve()
    within_root = _is_beneath(path, root)
    if not allow_profile_override and path != default:
        raise HarnessError(
            f"{label} production solution must be exactly {default}; profile solution "
            "overrides require the explicit scale-only profile override switch"
        )
    if not within_root and not allow_profile_override:
        raise HarnessError(f"{label} solution escapes corresponding root {root}: {path}")
    if not path.is_file():
        raise HarnessError(f"{label} solution is not a regular file: {path}")
    if not os.access(path, os.X_OK):
        raise HarnessError(f"{label} solution is not executable: {path}")
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "cwd": str(root),
        "within_corresponding_root": within_root,
        "is_default_root_solution": path == default,
        "profile_override_allowed": allow_profile_override,
    }


def _read_text_exact(path: Path, label: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise HarnessError(f"cannot read UTF-8 {label} {path}: {error}") from error
    return raw, text


def _read_proc_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _environment_metadata(allow_non_aarch64: bool) -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    strict_ok = system == "Linux" and machine.lower() in {"aarch64", "arm64"}
    if not strict_ok and not allow_non_aarch64:
        raise HarnessError(
            f"locked audit requires Linux AArch64, observed {system} {machine}; "
            "--allow-non-aarch64 is diagnostic-only and is recorded as nonstandard"
        )
    return {
        "system": system,
        "platform": platform.platform(),
        "machine": machine,
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cpuinfo": _read_proc_text(Path("/proc/cpuinfo")),
        "meminfo": _read_proc_text(Path("/proc/meminfo")),
        "strict_linux_aarch64": strict_ok,
        "allow_non_aarch64_override": allow_non_aarch64,
    }


def _validate_output_path(output: Path, protected_roots: Sequence[Path]) -> Path:
    output = output.resolve()
    for root in protected_roots:
        if _is_beneath(output, root):
            raise HarnessError(f"raw JSON output must be outside audited root {root}: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _atomic_write_json(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _protocol_names(selection: str) -> tuple[str, ...]:
    if selection == "both":
        return ("default", "competition")
    return (selection,)


def _continue_bit(protocol: str) -> str:
    return "1" if protocol == "competition" else "0"


def _reject_bit(protocol: str) -> str:
    return "0" if protocol == "competition" else "1"


def _solution_command(solution: Path, protocol: str) -> list[str]:
    command = [str(solution.resolve())]
    if protocol == "competition":
        command.append("--competition-output")
    return command


def _load_encoding(official_root: Path) -> Any:
    cache = (official_root / "tiktoken_cache").resolve()
    if not cache.is_dir():
        raise HarnessError(f"locked tiktoken cache directory is missing: {cache}")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
    try:
        import tiktoken  # pylint: disable=import-outside-toplevel
    except Exception as error:  # pragma: no cover - environment dependent
        raise HarnessError(f"cannot import tiktoken: {type(error).__name__}: {error}") from error
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception as error:  # pragma: no cover - environment dependent
        raise HarnessError(
            f"cannot load cl100k_base from locked cache: {type(error).__name__}: {error}"
        ) from error


def _tokenize(encoding: Any, source: str) -> list[int]:
    token_ids = list(encoding.encode(source))
    if any(not isinstance(token_id, int) for token_id in token_ids):
        raise HarnessError("tokenizer returned a non-integer token ID")
    return token_ids


def _token_chunks(encoding: Any, token_ids: Sequence[int], source: str) -> list[bytes]:
    try:
        chunks = [encoding.decode_single_token_bytes(token_id) for token_id in token_ids]
    except Exception as error:
        raise HarnessError(
            f"cannot decode cl100k token bytes: {type(error).__name__}: {error}"
        ) from error
    source_bytes = source.encode("utf-8")
    if b"".join(chunks) != source_bytes:
        raise HarnessError(
            "cl100k token byte chunks do not reconstruct the exact UTF-8 source bytes"
        )
    return chunks


def _byte_end_offsets(chunks: Sequence[bytes]) -> list[int]:
    offsets: list[int] = []
    total = 0
    for chunk in chunks:
        total += len(chunk)
        offsets.append(total)
    return offsets


class _RssSampler:
    """Point-sample /proc/PID/status without instrumenting the child."""

    def __init__(self, pid: int, started_ns: int, interval_ms: float | None):
        self.pid = pid
        self.started_ns = started_ns
        self.interval_s = None if interval_ms is None else interval_ms / 1000.0
        self.samples: list[dict[str, Any]] = []
        self.attempt_count = 0
        self.read_errors = 0
        self.missing_vmrss_count = 0
        self.missing_vmhwm_count = 0
        self.peak_vmrss_kib: int | None = None
        self.peak_vmhwm_kib: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stopped = False

    @staticmethod
    def _status_values(pid: int) -> tuple[int | None, int | None]:
        vmrss = None
        vmhwm = None
        with Path(f"/proc/{pid}/status").open("r", encoding="ascii", errors="replace") as stream:
            for line in stream:
                if line.startswith("VmRSS:"):
                    vmrss = int(line.split()[1])
                elif line.startswith("VmHWM:"):
                    vmhwm = int(line.split()[1])
        return vmrss, vmhwm

    def _sample_once(self, reason: str) -> dict[str, Any] | None:
        if self.interval_s is None:
            return None
        with self._lock:
            self.attempt_count += 1
        error_text = None
        try:
            vmrss, vmhwm = self._status_values(self.pid)
        except (OSError, ValueError, IndexError) as error:
            vmrss = None
            vmhwm = None
            error_text = f"{type(error).__name__}: {error}"
        elapsed_ns = time.perf_counter_ns() - self.started_ns
        sample = {
            "elapsed_ns": elapsed_ns,
            "reason": reason,
            "vmrss_kib": vmrss,
            "vmhwm_kib": vmhwm,
            "read_error": error_text,
        }
        with self._lock:
            if error_text is not None:
                self.read_errors += 1
            if vmrss is None:
                self.missing_vmrss_count += 1
            else:
                self.peak_vmrss_kib = max(self.peak_vmrss_kib or vmrss, vmrss)
            if vmhwm is None:
                self.missing_vmhwm_count += 1
            else:
                self.peak_vmhwm_kib = max(self.peak_vmhwm_kib or vmhwm, vmhwm)
            self.samples.append(sample)
        return sample

    def _run(self) -> None:
        self._sample_once("sampler_start")
        assert self.interval_s is not None
        while not self._stop.wait(self.interval_s):
            self._sample_once("periodic")

    def start(self) -> None:
        if self.interval_s is None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"vmrss-sampler-{self.pid}",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self, reason: str) -> dict[str, Any] | None:
        return self._sample_once(reason)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=max(1.0, (self.interval_s or 0.0) * 4.0))

    def finish(self) -> dict[str, Any]:
        self.stop()
        with self._lock:
            samples = list(self.samples)
            deadline_samples = [
                sample
                for sample in samples
                if sample["reason"] in {
                    "deadline_before_signal",
                    "exit_deadline_before_signal",
                }
            ]
            deadline_vmhwm = (
                None if not deadline_samples else deadline_samples[-1]["vmhwm_kib"]
            )
        return {
            "source": f"/proc/{self.pid}/status",
            "interval_ms": None if self.interval_s is None else self.interval_s * 1000.0,
            "attempt_count": self.attempt_count,
            "sample_count": len(samples),
            "read_errors": self.read_errors,
            "missing_vmrss_count": self.missing_vmrss_count,
            "missing_vmhwm_count": self.missing_vmhwm_count,
            "peak_vmrss_kib": self.peak_vmrss_kib,
            "peak_vmhwm_kib": self.peak_vmhwm_kib,
            "deadline_snapshot_vmhwm_kib": deadline_vmhwm,
            "gate_peak_vmhwm_kib": self.peak_vmhwm_kib,
            "gate_rss_field": "gate_peak_vmhwm_kib",
            "samples": samples,
            "caveat": (
                "RSS gate analysis must use kernel VmHWM (gate_peak_vmhwm_kib), not "
                "point-sampled VmRSS; missing field/read counts are explicit"
            ),
        }


def _send_process_group_signal(proc: subprocess.Popen[bytes], signum: int) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signum)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            pass


def _nonblocking_deadline_drain(
    proc: subprocess.Popen[bytes],
    stdout_all: bytearray,
    stderr_all: bytearray,
    pending_stdout: bytearray,
) -> dict[str, Any]:
    """Drain only bytes already readable before timeout cleanup starts."""
    drained = {"stdout_bytes": 0, "stderr_bytes": 0, "errors": []}
    for label, stream, target in (
        ("stdout", proc.stdout, stdout_all),
        ("stderr", proc.stderr, stderr_all),
    ):
        if stream is None or stream.closed:
            continue
        descriptor = stream.fileno()
        try:
            was_blocking = os.get_blocking(descriptor)
            os.set_blocking(descriptor, False)
        except OSError as error:
            drained["errors"].append(
                f"{label} nonblocking setup: {type(error).__name__}: {error}"
            )
            continue
        try:
            while True:
                try:
                    chunk = os.read(descriptor, 65536)
                except BlockingIOError:
                    break
                except OSError as error:
                    drained["errors"].append(
                        f"{label} drain: {type(error).__name__}: {error}"
                    )
                    break
                if not chunk:
                    break
                target.extend(chunk)
                drained[f"{label}_bytes"] += len(chunk)
                if label == "stdout":
                    pending_stdout.extend(chunk)
        finally:
            try:
                os.set_blocking(descriptor, was_blocking)
            except OSError as error:
                drained["errors"].append(
                    f"{label} blocking restore: {type(error).__name__}: {error}"
                )
    return drained


def _strict_stdout_records(raw: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw.splitlines(keepends=True)):
        strict_bit = record[:1].decode("ascii") if record in {b"0\n", b"1\n"} else None
        records.append(
            {
                "index": index,
                "raw_b64": _b64(record),
                "text_utf8_lossy": _lossy(record),
                "strict_bit": strict_bit,
            }
        )
    return records


def _extract_profile_stderr(raw: bytes) -> dict[str, Any]:
    """Parse optional test-build profile records while preserving exact stderr."""
    retained: list[bytes] = []
    payloads: dict[str, list[bytes]] = {"phase": [], "counters": []}
    for record in raw.splitlines(keepends=True):
        if record.startswith(PHASE_PROFILE_MARKER):
            payloads["phase"].append(
                record[len(PHASE_PROFILE_MARKER) :].rstrip(b"\r\n")
            )
        elif record.startswith(COUNTER_PROFILE_MARKER):
            payloads["counters"].append(
                record[len(COUNTER_PROFILE_MARKER) :].rstrip(b"\r\n")
            )
        else:
            retained.append(record)

    parsed: dict[str, dict[str, int] | None] = {"phase": None, "counters": None}
    errors: list[str] = []
    for kind, candidates in payloads.items():
        if not candidates:
            continue
        if len(candidates) != 1:
            errors.append(
                f"expected at most one {kind} profile record, got {len(candidates)}"
            )
            continue
        try:
            value = json.loads(candidates[0].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            errors.append(
                f"invalid {kind} profile JSON: {type(error).__name__}: {error}"
            )
            continue
        if not isinstance(value, dict):
            errors.append(f"{kind} profile payload is not an object")
            continue
        invalid = [
            key
            for key, item in value.items()
            if not isinstance(key, str)
            or not isinstance(item, int)
            or isinstance(item, bool)
            or item < 0
        ]
        if invalid:
            errors.append(
                f"{kind} profile has invalid nonnegative integer fields: {invalid}"
            )
            continue
        parsed[kind] = value

    required_phase_fields = (
        "semantic_init_ns",
        "token_table_init_ns",
        "grammar_init_ns",
        "startup_wall_ns",
        "syntax_check_ns",
        "semantic_check_ns",
    )
    phase = parsed["phase"]
    if phase is not None:
        missing = [key for key in required_phase_fields if key not in phase]
        if missing:
            errors.append(f"phase profile is missing required fields: {missing}")
            parsed["phase"] = None

    non_profile = b"".join(retained)
    return {
        "phase": parsed["phase"],
        "counters": parsed["counters"],
        "phase_record_count": len(payloads["phase"]),
        "counter_record_count": len(payloads["counters"]),
        "parse_errors": errors,
        "stderr_without_profile_sha256": _sha256_bytes(non_profile),
        "stderr_without_profile_raw_b64": _b64(non_profile),
        "stderr_without_profile_utf8_lossy": _lossy(non_profile),
    }


def _run_interactive(
    *,
    role: str,
    solution: Path,
    cwd: Path,
    protocol: str,
    token_ids: Sequence[int],
    token_byte_lengths: Sequence[int],
    case_expected: str,
    timeout_seconds: float,
    exit_timeout_seconds: float,
    rss_sample_ms: float | None,
    request_phase_profile: bool,
    official_target: int | None = None,
) -> dict[str, Any]:
    """Run a fresh child and pair exactly one flushed response with each token."""
    command = _solution_command(solution, protocol)
    started_ns = time.perf_counter_ns()
    deadline_ns = started_ns + int(timeout_seconds * 1_000_000_000)
    response_events: list[dict[str, Any]] = []
    token_send_events: list[dict[str, int]] = []
    stdout_all = bytearray()
    stderr_all = bytearray()
    pending_stdout = bytearray()
    protocol_error: str | None = None
    timeout_phase: str | None = None
    timed_out = False
    termination = "not-started"
    stop_reason = "not-started"
    tokens_sent = 0
    rejection_token_index: int | None = None
    proc: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    sampler: _RssSampler | None = None
    spawn_exception: dict[str, str] | None = None
    deadline_elapsed_ns: int | None = None
    deadline_drain_completed_elapsed_ns: int | None = None
    deadline_answer_count: int | None = None
    deadline_stdout_byte_count: int | None = None
    deadline_drain: dict[str, Any] | None = None
    deadline_communicate_stdout_raw = b""
    cleanup_started_ns: int | None = None
    pre_cleanup_stdout_byte_count: int | None = None

    token_limit = len(token_ids) if official_target is None else official_target + 1
    if len(token_byte_lengths) != len(token_ids):
        raise HarnessError("token_byte_lengths and token_ids differ in length")
    token_byte_ends: list[int] = []
    token_bytes_consumed = 0
    for length in token_byte_lengths:
        token_bytes_consumed += length
        token_byte_ends.append(token_bytes_consumed)
    try:
        child_env = dict(os.environ)
        # Ambient profiling must not silently alter a production trial.
        child_env.pop("CANGJIE_PROFILE", None)
        if request_phase_profile:
            child_env["CANGJIE_PROFILE"] = "1"
        proc = subprocess.Popen(
            command,
            cwd=str(cwd.resolve()),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        termination = "running"
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        sampler = _RssSampler(proc.pid, started_ns, rss_sample_ms)
        sampler.start()
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        stdout_eof = False

        for token_index, token_id in enumerate(token_ids[:token_limit]):
            now_ns = time.perf_counter_ns()
            if now_ns >= deadline_ns:
                timed_out = True
                timeout_phase = "before_token_write"
                stop_reason = "timeout"
                break
            write_started_ns = now_ns
            try:
                proc.stdin.write(f"{token_id}\n".encode("ascii"))
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                protocol_error = f"stdin write failed at token {token_index}: {error}"
                stop_reason = "stdin_write_error"
                break
            tokens_sent += 1
            flushed_ns = time.perf_counter_ns()
            token_send_events.append(
                {
                    "token_index": token_index,
                    "token_id": token_id,
                    "write_started_elapsed_ns": write_started_ns - started_ns,
                    "flushed_elapsed_ns": flushed_ns - started_ns,
                }
            )

            while b"\n" not in pending_stdout:
                now_ns = time.perf_counter_ns()
                remaining_ns = deadline_ns - now_ns
                if remaining_ns <= 0:
                    timed_out = True
                    timeout_phase = "waiting_for_response"
                    stop_reason = "timeout"
                    break
                events = selector.select(min(remaining_ns / 1_000_000_000, 0.050))
                if not events:
                    if proc.poll() is not None:
                        protocol_error = (
                            f"process exited before response for token {token_index}"
                        )
                        stop_reason = "stdout_eof"
                        break
                    continue
                for key, _ in events:
                    try:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                    except OSError as error:
                        protocol_error = f"pipe read failed: {error}"
                        stop_reason = "pipe_read_error"
                        chunk = b""
                    if key.data == "stderr":
                        if chunk:
                            stderr_all.extend(chunk)
                        else:
                            try:
                                selector.unregister(key.fileobj)
                            except Exception:
                                pass
                    else:
                        if chunk:
                            stdout_all.extend(chunk)
                            pending_stdout.extend(chunk)
                        else:
                            stdout_eof = True
                            try:
                                selector.unregister(key.fileobj)
                            except Exception:
                                pass
                if protocol_error or timed_out:
                    break
                if stdout_eof and b"\n" not in pending_stdout:
                    protocol_error = f"stdout EOF before response for token {token_index}"
                    stop_reason = "stdout_eof"
                    break

            if protocol_error or timed_out:
                break
            if b"\n" not in pending_stdout:
                protocol_error = f"missing newline-terminated response for token {token_index}"
                stop_reason = "malformed_response"
                break

            line_end = pending_stdout.index(b"\n") + 1
            raw_line = bytes(pending_stdout[:line_end])
            del pending_stdout[:line_end]
            response_ns = time.perf_counter_ns()
            strict_bit = raw_line[:1].decode("ascii") if raw_line in {b"0\n", b"1\n"} else None
            if official_target is not None:
                expected_bit = (
                    _reject_bit(protocol)
                    if token_index == official_target
                    else _continue_bit(protocol)
                )
            else:
                expected_bit = (
                    _continue_bit(protocol) if case_expected == "accept" else None
                )
            response_events.append(
                {
                    "token_index": token_index,
                    "token_id": token_id,
                    "token_byte_start": (
                        0 if token_index == 0 else token_byte_ends[token_index - 1]
                    ),
                    "token_byte_end": token_byte_ends[token_index],
                    "write_started_elapsed_ns": write_started_ns - started_ns,
                    "flushed_elapsed_ns": flushed_ns - started_ns,
                    "response_elapsed_ns": response_ns - started_ns,
                    "response_source": "interactive_read",
                    "raw_b64": _b64(raw_line),
                    "text_utf8_lossy": _lossy(raw_line),
                    "strict_bit": strict_bit,
                    "expected_bit": expected_bit,
                    "matches_expected_bit": (
                        None if expected_bit is None else strict_bit == expected_bit
                    ),
                }
            )
            if pending_stdout:
                protocol_error = (
                    "checker emitted stdout before the next token was written; "
                    f"{len(pending_stdout)} over-read byte(s) retained in trailing stdout"
                )
                stop_reason = "unsolicited_stdout"
                break
            if strict_bit is None:
                protocol_error = f"response at token {token_index} is not exactly 0\\n or 1\\n"
                stop_reason = "malformed_response"
                break
            if strict_bit == _reject_bit(protocol):
                rejection_token_index = token_index
            if official_target is not None and strict_bit != expected_bit:
                protocol_error = (
                    f"official mismatch at token {token_index}: expected {expected_bit}, "
                    f"got {strict_bit}"
                )
                stop_reason = "official_first_error_mismatch"
                break
            if rejection_token_index == token_index:
                stop_reason = "reject_observed"
                break
        else:
            stop_reason = "input_exhausted"

        if timed_out:
            deadline_elapsed_ns = time.perf_counter_ns() - started_ns
            deadline_drain = _nonblocking_deadline_drain(
                proc, stdout_all, stderr_all, pending_stdout
            )
            # Count only newline-complete records that were already readable at
            # the deadline and that can be paired with an already-sent token.
            while b"\n" in pending_stdout and len(response_events) < tokens_sent:
                token_index = len(response_events)
                line_end = pending_stdout.index(b"\n") + 1
                raw_line = bytes(pending_stdout[:line_end])
                del pending_stdout[:line_end]
                strict_bit = (
                    raw_line[:1].decode("ascii")
                    if raw_line in {b"0\n", b"1\n"}
                    else None
                )
                if official_target is not None:
                    expected_bit = (
                        _reject_bit(protocol)
                        if token_index == official_target
                        else _continue_bit(protocol)
                    )
                else:
                    expected_bit = (
                        _continue_bit(protocol) if case_expected == "accept" else None
                    )
                send_event = token_send_events[token_index]
                response_events.append(
                    {
                        "token_index": token_index,
                        "token_id": token_ids[token_index],
                        "token_byte_start": (
                            0 if token_index == 0 else token_byte_ends[token_index - 1]
                        ),
                        "token_byte_end": token_byte_ends[token_index],
                        "write_started_elapsed_ns": send_event[
                            "write_started_elapsed_ns"
                        ],
                        "flushed_elapsed_ns": send_event["flushed_elapsed_ns"],
                        "response_elapsed_ns": deadline_elapsed_ns,
                        "response_source": "deadline_nonblocking_drain",
                        "raw_b64": _b64(raw_line),
                        "text_utf8_lossy": _lossy(raw_line),
                        "strict_bit": strict_bit,
                        "expected_bit": expected_bit,
                        "matches_expected_bit": (
                            None if expected_bit is None else strict_bit == expected_bit
                        ),
                    }
                )
                if strict_bit == _reject_bit(protocol):
                    rejection_token_index = token_index
                if strict_bit is None and protocol_error is None:
                    protocol_error = (
                        f"deadline-drained response at token {token_index} is not "
                        "exactly 0\\n or 1\\n"
                    )
                if (
                    official_target is not None
                    and strict_bit != expected_bit
                    and protocol_error is None
                ):
                    protocol_error = (
                        f"official mismatch at deadline-drained token {token_index}: "
                        f"expected {expected_bit}, got {strict_bit}"
                    )
            deadline_drain_completed_elapsed_ns = time.perf_counter_ns() - started_ns
            deadline_answer_count = len(response_events)
            deadline_stdout_byte_count = len(stdout_all)
            if sampler is not None:
                sampler.snapshot("deadline_before_signal")
                sampler.stop()
        elif sampler is not None:
            # Short-lived normal trials need a deliberate pre-close sample;
            # the periodic thread alone may not run before the child exits.
            sampler.snapshot("before_stdin_close")

        # Close stdin immediately after rejection, mismatch, full input, or
        # deadline snapshot.  Bytes read during cleanup remain raw evidence but
        # are never added to response_events/answer_count.
        cleanup_started_ns = time.perf_counter_ns()
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.stdin = None
        if not timed_out and sampler is not None:
            sampler.snapshot("before_exit_wait")
        pre_cleanup_stdout_byte_count = len(stdout_all)
        if selector is not None:
            selector.close()
            selector = None

        remaining_global_s = max(0.0, (deadline_ns - time.perf_counter_ns()) / 1e9)
        if timed_out:
            _send_process_group_signal(proc, signal.SIGTERM)
            termination = "sigterm-after-timeout"
            natural_wait_s = 1.0
        else:
            natural_wait_s = min(exit_timeout_seconds, remaining_global_s)

        try:
            tail_stdout, tail_stderr = proc.communicate(timeout=natural_wait_s)
            stdout_all.extend(tail_stdout)
            stderr_all.extend(tail_stderr)
            if termination == "running":
                termination = "natural"
        except subprocess.TimeoutExpired as error:
            if not timed_out:
                timed_out = True
                timeout_phase = "process_exit"
                stop_reason = "timeout"
                deadline_elapsed_ns = time.perf_counter_ns() - started_ns
                partial_stdout = error.output or b""
                if isinstance(partial_stdout, str):
                    partial_stdout = partial_stdout.encode("utf-8", errors="replace")
                deadline_communicate_stdout_raw = bytes(partial_stdout)
                deadline_answer_count = len(response_events)
                deadline_stdout_byte_count = (
                    len(stdout_all) + len(deadline_communicate_stdout_raw)
                )
                deadline_drain_completed_elapsed_ns = deadline_elapsed_ns
                deadline_drain = {
                    "stdout_bytes": len(deadline_communicate_stdout_raw),
                    "stderr_bytes": 0,
                    "errors": [],
                    "source": "subprocess.TimeoutExpired.output during exit wait",
                }
                if sampler is not None:
                    sampler.snapshot("exit_deadline_before_signal")
                    sampler.stop()
            _send_process_group_signal(proc, signal.SIGTERM)
            termination = "sigterm-after-exit-timeout"
            try:
                tail_stdout, tail_stderr = proc.communicate(timeout=1.0)
                stdout_all.extend(tail_stdout)
                stderr_all.extend(tail_stderr)
            except subprocess.TimeoutExpired:
                _send_process_group_signal(proc, signal.SIGKILL)
                termination = "sigkill"
                tail_stdout, tail_stderr = proc.communicate()
                stdout_all.extend(tail_stdout)
                stderr_all.extend(tail_stderr)
    except (OSError, ValueError) as error:
        spawn_exception = {"kind": type(error).__name__, "message": str(error)}
        protocol_error = f"subprocess setup failed: {type(error).__name__}: {error}"
        stop_reason = "spawn_error"
    finally:
        if selector is not None:
            selector.close()
        if proc is not None and proc.poll() is None:
            if cleanup_started_ns is None:
                cleanup_started_ns = time.perf_counter_ns()
            if pre_cleanup_stdout_byte_count is None:
                pre_cleanup_stdout_byte_count = len(stdout_all)
            if sampler is not None:
                sampler.snapshot("finalizer_before_signal")
                sampler.stop()
            _send_process_group_signal(proc, signal.SIGKILL)
            termination = "sigkill-finalizer"
            try:
                tail_stdout, tail_stderr = proc.communicate(timeout=1.0)
                stdout_all.extend(tail_stdout)
                stderr_all.extend(tail_stderr)
            except (subprocess.TimeoutExpired, OSError):
                pass
        rss = (
            sampler.finish()
            if sampler is not None
            else {
                "source": None,
                "interval_ms": rss_sample_ms,
                "attempt_count": 0,
                "sample_count": 0,
                "read_errors": 0,
                "missing_vmrss_count": 0,
                "missing_vmhwm_count": 0,
                "peak_vmrss_kib": None,
                "peak_vmhwm_kib": None,
                "deadline_snapshot_vmhwm_kib": None,
                "gate_peak_vmhwm_kib": None,
                "gate_rss_field": "gate_peak_vmhwm_kib",
                "samples": [],
                "caveat": "process did not start; no RSS samples",
            }
        )

    completed_ns = time.perf_counter_ns()
    raw_stdout = bytes(stdout_all)
    raw_stderr = bytes(stderr_all)
    cleanup_offset = (
        len(raw_stdout)
        if pre_cleanup_stdout_byte_count is None
        else min(pre_cleanup_stdout_byte_count, len(raw_stdout))
    )
    cleanup_stdout = raw_stdout[cleanup_offset:]
    profile_stderr = _extract_profile_stderr(raw_stderr)
    phase_profile = profile_stderr["phase"]
    paired_bytes = sum(len(base64.b64decode(event["raw_b64"])) for event in response_events)
    trailing_stdout = raw_stdout[paired_bytes:]
    stdout_records = _strict_stdout_records(raw_stdout)
    returncode = None if proc is None else proc.returncode
    response_bits = [event["strict_bit"] for event in response_events]
    continue_bit = _continue_bit(protocol)
    reject_bit = _reject_bit(protocol)
    expected_prefix_ok = all(
        bit == continue_bit
        for bit in response_bits[: (
            rejection_token_index if rejection_token_index is not None else len(response_bits)
        )]
    )
    if rejection_token_index is not None:
        expected_prefix_ok = expected_prefix_ok and response_bits[rejection_token_index] == reject_bit

    return {
        "role": role,
        "command": command,
        "cwd": str(cwd.resolve()),
        "pid": None if proc is None else proc.pid,
        "protocol": protocol,
        "protocol_bits": {"continue": continue_bit, "reject": reject_bit},
        "case_expected": case_expected,
        "phase_profile_requested": request_phase_profile,
        "official_target": official_target,
        "timeout_seconds": timeout_seconds,
        "configured_timeout_lower_bound_ns": int(timeout_seconds * 1_000_000_000),
        "exit_timeout_seconds": exit_timeout_seconds,
        "timed_out": timed_out,
        "timeout_phase": timeout_phase,
        "deadline_elapsed_ns": deadline_elapsed_ns,
        "deadline_drain_completed_elapsed_ns": deadline_drain_completed_elapsed_ns,
        "deadline_answer_count": deadline_answer_count,
        "deadline_stdout_byte_count": deadline_stdout_byte_count,
        "deadline_drain": deadline_drain,
        "deadline_communicate_stdout_raw_b64": _b64(
            deadline_communicate_stdout_raw
        ),
        "termination": termination,
        "stop_reason": stop_reason,
        "spawn_exception": spawn_exception,
        "protocol_error": protocol_error,
        "token_count_available": len(token_ids),
        "token_limit": token_limit,
        "tokens_sent": tokens_sent,
        "token_send_events": token_send_events,
        "answer_count": len(response_events),
        "answer_count_scope": (
            "newline-complete records paired with already-sent tokens before cleanup; "
            "cleanup stdout is excluded"
        ),
        "stdout_record_count": len(stdout_records),
        "rejection_token_index": rejection_token_index,
        "rejection_byte_end": (
            None
            if rejection_token_index is None
            else token_byte_ends[rejection_token_index]
        ),
        "response_bits": response_bits,
        "response_events": response_events,
        "first_response_elapsed_ns": (
            None if not response_events else response_events[0]["response_elapsed_ns"]
        ),
        "last_response_elapsed_ns": (
            None if not response_events else response_events[-1]["response_elapsed_ns"]
        ),
        "process_total_ns": completed_ns - started_ns,
        "interaction_elapsed_ns": (
            None
            if cleanup_started_ns is None
            else cleanup_started_ns - started_ns
        ),
        "cleanup_started_elapsed_ns": (
            None
            if cleanup_started_ns is None
            else cleanup_started_ns - started_ns
        ),
        "cleanup_elapsed_ns": (
            None
            if cleanup_started_ns is None
            else completed_ns - cleanup_started_ns
        ),
        "syntax_time_ns": (
            None if phase_profile is None else phase_profile["syntax_check_ns"]
        ),
        "semantic_time_ns": (
            None if phase_profile is None else phase_profile["semantic_check_ns"]
        ),
        "timing_breakdown_unavailable_reason": (
            None
            if phase_profile is not None
            else (
                "no valid CANGJIE_PHASE_PROFILE record; the default production binary "
                "does not contain phase instrumentation"
            )
        ),
        "profile_stderr": profile_stderr,
        "returncode": returncode,
        "stdout_sha256": _sha256_bytes(raw_stdout),
        "stdout_raw_b64": _b64(raw_stdout),
        "stdout_utf8_lossy": _lossy(raw_stdout),
        "stdout_records": stdout_records,
        "stdout_records_all_strict": all(
            record["strict_bit"] is not None for record in stdout_records
        ),
        "trailing_stdout_sha256": _sha256_bytes(trailing_stdout),
        "trailing_stdout_raw_b64": _b64(trailing_stdout),
        "trailing_stdout_utf8_lossy": _lossy(trailing_stdout),
        "cleanup_stdout_sha256": _sha256_bytes(cleanup_stdout),
        "cleanup_stdout_raw_b64": _b64(cleanup_stdout),
        "cleanup_stdout_utf8_lossy": _lossy(cleanup_stdout),
        "stderr_sha256": _sha256_bytes(raw_stderr),
        "stderr_raw_b64": _b64(raw_stderr),
        "stderr_utf8_lossy": _lossy(raw_stderr),
        "expected_prefix_ok": expected_prefix_ok,
        "rss": rss,
    }


def _official_run_ok(run: dict[str, Any], target: int, protocol: str) -> bool:
    expected = [
        _reject_bit(protocol) if index == target else _continue_bit(protocol)
        for index in range(target + 1)
    ]
    expected_stdout = "".join(f"{bit}\n" for bit in expected).encode("ascii")
    return all(
        (
            not run["timed_out"],
            run["spawn_exception"] is None,
            run["protocol_error"] is None,
            run["tokens_sent"] == target + 1,
            run["answer_count"] == target + 1,
            run["response_bits"] == expected,
            base64.b64decode(run["stdout_raw_b64"]) == expected_stdout,
            base64.b64decode(run["trailing_stdout_raw_b64"]) == b"",
            run["returncode"] == 0,
            base64.b64decode(run["stderr_raw_b64"]) == b"",
            run["rejection_token_index"] == target,
            run["termination"] == "natural",
        )
    )


def _scale_run_case_ok(run: dict[str, Any], expected: str) -> bool:
    stdout = base64.b64decode(run["stdout_raw_b64"])
    stderr = base64.b64decode(run["stderr_raw_b64"])
    stderr_without_profile = base64.b64decode(
        run["profile_stderr"]["stderr_without_profile_raw_b64"]
    )
    trailing = base64.b64decode(run["trailing_stdout_raw_b64"])
    base_clean = all(
        (
            not run["timed_out"],
            run["spawn_exception"] is None,
            run["protocol_error"] is None,
            run["stdout_records_all_strict"],
            trailing == b"",
            stderr_without_profile == b"",
            not run["profile_stderr"]["parse_errors"],
            run["phase_profile_requested"] or stderr == b"",
            run["returncode"] == 0,
            len(stdout) > 0,
        )
    )
    if expected == "accept":
        return base_clean and all(
            (
                run["tokens_sent"] == run["token_count_available"],
                run["answer_count"] == run["token_count_available"],
                run["rejection_token_index"] is None,
                all(bit == run["protocol_bits"]["continue"] for bit in run["response_bits"]),
            )
        )
    return base_clean and all(
        (
            run["rejection_token_index"] is not None,
            run["answer_count"] == run["rejection_token_index"] + 1,
            run["expected_prefix_ok"],
        )
    )


def _load_official_cases(official_root: Path) -> tuple[dict[str, Any], list[InputCase]]:
    registry_path = official_root / "wrong_error_positions.json"
    raw, text = _read_text_exact(registry_path, "official registry")
    digest = _sha256_bytes(raw)
    if digest != OFFICIAL_REGISTRY_SHA256:
        raise HarnessError(
            f"official registry sha256 is {digest}, expected {OFFICIAL_REGISTRY_SHA256}"
        )
    try:
        registry = json.loads(text)
    except json.JSONDecodeError as error:
        raise HarnessError(f"invalid official registry JSON: {error}") from error
    items = registry.get("wrong_examples") if isinstance(registry, dict) else None
    if not isinstance(items, list) or len(items) != OFFICIAL_CASE_COUNT:
        raise HarnessError(
            f"official registry must contain exactly {OFFICIAL_CASE_COUNT} wrong_examples"
        )
    cases: list[InputCase] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise HarnessError(f"official wrong_examples[{index}] is not an object")
        name = item.get("name")
        target = item.get("first_error_token_index")
        if not isinstance(name, str) or not name or name in seen:
            raise HarnessError(f"invalid/duplicate official case name at index {index}: {name!r}")
        if not isinstance(target, int) or isinstance(target, bool) or target < 0:
            raise HarnessError(f"official case {name} has invalid first_error_token_index")
        seen.add(name)
        source_path = official_root / "wrong" / f"{name}.cj"
        source_raw, source = _read_text_exact(source_path, f"official case {name}")
        cases.append(
            InputCase(
                name=name,
                family="official_wrong",
                expected="reject",
                source=source,
                source_path=str(source_path.resolve()),
                source_sha256=_sha256_bytes(source_raw),
                origin="locked_official_registry",
                official_first_error_token_index=target,
            )
        )
    return {
        "path": str(registry_path.resolve()),
        "sha256": digest,
        "wrong_examples": len(items),
    }, cases


def _locals_source(count: int) -> str:
    if count < 0:
        raise HarnessError(f"negative local count: {count}")
    if count == 0:
        return "main(): Unit {\n}\n"
    declarations = "\n".join(
        f" let value_{index}: Int64 = {index}" for index in range(count)
    )
    return f"main(): Unit {{\n{declarations}\n println(value_{count - 1})\n}}\n"


def _load_scale_cases(candidate_root: Path) -> tuple[dict[str, Any], list[InputCase], list[InputCase]]:
    manifest_path = candidate_root / "test_cases" / "comprehensive" / "manifest.json"
    raw, text = _read_text_exact(manifest_path, "candidate comprehensive manifest")
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as error:
        raise HarnessError(f"invalid candidate manifest JSON: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise HarnessError("candidate manifest must contain a cases array")
    scale_items = [
        item
        for item in manifest["cases"]
        if isinstance(item, dict) and item.get("family") == "scale_stress"
    ]
    if len(scale_items) != SCALE_FAMILY_COUNT:
        raise HarnessError(
            f"candidate manifest scale_stress count is {len(scale_items)}, expected {SCALE_FAMILY_COUNT}"
        )
    names = [item.get("name") for item in scale_items]
    if len(set(names)) != len(names):
        raise HarnessError("candidate manifest has duplicate scale case names")
    if names.count(LOCAL_MANIFEST_NAME) != 1 or names.count(IDENTIFIER_MANIFEST_NAME) != 1:
        raise HarnessError(
            "candidate manifest must contain exactly one canonical 300-locals and 4KiB identifier case"
        )

    manifest_root = manifest_path.parent
    loaded: list[InputCase] = []
    for item in scale_items:
        name = item.get("name")
        relative = item.get("file")
        expected = item.get("expected")
        declared_sha = item.get("source_sha256")
        if not isinstance(name, str) or not name:
            raise HarnessError("scale manifest item has an invalid name")
        if not isinstance(relative, str) or not relative.endswith(".cj"):
            raise HarnessError(f"scale case {name} has an invalid file path")
        if expected not in {"accept", "reject"}:
            raise HarnessError(f"scale case {name} has invalid expected={expected!r}")
        path = _resolve_beneath(manifest_root, relative, f"scale case {name} file")
        source_raw, source = _read_text_exact(path, f"scale case {name}")
        actual_sha = _sha256_bytes(source_raw)
        if declared_sha != actual_sha:
            raise HarnessError(
                f"scale case {name} source sha mismatch: manifest={declared_sha}, actual={actual_sha}"
            )
        if item.get("source_bytes") != len(source_raw):
            raise HarnessError(f"scale case {name} source_bytes mismatch")
        if item.get("expectation_tier") != "diagnostic_scale":
            raise HarnessError(f"scale case {name} is not tagged diagnostic_scale")
        loaded.append(
            InputCase(
                name=name,
                family="scale_stress",
                expected=expected,
                source=source,
                source_path=str(path),
                source_sha256=actual_sha,
                origin="candidate_locked_manifest",
                manifest_item=dict(item),
            )
        )

    canonical = next(case for case in loaded if case.name == LOCAL_MANIFEST_NAME)
    reconstructed = _locals_source(300)
    if reconstructed.encode("utf-8") != canonical.source.encode("utf-8"):
        raise HarnessError(
            "independent locals generator does not byte-match the locked canonical 300-locals source"
        )
    generated_locals = [
        InputCase(
            name=f"locals-{count}",
            family="generated_locals",
            expected="accept",
            source=_locals_source(count),
            source_path="<independent-generator>",
            source_sha256=_sha256_bytes(_locals_source(count).encode("utf-8")),
            origin=(
                "byte-identical-to-canonical-manifest-case"
                if count == 300
                else "independent-generator-validated-against-canonical-300-template"
            ),
        )
        for count in LOCAL_COUNTS
    ]
    other_scale = [case for case in loaded if case.name != LOCAL_MANIFEST_NAME]
    return {
        "path": str(manifest_path.resolve()),
        "sha256": _sha256_bytes(raw),
        "schema_version": manifest.get("schema_version"),
        "manifest_case_count": manifest.get("case_count"),
        "scale_case_count": len(scale_items),
        "canonical_locals_name": canonical.name,
        "canonical_locals_sha256": canonical.source_sha256,
        "generated_300_sha256": generated_locals[LOCAL_COUNTS.index(300)].source_sha256,
        "canonical_300_byte_match": True,
    }, generated_locals, other_scale


def _case_record(
    case: InputCase,
    token_ids: Sequence[int],
    token_chunks: Sequence[bytes],
    *,
    include_source: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": case.name,
        "family": case.family,
        "expected": case.expected,
        "origin": case.origin,
        "source_path": case.source_path,
        "source_sha256": case.source_sha256,
        "source_bytes": len(case.source.encode("utf-8")),
        "token_count": len(token_ids),
        "token_ids": list(token_ids),
        "token_chunks_raw_b64": [_b64(chunk) for chunk in token_chunks],
        "token_byte_lengths": [len(chunk) for chunk in token_chunks],
        "token_byte_end_offsets": _byte_end_offsets(token_chunks),
        "token_ids_sha256": _sha256_bytes(
            b"".join(int(token_id).to_bytes(4, "big", signed=False) for token_id in token_ids)
        ),
        "official_first_error_token_index": case.official_first_error_token_index,
        "manifest_item": case.manifest_item,
    }
    if include_source:
        result["source_utf8"] = case.source
        result["source_raw_b64"] = _b64(case.source.encode("utf-8"))
    return result


def _locked_artifacts(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Path]]:
    control_root = args.control_root.resolve()
    candidate_root = args.candidate_root.resolve()
    official_root = args.official_root.resolve()
    if control_root == candidate_root:
        raise HarnessError(
            f"control and candidate roots resolve to the same path: {control_root}"
        )
    profile_override = bool(getattr(args, "allow_external_profile_solutions", False))
    request_phase_profile = bool(getattr(args, "request_phase_profile", False))
    if profile_override and not request_phase_profile:
        raise HarnessError(
            "--allow-external-profile-solutions requires --request-phase-profile"
        )
    if profile_override and (
        args.control_solution is None or args.candidate_solution is None
    ):
        raise HarnessError(
            "external profile override requires explicit --control-solution and "
            "--candidate-solution paths"
        )
    control_solution = (
        args.control_solution.resolve()
        if args.control_solution is not None
        else (control_root / "solution").resolve()
    )
    candidate_solution = (
        args.candidate_solution.resolve()
        if args.candidate_solution is not None
        else (candidate_root / "solution").resolve()
    )
    repositories = {
        "control": _verify_locked_repo(
            control_root,
            CONTROL_SHA,
            "control",
            allow_build_artifacts=True,
            require_no_alternates=True,
        ),
        "candidate": _verify_locked_repo(
            candidate_root,
            CANDIDATE_SHA,
            "candidate",
            allow_build_artifacts=True,
            require_no_alternates=True,
        ),
        "official": _verify_locked_repo(
            official_root,
            OFFICIAL_SHA,
            "official",
            allow_build_artifacts=False,
            require_no_alternates=False,
        ),
    }
    control_objects = repositories["control"]["objects_dir_realpath"]
    candidate_objects = repositories["candidate"]["objects_dir_realpath"]
    control_identity = (
        repositories["control"]["objects_dir_device"],
        repositories["control"]["objects_dir_inode"],
    )
    candidate_identity = (
        repositories["candidate"]["objects_dir_device"],
        repositories["candidate"]["objects_dir_inode"],
    )
    if control_objects == candidate_objects or control_identity == candidate_identity:
        raise HarnessError(
            "control and candidate do not have distinct clone-local git object directories"
        )
    solutions = {
        "control": _verify_solution(
            control_solution,
            control_root,
            "control",
            allow_profile_override=profile_override,
        ),
        "candidate": _verify_solution(
            candidate_solution,
            candidate_root,
            "candidate",
            allow_profile_override=profile_override,
        ),
    }
    return {
        "repositories": repositories,
        "solutions": solutions,
        "clone_independence": {
            "control_candidate_root_realpaths_distinct": True,
            "control_candidate_objects_realpaths_distinct": True,
            "control_candidate_objects_identities_distinct": True,
            "control_alternates_absent": True,
            "candidate_alternates_absent": True,
            "historical_clone_command_provable": False,
            "evidence_scope": (
                "current filesystem identity and absence of Git alternates support, but do "
                "not by themselves prove, that clone --no-local was used"
            ),
        },
    }, {
        "control_root": control_root,
        "candidate_root": candidate_root,
        "official_root": official_root,
        "control_solution": control_solution,
        "candidate_solution": candidate_solution,
    }


def _new_report(kind: str, args: argparse.Namespace, artifacts: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "g1-independent-audit-raw-v1",
        "kind": kind,
        "created_unix_ns": time.time_ns(),
        "created_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timer": "time.perf_counter_ns",
        "locked_values": {
            "control_sha": CONTROL_SHA,
            "candidate_sha": CANDIDATE_SHA,
            "official_sha": OFFICIAL_SHA,
            "official_registry_sha256": OFFICIAL_REGISTRY_SHA256,
            "official_case_count": OFFICIAL_CASE_COUNT,
        },
        "environment": _environment_metadata(args.allow_non_aarch64),
        "artifacts": artifacts,
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
            if key != "handler"
        },
        "status": "running",
        "runs": [],
        "trial_exceptions": [],
        "summaries": {},
        "scope_notice": {
            "collector_only": True,
            "collector_only_no_verdict": True,
            "covered_here": "locked official-50 protocol collection and scale collection",
            "not_covered_here": (
                "authoritative/non-scale/fuzz/native/context/oracle/project/sanitizer/"
                "shadow/anti-cheat/full official A/B/A validation"
            ),
            "required_external_evidence": (
                "use the existing independent logs for all other gates and run a separate "
                "validator over this raw JSON; this collector does not issue the final verdict"
            ),
        },
    }


def _role_schedule(control_repetitions: int, candidate_repetitions: int, start: str) -> list[str]:
    remaining = {"control": control_repetitions, "candidate": candidate_repetitions}
    schedule: list[str] = []
    current = start
    while remaining["control"] or remaining["candidate"]:
        if remaining[current]:
            schedule.append(current)
            remaining[current] -= 1
        other = "candidate" if current == "control" else "control"
        if remaining[other]:
            current = other
        elif remaining[current]:
            current = current
        else:
            current = other
    return schedule


def _median_or_none(values: Sequence[int | float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else statistics.median(present)


def _record_trial_exception(
    report: dict[str, Any],
    *,
    case_name: str,
    protocol: str,
    role: str,
    role_repetition: int,
    schedule_key: str,
    error: Exception,
) -> None:
    report["trial_exceptions"].append(
        {
            "attempt_index": len(report["runs"]) + len(report["trial_exceptions"]),
            "case_name": case_name,
            "protocol": protocol,
            "role": role,
            "role_repetition": role_repetition,
            "schedule_key": schedule_key,
            "kind": type(error).__name__,
            "message": str(error),
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
            "recorded_unix_ns": time.time_ns(),
            "required_observation_missing": True,
        }
    )


def run_strict_official(args: argparse.Namespace) -> int:
    artifacts, paths = _locked_artifacts(args)
    output = _validate_output_path(
        args.output,
        [paths["control_root"], paths["candidate_root"], paths["official_root"]],
    )
    registry_metadata, cases = _load_official_cases(paths["official_root"])
    encoding = _load_encoding(paths["official_root"])
    tokenized: list[tuple[InputCase, list[int], list[bytes]]] = []
    for case in cases:
        token_ids = _tokenize(encoding, case.source)
        token_chunks = _token_chunks(encoding, token_ids, case.source)
        target = case.official_first_error_token_index
        assert target is not None
        if target >= len(token_ids):
            raise HarnessError(
                f"official case {case.name}: target {target} outside {len(token_ids)} tokens"
            )
        tokenized.append((case, token_ids, token_chunks))

    report = _new_report("strict-official", args, artifacts)
    report["official_registry"] = registry_metadata
    report["protocol_contract"] = {
        "fresh_process_per_trial": True,
        "stdin": "one decimal cl100k_base token ID plus newline, flushed immediately",
        "stdout": "exactly one 0\\n or 1\\n response per token",
        "on_first_error_or_mismatch": (
            "close stdin immediately; capture all trailing stdout/stderr and final exit"
        ),
        "full_transcript_retained": True,
    }
    report["cases"] = [
        _case_record(case, token_ids, token_chunks, include_source=True)
        for case, token_ids, token_chunks in tokenized
    ]
    _atomic_write_json(output, report)

    roles = ("control", "candidate")
    role_repetitions = {role: 0 for role in roles}
    try:
        for protocol_index, protocol in enumerate(_protocol_names(args.protocol)):
            for case_index, (case, token_ids, token_chunks) in enumerate(tokenized):
                start = "control" if (protocol_index + case_index) % 2 == 0 else "candidate"
                schedule = _role_schedule(args.repetitions, args.repetitions, start)
                local_rep = {"control": 0, "candidate": 0}
                for role in schedule:
                    local_rep[role] += 1
                    role_repetitions[role] += 1
                    print(
                        f"strict-official {protocol} {case.name} {role} "
                        f"rep={local_rep[role]}/{args.repetitions}",
                        flush=True,
                    )
                    try:
                        run = _run_interactive(
                            role=role,
                            solution=paths[f"{role}_solution"],
                            cwd=paths[f"{role}_root"],
                            protocol=protocol,
                            token_ids=token_ids,
                            token_byte_lengths=[len(chunk) for chunk in token_chunks],
                            case_expected="reject",
                            timeout_seconds=args.timeout_seconds,
                            exit_timeout_seconds=args.exit_timeout_seconds,
                            rss_sample_ms=None,
                            request_phase_profile=False,
                            official_target=case.official_first_error_token_index,
                        )
                        run.update(
                            {
                                "run_id": len(report["runs"]),
                                "case_name": case.name,
                                "case_source_sha256": case.source_sha256,
                                "role_repetition": local_rep[role],
                                "scheduled_role_order": schedule,
                                "official_ok": _official_run_ok(
                                    run,
                                    int(case.official_first_error_token_index),
                                    protocol,
                                ),
                            }
                        )
                    except Exception as error:  # preserve and continue this fixed schedule
                        _record_trial_exception(
                            report,
                            case_name=case.name,
                            protocol=protocol,
                            role=role,
                            role_repetition=local_rep[role],
                            schedule_key=f"official:{case.name}:{protocol}",
                            error=error,
                        )
                        report["last_checkpoint_unix_ns"] = time.time_ns()
                        _atomic_write_json(output, report)
                        continue
                    report["runs"].append(run)
                    report["last_checkpoint_unix_ns"] = time.time_ns()
                    _atomic_write_json(output, report)
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["interruption"] = "KeyboardInterrupt"
        _atomic_write_json(output, report)
        return 130

    failed_runs = [run for run in report["runs"] if not run["official_ok"]]
    expected_runs_per_case = len(_protocol_names(args.protocol)) * 2 * args.repetitions
    passed_names: set[str] = set()
    for case in cases:
        case_runs = [
            run for run in report["runs"] if run["case_name"] == case.name
        ]
        if len(case_runs) == expected_runs_per_case and all(
            run["official_ok"] for run in case_runs
        ):
            passed_names.add(case.name)
    expected_run_count = len(cases) * expected_runs_per_case
    missing_required_observations: list[dict[str, Any]] = []
    for case in cases:
        for protocol in _protocol_names(args.protocol):
            for role in ("control", "candidate"):
                for repetition in range(1, args.repetitions + 1):
                    present = any(
                        run["case_name"] == case.name
                        and run["protocol"] == protocol
                        and run["role"] == role
                        and run["role_repetition"] == repetition
                        for run in report["runs"]
                    )
                    if not present:
                        missing_required_observations.append(
                            {
                                "case_name": case.name,
                                "protocol": protocol,
                                "role": role,
                                "role_repetition": repetition,
                            }
                        )
    report["summaries"] = {
        "collector_only_no_verdict": True,
        "run_count": len(report["runs"]),
        "trial_exception_count": len(report["trial_exceptions"]),
        "passed_run_count": len(report["runs"]) - len(failed_runs),
        "failed_run_count": len(failed_runs),
        "case_count": len(cases),
        "fully_passed_case_count": len(passed_names),
        "expected_run_count": expected_run_count,
        "expected_runs_per_case": expected_runs_per_case,
        "missing_required_observation_count": len(missing_required_observations),
        "missing_required_observations": missing_required_observations,
        "all_trials_exact": (
            not failed_runs
            and len(report["runs"]) == expected_run_count
            and not missing_required_observations
            and len(passed_names) == OFFICIAL_CASE_COUNT
        ),
        "role_trial_counts": role_repetitions,
    }
    report["status"] = "complete"
    report["completed_unix_ns"] = time.time_ns()
    _atomic_write_json(output, report)
    print(f"raw JSON: {output}", flush=True)
    return 0 if report["summaries"]["all_trials_exact"] else 1


def _scale_identifier_summary(report: dict[str, Any], protocols: Sequence[str]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for protocol in protocols:
        schedules = [
            schedule
            for schedule in report.get("schedules", [])
            if schedule["case_name"] == IDENTIFIER_MANIFEST_NAME
            and schedule["protocol"] == protocol
        ]
        runs = [
            run
            for run in report["runs"]
            if run["case_name"] == IDENTIFIER_MANIFEST_NAME
            and run["protocol"] == protocol
        ]
        if not schedules:
            summaries[protocol] = {
                "scheduled": False,
                "collector_only_no_verdict": True,
                "missing_required_observation_count": 0,
            }
            continue
        expected_by_role = {
            role: sum(schedule[f"{role}_repetitions"] for schedule in schedules)
            for role in ("control", "candidate")
        }
        observed_by_role = {
            role: sum(run["role"] == role for run in runs)
            for role in ("control", "candidate")
        }
        missing_by_role = {
            role: max(0, expected_by_role[role] - observed_by_role[role])
            for role in ("control", "candidate")
        }
        effective_answer_count = lambda run: (
            run["deadline_answer_count"]
            if run["timed_out"] and run["deadline_answer_count"] is not None
            else run["answer_count"]
        )
        min_answers = (
            None if not runs else min(effective_answer_count(run) for run in runs)
        )
        common_correct = 0
        expected = _continue_bit(protocol)
        for index in range(min_answers or 0):
            bits = [run["response_bits"][index] for run in runs]
            if any(bit != expected for bit in bits) or any(
                bit != bits[0] for bit in bits[1:]
            ):
                break
            common_correct += 1
        prefix_timings: list[dict[str, Any]] = []
        for run in runs:
            elapsed = (
                run["response_events"][common_correct - 1]["response_elapsed_ns"]
                if common_correct > 0 and run["answer_count"] >= common_correct
                else None
            )
            elapsed_80 = (
                run["response_events"][IDENTIFIER_MIN_COMMON_PREFIX - 1]["response_elapsed_ns"]
                if run["answer_count"] >= IDENTIFIER_MIN_COMMON_PREFIX
                else None
            )
            prefix_timings.append(
                {
                    "run_id": run["run_id"],
                    "role": run["role"],
                    "role_repetition": run["role_repetition"],
                    "answer_count": run["answer_count"],
                    "deadline_answer_count": run["deadline_answer_count"],
                    "effective_deadline_answer_count": effective_answer_count(run),
                    "selected_common_prefix_elapsed_ns": elapsed,
                    "prefix_80_elapsed_ns": elapsed_80,
                }
            )
        answer_medians = {
            role: _median_or_none(
                [
                    effective_answer_count(run)
                    for run in runs
                    if run["role"] == role
                ]
            )
            for role in ("control", "candidate")
        }
        prefix_medians = {
            role: _median_or_none(
                [
                    item["selected_common_prefix_elapsed_ns"]
                    for item in prefix_timings
                    if item["role"] == role
                ]
            )
            for role in ("control", "candidate")
        }
        control_answer_median = answer_medians["control"]
        summaries[protocol] = {
            "scheduled": True,
            "collector_only_no_verdict": True,
            "trial_count": len(runs),
            "required_trials_per_role": SCALE_REPETITIONS,
            "expected_trials_by_role": expected_by_role,
            "observed_trials_by_role": observed_by_role,
            "missing_trials_by_role": missing_by_role,
            "missing_required_observation_count": sum(missing_by_role.values()),
            "minimum_answers_across_all_trials": min_answers,
            "selected_common_correct_prefix_count": common_correct,
            "required_minimum_common_prefix_count": IDENTIFIER_MIN_COMMON_PREFIX,
            "meets_minimum_common_prefix": common_correct >= IDENTIFIER_MIN_COMMON_PREFIX,
            "per_trial_prefix_timings": prefix_timings,
            "answer_count_median_by_role": answer_medians,
            "selected_prefix_elapsed_ns_median_by_role": prefix_medians,
            "answer_count_allowed_candidate_shortfall": (
                None
                if control_answer_median is None
                else max(2.0, control_answer_median * 0.02)
            ),
            "gate_peak_vmhwm_kib_median_by_role": {
                role: _median_or_none(
                    [
                        run["rss"]["gate_peak_vmhwm_kib"]
                        for run in runs
                        if run["role"] == role
                    ]
                )
                for role in ("control", "candidate")
            },
            "all_emitted_response_prefixes_correct": (
                None
                if not runs or sum(missing_by_role.values())
                else all(
                    run["expected_prefix_ok"]
                    and all(bit == expected for bit in run["response_bits"])
                    for run in runs
                )
            ),
        }
    return summaries


def _scale_group_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    keyed: dict[tuple[str, str], None] = {}
    for schedule in report.get("schedules", []):
        keyed[(schedule["case_name"], schedule["protocol"])] = None
    for run in report["runs"]:
        keyed[(run["case_name"], run["protocol"])] = None
    keys = sorted(keyed)
    result: list[dict[str, Any]] = []
    for case_name, protocol in keys:
        schedules = [
            schedule
            for schedule in report.get("schedules", [])
            if schedule["case_name"] == case_name
            and schedule["protocol"] == protocol
        ]
        runs = [
            run
            for run in report["runs"]
            if run["case_name"] == case_name and run["protocol"] == protocol
        ]
        expected_by_role = {
            role: sum(schedule[f"{role}_repetitions"] for schedule in schedules)
            for role in ("control", "candidate")
        }
        by_role: dict[str, Any] = {}
        role_observations: dict[str, list[dict[str, Any]]] = {}
        role_multisets: dict[str, Counter[tuple[Any, ...]]] = {}
        for role in ("control", "candidate"):
            role_runs = [run for run in runs if run["role"] == role]
            completed_runs = [run for run in role_runs if not run["timed_out"]]
            timed_out_runs = [run for run in role_runs if run["timed_out"]]
            missing = max(0, expected_by_role[role] - len(role_runs))
            by_role[role] = {
                "expected_trial_count": expected_by_role[role],
                "trial_count": len(role_runs),
                "missing_required_observation_count": missing,
                "completed_process_total_ns_median": _median_or_none(
                    [run["process_total_ns"] for run in completed_runs]
                ),
                "answer_count_median": _median_or_none(
                    [
                        run["deadline_answer_count"]
                        if run["timed_out"]
                        and run["deadline_answer_count"] is not None
                        else run["answer_count"]
                        for run in role_runs
                    ]
                ),
                "gate_peak_vmhwm_kib_median": _median_or_none(
                    [run["rss"]["gate_peak_vmhwm_kib"] for run in role_runs]
                ),
                "timed_out_trials": len(timed_out_runs),
                "timeout_configured_lower_bound_ns": [
                    run["configured_timeout_lower_bound_ns"]
                    for run in timed_out_runs
                ],
                "timeout_deadline_elapsed_ns_observed": [
                    run["deadline_elapsed_ns"] for run in timed_out_runs
                ],
                "process_total_ns_cleanup_inclusive_all_trials": [
                    run["process_total_ns"] for run in role_runs
                ],
                "timeout_summary_rule": (
                    "timed-out trials contribute only configured_timeout_lower_bound_ns; "
                    "cleanup-inclusive process_total_ns is retained separately"
                ),
                "case_ok_trials": sum(bool(run["case_ok"]) for run in role_runs),
            }
            observations: list[dict[str, Any]] = []
            tuples: list[tuple[Any, ...]] = []
            for run in role_runs:
                observation = {
                    "run_id": run["run_id"],
                    "role_repetition": run["role_repetition"],
                    "stdout_sha256": run["stdout_sha256"],
                    "stderr_sha256": run["stderr_sha256"],
                    "returncode": run["returncode"],
                    "timed_out": run["timed_out"],
                    "answer_count": run["answer_count"],
                    "deadline_answer_count": run["deadline_answer_count"],
                }
                observations.append(observation)
                tuples.append(
                    (
                        run["stdout_sha256"],
                        run["stderr_sha256"],
                        run["returncode"],
                        run["timed_out"],
                        run["answer_count"],
                        run["deadline_answer_count"],
                    )
                )
            role_observations[role] = observations
            role_multisets[role] = Counter(tuples)
        missing_total = sum(
            by_role[role]["missing_required_observation_count"]
            for role in ("control", "candidate")
        )
        multiset_json = {
            role: [
                {
                    "observation": {
                        "stdout_sha256": value[0],
                        "stderr_sha256": value[1],
                        "returncode": value[2],
                        "timed_out": value[3],
                        "answer_count": value[4],
                        "deadline_answer_count": value[5],
                    },
                    "multiplicity": multiplicity,
                }
                for value, multiplicity in sorted(
                    role_multisets[role].items(), key=lambda item: repr(item[0])
                )
            ]
            for role in ("control", "candidate")
        }
        result.append(
            {
                "case_name": case_name,
                "protocol": protocol,
                "collector_only_no_verdict": True,
                "by_role": by_role,
                "missing_required_observation_count": missing_total,
                "required_observations_complete": missing_total == 0,
                "role_observations_per_trial": role_observations,
                "role_observation_multisets": multiset_json,
                "control_candidate_observation_multisets_equal": (
                    None
                    if missing_total
                    else role_multisets["control"] == role_multisets["candidate"]
                ),
            }
        )
    return result


def run_scale(args: argparse.Namespace) -> int:
    artifacts, paths = _locked_artifacts(args)
    output = _validate_output_path(
        args.output,
        [paths["control_root"], paths["candidate_root"], paths["official_root"]],
    )
    # Registry lock is rechecked even though scale sources come from candidate.
    registry_metadata, _ = _load_official_cases(paths["official_root"])
    manifest_metadata, locals_cases, other_cases = _load_scale_cases(
        paths["candidate_root"]
    )
    encoding = _load_encoding(paths["official_root"])
    protocols = _protocol_names(args.protocol)
    selected_cases: list[InputCase] = []
    if args.section in {"all", "locals"}:
        selected_cases.extend(locals_cases)
    if args.section in {"all", "other"}:
        selected_cases.extend(other_cases)
    tokenized: dict[str, tuple[list[int], list[bytes]]] = {}
    for case in selected_cases:
        token_ids = _tokenize(encoding, case.source)
        tokenized[case.name] = (
            token_ids,
            _token_chunks(encoding, token_ids, case.source),
        )

    report = _new_report("scale", args, artifacts)
    report["collector_contract"] = {
        "collector_only_no_verdict": True,
        "exit_code_zero_meaning": (
            "collection schedule completed and raw JSON was written; it does not mean any "
            "correctness, performance, RSS, or acceptance gate passed"
        ),
        "validator_required": True,
    }
    report["official_registry"] = registry_metadata
    report["candidate_manifest"] = manifest_metadata
    report["scale_rules"] = {
        "local_counts": list(LOCAL_COUNTS),
        "repetitions_0_through_250_each_role": SCALE_REPETITIONS,
        "repetitions_300_candidate": SCALE_REPETITIONS,
        "repetitions_300_control": 1,
        "control_300_timeout_seconds": CONTROL_300_TIMEOUT_SECONDS,
        "repetitions_500_candidate": SCALE_REPETITIONS,
        "repetitions_500_control_if_300_completed": 1,
        "skip_control_500_if_control_300_timed_out": True,
        "other_scale_repetitions_each_role": SCALE_REPETITIONS,
        "identifier_timeout_seconds": IDENTIFIER_TIMEOUT_SECONDS,
        "identifier_minimum_common_prefix": IDENTIFIER_MIN_COMMON_PREFIX,
        "role_order": "alternating; starting role counterbalanced by case/protocol parity",
        "protocols": list(protocols),
        "timing_breakdown": {
            "process_total_ns": "measured",
            "syntax_time_ns": None,
            "semantic_time_ns": None,
            "reason": (
                "CANGJIE_PHASE_PROFILE is parsed only when present; the default "
                "production binary has no phase instrumentation, so both fields are null"
            ),
            "phase_profile_requested": args.request_phase_profile,
        },
    }
    report["cases"] = [
        _case_record(
            case,
            tokenized[case.name][0],
            tokenized[case.name][1],
            include_source=True,
        )
        for case in selected_cases
    ]
    report["schedules"] = []
    _atomic_write_json(output, report)

    control_300_timed_out: dict[str, bool] = {}

    def execute_case(
        case: InputCase,
        protocol: str,
        control_repetitions: int,
        candidate_repetitions: int,
        *,
        timeout_for_role: dict[str, float],
        schedule_key: str,
        start_role: str,
    ) -> None:
        schedule = _role_schedule(control_repetitions, candidate_repetitions, start_role)
        schedule_record = {
            "key": schedule_key,
            "case_name": case.name,
            "protocol": protocol,
            "control_repetitions": control_repetitions,
            "candidate_repetitions": candidate_repetitions,
            "roles": schedule,
            "timeouts_seconds": timeout_for_role,
        }
        report["schedules"].append(schedule_record)
        local_rep = {"control": 0, "candidate": 0}
        for role in schedule:
            local_rep[role] += 1
            print(
                f"scale {protocol} {case.name} {role} "
                f"rep={local_rep[role]}/{control_repetitions if role == 'control' else candidate_repetitions} "
                f"timeout={timeout_for_role[role]:g}s",
                flush=True,
            )
            try:
                run = _run_interactive(
                    role=role,
                    solution=paths[f"{role}_solution"],
                    cwd=paths[f"{role}_root"],
                    protocol=protocol,
                    token_ids=tokenized[case.name][0],
                    token_byte_lengths=[
                        len(chunk) for chunk in tokenized[case.name][1]
                    ],
                    case_expected=case.expected,
                    timeout_seconds=timeout_for_role[role],
                    exit_timeout_seconds=args.exit_timeout_seconds,
                    rss_sample_ms=args.rss_sample_ms,
                    request_phase_profile=args.request_phase_profile,
                )
                run.update(
                    {
                        "run_id": len(report["runs"]),
                        "case_name": case.name,
                        "case_family": case.family,
                        "case_source_sha256": case.source_sha256,
                        "role_repetition": local_rep[role],
                        "schedule_key": schedule_key,
                        "case_ok": _scale_run_case_ok(run, case.expected),
                    }
                )
            except Exception as error:  # persist the missing observation, then continue
                _record_trial_exception(
                    report,
                    case_name=case.name,
                    protocol=protocol,
                    role=role,
                    role_repetition=local_rep[role],
                    schedule_key=schedule_key,
                    error=error,
                )
                report["last_checkpoint_unix_ns"] = time.time_ns()
                _atomic_write_json(output, report)
                continue
            report["runs"].append(run)
            report["last_checkpoint_unix_ns"] = time.time_ns()
            _atomic_write_json(output, report)

    try:
        if args.section in {"all", "locals"}:
            for case_index, case in enumerate(locals_cases):
                count = int(case.name.split("-", 1)[1])
                for protocol_index, protocol in enumerate(protocols):
                    if count <= 250:
                        control_reps = SCALE_REPETITIONS
                        candidate_reps = SCALE_REPETITIONS
                    elif count == 300:
                        control_reps = 1
                        candidate_reps = SCALE_REPETITIONS
                    else:
                        control_reps = 0 if control_300_timed_out.get(protocol) else 1
                        candidate_reps = SCALE_REPETITIONS
                    timeout_for_role = {
                        "control": (
                            CONTROL_300_TIMEOUT_SECONDS
                            if count == 300
                            else args.scale_timeout_seconds
                        ),
                        "candidate": args.scale_timeout_seconds,
                    }
                    start = (
                        "control"
                        if (case_index + protocol_index) % 2 == 0 and control_reps
                        else "candidate"
                    )
                    execute_case(
                        case,
                        protocol,
                        control_reps,
                        candidate_reps,
                        timeout_for_role=timeout_for_role,
                        schedule_key=f"locals-{count}:{protocol}",
                        start_role=start,
                    )
                    if count == 300:
                        matching = [
                            run
                            for run in report["runs"]
                            if run["case_name"] == case.name
                            and run["protocol"] == protocol
                            and run["role"] == "control"
                        ]
                        control_300_timed_out[protocol] = (
                            not matching or any(run["timed_out"] for run in matching)
                        )
                    if count == 500 and control_reps == 0:
                        report["schedules"][-1]["control_skip_reason"] = (
                            "locked rule: same-protocol control timed out or its required "
                            "300-locals observation was missing"
                        )
                        _atomic_write_json(output, report)

        if args.section in {"all", "other"}:
            for case_index, case in enumerate(other_cases):
                for protocol_index, protocol in enumerate(protocols):
                    timeout = (
                        IDENTIFIER_TIMEOUT_SECONDS
                        if case.name == IDENTIFIER_MANIFEST_NAME
                        else args.scale_timeout_seconds
                    )
                    start = (
                        "control"
                        if (case_index + protocol_index) % 2 == 0
                        else "candidate"
                    )
                    execute_case(
                        case,
                        protocol,
                        SCALE_REPETITIONS,
                        SCALE_REPETITIONS,
                        timeout_for_role={"control": timeout, "candidate": timeout},
                        schedule_key=f"manifest:{case.name}:{protocol}",
                        start_role=start,
                    )
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["interruption"] = "KeyboardInterrupt"
        report["summaries"]["collector_only_no_verdict"] = True
        report["summaries"]["trial_exception_count"] = len(
            report["trial_exceptions"]
        )
        report["summaries"]["groups"] = _scale_group_summaries(report)
        report["summaries"]["identifier"] = _scale_identifier_summary(report, protocols)
        _atomic_write_json(output, report)
        return 130

    report["summaries"] = {
        "collector_only_no_verdict": True,
        "run_count": len(report["runs"]),
        "trial_exception_count": len(report["trial_exceptions"]),
        "groups": _scale_group_summaries(report),
        "identifier": _scale_identifier_summary(report, protocols),
        "control_300_timed_out_by_protocol": control_300_timed_out,
        "note": (
            "These are collector-only mechanical views. A separate independent validator "
            "must enforce every threshold from raw runs without discarding any trial. "
            "Scale command exit 0 is never a gate or verdict."
        ),
    }
    report["status"] = "complete"
    report["completed_unix_ns"] = time.time_ns()
    _atomic_write_json(output, report)
    print(f"raw JSON: {output}", flush=True)
    return 0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not (parsed > 0.0):
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return parsed


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--control-root", type=Path, default=Path("/control"))
    parser.add_argument("--candidate-root", type=Path, default=Path("/candidate"))
    parser.add_argument("--official-root", type=Path, default=Path("/official"))
    parser.add_argument(
        "--control-solution",
        type=Path,
        help="must resolve to CONTROL_ROOT/solution unless the scale-only profile override is explicit",
    )
    parser.add_argument(
        "--candidate-solution",
        type=Path,
        help="must resolve to CANDIDATE_ROOT/solution unless the scale-only profile override is explicit",
    )
    parser.add_argument("--output", type=Path, required=True, help="raw JSON path outside all audited roots")
    parser.add_argument(
        "--protocol",
        choices=("both", "default", "competition"),
        default="both",
        help="locked audit default is both; single-protocol mode is diagnostic",
    )
    parser.add_argument(
        "--allow-non-aarch64",
        action="store_true",
        help="diagnostic-only override; official audit must not use it",
    )
    parser.add_argument(
        "--exit-timeout-seconds",
        type=_positive_float,
        default=2.0,
        help="maximum natural-exit wait after stdin is closed",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Raw official-50/scale collector only; not the complete G1 audit and not a verdict"
        ),
        epilog=(
            "Authoritative, non-scale, fuzz, native, context, oracle, project, sanitizer, "
            "shadow, anti-cheat, and official A/B/A gates must come from the existing "
            "independent logs and separate validators."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    official = subparsers.add_parser(
        "strict-official",
        help="run locked official 50 with exact first-error and full transcripts",
    )
    _add_common_arguments(official)
    official.add_argument("--repetitions", type=_positive_int, default=1)
    official.add_argument("--timeout-seconds", type=_positive_float, default=10.0)
    official.set_defaults(handler=run_strict_official)

    scale = subparsers.add_parser(
        "scale",
        help="run generated locals and the eight remaining manifest scale cases",
    )
    _add_common_arguments(scale)
    scale.add_argument(
        "--section",
        choices=("all", "locals", "other"),
        default="all",
        help="all is the locked full run; subsets are for staged execution",
    )
    scale.add_argument(
        "--scale-timeout-seconds",
        type=_positive_float,
        default=35.0,
        help="timeout for non-identifier scale trials (control 300 remains locked to 35s)",
    )
    scale.add_argument(
        "--rss-sample-ms",
        type=_positive_float,
        default=5.0,
        help="/proc/PID/status VmRSS point-sampling interval",
    )
    scale.add_argument(
        "--request-phase-profile",
        action="store_true",
        help=(
            "set CANGJIE_PROFILE=1 and parse optional CANGJIE_PHASE_PROFILE records; "
            "default production builds emit none, leaving syntax/semantic null"
        ),
    )
    scale.add_argument(
        "--allow-external-profile-solutions",
        action="store_true",
        help=(
            "explicit exception for separately built profile binaries; requires "
            "--request-phase-profile and both explicit solution paths"
        ),
    )
    scale.set_defaults(handler=run_scale)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except HarnessError as error:
        print(f"HARNESS ERROR: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
