import subprocess
import os
import time
import psutil
from typing import Dict, Optional
import threading

class CodeRunner:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running_files: Dict[str, bool] = {}
        self.start_times: Dict[str, float] = {}
        self.results: Dict[str, Dict] = {}  # Store results for completed processes
        self.lock = threading.Lock()

    def run_file(self, filename: str, upload_dir: str) -> Dict:
        """Run a Python file and return the result"""
        file_path = os.path.join(upload_dir, filename)
        
        print(f"🔍 run_file: {file_path}")
        
        if not os.path.exists(file_path):
            return {"error": f"File '{filename}' not found at {file_path}"}
        
        # Check file size
        file_size = os.path.getsize(file_path)
        print(f"📏 File size: {file_size} bytes")
        if file_size == 0:
            return {"error": f"File '{filename}' is empty (0 bytes)"}
        
        # Check if already running
        with self.lock:
            if filename in self.running_files and self.running_files[filename]:
                return {"error": f"File '{filename}' is already running"}
        
        try:
            # Start the process
            start_time = time.time()
            process = subprocess.Popen(
                ["python", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=upload_dir,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            with self.lock:
                self.processes[filename] = process
                self.running_files[filename] = True
                self.start_times[filename] = start_time
                # Clear any old result
                if filename in self.results:
                    del self.results[filename]
            
            print(f"✅ Process started with PID: {process.pid}")
            return {
                "running": True,
                "message": f"File '{filename}' started successfully"
            }
            
        except Exception as e:
            with self.lock:
                self.running_files[filename] = False
            return {"error": f"Failed to run: {str(e)}"}

    def stop_file(self, filename: str) -> Dict:
        """Stop a running file"""
        with self.lock:
            if filename not in self.processes:
                # Maybe it's already finished
                if filename in self.results:
                    return {"message": f"File '{filename}' already finished"}
                return {"error": f"File '{filename}' is not running"}
            process = self.processes[filename]
        
        try:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except:
                    pass
            parent.kill()
            
            with self.lock:
                self.running_files[filename] = False
                # Store a stopped result
                self.results[filename] = {
                    "finished": True,
                    "status": "Stopped",
                    "output": "🛑 Program stopped by user",
                    "error": "",
                    "return_code": -1,
                    "execution_time": time.time() - self.start_times.get(filename, time.time()),
                    "memory_usage": 0
                }
                if filename in self.processes:
                    del self.processes[filename]
                if filename in self.start_times:
                    del self.start_times[filename]
            
            return {"message": f"File '{filename}' stopped successfully"}
        except Exception as e:
            return {"error": str(e)}

    def get_result(self, filename: str) -> Dict:
        """Get the result of a completed file"""
        print(f"🔍 get_result for: {filename}")
        with self.lock:
            # Check if we already have a stored result
            if filename in self.results:
                print(f"✅ Returning stored result for {filename}")
                return self.results[filename]
            
            # Check if the process is still running
            if filename not in self.processes:
                print(f"❌ File '{filename}' not in processes")
                return {"error": f"File '{filename}' not found or not running"}
            
            process = self.processes[filename]
        
        # Check if process is still running
        if process.poll() is None:
            print(f"⏳ Process {process.pid} is still running")
            return {"finished": False}
        
        print(f"✅ Process {process.pid} has finished")
        
        # Process finished - get output
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        
        return_code = process.returncode
        execution_time = time.time() - self.start_times.get(filename, time.time())
        
        # Build result
        result = {
            "finished": True,
            "return_code": return_code,
            "execution_time": round(execution_time, 3),
            "memory_usage": 0
        }
        
        if return_code == 0:
            result["status"] = "Finished"
            result["output"] = stdout or "✅ Execution completed successfully!"
            result["error"] = stderr or ""
        else:
            result["status"] = "Error"
            result["output"] = stdout or ""
            result["error"] = stderr or f"❌ Process exited with code {return_code}"
        
        # Store result for future requests
        with self.lock:
            self.results[filename] = result
            # Clean up process tracking
            if filename in self.processes:
                del self.processes[filename]
            if filename in self.running_files:
                del self.running_files[filename]
            if filename in self.start_times:
                del self.start_times[filename]
        
        print(f"✅ Result stored for {filename}")
        return result

    def stop_all(self):
        """Stop all running processes"""
        with self.lock:
            filenames = list(self.processes.keys())
            for filename in filenames:
                self.stop_file(filename)

# Singleton instance
runner = CodeRunner()