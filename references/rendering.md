# 真实 PNG 导出与自主视觉迭代

## 1. 原理与边界

`render_drawio.cjs` 读取本地 draw.io XML → Playwright 启动无头 Chrome/Chromium → 加载官方 `export3.html` → 调用 `render({xml, format:'png', ...})` → 等待 `#LoadingComplete`、字体/图片 → 按 `getGraphBounds()` 动态截图。默认 DPR=2，输出真实 Cisco stencil、HTML 表格和文字，不是模型重绘，也不是 `topo_check.py` 的色块近似预览。

- 官方 MCP 管编辑/打开/查图标；**它不负责这里的 PNG 导出**。
- 导出器做加载与尺寸检查，**不会理解美观、接线语义或自动修改 XML**。自主视觉迭代由调用 skill 的 agent 看 PNG 后执行，不得把 JSON 报告当视觉审查。
- 默认加载 `https://app.diagrams.net/` 的官方引擎，并非完整离线方案。XML 通过浏览器进程内的 `page.evaluate` 传给引擎，不提交到远程导出 API；但在线页面是远程代码，图中外链图片/字体也可能发起请求。敏感图纸应使用获准的自建实例与已审计资源，不能把“无上传 API”说成绝对无网络风险。
- 不使用第三方在线文件转换服务；不把图纸发给图像生成服务。

## 2. 一次性配置

在 skill 根目录执行（路径有空格时加引号）：

```bash
npm --prefix scripts install
# 有本机 Chrome/Edge 时可直接用；没有浏览器时安装 Playwright Chromium：
npx --prefix scripts playwright install chromium
node scripts/render_drawio.cjs --doctor
```

脚本不会自行安装 npm 依赖或浏览器；按当前环境权限和用户授权配置。`scripts/package.json` 声明 Playwright；`node_modules`、浏览器和大型缓存不进仓库。机器已有受管理的 Playwright 时，可设置 `DRAWIO_PLAYWRIGHT_MODULE` 到该模块目录，避免重复安装。不要硬编码其他任务的 `/tmp/...`、项目名、机器用户名或缓存文件。

浏览器选择：

```bash
node scripts/render_drawio.cjs --doctor --browser chrome
node scripts/render_drawio.cjs a.drawio --browser chrome
node scripts/render_drawio.cjs a.drawio --browser /绝对路径/Chrome
```

可选配置见 skill 根目录 `.env.example`。CLI 参数优先于环境/配置；设置自建实例时使用 `--base-url https://drawio.example/`。只覆写 `.env.example`，不要把本机私有 `.env` 提交进版本控制。

## 3. 日常命令（优先复用，不重写脚本）

```bash
# 输出 a.png 和 a.render.json，已有输出默认拒绝覆盖：
node <skill>/scripts/render_drawio.cjs /项目/a.drawio
# 同一任务修正后的重新导出，明确覆盖生成物：
node <skill>/scripts/render_drawio.cjs /项目/a.drawio --overwrite
# 批量导出，复用浏览器：
node <skill>/scripts/render_drawio.cjs /项目/前.drawio /项目/后.drawio --out-dir /项目/图片 --overwrite
# 指定单张输出和页面（序号从 0 起，也可传 diagram id）：
node <skill>/scripts/render_drawio.cjs a.drawio -o /临时/a.png --page 1
node <skill>/scripts/render_drawio.cjs a.drawio --page diagram-id --scale 1 --dpr 2 --border 20
```

默认首个 diagram，不假定 id 为 `topo`。多页图一次指定一页；若交付多页，逐页导出并逐页审查。脚本应支持 draw.io 原生压缩/未压缩内容，但非 draw.io XML、无效页号/ID 必须报错，不能静默导出错误页面。

- `--scale`：图形几何缩放；`--dpr`：截图像素密度。增大 DPR 只是更清晰，不能解决画布中文字太小。
- `--border`：实际图形边界外的空白，不使用固定的 2460×1550 视口截整页。图题/表格超出边界也要检查。
- `--timeout`：每次页面/渲染等待时限（毫秒，默认 120000）。
- `--report`：单张图指定 JSON 报告路径；默认同名 `.render.json`。
- `--help`：完整参数。`--doctor`：检查依赖/浏览器/资源，不渲染、不安装。
- 非 0 退出码不得报告导出通过；检查报告和 stderr，而不是只判断 PNG 文件存在（可能是旧文件）。失败不应把旧图冒充新结果。

## 4. 官方资源缓存与失败诊断

默认直接加载官方页面。网络慢或资源较大时，可传结构化覆盖目录：

```text
<asset-dir>/
├── js/app.min.js
├── js/export.js
├── js/extensions.min.js
└── ...其他与页面 URL 路径一致的资源
```

```bash
node scripts/render_drawio.cjs a.drawio --asset-dir /受管理的同版本drawio资源
```

只覆盖该目录内存在的对应资源；其他请求仍联网。**`--asset-dir` 不等于完整离线**。同一引擎版本的资源应成套保存；不要混用版本、禁用 extensions、空响应替代加载失败，或把官方大 JS 复制进 skill。缓存来源/版本由维护者确认；渲染失败时先回到官方在线页面排除缓存不匹配。

常见故障：

| 现象 | 处理 |
|---|---|
| 找不到 Playwright | 在 scripts 安装依赖，或设置 `DRAWIO_PLAYWRIGHT_MODULE` |
| 找不到浏览器 | `--doctor` 后指定 `--browser chrome`/绝对路径，或安装 Chromium |
| `render`/`Graph` 超时，JS 语法异常 | 检查网络、代理、资源完整性；大 JS 可能下载不全。不要盲目增加 timeout 掩盖损坏文件 |
| stencil 未加载/图标缺失 | 确认 shape 名来自官方 search_shapes；检查 stencils 请求，排除资源版本混用 |
| 字体回退 | 检查本机中文字体；布局预览字体与浏览器字体是两回事。报告字体警告并人工检查 |
| 输出边缘截断/空白过大 | 读 bounds/像素尺寸，检查页面中的隐藏/越界元素，不能只裁掉被截文字 |
| 导出成功但不好看 | 这是视觉审查任务，不是再改截图参数；修改图纸布局后重新渲染 |

## 5. 视觉门禁与迭代（agent 执行）

**每次最终导出后必须打开真实 PNG 看图。**全图用于判断组织、密度和对比，必要局部用于查标签、桥接交叉、图标/表格；不能只看一小块就宣称全图通过。

### 初检顺序

1. 全图：原图设备是否都在？是否加载失败/缺图标？左右权重、层间距、说明占比、图题和白边是否合理？
2. 文字：在实际交付尺寸下名称/速率是否可读？中文是否正常？表格是否溢出？不要用高清像素数量冒充字号合理。
3. 链路密集区：压字、穿设备、跨区走线、交叉误连、折线绕行、数量、聚合、独立 Fabric 关系。
4. 存储/集群区：存储图标和名称为主、控制器为子组件；集群范围和复制关系不同；资料未确认的物理承载不能画成确定接线。
5. 前后图：机房左右顺序、颜色、编号、设备流向与说明一致；无设备的区域可缩窄但需交代原因。
6. 对照表：图例仅列出现元素；清单数量与图符一致，徽标状态有事实依据；编辑器入口和 PNG 与最终 XML 同版本。

### 判定与自动修正

- **阻断项**：缺图标、截字、压字/穿设备、虚构接线、数量不符、图纸/PNG 不同版本。必须修复，不能写“通过”。
- **可直接改进项**：大面积空白、说明框抢主体、字号太小、存储图标像装饰、重复标题、骨干穿过接入扇形、逻辑/物理关系难分。默认自行修正，不只给建议。
- **需用户确认项**：设备实际来源/状态冲突、存储控制器真实冗余接线、速率/介质/端口缺失。保留来源、标待确认，不为美观改事实。
- 运行最多“初稿 + 3 轮修正”，每轮记录简短差异；连续两轮无改善或遇环境阻断，停止并说明。已通过即停，不能无限美化或无依据声称完美。

可在任务临时目录记录：

```text
轮次 | 图片 | 发现问题 | 修改 | lint/导出/看图结论
0    | a.png | ISL 穿接入扇形 | 下移到独立带 | 待复检
1    | a.png | 无阻断项 | — | lint 0/0；实际 PNG 已查看
```

只向用户汇总最终结论、重要改动、未确认项。无需每轮把图片、完整 XML、浏览器日志和长编辑链接反复塞入模型上下文；但**不得为了省 token 跳过最终看图**。

## 6. 测试与维护

```bash
node --test scripts/test_render_drawio.cjs
node scripts/render_drawio.cjs --doctor
# smoke：真实图、含中文/HTML 表格/Cisco stencil，多页图再测 --page
node scripts/render_drawio.cjs /测试/a.drawio --out-dir /临时/render-smoke --overwrite
```

单测不代表浏览器集成成功。维护渲染器后至少实际导出一张含图标/中文/表格的图并打开 PNG；最好再测批量与非 `topo` 页 ID。报告失败必须清晰可诊断，不默认静默绕过真实引擎验证。
