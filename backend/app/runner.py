import os
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

import psutil

# Hard ceiling on a single execution. Without this, one `while True:` pins a CPU
# on your Render instance forever and every other user's run gets starved.
MAX_EXECUTION_SECONDS = int(os.getenv("MAX_EXECUTION_SECONDS", "30"))


class CodeRunner:
    """
    Runs user Python files as subprocesses.

    All tracking dicts are keyed by an opaque `key`, not by filename, so two
    users who both have a main.py don't collide. Callers should pass a
    per-user key such as "alice/main.py" (see routers/execution.py).
    """

    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running_files: Dict[str, bool] = {}
        self.start_times: Dict[str, float] = {}
        self.results: Dict[str, Dict] = {}
        self.lock = threading.Lock()

    def run_file(self, filename: str, upload_dir: str, key: Optional[str] = None) -> Dict:
        """Start `filename` (inside `upload_dir`) and return immediately."""
        key = key or filename
        file_path = os.path.join(upload_dir, filename)

        if not os.path.exists(file_path):
            return {"error": f"File '{filename}' not found at {file_path}"}

        if os.path.getsize(file_path) == 0:
            return {"error": f"File '{filename}' is empty (0 bytes)"}

        with self.lock:
            if self.running_files.get(key):
                return {"error": f"File '{filename}' is already running"}

        try:
            start_time = time.time()
            # sys.executable is the interpreter actually running the app — more
            # reliable than "python", which may not exist on slim images.
            process = subprocess.Popen(
                [sys.executable, "-u", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=upload_dir,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            with self.lock:
                self.processes[key] = process
                self.running_files[key] = True
                self.start_times[key] = start_time
                self.results.pop(key, None)

            print(f"✅ Started {key} (PID {process.pid})")
            return {"running": True, "message": f"File '{filename}' started successfully"}

        except Exception as e:
            with self.lock:
                self.running_files[key] = False
            return {"error": f"Failed to run: {str(e)}"}

    def _kill_tree(self, process: subprocess.Popen) -> None:
        """Kill the process and any children it spawned."""
        try:
            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            parent.kill()
        except psutil.Error:
            try:
                process.kill()
            except Exception:
                pass

    def _finalize(self, key: str, result: Dict) -> Dict:
        """Store a terminal result and drop the process bookkeeping."""
        with self.lock:
            self.results[key] = result
            self.processes.pop(key, None)
            self.running_files.pop(key, None)
            self.start_times.pop(key, None)
        return result

    def stop_file(self, key: str) -> Dict:
        """Stop a running execution."""
        with self.lock:
            if key not in self.processes:
                if key in self.results:
                    return {"message": f"'{key}' already finished"}
                return {"error": f"'{key}' is not running"}
            process = self.processes[key]
            started = self.start_times.get(key, time.time())

        try:
            self._kill_tree(process)
            self._finalize(
                key,
                {
                    "finished": True,
                    "status": "Stopped",
                    "output": "🛑 Program stopped by user",
                    "error": "",
                    "return_code": -1,
                    "execution_time": round(time.time() - started, 3),
                    "memory_usage": 0,
                },
            )
            return {"message": "Stopped successfully"}
        except Exception as e:
            return {"error": str(e)}

    def get_result(self, key: str) -> Dict:
        """Poll for a result. Enforces MAX_EXECUTION_SECONDS."""
        with self.lock:
            if key in self.results:
                return self.results[key]
            if key not in self.processes:
                return {"error": f"'{key}' not found or not running"}
            process = self.processes[key]
            started = self.start_times.get(key, time.time())

        # Still running — has it overstayed its welcome?
        if process.poll() is None:
            elapsed = time.time() - started
            if elapsed > MAX_EXECUTION_SECONDS:
                self._kill_tree(process)
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    stdout, stderr = "", ""
                return self._finalize(
                    key,
                    {
                        "finished": True,
                        "status": "Timeout",
                        "output": stdout or "",
                        "error": (stderr or "")
                        + f"\n⏱️ Killed after {MAX_EXECUTION_SECONDS}s execution limit.",
                        "return_code": -1,
                        "execution_time": round(elapsed, 3),
                        "memory_usage": 0,
                    },
                )
            return {"finished": False}

        # Finished — collect output.
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()

        return_code = process.returncode
        execution_time = time.time() - started

        result = {
            "finished": True,
            "return_code": return_code,
            "execution_time": round(execution_time, 3),
            "memory_usage": 0,
        }
        if return_code == 0:
            result["status"] = "Finished"
            result["output"] = stdout or "✅ Execution completed successfully!"
            result["error"] = stderr or ""
        else:
            result["status"] = "Error"
            result["output"] = stdout or ""
            result["error"] = stderr or f"❌ Process exited with code {return_code}"

        return self._finalize(key, result)

    def running_keys(self, prefix: str = "") -> list[str]:
        """Keys currently running, optionally filtered by a user prefix."""
        with self.lock:
            return [k for k, running in self.running_files.items()
                    if running and k.startswith(prefix)]

    def stop_all(self):
        for key in list(self.processes.keys()):
            self.stop_file(key)


# Singleton instance
runner = CodeRunner()
