# network-topology-drawio

用统一的"方案附图级"风格生成可编辑的 draw.io 网络拓扑图：楼宇/机房分区、Cisco 经典图标、虚拟化/主备设备组框、按速率着色的连线、链路聚合椭圆、底部图例 + 设备表 + 说明。

打开、编辑、查图形通过**官方 draw.io MCP**（`npx @drawio/mcp` 或 `https://mcp.draw.io/mcp`）；真实 PNG 通过**官方渲染引擎 + Playwright/Chrome** 导出。**不依赖 draw.io 桌面程序**。Agent 必须执行“生成 → lint → 实际 PNG → 看图 → 自行修正 → 重新验证”，不能把“0 碰撞”当视觉通过。

## 目录结构

```
network-topology-drawio/
├── SKILL.md                          # Agent 使用说明（触发条件、工作流程、速记规则）
├── references/style-guide.md         # 详细视觉规范 + MCP 使用约定
├── references/rendering.md           # 真实 PNG 导出、环境排错、视觉门禁与迭代
├── scripts/
│   ├── topo_lib.py                   # 绘图库（样式常量、组件、check()、open_in_drawio()）
│   ├── topo_check.py                 # 几何自检 + 近似布局预览（不是最终图）
│   ├── render_drawio.cjs             # 批量真实 PNG 导出 + JSON 报告
│   ├── test_render_drawio.cjs        # 无浏览器的导出器单元测试
│   ├── package.json                 # Playwright 依赖
│   └── drawio_mcp.py                 # 官方 draw.io MCP 极简客户端（stdio / 托管 HTTP）
├── examples/dc_relocation_example.py # 参考实现：数据中心区搬迁前/后两张图
├── .env.example                      # 可选配置模板
└── .gitignore
```

## 为什么版面仍由 Python 生成

本风格依赖精确坐标、对称版式、直线连线与聚合标记。MCP 的 `postLayout`(ELK)/`routing`(libavoid) 会重排设备或把直线改成折线，所以：
- **生成**：`topo_lib.py` 输出确定性的 draw.io XML；
- **打开/编辑**：交给官方 MCP（实测往返后几何坐标 0 变化）；
- **几何自检**：`topo_check.py` 做碰撞检查 + 色块近似预览；
- **实际导图**：`render_drawio.cjs` 使用 draw.io 渲染真实图标/HTML 表格，不使用远程导出 API；
- **视觉复检**：Agent 打开真实 PNG 审查，发现可修复问题自行调整，再 lint/导出/看图，最多 3 轮修正。图形事实不得为美观而改变。

## 环境要求

- Python 3.8+（生成与 lint 仅标准库；预览图需要 `pip install pillow`）
- Node.js 18+，`npx @drawio/mcp`（首次联网下载后可走 npm 缓存）
- PNG：`npm --prefix scripts install` 安装 Playwright；可使用现有 Chrome，或 `npx --prefix scripts playwright install chromium`
- `node scripts/render_drawio.cjs --doctor` 诊断；依赖不会由脚本自动安装
- 编辑器链接和默认 PNG 渲染需访问 `app.diagrams.net`；自建渲染使用 `--base-url` / `DRAWIO_RENDER_BASE_URL`
- PNG 配置、受管理资源覆盖与隐私边界详见 [references/rendering.md](references/rendering.md)

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
python scripts/topo_check.py a.drawio --png a.preview.png            # 几何自检（退出码 1 表示有 ERROR）
node scripts/render_drawio.cjs a.drawio --overwrite                  # 真实 PNG + .render.json
node scripts/render_drawio.cjs 前.drawio 后.drawio --overwrite       # 批量，复用浏览器
node --test scripts/test_render_drawio.cjs                          # 导出器单测
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

## 安装与复用

整个目录放入支持 Agent Skills 的客户端发现目录，例如 `~/.agents/skills/network-topology-drawio/`；Pi 支持该位置。也可按客户端约定放入项目 `.agents/skills/` 或 Warp skills 目录。活动 Pi 会话修改后可 `/reload` 重新发现。

日常只需读 `SKILL.md` 并按命令复用脚本；首次配置/失败时再读 `references/rendering.md`，不重写浏览器导出代码，不依赖任何具体项目的临时脚本。最终交付可编辑图、真实 PNG、简短验证及待确认说明；渲染不可用必须如实降级。

## 修改风格

先改 `references/style-guide.md`，再同步修改 `scripts/topo_lib.py` 顶部的 `COLOR` / `LINK` / `ZONE` / `ICON` 常量，最后运行示例、几何检查、实际 PNG 导出并打开看图确认；维护导出器还需运行单元测试和浏览器 smoke 测试。
