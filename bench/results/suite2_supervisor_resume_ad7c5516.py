"""Execute Suite 2 phases with the frozen Windows launcher and memory thresholds."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

import psutil

from bench import egpot_suite2_locked as suite
from bench.results import datahub_supervisor_1cf9dce0 as original

GIB = original.GIB


def stamp():
    return datetime.now(timezone.utc).isoformat()


def event(path, action, **data):
    record = {"timestamp_utc": stamp(), "event": action, **data}
    with path.open("a", encoding="utf8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True), flush=True)


def snapshot(checkpoint):
    manifest = checkpoint / "manifest.json"
    if not manifest.is_file():
        return False
    files = sorted(path for path in checkpoint.glob("*.json") if original.KEY.fullmatch(path.name))
    rows = {path.stem: suite.runner.read_json(path)["result"]["deterministic"] for path in files}
    original.report(checkpoint.parent / "checkpoint-before-switch.json", {
        "count": len(files), "manifest_sha256": suite.runner.sha256(manifest),
        "checkpoint_file_sha256": {path.stem: suite.runner.sha256(path) for path in files},
        "deterministic_rows_sha256": suite.runner.digest(rows),
    })
    return True


def run_phase(phase, scratch, deviations, resume=False):
    phase_dir = scratch / phase
    phase_dir.mkdir(exist_ok=True)
    checkpoint = phase_dir / "checkpoint"
    output = phase_dir / "rows.json"
    status = phase_dir / "status.json"
    plan = suite.PHASES[phase][2]
    workers = 4
    if resume and not snapshot(checkpoint):
        raise ValueError("Resume requires a prior checkpoint manifest")
    start = time.monotonic()
    while True:
        available = psutil.virtual_memory().available / GIB
        if available < 3:
            event(deviations, "memory_stop", phase=phase, free_gib=round(available, 3),
                  done=original.count(checkpoint))
            return False
        command = [sys.executable, "-u", "-B", str(scratch / "suite2_stagger_ad7c5516.py"),
                   "--phase", phase, "--workers", str(workers), "--checkpoint",
                   str(checkpoint), "--out", str(output)]
        if resume:
            command.append("--resume")
        event(deviations, "phase_resume" if resume else "phase_start",
              phase=phase, workers=workers, free_gib=round(available, 3),
              done=original.count(checkpoint), planned=plan)
        peaks, roles = {}, {}
        stop = None
        next_update = 0
        with (phase_dir / "runner.log").open("a", encoding="utf8") as log:
            job, child = original.launch(command, log)
            try:
                while child.poll() is None:
                    now = time.monotonic()
                    original.update_peaks(child.pid, peaks, roles)
                    available = psutil.virtual_memory().available / GIB
                    if available < 3:
                        stop = "memory_stop"
                    elif phase == "datahub" and available < 5 and workers > 1:
                        stop = "worker_reduction"
                    if stop:
                        original.checked(original.K.TerminateJobObject(job, 125))
                        break
                    if now >= next_update:
                        done = original.count(checkpoint)
                        elapsed = now - start
                        original.report(status, {
                            "phase": phase, "state": "running", "done": done, "planned": plan,
                            "workers": workers, "free_gib": round(available, 3),
                            "timestamp_utc": stamp(), "elapsed_s": elapsed,
                            "eta_s": (plan - done) * elapsed / done if done else None,
                        })
                        next_update = now + 60
                    time.sleep(0.22)
                child.wait(timeout=30)
            finally:
                original.K.CloseHandle(job)
        done = original.count(checkpoint)
        event(deviations, stop or ("phase_complete" if child.returncode == 0 else "runner_error"),
              phase=phase, workers=workers, next_workers=workers - 1 if stop == "worker_reduction" else None,
              free_gib=round(available, 3), done=done, planned=plan, exit_code=child.returncode,
              elapsed_s=round(time.monotonic() - start, 3), memory=original.memory_rows(peaks, roles))
        if stop == "worker_reduction":
            workers -= 1
            resume = snapshot(checkpoint)
            continue
        original.report(status, {
            "phase": phase, "state": stop or ("complete" if child.returncode == 0 else "runner_error"),
            "done": done, "planned": plan, "workers": workers, "timestamp_utc": stamp(),
            "elapsed_s": round(time.monotonic() - start, 3), "exit_code": child.returncode,
        })
        return stop is None and child.returncode == 0 and done == plan and output.is_file()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("deviations", type=Path)
    parser.add_argument("--phase", choices=suite.PHASES, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.resume and any((args.scratch / args.phase / filename).exists()
           for filename in ("status.json", "rows.json", "checkpoint")):
        raise FileExistsError("A previous phase attempt already exists")
    os.environ["PYTHONPATH"] = str(suite.ROOT)
    try:
        return 0 if run_phase(args.phase, args.scratch, args.deviations, args.resume) else 1
    except BaseException as exc:
        event(args.deviations, "supervisor_error", phase=args.phase,
              error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
