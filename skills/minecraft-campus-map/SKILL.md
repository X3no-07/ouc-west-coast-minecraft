# Minecraft 校园地图

## 接活与定规

- 先问清用户要什么：只问“怎么做”就只给可照抄的说明，说“做并导入”或“直接给我做完”才生成、验证、导入并报告新世界在单人游戏列表里的名字。

- 定死生成铁律：用公开地图、校方图纸和固定规则批量生成，不用 AI 推断建筑形状，不在游戏里逐块手搭。

- 每个新版本用新名字，保留全部旧存档和游戏进度，不覆盖、不删除旧世界。

- 不确定的地方标明未核实或估算，不当定论讲。照片和全景里看不清的总层数、屋顶面、背面、东西向一律写清看不清什么。

- 版本号等改完、验证通过再定。不要先占版本号，也不要用选项卡片让用户点选，有选择直接在聊天里问或直接做决定。

## 找真实资料

- 先查有没有可下载的三维数据：实景网格、点云、3D Tiles、Cesium 场景、glb、obj、las。没有就如实说没有，不要强行交差。

- 没有三维数据就用实拍图和全景代替，只做示意级，不做度量级。楼高按层数估算，屋顶细节有限。

- 首选校方官网校园 VR 全景。打开后默认是另一个校区，必须点底部切换到目标校区。点底部只切换下方缩略图分组，不换全景。点某组名第一次可能先打开该组首个点位，第二次才展开点位列表，悬停组名保持列表展开后才能点到具体点位。

- 全景点位很多是室内，室内看不到外立面。每个点位记下外墙颜色和材质、屋顶形式和颜色、窗列样式、主入口形式与台阶、院落和地面铺装，看不清的写明，不要猜。

- 再找校方建设网单体页、校方新闻、本地新闻、餐饮页配图、航拍报道。视频与社交平台用哔哩哔哩、抖音、小红书、微博、知乎、贴吧、微信公众号搜图文与短视频，记链接、作者、发布时间和画面实际内容。

- 排除错图：他校区的校门、他城市的广场、疑似他校区的楼、AI 生成的航拍一律单列，不可用。

## 生成与修正

- 底图用 Arnis 离线生成：OSM 数据加 local 线性投影，约 1 米等于 1 格，目标 Java 1.21.4。先记下 BBOX、格数、区块数、出生点、创造模式、允许命令，之后每版都对同一套参数。

- 对齐用逐栋规则，不用全局旋转。Arnis 的 rotation 参数转整个世界，各楼角度不同，不能代替逐栋对齐。每组楼单独算主导角再正交化。

- 屋顶不要只改标签统一。Arnis 平顶时屋顶材质和颜色会随机抽，统一屋顶要靠生成后按轮廓加屋顶层限定的确定性收尾规则。

- 编辑区块要保留方块完整状态。只写方块名不写属性会丢楼梯、门、活板门状态，读块只看原始 region 数据会读不到同一进程内先写步骤的编辑。写块与读块都要走修过的读写层，验证时按当前脚下高度贴地找地面。

- 每版只改该版的范围，改完立即验证。信息楼重做先核对主楼与低翼关系、院落、屋顶颜色、窗列、主入口。补门先确认准星指的楼和那面墙，门外门槛、步道、首层地板接通，全校逐栋开门时用 BFS 实测门外到门内走通。门槛高差过大的坡地宿舍不要硬开。

- 地面杂斑先查生成规则再重铺。先确认该点的分类与成因，再按真实用途重铺，不要只看颜色猜。

- 篮球场按实际位置和朝向做边线、中线、中圈、罚球区和篮架。东门按门洞能走通、前后接道路做，高度无官方出处就标估算。

- 道路重铺要分清车道、人行道、路缘、广场。车道不要用纯黑大色块，加车道线与斑马线，路缘用石砖或安山岩收边，人行道统一浅灰石板，路口、斜坡、楼前台阶接得上。

## 验证与交付

- 每版必跑三层验证：读块验收改动、步行连通 BFS、世界完整性。出生点、创造模式、允许命令、DataVersion、region 文件数逐项核对。

- Mojang 官方全量校验只在用户电脑上跑。校验脚本依赖 jpype，只有电脑的 Python 有，虚拟机没有 Java 也没有校验用的 JRE 与 jar。虚拟机上装 jpype 也跑不起来，缺文件就是缺文件。

- 虚拟机上的替代验证是自写验证脚本加 nbtlib 独立读回 level.dat。Mojang 校验没跑就如实说没跑，等隧道恢复后在电脑上补跑。

- 把新世界 LastPlayed 刷成当前时间，让它排在单人游戏列表最前。装前装后比对全部旧世界 level.dat 哈希，确认一个未动。

- 交付一份完整的新存档 ZIP。顶层即世界文件夹加 level.dat 加 region 文件夹，无多余文件夹层。核对 ZIP 内文件数、大小、SHA256，解压抽查 level.dat 能读出世界名与出生点。

- 汇报给用户五项：新世界名、ZIP 位置与大小、校验结果、逐栋改动表、游戏坐标。另附未找到与看不清的清单。

## 推 GitHub 与导入 PCL

- 世界 ZIP 是二进制，不进库。只推脚本、数据、报告、核对表、资源表和 README。

- 推之前核对清单：全部文件都在、全部 UTF-8、远端 head 与同步记录一致、新路径确认远端不存在、旧路径确认无他人改动、无冲突。

- 批准卡有效期约 30 分钟。用户必须在场并在 30 分钟内点批准，超时作废就等用户说再推，不要无指令反复重试。

- 推成功后到 GitHub 网页上核实 head 变了、文件可读，再更新同步记录文件。失败的推送不推进记录。

- 导入 PCL 时先确认 saves 里没有同名文件夹，有就停下来汇报，不要覆盖。拷文件夹、比对旧世界哈希、刷 LastPlayed、读 level.dat 验证，提醒用户退出重进一次单人游戏列表。

## 远程操作

- 到用户电脑走 Tailscale 隧道加 SSH。计划任务触发后立即断开，结果一律存电脑上的文件，再用短 SSH 连接分次取回。不要挂长连接等结果。

- 电脑上新建计划任务一律用 pythonw.exe 无窗口启动。命令行建的任务默认带仅交流电时启动条件，笔记本用电池时任务不真正执行，建任务改用 XML 导入并关掉电池条件。

- 隧道规律：手机 App 切后台约 3 分钟后平台挂起网络、隧道断。回前台约 15 秒内恢复。隧道断了就停手，不要反复撞墙，等用户确认电脑醒着、Tailscale 连着、App 在前台后再续跑。

- 干跑可以在虚拟机上先跑通。虚拟机有正式版世界 ZIP 副本时，构建、验证、打包都能在虚拟机上做，只剩 Mojang 官方校验与导入 PCL 必须等隧道。

## 出图

- 从真实世界文件渲染每个地方的图。用读块工具直接读 region 文件的 NBT，按方块类型上色，不要示意图、不要手画、不要 AI 生成。

- 每处一张图，重点建筑再加斜视图。俯视图取每列最高实心方块，北在上方，带北向箭头。斜视图按真实方块逐层分色，屋顶带、窗带、百叶带、墙身、基座各是什么方块就画什么颜色。

- 每张图角落标注地点名、游戏坐标范围和来源世界。正式版 ZIP 出来后核对它的 region 文件与干跑世界逐文件 SHA256 一致，不一致就用正式版重出一遍。

- 图上印明这是世界文件渲染图，不是游戏内截图。俯视图看不清立面细节要如实说，斜视图补不上的也写清。

## Available connectors

- [GitHub](/opt/hatch/connectors/github/CONNECTOR.md) for pushing scripts, data, reports and checklists to the public repo and verifying the remote head.

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [校园 VR 全景](https://www.kuleiman.com/165316/index.html) for per building exteriors from 360 degree photos. Carry the navigation notes from the find real sources section into the browser task and verify each point by its scene title after the click.

- [校方建设网](https://xhaxq.ouc.edu.cn/) for project pages with photos and floor areas per building and the campus master plan.

- [哔哩哔哩](https://www.bilibili.com/) for dorm and campus walkthrough videos. Search by campus name plus building name and read titles, descriptions, covers and comments.

## Alternatives for better results

- 拿不到三维数据时，把全景核对与网上实拍结合起来互相印证，同一处外观有两个来源对上才算核实。

- 找不到照片的楼不要停下来等，先按全景与规则改能改的，找不到的单列清单，等用户或新来源出现再补。

- 干跑先在虚拟机上跑通再上电脑，隧道断了也不丢进度，恢复后按续跑手册接着做。
