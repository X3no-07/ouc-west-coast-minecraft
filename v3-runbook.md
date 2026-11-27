# v3 PC 执行手册（隧道恢复后按序执行）

前置：确认到电脑的 Tailscale 隧道通（`ssh_pc.sh "echo OK"` 有回显）。
若不通：请吕总把 Muse App 切到前台、确认电脑醒着且 Tailscale 连着，再重试。

工作目录（PC）：`C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus\`
世界副本：`work\ouc-campus\staging-v3\OUC-West-Coast-v3\`（v3 的编辑底本，saves 里的 v2 不动）

## 1. 上传文件（VM → PC）
```bash
cd ~/workspace/minecraft-ouc
# 先备份 PC 上的原文件（anvil.py / finish_world.py 已在 PC 上备份为 .bak-v2，
# 若上一步没跑成，先在 PC 上执行备份命令再传）
~/workspace/pc-link/scp_pc.sh anvil.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/anvil.py"
~/workspace/pc-link/scp_pc.sh finish_world.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/finish_world.py"
~/workspace/pc-link/scp_pc.sh test_anvil.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/test_anvil.py"
~/workspace/pc-link/scp_pc.sh build_v3.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/build_v3.py"
~/workspace/pc-link/scp_pc.sh check_v3_ground.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/check_v3_ground.py"
~/workspace/pc-link/scp_pc.sh verify_v3.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/verify_v3.py"
~/workspace/pc-link/scp_pc.sh v3-build-data.json "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/v3-build-data.json"
~/workspace/pc-link/scp_pc.sh v3-osm-missing.json "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/v3-osm-missing.json"
~/workspace/pc-link/scp_pc.sh compare_osm_plan.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/compare_osm_plan.py"
~/workspace/pc-link/scp_pc.sh make_v3_data.py "lenovo@100.92.221.109:C:/Users/lenovo/Documents/Codex/2026-11-25/wo/work/ouc-campus/make_v3_data.py"
```
注意：PC 上的 python 是哪个？v2 脚本在 PC 上跑过（`python` 或 `py`）。先用
`ssh_pc.sh "python --version"` 确认；若无 python，用 v2 当时用的解释器路径。

## 2. 地面核查（PC 上跑，只读世界，生成 v3-ground-fixes.json）
```cmd
cd C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus
python check_v3_ground.py > v3-ground-check.log 2>&1
```
看输出：`(944,694)` 的 Sentinel class（应为 50）、各杂斑的 fix 材料。
把 `v3-ground-check.log`、`v3-ground-check.json`、`v3-ground-fixes.json` 取回 VM 检查。
要点：杂斑默认草地；贴着建筑裙边/广场的才铺石砖；若某杂斑实际是广场/铺装，
在 v3-ground-fixes.json 里把那一项的 material 改成 stone_bricks 再继续。

## 3. 构建 v3（PC 上跑，改 staging-v3 副本）
```cmd
cd C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus
python build_v3.py > v3-build.log 2>&1
```
看输出：`BUILD DONE: N cells changed`，并检查 `v3-build-report.json`（门的数量、
补门坐标、缺楼是否已建）。把 `v3-build.log` 与 `v3-build-report.json` 取回 VM。

## 4. 验证（PC 上跑，含原版 1.21.4 全量校验）
```cmd
cd C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus
python verify_v3.py > v3-verify.log 2>&1
```
看输出：`Vanilla decoded 8,253 of 8,253 chunks`、五项验收、BFS 结果。
把 `v3-verify.log` 与 `v3-verify-report.json` 取回 VM。
若 validate_mojang 报错（区块数变化）：以实测为准，在汇报里写清实际数字。

## 5. 打包（PC 上）
```cmd
cd C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus\staging-v3
powershell -Command "Compress-Archive -Path OUC-West-Coast-v3 -DestinationPath ..\outputs\OUC-West-Coast-v3.zip -Force"
dir ..\outputs\OUC-West-Coast-v3.zip
```
把 ZIP 取回 VM：`~/workspace/minecraft-ouc/OUC-West-Coast-v3.zip`。
核对：ZIP 内顶层是 `OUC-West-Coast-v3/level.dat` + `region/`，不要多一层文件夹。

## 6. GitHub 推送（VM 上做）
- 推送内容：`anvil.py`、`finish_world.py`、`test_anvil.py`、`build_v3.py`、
  `check_v3_ground.py`、`verify_v3.py`、`v3-build-data.json`、`v3-osm-missing.json`、
  `compare_osm_plan.py`、`make_v3_data.py`、更新后的 `README.md`（v3 章节）、
  `v3-build-report.json`、`v3-verify-report.json`（可选，作为构建记录）。
- 不推：世界 ZIP 二进制、`.mca`、其他三个库（LifeLogRPG / ramp-q / voice-minutes）。
- 用 GitHub 连接器（OAuth）推送到 `X3no-07/ouc-west-coast-minecraft` 的 main 分支。

## 7. 汇报
按 v3-build-report.json + v3-verify-report.json 写最终汇报（新世界名、ZIP 位置与大小、
校验结果、五项验收、坐标表、未找到的资料清单、三维查询草稿、全校门的抽查结果）。
**不要导入 PCL**，等吕总说导入再说。
