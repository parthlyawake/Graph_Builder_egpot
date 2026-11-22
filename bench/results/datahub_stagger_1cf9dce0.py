from concurrent.futures import ProcessPoolExecutor
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import sys
import time

from bench import egpot_multi_eval as runner


MUTEX_NAME = r"Local\EGPOT-DataHub-1cf9dce0-worker-initialization"
PLAN = 14196


def stagger_initializer(initializer, arguments):
    win = ctypes.WinDLL("kernel32", use_last_error=True)
    win.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    win.CreateMutexW.restype = wintypes.HANDLE
    win.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    win.WaitForSingleObject.restype = wintypes.DWORD
    win.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    win.CloseHandle.argtypes = (wintypes.HANDLE,)
    mutex = win.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        acquired = win.WaitForSingleObject(mutex, 0xFFFFFFFF) in (0, 0x80)
        if not acquired:
            raise ctypes.WinError(ctypes.get_last_error())
        print(f"WORKER_SETUP_BEGIN pid={os.getpid()} monotonic_s={time.monotonic():.3f}", flush=True)
        initializer(*arguments)
        print(f"WORKER_SETUP_END pid={os.getpid()} monotonic_s={time.monotonic():.3f}", flush=True)
    finally:
        if acquired:
            win.ReleaseMutex(mutex)
        win.CloseHandle(mutex)


class StaggeredPool(ProcessPoolExecutor):
    """Serialize the existing initializer and reject submissions for checkpointed keys."""

    def __init__(self, *, initializer, initargs, **kwargs):
        checkpoint = Path(sys.argv[sys.argv.index("--checkpoint") + 1])
        self.saved = {p.stem for p in checkpoint.glob("*.json") if re.fullmatch(r"[0-9a-f]{64}", p.stem)}
        self.submitted_keys = set()
        print(f"RESUME_GUARD protected_completed_calls={len(self.saved)}", flush=True)
        super().__init__(initializer=stagger_initializer, initargs=(initializer, initargs), **kwargs)

    def submit(self, fn, task, **kwargs):
        key = task["key"]
        if key in self.saved or key in self.submitted_keys:
            raise RuntimeError("Rejected submission of an already completed or scheduled call")
        future = super().submit(fn, task, **kwargs)
        self.submitted_keys.add(key)
        if len(self.saved) + len(self.submitted_keys) == PLAN:
            print(f"RESUME_GUARD_PASS protected={len(self.saved)} pending_submitted={len(self.submitted_keys)}",
                  flush=True)
        return future


def inspect_snapshot(checkpoint):
    snapshot = runner.read_json(checkpoint.parent / "checkpoint-before-switch.json")
    if runner.sha256(checkpoint / "manifest.json") != snapshot["manifest_sha256"]:
        raise ValueError("Checkpoint manifest changed during worker switch")
    rows = {}
    for key, checksum in snapshot["checkpoint_file_sha256"].items():
        path = checkpoint / f"{key}.json"
        if runner.sha256(path) != checksum:
            raise ValueError("An original completed checkpoint file changed")
        rows[key] = runner.read_json(path)["result"]["deterministic"]
    if len(rows) != snapshot["count"] or runner.digest(rows) != snapshot["deterministic_rows_sha256"]:
        raise ValueError("Completed row hash changed")
    print(f"SNAPSHOT_VERIFIED calls={len(rows)} sha256={snapshot['deterministic_rows_sha256']}", flush=True)


if __name__ == "__main__":
    checkpoint = Path(sys.argv[sys.argv.index("--checkpoint") + 1])
    inspect_snapshot(checkpoint)
    runner.ProcessPoolExecutor = StaggeredPool
    raise SystemExit(runner.main())
