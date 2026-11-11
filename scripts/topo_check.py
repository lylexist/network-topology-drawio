# -*- coding: utf-8 -*-
"""
topo_check —— 不依赖 draw.io 桌面版的拓扑图自检工具（纯 Python + 可选 Pillow）。

1) lint：解析 .drawio，按几何关系检查
   - 连线压字（连线穿过设备标签 / 胶囊标签 / 标注文字）
   - 连线穿过非端点设备图标
   - 文字与文字、文字与图标重叠
   - 元素超出页面
   - 分区内左右留白失衡（提示）
2) preview：用 Pillow 画出近似布局图（图标以色块表示），供 Agent 查看排版、留白与碰撞。
   预览不是像素级还原，最终效果以 draw.io（MCP 打开的编辑器）为准。

命令行：
  python topo_check.py a.drawio [--page 0] [--png out.png] [--scale 1.0] [--crop X1 Y1 X2 Y2] [--quiet]
退出码：存在 ERROR 时为 1。
"""
import base64
import html as htmlmod
import math
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

# ------------------------------------------------------------------ 字体（仅字体文件，非可执行程序）
def _load_dotenv():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    if v.strip():
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
FONT_CANDIDATES = [
    os.environ.get('PREVIEW_FONT', ''),
    r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyh.ttf', r'C:\Windows\Fonts\simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]
BOLD_CANDIDATES = [os.environ.get('PREVIEW_FONT_BOLD', ''), r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyhbd.ttf']
_font_cache = {}


def _font(size, bold=False):
    key = (int(size), bold)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    try:
        from PIL import ImageFont
        for p in (BOLD_CANDIDATES if bold else []) + FONT_CANDIDATES:
            if p and os.path.isfile(p):
                f = ImageFont.truetype(p, int(size))
                break
    except Exception:
        f = None
    _font_cache[key] = f
    return f


def text_w(s, size, bold=False):
    f = _font(size, bold)
    if f is not None:
        try:
            return f.getlength(s)
        except Exception:
            pass
    w = sum(12 if ord(ch) > 255 else 7 for ch in s) * size / 12.0
    return w * (1.06 if bold else 1)


# ------------------------------------------------------------------ 解析
def pstyle(s):
    d = {}
    for i, tok in enumerate((s or '').split(';')):
        if not tok:
            continue
        if '=' in tok:
            k, v = tok.split('=', 1)
            d[k] = v
        else:
            d[tok] = '1'
            if i == 0:
                d['_base'] = tok
    return d


def _inflate(txt):
    raw = zlib.decompress(base64.b64decode(txt), -15).decode('utf-8')
    return urllib.parse.unquote(raw)


def load_model(path, page=0):
    root = ET.parse(path).getroot()
    if root.tag == 'mxGraphModel':
        return root
    diagrams = root.findall('diagram')
    dg = diagrams[page if isinstance(page, int) else 0]
    m = dg.find('mxGraphModel')
    if m is None:
        m = ET.fromstring(_inflate(dg.text.strip()))
    return m


def html_lines(value, base_size, base_bold=False):
    """把 HTML 标签值拆成 [(文本, 字号, 粗体, 颜色)]"""
    if value is None or value == '':
        return []
    v = value.replace('\n', '<br>')
    v = re.sub(r'(?i)</t[dh]>', ' │ ', v)
    v = re.sub(r'(?i)</(tr|div|p|li|table)>|<br\s*/?>', '\n', v)
    out = []
    for raw in v.split('\n'):
        m = re.search(r'font-size:\s*(\d+)px', raw)
        size = int(m.group(1)) if m else base_size
        bold = base_bold or bool(re.search(r'(?i)<b[\s>]|font-weight:\s*bold', raw))
        c = re.search(r'color[=:]\s*"?(#[0-9A-Fa-f]{6})', raw)
        t = htmlmod.unescape(re.sub(r'<[^>]+>', '', raw)).strip()
        if t:
            out.append((t, size, bold, c.group(1) if c else None))
    return out


class Cell:
    __slots__ = ('id', 'idx', 'vertex', 'edge', 'style', 'value', 'x', 'y', 'w', 'h', 'kind', 'src', 'tgt',
                 'pts', 'sp', 'tp', 'lines', 'tbox', 'parent')


def parse(path, page=0):
    model = load_model(path, page)
    pw = float(model.get('pageWidth', 0) or 0)
    ph = float(model.get('pageHeight', 0) or 0)
    cells, order = {}, []
    for idx, c in enumerate(model.iter('mxCell')):
        o = Cell()
        o.id, o.idx = c.get('id'), idx
        o.vertex, o.edge = c.get('vertex') == '1', c.get('edge') == '1'
        o.style = pstyle(c.get('style'))
        o.value = c.get('value') or ''
        o.parent, o.src, o.tgt = c.get('parent'), c.get('source'), c.get('target')
        o.x = o.y = o.w = o.h = 0.0
        o.pts, o.sp, o.tp = [], None, None
        g = c.find('mxGeometry')
        if g is not None:
            o.x, o.y = float(g.get('x', 0) or 0), float(g.get('y', 0) or 0)
            o.w, o.h = float(g.get('width', 0) or 0), float(g.get('height', 0) or 0)
            for p in g.iter('mxPoint'):
                pt = (float(p.get('x', 0) or 0), float(p.get('y', 0) or 0))
                if p.get('as') == 'sourcePoint':
                    o.sp = pt
                elif p.get('as') == 'targetPoint':
                    o.tp = pt
                else:
                    o.pts.append(pt)
        cells[o.id] = o
        order.append(o)
    # 绝对坐标（容器内子元素）
    for o in order:
        p = cells.get(o.parent)
        while p is not None and p.vertex:
            o.x += p.x
            o.y += p.y
            p = cells.get(p.parent)
    for o in order:
        if o.vertex:
            classify(o)
    return cells, order, pw, ph


def classify(o):
    s = o.style
    fs = float(s.get('fontSize', 12))
    bold = s.get('fontStyle', '0') in ('1', '3', '5', '7')
    o.lines = html_lines(o.value, fs, bold)
    if 'shape' in s and s['shape'].startswith('mxgraph.'):
        o.kind = 'icon'
    elif s.get('_base') == 'ellipse':
        o.kind = 'mark'
    elif s.get('_base') == 'text':
        o.kind = 'panel' if s.get('overflow') == 'fill' else 'text'
    elif not o.lines:
        o.kind = 'frame' if s.get('dashed') == '1' else 'box'
    elif s.get('arcSize') == '50':
        o.kind = 'pill'
    else:
        o.kind = 'label'   # 分区标题栏、说明框等带文字的矩形
    o.tbox = text_box(o) if o.kind in ('icon', 'text', 'pill', 'label') and o.lines else None


def text_box(o):
    s = o.style
    lw = 0.0
    lh = 0.0
    lines = []
    maxw = o.w - 4 if s.get('whiteSpace') == 'wrap' and o.kind != 'icon' and o.w > 10 else None
    for t, size, bold, _ in o.lines:
        w = text_w(t, size, bold)
        n = 1
        if maxw and w > maxw:
            n = math.ceil(w / maxw)
            w = maxw
        lines.append((t, size, bold, w))
        lw = max(lw, w)
        lh += size * 1.25 * n
    if o.kind == 'icon':
        lp = s.get('labelPosition', 'center')
        vlp = s.get('verticalLabelPosition', 'middle')
        cx, cy = o.x + o.w / 2, o.y + o.h / 2
        if lp == 'left':
            x2 = o.x - float(s.get('spacingRight', 0)) - 2
            return (x2 - lw, cy - lh / 2, x2, cy + lh / 2)
        if lp == 'right':
            x1 = o.x + o.w + float(s.get('spacingLeft', 0)) + 2
            return (x1, cy - lh / 2, x1 + lw, cy + lh / 2)
        if vlp == 'bottom':
            y1 = o.y + o.h + float(s.get('spacingTop', 0)) + 2
            return (cx - lw / 2, y1, cx + lw / 2, y1 + lh)
        if vlp == 'top':
            y2 = o.y - 2
            return (cx - lw / 2, y2 - lh, cx + lw / 2, y2)
        return (cx - lw / 2, cy - lh / 2, cx + lw / 2, cy + lh / 2)
    align = s.get('align', 'center')
    valign = s.get('verticalAlign', 'middle')
    if align == 'left':
        x1 = o.x + float(s.get('spacingLeft', 0)) + 2
    elif align == 'right':
        x1 = o.x + o.w - float(s.get('spacingRight', 0)) - 2 - lw
    else:
        x1 = o.x + (o.w - lw) / 2
    if valign == 'top':
        y1 = o.y + float(s.get('spacingTop', 0)) + 2
    elif valign == 'bottom':
        y1 = o.y + o.h - lh - 2
    else:
        y1 = o.y + (o.h - lh) / 2
    return (x1, y1, x1 + lw, y1 + lh)


def edge_path(e, cells):
    s = e.style
    src, tgt = cells.get(e.src), cells.get(e.tgt)

    def anchor(c, kx, ky, other):
        if c is None:
            return None
        if kx in s and ky in s:
            return (c.x + float(s[kx]) * c.w, c.y + float(s[ky]) * c.h)
        return (c.x + c.w / 2, c.y + c.h / 2)   # 未指定锚点：近似取中心

    p0 = anchor(src, 'exitX', 'exitY', tgt) or e.sp
    p1 = anchor(tgt, 'entryX', 'entryY', src) or e.tp
    if p0 is None or p1 is None:
        return []
    return [p0] + e.pts + [p1]


# ------------------------------------------------------------------ 几何
def shrink(r, d):
    return (r[0] + d, r[1] + d, r[2] - d, r[3] - d)


def rect_of(c):
    return (c.x, c.y, c.x + c.w, c.y + c.h)


def seg_hits_rect(p, q, r):
    """Liang–Barsky：线段 pq 是否与矩形 r 相交"""
    x0, y0 = p
    dx, dy = q[0] - x0, q[1] - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if pp == 0:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def short(c):
    t = ' '.join(l[0] for l in (c.lines or []))[:24]
    return '%s「%s」' % (c.id, t) if t else c.id


# ------------------------------------------------------------------ lint
def lint(path, page=0):
    cells, order, pw, ph = parse(path, page)
    issues = []
    verts = [c for c in order if c.vertex]
    edges = [c for c in order if c.edge]
    texts = [c for c in verts if c.tbox]
    icons = [c for c in verts if c.kind == 'icon']

    def opaque(c):
        f = c.style.get('fillColor', 'none')
        return f not in ('none', '') and c.kind in ('text', 'pill', 'label')

    for e in edges:
        path_ = edge_path(e, cells)
        segs = list(zip(path_, path_[1:]))
        for c in texts:
            if c.kind == 'label' and c.w * c.h > 60000:
                continue
            box = shrink(c.tbox, 1.5)
            if any(seg_hits_rect(p, q, box) for p, q in segs):
                # 不透明标签画在连线之后 → 线被盖住，视为"线上标注"，可接受
                if opaque(c) and c.idx > e.idx:
                    continue
                issues.append(('ERROR', '连线压字', '连线 %s（%s→%s）穿过 %s 的文字' % (
                    e.id, e.src or '-', e.tgt or '-', short(c)), c.tbox))
        for c in icons:
            if c.id in (e.src, e.tgt):
                continue
            if any(seg_hits_rect(p, q, shrink(rect_of(c), 3)) for p, q in segs):
                issues.append(('ERROR', '连线穿过设备', '连线 %s（%s→%s）穿过设备 %s' % (
                    e.id, e.src or '-', e.tgt or '-', short(c)), rect_of(c)))

    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            ov = overlap(a.tbox, b.tbox)
            if ov > 20:
                issues.append(('ERROR', '文字重叠', '%s 与 %s 文字重叠约 %d px²' % (short(a), short(b), ov), a.tbox))
        for c in icons:
            if c is a:
                continue
            ov = overlap(a.tbox, shrink(rect_of(c), 2))
            if ov > 20:
                issues.append(('ERROR', '文字压图标', '%s 的文字压住设备 %s' % (short(a), short(c)), a.tbox))

    for i, a in enumerate(icons):
        for b in icons[i + 1:]:
            if overlap(rect_of(a), rect_of(b)) > 0:
                issues.append(('ERROR', '设备重叠', '%s 与 %s 图标重叠' % (short(a), short(b)), rect_of(a)))

    if pw and ph:
        for c in verts:
            r = c.tbox or rect_of(c)
            if r[2] > pw + 1 or r[3] > ph + 1 or r[0] < -1 or r[1] < -1:
                issues.append(('WARN', '超出页面', '%s 超出页面 %dx%d' % (short(c), pw, ph), r))

    # 分区留白：大面积无文字矩形视为分区，统计其中设备（含标签）左右余量
    zones = [c for c in verts if c.kind == 'box' and c.style.get('rounded', '0') != '1' and c.w * c.h > 250000]
    for z in zones:
        inner = [c for c in icons if z.x < c.x + c.w / 2 < z.x + z.w and z.y < c.y + c.h / 2 < z.y + z.h]
        if len(inner) < 2:
            continue
        xs = [min(c.x, (c.tbox or rect_of(c))[0]) for c in inner]
        xe = [max(c.x + c.w, (c.tbox or rect_of(c))[2]) for c in inner]
        left, right = min(xs) - z.x, z.x + z.w - max(xe)
        lo, hi = sorted((left, right))
        if hi > 200 and hi > 2.5 * max(lo, 1):
            issues.append(('WARN', '留白失衡', '分区 %s 内设备左余 %d / 右余 %d px，可整体平移居中' % (
                z.id, left, right), rect_of(z)))
    return issues


# ------------------------------------------------------------------ preview
def _color(v, default=None):
    if not v or v in ('none', 'default'):
        return default
    if v.startswith('#') and len(v) in (4, 7):
        return v
    return default


def _dashed_line(dr, p, q, fill, width, dash=(8, 5)):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L == 0:
        return
    ux, uy = dx / L, dy / L
    t, on = 0.0, True
    while t < L:
        seg = dash[0] if on else dash[1]
        t2 = min(L, t + seg)
        if on:
            dr.line([(p[0] + ux * t, p[1] + uy * t), (p[0] + ux * t2, p[1] + uy * t2)], fill=fill, width=width)
        t, on = t2, not on


def preview(path, out, page=0, scale=1.0, crop=None, mark=None):
    from PIL import Image, ImageDraw
    cells, order, pw, ph = parse(path, page)
    W = int(pw or max(c.x + c.w for c in order if c.vertex) + 40)
    H = int(ph or max(c.y + c.h for c in order if c.vertex) + 40)
    img = Image.new('RGB', (W, H), 'white')
    dr = ImageDraw.Draw(img)

    def draw_text(c):
        if not c.tbox:
            return
        x1, y, x2, _ = c.tbox
        col = _color(c.style.get('fontColor'), '#1B2631')
        align = 'center' if c.kind == 'icon' and c.style.get('labelPosition', 'center') == 'center' else \
            c.style.get('align', 'center')
        if c.kind == 'icon' and c.style.get('labelPosition') == 'left':
            align = 'right'
        for t, size, bold, lc in c.lines:
            f = _font(size, bold)
            w = text_w(t, size, bold)
            tx = x1 if align == 'left' else (x2 - w if align == 'right' else (x1 + x2 - w) / 2)
            dr.text((tx, y), t, fill=lc or col, font=f)
            y += size * 1.25

    for c in order:
        s = c.style
        if c.vertex:
            r = rect_of(c)
            fill = _color(s.get('fillColor'))
            stroke = _color(s.get('strokeColor'))
            if c.kind == 'icon':
                dr.rounded_rectangle(r, radius=6, fill=fill or '#2471A3')
            elif c.kind == 'mark':
                dr.ellipse(r, outline=stroke or '#1B2631', width=2)
            elif c.kind == 'panel':
                dr.rectangle(r, outline='#D5D8DC')
                y = c.y + 4
                for t, size, bold, lc in c.lines:
                    if y > c.y + c.h - size:
                        break
                    dr.text((c.x + 6, y), t[:140], fill=lc or '#1B2631', font=_font(size, bold))
                    y += size * 1.45
                continue
            elif s.get('_base') != 'text' or fill or stroke:
                rad = 11 if s.get('arcSize') == '50' else (8 if s.get('rounded') == '1' else 0)
                if fill:
                    dr.rounded_rectangle(r, radius=rad, fill=fill) if rad else dr.rectangle(r, fill=fill)
                if stroke:
                    sw = max(1, int(float(s.get('strokeWidth', 1))))
                    if s.get('dashed') == '1':
                        pts = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]), (r[0], r[1])]
                        for p, q in zip(pts, pts[1:]):
                            _dashed_line(dr, p, q, stroke, sw, (6, 4))
                    else:
                        dr.rounded_rectangle(r, radius=rad, outline=stroke, width=sw) if rad else \
                            dr.rectangle(r, outline=stroke, width=sw)
            draw_text(c)
        elif c.edge:
            pth = edge_path(c, cells)
            col = _color(s.get('strokeColor'), '#566573')
            wdt = max(1, int(round(float(s.get('strokeWidth', 1)))))
            for p, q in zip(pth, pth[1:]):
                if s.get('dashed') == '1':
                    _dashed_line(dr, p, q, col, wdt)
                else:
                    dr.line([p, q], fill=col, width=wdt)
    if mark:
        for r in mark:
            dr.rectangle(r, outline='#FF00FF', width=3)
    if crop:
        img = img.crop(tuple(int(v) for v in crop))
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    img.save(out)
    return out


def main(argv):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    path, page, png, scale, crop, quiet = argv[0], 0, None, 1.0, None, False
    it = iter(argv[1:])
    for a in it:
        if a == '--page':
            page = int(next(it))
        elif a == '--png':
            png = next(it)
        elif a == '--scale':
            scale = float(next(it))
        elif a == '--crop':
            crop = [float(next(it)) for _ in range(4)]
        elif a == '--quiet':
            quiet = True
    issues = lint(path, page)
    errs = [i for i in issues if i[0] == 'ERROR']
    if not quiet or issues:
        for lv, cat, msg, _ in issues:
            print('[%s] %s：%s' % (lv, cat, msg))
        print('检查完成：%d 个错误，%d 个提示' % (len(errs), len(issues) - len(errs)))
    if png:
        print(preview(path, png, page, scale, crop, mark=[i[3] for i in errs]))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
