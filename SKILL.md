---
name: network-topology-drawio
description: 生成、重构可编辑 draw.io 网络拓扑/组网图（机房分区、Cisco 图标、设备组框、语义链路、底部三栏），自动导出真实 PNG、看图审查、自行修正迭代。用户要画网络拓扑、机房/数据中心拓扑、搬迁前后对比、方案附图、.drawio 拓扑或沿用拓扑风格时使用。Generate editable proposal-grade topologies with real PNG rendering and mandatory visual iteration.
---

# 网络拓扑：生成 → 渲染 → 看图 → 自行修正

默认交付**可编辑 `.drawio` + 同版本真实 `.png`**。不要求 draw.io 桌面版。**lint 0 错误不等于视觉通过；不能只列改进建议等用户催。**

## 资源与按需读取（节省上下文）

- `scripts/topo_lib.py`：布局/组件/输出 XML，优先 import，不重写 XML 生成器。
- `scripts/topo_check.py`：几何 lint + `.preview.png`（色块近似预览，不是最终图）。
- `scripts/render_drawio.cjs`：官方 draw.io 引擎 + Playwright/Chrome → 真实 PNG 与 `.render.json`。不要每次重写浏览器导出脚本。
- `scripts/drawio_mcp.py`：官方 MCP 打开/编辑/查图标。**不传 `postLayout`、`routing`、`direction`**，避免破坏布局。
- 首次规划/改风格读 `references/style-guide.md`；组件 API 按需查函数，组合不熟才读 `examples/dc_relocation_example.py`，无需每次通读整个库和示例。
- 首次配置导图、故障排查或详细视觉门禁读 `references/rendering.md`；日常按下方命令执行即可。

## 必须执行的工作流

### 1. 事实与备份

提取机房、设备型号/数量/角色/状态、链路两端/条数/速率/介质，以及聚合/主备/集群关系。未提供的信息留待确认；**不编造端口、连接、速率、采购状态或冗余方案**。来源矛盾保留本次口径并提示。已有图先经 MCP `get` 读当前页，修改前备份，不盲目覆盖手工调整。

规划先于坐标：左旧右新，同层对齐；跨楼骨干/ISL 预留独立走线带，不穿服务器接入扇形。前后图保持机房左右顺序和层级含义；搬迁前目标区无已知设备时可缩窄为说明区，不为对称浪费半张纸或填虚构设备。

### 2. 生成与几何检查

生成脚本放任务临时目录，使用 `topo_lib` 组件。新图标先经官方 MCP `search_shapes` 查真实 stencil。**存储、交换机、服务器必须有可识别设备图标，不能只用文字框代替**。图符、物理链路、标签、清单数量一致。

以下 `<skill>` 为当前 skill 根目录，工具调用用绝对路径：

```bash
python3 <skill>/scripts/topo_check.py <图.drawio> --png <临时目录>/图.preview.png
```

修复全部 ERROR 并处理 WARN；近似预览仅用于定位，不能代替下一步。

### 3. 导出实际 PNG（强制）

```bash
node <skill>/scripts/render_drawio.cjs <图.drawio> --overwrite
# 批量复用浏览器，避免反复初始化：
node <skill>/scripts/render_drawio.cjs <搬迁前.drawio> <搬迁后.drawio> --overwrite
```

默认同名 PNG/报告；只有本次明确要替换已有生成物才加 `--overwrite`。首次可运行 `--doctor`；依赖与隐私说明见 `references/rendering.md`。不得依赖其他项目的临时缓存/硬编码路径。

### 4. 看图 → 修正 → 再验证（强制）

**必须用图片查看工具打开真实 PNG**：先全图，再按需放大密集局部；双图还需对照。只读 XML/JSON、只看色块预览、只看局部都不算通过。检查：

- 图标/中文/表格实际加载，无缺图、截断、白屏或多余截图白边。
- 全图尺寸下名称/速率可读；放大字号/图标，不能只提高 DPI。
- 无压字/穿设备；交叉易追踪且不误连，ISL 与接入线分开。
- 无无意义留白/左右失衡；底栏按内容收紧，说明不抢主体，名称不重复堆叠。
- 集群范围、物理互联、复制逻辑不同；Fabric 独立性、条数、状态与来源一致；存储图标为主体、控制器为下级。

发现可修复问题，**自行修改当前页/生成脚本 → lint → 重新导出 → 再看图**；不得停在建议清单。只优化表达，不改变设备/接线事实，事实不清标待确认。每次改图都要刷新 PNG，不能交付旧截图。

初稿后默认最多 **3 轮修正**；通过即停。临时简记“问题→修改→复检”，只保留必要图片/局部/简短日志，不向模型重复灌完整 XML 和长 URL。3 轮仍有关键问题、环境阻断或连续两轮无改善时停止并说明，不能声称已通过。用户要求继续时可再迭代。

### 5. 交付

最终再用官方 MCP 打开 `.drawio`：

```bash
python3 <skill>/scripts/drawio_mcp.py open <图.drawio>
```

长编辑链接写入项目 Markdown 入口，回复只给入口；修改后同步刷新链接（它是快照）。交付 draw.io + PNG、关键改进、验证状态和未补猜项，保留备份。

**降级**：浏览器/依赖/网络阻断时可交付 draw.io 与明确标注的布局预览，但必须写“实际渲染/视觉验证未完成”及原因，不能把 `.preview.png` 改名充当正式 PNG，更不能说已看过最终图。

## 表达约束速记

- 白底浅色分区：绿旧/现网、蓝新/目标、灰闲置；深蓝核心、墨绿汇聚、红安全、灰闲置。
- 默认 10GE 橙、1GE 蓝、未知灰。FC 可沿用来源的 A 蓝/B 橙，必须明确“Fabric + 速率”图例，不得误写以太网速率；ISL 未给速率用灰，距离不是速率。
- 物理线无箭头，N 条画足；仅明确聚合才画聚合椭圆。只说上联设备组就连组框，不猜成员/端口。
- 集群优先范围框、复制用带说明的逻辑虚线，主备另用 HA，勿用完全相同线型混淆。
- 标签放无连线的一侧；胶囊不机械固定上下。存储图标+名称为主、控制器为子，避免重复标题。
- 底部三栏：仅实际出现元素的图例 | 清单/变更表 | 4–6 条说明；末条注明端口与逐端口接线以实施确认为准。

环境：Python 3.8+（近似预览需 Pillow）、Node.js 18+、Playwright + Chrome/Chromium；MCP 用 `npx @drawio/mcp`。完整安装、CLI、自建渲染与缓存规则见 `references/rendering.md`/`.env.example`。不提交浏览器、`node_modules`、大型官方 JS 或项目图纸到 skill 仓库。
