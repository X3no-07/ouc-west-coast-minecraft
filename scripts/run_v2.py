"""Runner for the v2 full-school build, executed on the PC by a
scheduled task (pythonw, no window).  All output goes to run_v2.log
next to this file; the build script itself prints progress there."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY312 = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe"
LOG = HERE / "run_v2.log"

def main():
    with LOG.open("w", encoding="utf-8") as log:
        log.write("run_v2 start\n")
        log.flush()
        import os
        env = dict(os.environ)
        env["PYTHONPATH"] = str(HERE / "v3-python-deps")
        result = subprocess.run(
            [PY312, str(HERE / "build_v2.py")],
            cwd=str(HERE), env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        log.write(f"run_v2 exit={result.returncode}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
