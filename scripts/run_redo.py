"""Runner for redo_finish.py, executed on the PC by a scheduled task."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY312 = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe"
LOG = HERE / "run_redo.log"
RUN_DIR = HERE / "landmark-revision-h3ay7v86"

def main():
    with LOG.open("w", encoding="utf-8") as log:
        log.write("run_redo start\n")
        log.flush()
        import os
        env = dict(os.environ)
        env["PYTHONPATH"] = str(HERE / "v3-python-deps")
        result = subprocess.run(
            [PY312, str(HERE / "redo_finish.py"), str(RUN_DIR)],
            cwd=str(HERE), env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        log.write(f"run_redo exit={result.returncode}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
