# 中国海洋大学西海岸校区 · Minecraft Java 地图生成

用公开地图轮廓生成中国海洋大学西海岸校区的 Minecraft Java 世界（1.21.4，约 1 米 = 1 格，2093×996 格，8253 区块），再按固定规则做对齐、铺装和屋顶统一。不用 AI 推断建筑形状，也不在游戏里一格一格手搭。

两个已生成的世界（在 PCL 实例 `26.2-Fabric 0.19.3` 的 saves 里）：

| 世界文件夹 | 游戏内名 | 内容 |
|---|---|---|
| `OUC-West-Coast-InfoNorth-Sample` | 中国海洋大学西海岸校区（信息北楼小样） | 只改信息北楼一组，其余楼、地形原样 |
| `OUC-West-Coast-AlignedRevision` | 中国海洋大学西海岸校区（对齐修订版） | 全校版，见下 |

## 生成方式

1. **地形与建筑**：Arnis 3.5.0（离线）读 `data/osm-area.xml`（OpenStreetMap 轮廓）生成，local 线性投影，BBOX 为 (35.77065, 120.01335, 35.77960, 120.03655)。建筑资料以 `data/v3-*.geojson` 的 38 个已核对部件为准（学习综合体、海德楼、智慧海洋楼、宿舍、信息北楼），其余楼按 OSM 原轮廓生成。
2. **对齐**：每组楼单独算长度加权主导角，绕组质心旋转，再正交化、取整（`scripts/align_buildings.py`、`scripts/align_all.py`）。Arnis 的 `--rotation` 是转整个世界，各楼角度不同，达不到逐栋对齐，所以对齐在输入数据层做。v3 没覆盖的楼（未来楼、信息南楼等）在 OSM 层转节点（`scripts/make_osm_aligned.py`），不改它们的层数/高度标签。听海苑 5/6/2 号楼是带斜翼的折线楼，主导角是假象（边角支撑度为 0），不旋转，只把近轴边压平。
3. **铺装**（`scripts/paving.py`）：按组从对齐后轮廓派生——楼外扩 2 格基座裙边、两楼面对面间距 ≤15 格时整片通道、≤30 格时各铺 4 格宽步道带、离最近 OSM 公路 ≤25 格时画 4 格宽 L 形步道。只在派生多边形内换草为石砖，保留真草坪、坡地和架空连廊下的空间。
4. **屋顶统一**（`scripts/finish_world.py`，直接读写 Anvil `.mca`）：每栋楼顶层在轮廓内统一成一个方块。目标色默认取该楼顶层最常见的正经屋面块（混凝土/陶土/平滑石/花岗岩楼梯/安山岩系）；羊毛、抛光黑石是 Arnis 调色板噪音，绝不作目标色；石砖/石英收边、玻璃天窗、顶面以上设备原样保留。只改标签统一不了屋顶——Arnis 源码证实平顶 `roof:material=concrete` 会在三种块里随机抽，`roof:colour` 也在最近三个近色里随机抽。
5. **校验**：生成后跑 `scripts/finish_world.py` 收尾，再用 Mojang 官方类全量校验（8253 区块、1.21.4、出生点在），最后打包成 ZIP。

## 本地生成

在 Windows 电脑上（工程根目录即本仓库检出位置 `work\ouc-campus`）：

```cmd
:: 1. 对齐（Python 3.12，需 v3-python-deps 里有 shapely/numpy/PIL）
set PYTHONPATH=C:\...\wo\work\ouc-campus\v3-python-deps
python.exe align_all.py
python.exe make_osm_aligned.py
python.exe make_full_plan.py
:: 2. 生成全校版（计划任务触发，见 scripts\run_full.py；不要挂长 SSH 等结果）
:: 3. 安装进 PCL
python.exe install_aligned_revision.py ..\..\outputs\OUC-West-Coast-Java-AlignedRevision.zip "C:\...\versions\26.2-Fabric 0.19.3\saves"
```

生成依赖本仓库没有的东西（都在电脑工程目录里，不进库）：`arnis-windows.exe`（Arnis 3.5.0）、`CACHE\arnis-tile-cache`（卫星底图缓存）、`v3-python-deps`、`validation\`（Mojang 校验用 JRE/jar）。世界 ZIP（约 8MB）在 `outputs\`，不在本仓库里——本仓库只放脚本、数据和说明，ZIP 每次用上面步骤本地生成。

## 已核实的数据

- 信息北楼三翼对齐后：长翼 X1018–1089, Z540–557（71×17）；主楼 X1050–1098, Z582–611（48×29）；西翼 X1018–1037, Z558–611（19×53）；组角 7.596°。
- 全校共 44 栋（组）对齐：学习综合体 7.52°、海德楼 6.38°、智慧海洋楼 7.27°、信息北楼 7.60°、信息南楼 7.16°、未来楼 6.15°；宿舍大多 0–3°；听海苑 5/6/2 号楼不转（见上）。
- 屋顶：信息北楼长翼红陶土、主楼灰混凝土、西翼浅灰混凝土；其余按实测主导色自动定（见 `data/plan-full.json` 的收尾报告思路与 `scripts/finish_world.py` 的规则）。图书馆中庭采光顶是玻璃顶、坡顶宿舍（花岗岩楼梯）是确定性渲染，两者不动。
- 铺装：全校约 2.8 万格派生铺装（各条目合计，含重叠），收尾共换草 10724 格、清植被 6722、填低洼 18092 格、补基座 9020 格；信息北楼院子 25 格草已全部换成石砖。
- 校验：两版世界均为 8253/8253 区块、1.21.4、出生点 (1361, 711)。

## 已知误差 / 未完全确认的点

- 地图只覆盖 BBOX 以内：南区（综合教学楼、实验楼群、研究生公寓、学 1–8 号楼、珠山餐厅、文体中心等）纬度在 BBOX 以南，不在生成的世界里；要扩进来得换 BBOX 重跑整张图。
- 智慧海洋楼内院是低洼草坪（顶面 Y=-51，比周围低 6 格），未铺——填高会埋一楼入口。
- 听海苑 7 号楼低层屋面（Y=-36）统一时，连带改了约 1000 格高层部分的室内楼板（同色系，从外面看不见）。
- 各楼屋顶目标色是按实测主导色定的，未经逐栋人工确认；浅灰混凝土只是上一轮演示色，最终配色未定。
- 入口位置：OSM 里没有任何 entrance 节点，步道按离楼最近的公路推断。
- 东西向：全校最终配色、宿舍异常角楼的真实朝向，以实地/图纸为准。

## 来源

- 建筑与道路轮廓：OpenStreetMap（`data/osm-area.xml`，ODbL）
- 卫星底图：MapTiler / Sentinel-2（仅作生成时地表分类的底图，不进库）
- 楼层与屋面资料：`data/v3-*.geojson` 各部件的 `source` / `source_urls` 字段
- 生成器：Arnis 3.5.0（github.com/louis-e/arnis，离线运行）

## 目录

- `scripts/`：生成、对齐、铺装、收尾、校验、安装脚本（Python 3.12）
- `data/`：GeoJSON 建筑部件、OSM 数据（原版与对齐版）、收尾计划
