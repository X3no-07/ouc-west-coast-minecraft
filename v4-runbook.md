# v4 构建与验证 runbook（PC 端，Windows cmd）

> 规矩：短 SSH 分次取结果、结果存 PC 文件、不要挂长连接；saves 里的 v3/v2/v1 与
> 所有旧世界一律不动；**不要导入 PCL**；不要发建设指挥部邮件。
> VM 干跑先行：build_v4.py / verify_v4.py 支持 `V4_WORLD` 环境变量覆盖世界目录。

## 0. 前置检查（PC）

```cmd
cd /d C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus
dir staging-v3
py --version
```

## 1. 取 v4 文件到 PC

从 VM 传 `build_v4.py`、`verify_v4.py`、`v4-build-data.json`、
`v4-checklist.md`、`v4-runbook.md`、`README-v4-draft.md` 到
`work\ouc-campus\`。`finish_world.py`、`validate_mojang.py`、
`v3-build-report.json` 已在 PC 上（v3 构建时用的同一份）。

## 2. VM 干跑（先做，VM 上）

```bash
cd ~/workspace/minecraft-ouc
cp -r OUC-West-Coast-v3 /tmp/v4-work/staging-v4-dryrun  # 已有 v3 解压副本时用
python3 build_v4.py   # V4_WORLD=/tmp/v4-work/staging-v4-dryrun/OUC-West-Coast-v3
python3 verify_v4.py  # 同上 V4_WORLD
```

干跑目的：语法、逻辑、BFS、计数；`validate_mojang.py` 在 VM 上因无 jpype
会报错记录，不影响干跑其余项。

## 3. PC 构建（v3 副本 → staging-v4）

```cmd
cd /d C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus
xcopy /E /I /Y staging-v3 staging-v4
ren staging-v4\OUC-West-Coast-v3 OUC-West-Coast-v4
py build_v4.py
```

构建约几分钟。输出 `v4-build-report.json`（改动格数、入口、院落计数）。
若报错，把报错全文存文件再回 VM 看。

## 4. PC 验证

```cmd
py verify_v4.py
```

含 `validate_mojang.py` 全量校验（8253 区块，Java 1.21.4；区块数若变以实测为准）。
输出 `v4-verify-report.json`。五项验收：

1. 信息楼南北外观：屋顶浅灰、无红陶土、杂物清零；外墙浅灰面 + 深灰竖框 +
   浅蓝玻璃；底层幕墙玻璃。
2. 两处主入口：门块正确 + 朝向对；台阶 8 级、挑檐 9×5；BFS 院子→室内走通。
3. 院落白楼：新建存在、白墙 + 横向窗带 + 平顶浅灰、东面深橡木门、BFS 走通。
4. 院落铺装：蓝步道十字 + 石砖广场、黑混凝土清零（院落带内）。
5. 回归：v3 三扇北楼门 + 准星门仍在；Mojang 校验 8253/8253。

## 5. 打包 ZIP

```cmd
cd /d C:\Users\lenovo\Documents\Codex\2026-11-25\wo
powershell -Command "Compress-Archive -Path work\ouc-campus\staging-v4\OUC-West-Coast-v4 -DestinationPath outputs\OUC-West-Coast-v4.zip -Force"
dir outputs\OUC-West-Coast-v4.zip
```

再把 ZIP 拷回 VM：`~/workspace/minecraft-ouc/OUC-West-Coast-v4.zip`。

## 6. GitHub（备好，不推）

v4 文件放进 `~/workspace/minecraft-ouc/github-repo/`，与 v3 的 25 个文件合并成
一份推送清单（见 `v4-push-paths.txt`）。**先不要推**，等主聊天通知（批准卡
超时过两次，要用户在场时再推）。世界 ZIP 二进制不推；不要动另外三个库。
