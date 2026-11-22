import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import psutil


GIB = 2**30
PLAN = 14196
KEY = re.compile(r"[0-9a-f]{64}\.json")
K = c.WinDLL("kernel32", use_last_error=True)
K.CreateJobObjectW.argtypes = (c.c_void_p, w.LPCWSTR)
K.CreateJobObjectW.restype = w.HANDLE
K.SetInformationJobObject.argtypes = (w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
K.AssignProcessToJobObject.argtypes = (w.HANDLE, w.HANDLE)
K.TerminateJobObject.argtypes = (w.HANDLE, w.UINT)
K.CloseHandle.argtypes = (w.HANDLE,)


class BasicLimits(c.Structure):
    _fields_ = [
        ("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
        ("min_working_set", c.c_size_t), ("max_working_set", c.c_size_t), ("max_processes", w.DWORD),
        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD),
    ]


class ExtendedLimits(c.Structure):
    _fields_ = [
        ("basic", BasicLimits), ("io", c.c_ulonglong * 6),
        ("process_memory", c.c_size_t), ("job_memory", c.c_size_t),
        ("peak_process_memory", c.c_size_t), ("peak_job_memory", c.c_size_t),
    ]


def checked(result):
    if not result:
        raise c.WinError(c.get_last_error())
    return result


def launch(command, log):
    job = checked(K.CreateJobObjectW(None, None))
    try:
        limit = ExtendedLimits()
        limit.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        checked(K.SetInformationJobObject(job, 9, c.byref(limit), c.sizeof(limit)))
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            checked(K.AssignProcessToJobObject(job, child._handle))
        except BaseException:
            child.kill()
            child.wait()
            raise
        return job, child
    except BaseException:
        K.CloseHandle(job)
        raise


def count(checkpoint):
    return sum(KEY.fullmatch(item.name) is not None for item in checkpoint.glob("*.json"))


def update_peaks(root, peaks, roles):
    try:
        process = psutil.Process(root)
        processes = [process, *process.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    for proc in processes:
        try:
            pid = proc.pid
            if pid not in roles:
                cmd = proc.cmdline()
                roles[pid] = "worker" if any("--multiprocessing-fork" in word for word in cmd) else "controller"
            values = proc.memory_info()
            peaks[pid] = max(peaks.get(pid, 0), values.peak_wset)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def memory_rows(peaks, roles):
    return [{"pid": p, "role": roles[p], "peak_gib": round(v / GIB, 3)}
            for p, v in sorted(peaks.items()) if v]


def report(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch", type=Path)
    parser.add_argument("mode", choices=("operational-smoke", "locked"))
    parser.add_argument("workers", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 6:
        raise ValueError("Invalid worker count")
    locked = args.mode == "locked"
    start = time.monotonic()
    workers = args.workers
    checkpoint = args.scratch / ("checkpoint" if locked else f"smoke-operational-{workers}")
    status_path = args.scratch / (f"{args.mode}-status.json" if locked else f"{args.mode}-{workers}-status.json")
    logfile = status_path.with_suffix(".log")
    started = datetime.now(timezone.utc).isoformat()
    attempts = []
    resume = args.resume
    phase = "stopped"
    error = None
    epoch_reported = False
    before = count(checkpoint)
    try:
        with logfile.open("a", encoding="utf8") as log:
            while True:
                available = psutil.virtual_memory().available / GIB
                if available < 3:
                    phase = "ram_abort"
                    break
                if locked:
                    command = [sys.executable, "-u", "-B", str(args.scratch / "stagger.py"),
                               "--mode", "run-locked", "--repo", "datahub", "--workers", str(workers),
                               "--checkpoint", str(checkpoint)]
                else:
                    command = [sys.executable, "-u", "-B", str(args.scratch / "smoke.py"),
                               str(args.scratch), "operational", str(workers)]
                if resume:
                    command.append("--resume")
                job, child = launch(command, log)
                peaks, roles = {}, {}
                attempt = {"workers": workers, "resumed": resume, "start_calls": count(checkpoint)}
                attempts.append(attempt)
                next_progress = 0
                launch_time = time.monotonic()
                stop = None
                peak, projection = 0, 4
                try:
                    while child.poll() is None:
                        now = time.monotonic()
                        update_peaks(child.pid, peaks, roles)
                        available = psutil.virtual_memory().available / GIB
                        peak = max((v for p, v in peaks.items() if roles[p] == "worker"), default=0) / GIB
                        projection = peak * workers + 4
                        if available < (3 if locked else 4.5):
                            stop = "ram_abort"
                            break
                        if locked and available < 5 and workers > 1:
                            stop = "reduce_workers"
                            break
                        memory_checkpoint = locked and not epoch_reported and now - start >= 600
                        if now >= next_progress or memory_checkpoint:
                            done = count(checkpoint)
                            rate = (done - before) / max(now - start, 0.001)
                            remaining = PLAN - done if locked else None
                            attempt.update(calls_done=done, peak_worker_gib=round(peak, 3),
                                           memory=memory_rows(peaks, roles), available_gib=round(available, 3),
                                           projected_gib=round(projection, 3))
                            report(status_path, {"state": "running", "started_utc": started,
                                                 "elapsed_s": now - start, "attempts": attempts,
                                                 "eta_s": remaining / rate if remaining is not None and rate > 0 else None,
                                                 "calls_per_minute": rate * 60,
                                                 "checkpoint": str(checkpoint)})
                            print(f"PROGRESS workers={workers} calls={done}/{PLAN if locked else 9} "
                                  f"available_gib={available:.2f} peak_worker_gib={peak:.2f} "
                                  f"eta_s={remaining / rate if remaining is not None and rate > 0 else 'pending'}",
                                  flush=True)
                            if memory_checkpoint:
                                epoch_reported = True
                                print("MEMORY_10M", json.dumps({"elapsed_s": now-start, "calls": done, "calls_per_minute": rate*60,
                                      "eta_s": remaining/rate if rate else None, "available_gib": available,
                                      "attempts": attempts, "memory": attempt["memory"]}), flush=True)
                            next_progress = now + 60
                        time.sleep(0.22)
                    if stop is not None:
                        checked(K.TerminateJobObject(job, 125))
                    child.wait(timeout=30)
                finally:
                    K.CloseHandle(job)
                attempt.update(calls_done=count(checkpoint), available_gib=round(available, 3),
                               memory=memory_rows(peaks, roles),
                               peak_worker_gib=round(peak, 3), projected_gib=round(projection, 3),
                               exit_code=child.returncode, stop=stop, elapsed_s=time.monotonic()-launch_time)
                if stop == "reduce_workers":
                    print(f"MEMORY_REDUCTION available_gib={available:.3f} workers={workers}->{workers-1} calls={count(checkpoint)}", flush=True)
                    workers -= 1
                    resume = True
                    continue
                phase = stop or ("complete" if child.returncode == 0 else "runner_error")
                break
    except BaseException as exc:
        phase = "supervisor_error"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report(status_path, {"state": phase, "started_utc": started,
                             "elapsed_s": time.monotonic() - start,
                             "attempts": attempts, "calls_done": count(checkpoint),
                             "calls_before_supervisor": before,
                             "checkpoint": str(checkpoint), "error": error})
        print(f"SUPERVISOR {phase} calls={count(checkpoint)}", flush=True)
    return 0 if phase == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
