import json
r = json.load(open("v3-build-report.json", encoding="utf-8"))
print("doors:", len([d for d in r["door_sweep"] if d.get("door")]))
for d in r["door_sweep"]:
    print(repr(d["name"]), d.get("door") or d.get("reason"))
