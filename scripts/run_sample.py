"""Runner for the info-north sample build, executed on the PC by a
scheduled task (pythonw, no window).  All output goes to run_sample.log
next to this file; the build script itself prints progress there."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY312 = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe"
LOG = HERE / "run_sample.log"

def main():
    with LOG.open("w", encoding="utf-8") as log:
        log.write("run_sample start\n")
        log.flush()
        import os
        env = dict(os.environ)
        env["PYTHONPATH"] = str(HERE / "v3-python-deps")
        result = subprocess.run(
            [PY312, str(HERE / "build_info_north_sample.py")],
            cwd=str(HERE), env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        log.write(f"run_sample exit={result.returncode}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
