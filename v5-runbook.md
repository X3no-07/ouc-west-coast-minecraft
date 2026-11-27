# 下一版（内部 v5）续跑手册 — 隧道恢复后用

状态：2026-11-27，VM 干跑已完成并验证通过（55/55），**PC 正式构建还没跑**——隧道断了。
不要对外宣称版本号；等主聊天验收后才定名交付。不要导入 PCL，不要推 GitHub，不要发邮件。

## 已完成（VM 上，不依赖隧道）

- `build_v5.py`、`verify_v5.py`、`v5-build-data.json` 写好，见 `~/workspace/minecraft-ouc/`。
- 干跑：把 v4 世界拷到 `/tmp/v5-work/staging-v5/OUC-West-Coast-v5`，跑构建 + 验证。
  - 构建：144,347 格改动，50.5 秒；验证：**55/55 通过**（`v5-verify-report.json`）。
  - 干跑中修掉的 3 个真 bug：① 浩海广场重铺盖掉了斜路 1292068339 的车道——广场重铺改跳灰/白混凝土；
    ② 望海餐厅北面玻璃湾循环被注释吞掉（`bay_glass` 只有 36，应为 279）——已修，干跑重跑后 279；
    ③ 验证脚本自己的取样问题（植被算顶层、BFS 从门洞正中出发会站到梁上、2 号楼窗多为活板门）。
- GitHub 待推文件已备好放进 `~/workspace/minecraft-ouc/github-repo/`：
  `scripts/build_v5.py`、`scripts/verify_v5.py`、`data/v5-build-data.json`、
  `data/v5-build-report.json`、`data/v5-verify-report.json`（这两份报告是**干跑**的，PC 正式构建后要换成 PC 的）、
  `v5-panorama-checklist.md`、`v5-resources.md`、`v5-resources-round2.md`。
  先不要推，等主聊天通知。

## 隧道恢复后（按顺序，每步短 SSH，结果存 PC 文件）

1. 测隧道：`~/workspace/pc-link/ssh_pc.sh 'echo TUNNEL_OK'`。不通就停，不要反复撞。
2. 传脚本与数据到 PC（`~/workspace/pc-link/scp_pc.sh`，每次约 30 秒）：
   `build_v5.py`、`verify_v5.py`、`v5-build-data.json`、`v3-build-data.json`、
   `plan-v2.json`、`build_v4.py`、`build_v3.py`、`verify_v3.py`、
   `finish_world.py`、`anvil.py` → PC `C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus\`
   （PC 上已有 v4 的一份，覆盖成 VM 这份——干跑用的就是这份）。
3. PC 上建 staging-v5：把 `work\ouc-campus\staging-v4\OUC-West-Coast-v4` 整个拷成
   `work\ouc-campus\staging-v5\OUC-West-Coast-v5`（不要动 staging-v4 和 saves 里的旧世界）。
4. PC 上跑构建（`py` 3.12，不要用 `python` 3.8）：
   `cd work\ouc-campus && py build_v5.py`（约 1 分钟，改动应与干跑接近：约 144,000 格）。
5. PC 上跑 Mojang 全量校验：`py validate_mojang.py staging-v5\OUC-West-Coast-v5`
   （世界路径是位置参数；要 jpype，只在 `py` 里有），预期 8253 区块、Java 1.21.4。
6. PC 上跑读块验证：`py verify_v5.py`（它默认读 `WORK/staging-v5/OUC-West-Coast-v5`，
   即脚本所在目录下的 staging-v5），预期 55/55。
7. 打包：把 `staging-v5\OUC-West-Coast-v5` 整个打 ZIP 到 `outputs\OUC-West-Coast-v5.zip`，
   用 `scp_pc.sh` 拷回 VM 的 `~/workspace/minecraft-ouc/`（约 8 MB）。
8. 把 PC 产出的 `v5-build-report.json`、`v5-verify-report.json` 拷回 VM，覆盖
   `github-repo/data/` 里的干跑版。
9. 回报主聊天“下一版已完成待验收”：新世界名、ZIP 位置与大小、Mojang 校验结果、
   逐栋改动表（全景点位/来源、改了什么、哪些是估算）、游戏坐标、未找到/看不清清单、
   GitHub 待推文件清单。**不要对外宣称是 v5**。

## 关键坐标（验收用）

- 学习综合体东主入口门 (1258,-45,696) 朝东，大台阶 X1259–1268、Z688–708（10 级、中间 3 列白混凝土坡道）
- 听海苑宿舍：棕/奶油网格+蓝玻璃窗、底层深棕、屋顶红陶土；听海餐厅 (1182–1232, 292–348) 上层深海军蓝百叶、下层灰石柱玻璃门、东面外挂白楼梯到 2 楼门 (1232,-39,301)
- 望海餐厅 (584–635, 299–350)：奶油古典立面、红坡顶、三角楣、南面双门 (608/609,-28,350)、北面蓝玻璃湾 Z298
- 工程楼/食工楼（无名楼 1524352144，推断同一栋）：西面拱门 (1011,-40,505)，8 级台阶向西到路
- 浩海广场 (1259–1340, 640–760)：浅米色石板、中央草坪床、红色雕塑组（柱在 1305,700）
- 足球场 (679–749, 250–361)：绿草+白线+红跑道+两端球门；篮球场两区红边+泛光灯+深绿围栏
- 东门：柱顶平滑石帽、梁上浅色牌匾带+石顶、两侧围墙收口+人行小门 (1636,-51,740) 与 (1636,-51,758)、门前浅米色铺装
- 道路：全校灰混凝土车道+白虚线+石砖路缘+浅灰人行道，31 处斑马线

## 未找到/看不清（不要编，汇报里写清楚）

- 东门建成照片全网没找到；7 米是用户提供的，标估算
- 工程楼单体外景照片、材料楼任何外观没找到；工程楼=食工楼同一栋是推断，未经校方确认
- 博士后公寓、山海佳苑（北区）无法对应到世界里具体楼栋，未单独改
- 荷花塘在世界里不存在（水体扫描：水都在东侧海里），木栈道桥没建
- 会议中心无可对应轮廓，没单独建；“I ❤️ OUC”牌与“1924/2023/中国海洋大学”文字做不出，只做了红色雕塑块示意
- 学习综合体东立面上层内收，幕墙只在低层是整面玻璃；宿舍屋顶红瓦按航拍补齐，标估算
