---
name: network-topology-drawio
description: 按固定的"方案附图级"风格生成可编辑的 draw.io 网络拓扑图 / 组网图（楼宇机房分区、Cisco 图标、虚拟化/主备设备组框、按速率着色连线、链路聚合椭圆、底部图例+设备表+说明），并通过官方 draw.io MCP（npx @drawio/mcp / https://mcp.draw.io/mcp）打开、预览、编辑与查找图形。凡是用户要画网络拓扑、组网图、机房/数据中心拓扑、搬迁前后对比图、改造方案附图、.drawio 拓扑，或提到"沿用之前的拓扑风格"，都应使用本 skill，即使没有明确说 draw.io。Generate editable draw.io network topology diagrams in a consistent proposal-grade style using the official draw.io MCP.
---

# 网络拓扑图（draw.io）方案附图风格 · 官方 MCP 版

把用户提供的组网描述生成**可编辑的 `.drawio` 文件**，风格统一、像真实拓扑而不是示意图，适合直接作为方案附件给客户讲解。全流程不依赖本机安装的 draw.io 桌面程序。

## 分工（为什么这样设计）

- **版面由本 skill 的 Python 库精确生成**（`scripts/topo_lib.py`）。本风格的价值在于精确坐标、对称版式、直线连线与聚合标记，这些靠确定性代码最稳定；MCP 的自动布局做不到同样效果。
- **官方 draw.io MCP 负责打开 / 预览 / 编辑 / 查找图形**：
  - `open_drawio_xml`（本地 `npx @drawio/mcp`）或 `create_diagram`（托管 `https://mcp.draw.io/mcp`）：把生成的 XML 打开到 draw.io 编辑器，交给用户查看与微调。已验证往返后几何坐标完全不变。
  - `search_shapes`：需要新设备图标时查官方 style 字符串。
  - `list_pages` / `get_page` / `set_page`：对已有 `.drawio`（含用户手工改过的）做按页读取与回写。
- **自检由 `scripts/topo_check.py` 完成**（纯 Python + Pillow）：几何碰撞检查 + 布局预览图。MCP 不提供导出 PNG，这一步替代了以前依赖桌面版导出的自检。

**禁止**向 MCP 传 `postLayout`（ELK 会重排全部设备）、`routing`（libavoid 会把直线改成正交折线）、`direction`。这三个参数会直接破坏本风格。

## 资源

- 详细视觉规范：`references/style-guide.md`（颜色、尺寸、线型、版式坐标、检查清单、MCP 使用约定）。首次使用或调整风格时阅读。
- 绘图库：`scripts/topo_lib.py`（样式常量、组件函数、`check()`、`open_in_drawio()`），直接 import，不要重新手写 XML。
- 自检：`scripts/topo_check.py`。
- MCP 客户端：`scripts/drawio_mcp.py`（环境里未挂载 draw.io MCP 工具时，用它调用同一套官方工具）。
- 完整参考实现：`examples/dc_relocation_example.py`（医院数据中心区搬迁前/后两张图，覆盖全部组件）。动手前先通读。

## 工作流程

1. **梳理事实清单**（先于画图）
   逐条提取：机房/楼宇、每台设备（型号、数量、角色、新增/原有/迁移状态）、每条链路（两端、条数、速率、介质、是否聚合）、虚拟化/堆叠/主备/集群关系、明确排除不画的内容。资料没给的信息（端口号、逐端口接线、速率、厂商、新增与否）记为"未提供"，**不要补全猜测**——这是给客户的正式材料，编造的细节比留白危害大。描述矛盾时以用户"最新确认"为准；关键信息缺失且影响画法时再问。

2. **规划版面**
   每个机房一个分区；改造/搬迁类遵循**左旧右新**，前后两张图分区位置一致。纵向分层（核心/汇聚 → 安全 → 服务器交换 → 计算），左侧加分层标签。套用 style-guide 第 11 节模板定坐标；成对设备间距 160，服务器间距 160。

3. **写生成脚本**（放临时目录，如 `%TEMP%\<项目>_topo\gen.py`，不要放进用户交付目录）
   ```python
   import sys; sys.path.insert(0, r'<skill 目录>/scripts')
   from topo_lib import *
   d = Doc(2420, 1580)
   title(d, '标题', '副标题'); layers(d, ROWS)
   zone(d, ...); pair(d, ...); parallel_h(d, ...); dual_home(d, ...)
   bottom_panels(d, 1160, 380, legend_args, table_args, notes_items)
   d.save(r'<用户目录>\<标题>.drawio', '页名')
   ```
   需要库里没有的图标时，先用 MCP `search_shapes`（或 `python scripts/drawio_mcp.py search cisco wireless ap`）取官方 style，再加入 `ICON`。

4. **自检并迭代**（不可省略）
   `python scripts/topo_check.py <file.drawio> --png <临时目录>/x.preview.png`，然后：
   - 修复全部 `[ERROR]`（连线压字、穿过设备、文字重叠、文字压图标），处理 `[WARN]`（留白失衡、超出页面）。
   - 查看预览 PNG（问题处有洋红框），确认整体排版、对称和留白；必要时用 `--crop` 局部放大。
   - 改坐标重新生成，直到 0 错误、版面干净。预览是近似渲染（图标显示为色块），用于判断布局，不代表最终观感。

5. **用官方 MCP 打开给用户确认**
   - 已挂载 MCP 工具：调用 `open_drawio_xml`，`content` 传整个 `.drawio` 文件内容，只用默认参数（可选 `lightbox`）。
   - 未挂载：`python scripts/drawio_mcp.py open <file.drawio>`（加 `--browser` 自动打开浏览器，`--hosted` 走托管服务器）。
   把返回的 draw.io 编辑器链接给用户；最终文件仍是本地 `.drawio`。

6. **修改已有图**：用户在 draw.io 里改过文件后再提修改时，先 `get_page` 读取当前页，基于现状修改，再 `set_page` 回写（或重新运行生成脚本，取决于改动范围），然后重复第 4 步。

7. **交付说明**：告诉用户文件位置、图面组织方式，并**列出所有按"不编造"处理的点**（规格未知用灰线、连到设备组框、未标新增的设备、说明框里的内容），请其确认。

## 关键风格规则（速记）

- 颜色语义固定：深蓝=全网核心，墨绿=汇聚/原核心降级，红=防火墙，灰=闲置/下架；分区绿=旧/现网，蓝=新/目标，灰=闲置。
- 同型号不同角色用 **颜色 + 组框胶囊标签 + 状态徽标** 三重区分。
- 连线全部直线无箭头；速率决定颜色（10GE 橙、1GE 蓝、跨楼骨干深橙加粗、未知规格灰）；并行链路画足条数并加聚合椭圆。
- 有竖向连线穿过的设备，标签放左右两侧；组框上方有连线进入时，胶囊标签放下边框（`bottom=True` / `tag_bottom=True`）。
- 资料只说"上联某虚拟化组"时，线连到组框而非某台成员。
- 资料给出的数字在图形、标注、说明三处一致。
- 底部三栏：图例（只列出现的元素）| 设备清单或变更说明 | 编号说明（末条注明端口与逐端口接线以实施确认为准）。

## 环境

- Python 3.8+（生成与 lint 仅用标准库；预览图需 Pillow）。
- Node.js 18+ 与 `npx @drawio/mcp`（本地 MCP，可缓存离线使用；打开编辑器链接需能访问 app.diagrams.net 或 `DRAWIO_BASE_URL` 指定的自建实例）；或使用托管 `https://mcp.draw.io/mcp`。
- 可选配置见 `.env.example`（`DRAWIO_MCP_CMD`、`DRAWIO_MCP_URL`、`DRAWIO_BASE_URL`、`PREVIEW_FONT`）。
