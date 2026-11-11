# -*- coding: utf-8 -*-
"""
topo_lib —— 生成"方案附图级"网络拓扑 draw.io 文件的小型库。

风格要点（详见 references/style-guide.md）：
  楼宇/机房分区色块 + 左侧分层标签 + Cisco 经典图标 + 虚线设备组框 + 胶囊标签/状态徽标
  + 按链路类型着色的直线连线 + 聚合椭圆 + 底部 图例 / 设备表 / 说明 三栏。

用法：
  from topo_lib import *
  d = Doc(2420, 1580)
  title(d, '主标题', '副标题')
  ...
  d.save('xxx.drawio', '页名')
  check('xxx.drawio', preview_png='xxx.preview.png')   # 几何自检 + 布局预览（纯 Python）
  open_in_drawio('xxx.drawio')                         # 经官方 draw.io MCP 生成编辑器链接

不依赖任何已安装的 draw.io 桌面程序；渲染/编辑交给官方 MCP（npx @drawio/mcp 或 https://mcp.draw.io/mcp）。
"""
import os
import sys
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ 主题常量
FONT = "fontFamily=Microsoft YaHei;"

# kind -> (宽, 高, draw.io stencil)
ICON = {
    'l3':     (64, 64, 'mxgraph.cisco.switches.layer_3_switch'),      # 核心/汇聚三层交换机、多业务网关
    'sw':     (100, 40, 'mxgraph.cisco.switches.workgroup_switch'),   # 数据中心/服务器交换机
    'sw_s':   (90, 34, 'mxgraph.cisco.switches.workgroup_switch'),    # 接入交换机（略小）
    'fw':     (64, 48, 'mxgraph.cisco.security.firewall'),            # 防火墙
    'srv':    (46, 66, 'mxgraph.cisco.servers.fileserver'),           # 服务器 / ESXi 主机
    'router': (64, 44, 'mxgraph.cisco.routers.router'),               # 路由器
    'pc':     (50, 46, 'mxgraph.cisco.computers_and_peripherals.pc'), # 终端
}
# 图例中使用的缩小尺寸
ICON_SMALL = {'l3': (34, 34), 'sw': (56, 22), 'sw_s': (50, 20), 'fw': (36, 27), 'srv': (24, 36),
              'router': (40, 28), 'pc': (30, 28)}

COLOR = dict(
    core='#0B3D91',   # 全院/全网核心（深蓝）
    agg='#117A65',    # 汇聚 / 原有核心降级（墨绿）
    sw='#2471A3',     # 服务器交换机
    sw_s='#5B7DB1',   # 接入交换机
    fw='#C0392B',     # 防火墙（红）
    srv='#1F618D',    # 在网服务器
    idle='#A6ACAF',   # 闲置/下架设备（灰）
    router='#1A5276',
    pc='#566573',
)

# 连线类型
LINK = {
    '10g':  'strokeColor=#E67E22;strokeWidth=2;',                         # 万兆
    '1g':   'strokeColor=#2E86C1;strokeWidth=2;',                         # 千兆
    'x10g': 'strokeColor=#D35400;strokeWidth=3;',                         # 跨楼/骨干万兆（加粗）
    'gen':  'strokeColor=#566573;strokeWidth=2;',                         # 规格未给定的互联
    'ha':   'strokeColor=#27AE60;strokeWidth=2;dashed=1;dashPattern=6 3;', # 主备心跳
    'virt': 'strokeColor=#1B2631;strokeWidth=5;',                         # CSS/IRF/堆叠/虚拟化互联
    'vm':   'strokeColor=#8E44AD;strokeWidth=2.5;dashed=1;dashPattern=8 4;', # 虚拟化集群关系（逻辑）
    'wan':  'strokeColor=#16A085;strokeWidth=2;dashed=1;dashPattern=10 4;',  # 专线/运营商
    'mgmt': 'strokeColor=#95A5A6;strokeWidth=1.5;dashed=1;dashPattern=2 3;', # 管理/带外
}

# 状态徽标 (文字, 颜色)
BADGE_NEW = ('新增', '#E67E22')
BADGE_OLD = ('原有', '#7F8C8D')
BADGE_MOVE = ('迁入', '#8E44AD')
BADGE_DOWN = ('下架', '#566573')
BADGE_PLAN = ('规划', '#2E86C1')

# 分区配色 (标题栏色, 底色)
ZONE = {
    'green':  ('#2E8B57', '#F2FAF4'),   # 旧机房 / 现网
    'blue':   ('#2E6DA4', '#F2F7FC'),   # 新机房 / 目标
    'gray':   ('#7F8C8D', '#F7F8F8'),   # 闲置 / 待拆除
    'orange': ('#CA6F1E', '#FDF6EE'),   # 外网 / DMZ
    'purple': ('#7D3C98', '#F7F2FA'),   # 灾备 / 云
}


def tw(text, cn=12, en=7):
    """估算 11~12px 字号下文本像素宽度（中文 12，ASCII 7）"""
    return sum(cn if ord(ch) > 255 else en for ch in text)


# ------------------------------------------------------------------ 文档
class Doc:
    def __init__(self, W=2420, H=1580):
        self.W, self.H = W, H
        self.cells = []
        self.n = 0

    def _id(self):
        self.n += 1
        return "n%d" % self.n

    def v(self, x, y, w, h, val, style):
        """添加顶点，返回 dict(id,x,y,w,h)，供连线计算锚点"""
        i = self._id()
        self.cells.append(
            '<mxCell id="%s" value=%s style=%s vertex="1" parent="1">'
            '<mxGeometry x="%.1f" y="%.1f" width="%.1f" height="%.1f" as="geometry"/></mxCell>'
            % (i, quoteattr(val), quoteattr(style), x, y, w, h))
        return dict(id=i, x=x, y=y, w=w, h=h)

    def e(self, s, sp, t, tp, link, pts=None):
        """连线：s/t 为顶点，sp/tp 为绝对坐标锚点（落在顶点边框上），pts 为折点"""
        ex, ey = (sp[0] - s['x']) / s['w'], (sp[1] - s['y']) / s['h']
        nx, ny = (tp[0] - t['x']) / t['w'], (tp[1] - t['y']) / t['h']
        style = ("endArrow=none;startArrow=none;html=1;rounded=0;%s"
                 "exitX=%.4f;exitY=%.4f;exitDx=0;exitDy=0;exitPerimeter=0;"
                 "entryX=%.4f;entryY=%.4f;entryDx=0;entryDy=0;entryPerimeter=0;"
                 % (LINK[link], ex, ey, nx, ny))
        arr = ''
        if pts:
            arr = '<Array as="points">%s</Array>' % ''.join('<mxPoint x="%.1f" y="%.1f"/>' % p for p in pts)
        i = self._id()
        self.cells.append(
            '<mxCell id="%s" value="" style=%s edge="1" parent="1" source="%s" target="%s">'
            '<mxGeometry relative="1" as="geometry">%s</mxGeometry></mxCell>'
            % (i, quoteattr(style), s['id'], t['id'], arr))

    def fe(self, p1, p2, link):
        """不挂接顶点的自由线段（图例样例、跨区逻辑线）"""
        style = "endArrow=none;startArrow=none;html=1;rounded=0;" + LINK[link]
        i = self._id()
        self.cells.append(
            '<mxCell id="%s" value="" style=%s edge="1" parent="1">'
            '<mxGeometry relative="1" as="geometry">'
            '<mxPoint x="%.1f" y="%.1f" as="sourcePoint"/><mxPoint x="%.1f" y="%.1f" as="targetPoint"/>'
            '</mxGeometry></mxCell>' % (i, quoteattr(style), p1[0], p1[1], p2[0], p2[1]))

    def save(self, path, name='Page-1'):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        xml = ('<mxfile host="Electron"><diagram id="topo" name=%s>'
               '<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
               'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="%d" pageHeight="%d" '
               'background="#FFFFFF" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>%s'
               '</root></mxGraphModel></diagram></mxfile>'
               % (quoteattr(name), self.W, self.H, ''.join(self.cells)))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(xml)
        return path


# ------------------------------------------------------------------ 基础元素
def text(d, x, y, w, h, val, size=12, color='#1B2631', align='center', bold=False, bg=None, border=None):
    st = "text;html=1;whiteSpace=wrap;verticalAlign=middle;align=%s;fontSize=%d;fontColor=%s;%s%s" % (
        align, size, color, FONT, 'fontStyle=1;' if bold else '')
    if bg:
        st += "fillColor=%s;" % bg
    if border:
        st += "strokeColor=%s;rounded=1;arcSize=20;" % border
    return d.v(x, y, w, h, val, st)


def dev(d, kind, cx, cy, name, sub='', color=None, lab='bottom'):
    """设备图标（以中心点定位）。lab: bottom / left / right —— 有竖向连线穿过时用 left/right"""
    w, h, shape = ICON[kind]
    color = color or COLOR.get(kind, COLOR['sw'])
    val = '<b>%s</b>' % name
    if sub:
        val += '<br><font style="font-size:11px" color="#4D5656">%s</font>' % sub
    if lab == 'left':
        lp = "labelPosition=left;verticalLabelPosition=middle;align=right;verticalAlign=middle;spacingRight=6;"
    elif lab == 'right':
        lp = "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=6;"
    else:
        lp = "labelPosition=center;verticalLabelPosition=bottom;align=center;verticalAlign=top;spacingTop=2;"
    st = ("shape=%s;html=1;pointerEvents=1;dashed=0;fillColor=%s;strokeColor=#FFFFFF;strokeWidth=2;"
          "outlineConnect=0;whiteSpace=nowrap;fontSize=12;fontColor=#1B2631;%s%s" % (shape, color, lp, FONT))
    return d.v(cx - w / 2, cy - h / 2, w, h, val, st)


def pill(d, x, y, label, color, size=11):
    """胶囊标签（设备组名称 / 状态徽标）"""
    w = tw(label) + 20
    return d.v(x, y, w, 22, label, "rounded=1;arcSize=50;fillColor=%s;strokeColor=#FFFFFF;strokeWidth=1;"
               "fontColor=#FFFFFF;fontSize=%d;fontStyle=1;html=1;%s" % (color, size, FONT))


def frame(d, x, y, w, h, color, tag, badge=None, fill='#FFFFFF', bottom=False):
    """虚线圆角设备组框 + 左上胶囊标签 + 右上状态徽标。
    bottom=True 时标签放到下边框（框上方有大量连线进入时使用，避免连线压字）"""
    fr = d.v(x, y, w, h, '', "rounded=1;arcSize=8;fillColor=%s;strokeColor=%s;strokeWidth=1.5;"
             "dashed=1;dashPattern=6 4;html=1;" % (fill, color))
    ty = y + h - 11 if bottom else y - 11
    pill(d, x + 14, ty, tag, color)
    if badge:
        pill(d, x + w - tw(badge[0]) - 34, ty, badge[0], badge[1])
    return fr


def pair(d, kind, cxs, cy, names, subs, color, tag, tagc, badge=None, link=True, lab='side', lw=110,
         tag_bottom=False):
    """成对设备（虚拟化/堆叠/CSS/主备）：两台设备 + 设备组框 + 可选成员互联粗线。
    lab='side' 时 #1 标签在左、#2 标签在右（默认，便于上下方向连线不压字）；
    lab='bottom' 时标签在图标下方（仅上方有连线时用）。
    tag_bottom=True 把组标签/徽标放到下边框（连线从上方进入成员时使用）。返回 (frame, [dev1, dev2])"""
    w, h, _ = ICON[kind]
    if lab == 'side':
        fx, fx2 = cxs[0] - w / 2 - lw - 16, cxs[-1] + w / 2 + lw + 16
        fy, fy2 = cy - h / 2 - 28, cy + h / 2 + 18
        labs = ['left', 'right']
    else:
        fx, fx2 = cxs[0] - 90, cxs[-1] + 90
        fy, fy2 = cy - h / 2 - 28, cy + h / 2 + 50
        labs = ['bottom'] * len(cxs)
    if tag_bottom and lab != 'side':
        fy2 += 10
    fr = frame(d, fx, fy, fx2 - fx, fy2 - fy, tagc, tag, badge, bottom=tag_bottom)
    devs = [dev(d, kind, cx, cy, names[i], subs[i], color, labs[i % len(labs)]) for i, cx in enumerate(cxs)]
    if link and len(devs) == 2:
        d.e(devs[0], (cxs[0] + w / 2, cy), devs[1], (cxs[1] - w / 2, cy), 'virt')
    return fr, devs


def agg_h(d, x, yc, spread):
    """竖椭圆：套住水平方向的并行链路，表示链路聚合"""
    d.v(x - 8, yc - spread / 2 - 9, 16, spread + 18, '', "ellipse;fillColor=none;strokeColor=#1B2631;strokeWidth=1.5;")


def agg_v(d, xc, y, spread):
    """横椭圆：套住垂直方向的并行链路"""
    d.v(xc - spread / 2 - 9, y - 7, spread + 18, 14, '', "ellipse;fillColor=none;strokeColor=#1B2631;strokeWidth=1.5;")


def parallel_h(d, left, right, yc, n=4, gap=10, link='x10g', mark=True):
    """left 右边框 → right 左边框 的 n 条水平并行链路（聚合），两端加聚合椭圆。返回线段中点 x"""
    x1, x2 = left['x'] + left['w'], right['x']
    ys = [yc + (k - (n - 1) / 2) * gap for k in range(n)]
    for y in ys:
        d.e(left, (x1, y), right, (x2, y), link)
    if mark and n > 1:
        agg_h(d, x1 + 26, yc, (n - 1) * gap)
        agg_h(d, x2 - 26, yc, (n - 1) * gap)
    return (x1 + x2) / 2


def parallel_v(d, upper, lower, xc, n=2, gap=20, link='10g', mark=True, lower_anchor=None):
    """lower 顶边 → upper 底边 的 n 条竖直并行链路；聚合椭圆放在靠 upper 一端"""
    y_top = upper['y'] + upper['h']
    y_bot = lower['y'] if lower_anchor is None else lower_anchor
    xs = [xc + (k - (n - 1) / 2) * gap for k in range(n)]
    for x in xs:
        d.e(lower, (x, y_bot), upper, (x, y_top), link)
    if mark and n > 1:
        agg_v(d, xc, y_top + 25, (n - 1) * gap)


def dual_home(d, servers, sw_a, sw_b, link='10g', offset=9):
    """每台服务器 2 条链路分别接入 sw_a / sw_b（双归属）。入点在交换机底边均匀分布"""
    n = len(servers)
    for i, s in enumerate(servers):
        cx, top = s['x'] + s['w'] / 2, s['y']
        for j, sw in enumerate((sw_a, sw_b)):
            ex = sw['x'] + sw['w'] * (i + 1) / (n + 1)
            d.e(s, (cx + (offset if j else -offset), top), sw, (ex, sw['y'] + sw['h']), link)


def fan_in(d, servers, sw, per=2, link='10g', offset=8):
    """每台服务器 per 条链路接入同一台交换机（单归属多链路），入点按顺序分布，互不交叉"""
    total = len(servers) * per
    k = 0
    for s in servers:
        cx, top = s['x'] + s['w'] / 2, s['y']
        for j in range(per):
            dx = (j - (per - 1) / 2) * 2 * offset
            ex = sw['x'] + sw['w'] * (k + 1) / (total + 1)
            d.e(s, (cx + dx, top), sw, (ex, sw['y'] + sw['h']), link)
            k += 1


# ------------------------------------------------------------------ 版面元素
def zone(d, x, y, w, h, title_, sub='', color='blue'):
    """楼宇/机房分区：浅色底 + 实色标题栏（40px）"""
    hc, bg = ZONE[color] if color in ZONE else color
    d.v(x, y, w, h, '', "rounded=0;fillColor=%s;strokeColor=%s;strokeWidth=2;html=1;" % (bg, hc))
    val = '<b>%s</b>' % title_
    if sub:
        val += '&nbsp;&nbsp;<font style="font-size:13px">%s</font>' % sub
    return d.v(x, y, w, 40, val, "rounded=0;fillColor=%s;strokeColor=%s;fontColor=#FFFFFF;fontSize=18;align=left;"
               "spacingLeft=16;verticalAlign=middle;html=1;%s" % (hc, hc, FONT))


def title(d, t, sub=''):
    """页面主标题（30px 粗体居中）+ 蓝色下划线 + 副标题"""
    d.v(0, 22, d.W, 44, t, "text;html=1;align=center;verticalAlign=middle;fontSize=30;fontStyle=1;"
        "fontColor=#1B2631;" + FONT)
    d.v(d.W / 2 - 320, 68, 640, 4, '', "rounded=0;fillColor=#2E6DA4;strokeColor=none;")
    if sub:
        d.v(0, 74, d.W, 26, sub, "text;html=1;align=center;verticalAlign=middle;fontSize=13;fontColor=#5D6D7E;" + FONT)


def layers(d, rows, x=40, w=80):
    """左侧竖排分层标签：rows=[(y1, y2, '核心/汇聚层'), ...]"""
    for y1, y2, lab in rows:
        d.v(x, y1, w, y2 - y1, '<br>'.join(lab), "rounded=1;arcSize=12;fillColor=#EBF0F5;strokeColor=#AEB6BF;"
            "fontColor=#34495E;fontSize=14;fontStyle=1;whiteSpace=wrap;html=1;" + FONT)


def note_box(d, x, y, w, h, val):
    """虚线灰色说明框（不画进本图但需交代的内容，如存储/FC 见独立拓扑）"""
    return d.v(x, y, w, h, val, "rounded=1;arcSize=12;dashed=1;fillColor=#FBFCFC;strokeColor=#99A3A4;"
               "fontColor=#566573;fontSize=11;html=1;whiteSpace=wrap;" + FONT)


def downlink_note(d, x, y, w, val, align='center'):
    """灰色小字 '▼ 下联 xxx（本图略）'，交代范围外的下游"""
    return text(d, x, y, w, 40 if '<br>' in val else 20, val, 11, '#7B7D7D', align)


def legend(d, x, y, w, h, devs, links):
    """图例：左列设备，右列连线。
    devs 项: (kind, 说明, 颜色) | ('frame', 说明) | ('badge', 说明, [BADGE_NEW, ...])
    links 项: (LINK 键, 说明) | ('agg', '链路聚合')"""
    d.v(x, y, w, h, '', "rounded=1;arcSize=2;fillColor=#FFFFFF;strokeColor=#AEB6BF;strokeWidth=1.5;")
    text(d, x + 16, y + 10, 200, 26, '图&nbsp;&nbsp;例', 16, '#1B2631', 'left', True)
    row = (h - 60) / max(len(devs), len(links))
    for i, it in enumerate(devs):
        cy = y + 50 + row * i + row / 2
        cx = x + 54
        if it[0] == 'frame':
            d.v(cx - 28, cy - 14, 56, 28, '', "rounded=1;arcSize=12;fillColor=#FFFFFF;strokeColor=#2471A3;"
                "strokeWidth=1.5;dashed=1;dashPattern=6 4;")
        elif it[0] == 'badge':
            bx = x + 24
            for b in it[2]:
                pill(d, bx, cy - 11, b[0], b[1])
                bx += tw(b[0]) + 26
            text(d, bx + 4, cy - 12, w / 2 - (bx - x) - 10, 24, it[1], 12, '#1B2631', 'left')
            continue
        else:
            kw, kh = ICON_SMALL[it[0]]
            d.v(cx - kw / 2, cy - kh / 2, kw, kh, '', "shape=%s;html=1;pointerEvents=1;fillColor=%s;"
                "strokeColor=#FFFFFF;strokeWidth=1;outlineConnect=0;" % (ICON[it[0]][2], it[2]))
        text(d, x + 96, cy - 12, w / 2 - 100, 24, it[1], 12, '#1B2631', 'left')
    lx = x + w / 2 + 10
    for i, it in enumerate(links):
        cy = y + 50 + row * i + row / 2
        if it[0] == 'agg':
            d.fe((lx, cy - 5), (lx + 64, cy - 5), 'gen')
            d.fe((lx, cy + 5), (lx + 64, cy + 5), 'gen')
            d.v(lx + 25, cy - 13, 14, 26, '', "ellipse;fillColor=none;strokeColor=#1B2631;strokeWidth=1.5;")
        else:
            d.fe((lx, cy), (lx + 64, cy), it[0])
        text(d, lx + 76, cy - 12, w / 2 - 90, 24, it[1], 12, '#1B2631', 'left')


def table(d, x, y, w, h, caption, head, rows):
    """HTML 表格面板（设备清单 / 变更说明）。单元格可含 <b style="color:..."> 着色"""
    th = ''.join('<th style="background:#2E6DA4;color:#FFFFFF;padding:6px 6px;border:1px solid #AEB6BF;">%s</th>' % c
                 for c in head)
    body = ''
    for k, r in enumerate(rows):
        bg = '#F4F7FA' if k % 2 else '#FFFFFF'
        body += '<tr style="background:%s">%s</tr>' % (bg, ''.join(
            '<td style="padding:5px 6px;border:1px solid #AEB6BF;">%s</td>' % c for c in r))
    html = ('<div style="font-size:15px;font-weight:bold;color:#1B2631;margin:0 0 8px 2px;">%s</div>'
            '<table style="border-collapse:collapse;width:100%%;font-size:12px;color:#1B2631;">'
            '<tr>%s</tr>%s</table>' % (caption, th, body))
    d.v(x, y, w, h, '', "rounded=1;arcSize=2;fillColor=#FFFFFF;strokeColor=#AEB6BF;strokeWidth=1.5;")
    d.v(x + 14, y + 10, w - 28, h - 20, html, "text;html=1;whiteSpace=wrap;overflow=fill;align=left;"
        "verticalAlign=top;fontSize=12;" + FONT)


def notes(d, x, y, w, h, items, caption='说&nbsp;&nbsp;明'):
    """编号说明面板"""
    html = '<div style="font-size:15px;font-weight:bold;margin-bottom:8px;">%s</div>' % caption + ''.join(
        '<div style="margin:0 0 7px 0;line-height:1.5;">%d. %s</div>' % (i + 1, s) for i, s in enumerate(items))
    d.v(x, y, w, h, '', "rounded=1;arcSize=2;fillColor=#FFFFFF;strokeColor=#AEB6BF;strokeWidth=1.5;")
    d.v(x + 16, y + 10, w - 32, h - 20, html, "text;html=1;whiteSpace=wrap;overflow=fill;align=left;"
        "verticalAlign=top;fontSize=12;fontColor=#1B2631;" + FONT)


def bottom_panels(d, y, h, legend_args, table_args, notes_items, x0=150, x1=2370):
    """底部三栏：图例 | 表格 | 说明，宽度约 700 / 800 / 余量"""
    gap = 30
    lw, tw_ = 700, 800
    legend(d, x0, y, lw, h, *legend_args)
    table(d, x0 + lw + gap, y, tw_, h, *table_args)
    nx = x0 + lw + gap + tw_ + gap
    notes(d, nx, y, x1 - nx, h, notes_items)


# ------------------------------------------------------------------ 自检 / MCP
def check(path, preview_png=None, page=0, verbose=True):
    """几何自检（连线压字、重叠、留白）；可选输出 Pillow 布局预览图（问题处洋红框标出）。返回问题列表"""
    sys.path.insert(0, HERE)
    import topo_check
    issues = topo_check.lint(path, page)
    if verbose:
        for lv, cat, msg, _ in issues:
            print('[%s] %s：%s' % (lv, cat, msg))
        print('%s 检查完成：%d 个问题' % (os.path.basename(path), len(issues)))
    if preview_png:
        topo_check.preview(path, preview_png, page, mark=[i[3] for i in issues if i[0] == 'ERROR'])
    return issues


def open_in_drawio(path, browser=False, hosted=False, lightbox=False):
    """经官方 draw.io MCP 生成（并可自动打开）编辑器链接。绝不使用 postLayout/routing"""
    sys.path.insert(0, HERE)
    import drawio_mcp
    drawio_mcp.load_dotenv()
    return drawio_mcp.open_link(path, lightbox=lightbox, browser=browser, hosted=hosted)


if __name__ == '__main__':
    print(__doc__)
