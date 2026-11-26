"""Re-run the finish pass on an already-built world (after fixing
finish_world.py), then re-validate, re-render the preview and re-package.
Usage: redo_finish.py <run_dir>
The run dir is the landmark-revision-* dir under work/ouc-campus.
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_aligned_revision as bar  # noqa: E402
from finish_world import finish  # noqa: E402
from rules_preview import oblique_view, read_world  # noqa: E402
from validate_mojang import main as validate_vanilla  # noqa: E402


def main():
    run = Path(sys.argv[1])
    features = bar.load_features()
    world = run / "world" / "Arnis World 1"
    plan = json.loads((bar.WORK / "plan-full.json").read_text(encoding="utf-8"))
    report = finish(world, plan)
    print("Finish pass:", json.dumps(report, ensure_ascii=False)[:600], "...")
    (run / "finish-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    surface = read_world(world)
    preview = run / bar.PREVIEW_NAME
    oblique_view(world, surface, preview)
    validate_vanilla(world)
    archive = bar.package(run, world, features)
    outputs = bar.WORK.parents[1] / "outputs"
    shutil.copy2(archive, outputs / bar.ARCHIVE_NAME)
    shutil.copy2(preview, outputs / bar.PREVIEW_NAME)
    print(f"Verified archive: {outputs / bar.ARCHIVE_NAME}", flush=True)


if __name__ == "__main__":
    main()
