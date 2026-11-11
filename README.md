# network-topology-drawio

用统一的"方案附图级"风格生成可编辑的 draw.io 网络拓扑图：楼宇/机房分区、Cisco 经典图标、虚拟化/主备设备组框、按速率着色的连线、链路聚合椭圆、底部图例 + 设备表 + 说明。

打开、预览、编辑、查找图形全部通过**官方 draw.io MCP** 完成（`npx @drawio/mcp` 或 `https://mcp.draw.io/mcp`），**不依赖本机安装的 draw.io 桌面程序**。

## 目录结构

```
network-topology-drawio/
├── SKILL.md                          # Agent 使用说明（触发条件、工作流程、速记规则）
├── references/style-guide.md         # 详细视觉规范 + MCP 使用约定
├── scripts/
│   ├── topo_lib.py                   # 绘图库（样式常量、组件、check()、open_in_drawio()）
│   ├── topo_check.py                 # 几何自检 + Pillow 布局预览（替代桌面版导出 PNG）
│   └── drawio_mcp.py                 # 官方 draw.io MCP 极简客户端（stdio / 托管 HTTP）
├── examples/dc_relocation_example.py # 参考实现：数据中心区搬迁前/后两张图
├── .env.example                      # 可选配置模板
└── .gitignore
```

## 为什么版面仍由 Python 生成

本风格依赖精确坐标、对称版式、直线连线与聚合标记。MCP 的 `postLayout`(ELK)/`routing`(libavoid) 会重排设备或把直线改成折线，所以：
- **生成**：`topo_lib.py` 输出确定性的 draw.io XML；
- **打开/编辑**：交给官方 MCP（实测往返后几何坐标 0 变化）；
- **自检**：`topo_check.py` 做碰撞检查 + 预览图（MCP 不提供 PNG 导出）。

## 环境要求

- Python 3.8+（生成与 lint 仅标准库；预览图需要 `pip install pillow`）
- Node.js 18+，`npx @drawio/mcp`（首次联网下载后可走 npm 缓存）
- 打开编辑器链接需能访问 `app.diagrams.net`，或用 `DRAWIO_BASE_URL` 指向自建 draw.io

可选配置：`copy .env.example .env` 后按需填写。

## 在 Agent 中挂载官方 MCP（推荐）

Warp：`~/.warp/.mcp.json`

```json
{
  "mcpServers": {
    "drawio": { "command": "npx", "args": ["-y", "@drawio/mcp"] },
    "drawio-hosted": { "url": "https://mcp.draw.io/mcp" }
  }
}
```

其他客户端（Claude Code / Codex / VS Code / Cursor）配置方式见 <https://www.drawio.com/mcp/>。未挂载时，skill 会改用 `scripts/drawio_mcp.py` 调用同一套官方工具。

## 快速使用

```
python examples/dc_relocation_example.py <输出目录> --check --open   # 生成示例 + 自检预览 + MCP 编辑器链接
python scripts/topo_check.py a.drawio --png a.preview.png            # 自检（退出码 1 表示有 ERROR）
python scripts/topo_check.py a.drawio --png part.png --crop 0 0 1200 800
python scripts/drawio_mcp.py open a.drawio [--browser] [--hosted]    # 打开到 draw.io 编辑器
python scripts/drawio_mcp.py search cisco wireless access point      # 查官方图形 style
python scripts/drawio_mcp.py pages a.drawio | get a.drawio 0 | set a.drawio 0 page.xml
```

在自己的脚本中：

```python
import sys; sys.path.insert(0, r'<本目录>/scripts')
from topo_lib import *
d = Doc(2420, 1580)
title(d, '某某组网图', '副标题')
zone(d, 150, 110, 1380, 1010, '某机房', '（角色）', 'green')
core, _ = pair(d, 'l3', [740, 900], 270, ['S7706 #1', 'S7706 #2'], ['核心'] * 2,
               COLOR['core'], 'CSS 集群 · 核心', COLOR['core'], BADGE_OLD)
d.save('某某组网图.drawio', '页1')
check('某某组网图.drawio', preview_png='某某组网图.preview.png')
print(open_in_drawio('某某组网图.drawio'))
```

## 安装为 Warp Skill

整个目录放在 `~/.warp/skills/network-topology-drawio/`（当前位置），或复制到项目内的 `.warp/skills/` 下。

## 修改风格

先改 `references/style-guide.md`，再同步修改 `scripts/topo_lib.py` 顶部的 `COLOR` / `LINK` / `ZONE` / `ICON` 常量，最后运行示例并 `--check` 确认。
