# -*- coding: utf-8 -*-
"""
参考示例：医院内网数据中心区搬迁前 / 搬迁后核心组网图（基于真实项目脱敏）。

演示了本风格的全部要素：分区 + 分层标签 + 成对设备组 + 主备 HA + 跨楼 4×10GE 聚合
+ 服务器双归属 + 跨机房集群逻辑线 + 不画进图的说明框 + 底部三栏。

运行：python dc_relocation_example.py [输出目录] [--check] [--open]
  --check  几何自检并输出 *.preview.png 布局预览
  --open   经官方 draw.io MCP（npx @drawio/mcp）生成编辑器链接
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from topo_lib import *  # noqa: E402,F401,F403

ROWS = [(180, 350, '核心/汇聚层'), (400, 550, '安全防护层'), (610, 760, '服务器交换层'), (870, 1110, '计算资源层')]


def before(out):
    d = Doc(2420, 1580)
    title(d, '示例医院内网数据中心区核心组网图-搬迁前',
          '涉及机房：门诊楼 4F 原核心机房 ｜ 3号住院楼 5F 新机房 ｜ 1号住院楼 3F 老机房')
    layers(d, ROWS)
    # 左旧右新
    zone(d, 150, 110, 1380, 1010, '门诊楼 4F 原核心机房', '（现全院内网核心及数据中心虚拟化区）', 'green')
    zone(d, 1610, 110, 760, 400, '3号住院楼 5F 新机房', '（搬迁前：楼宇汇聚）', 'blue')
    zone(d, 1610, 560, 760, 560, '1号住院楼 3F 老机房', '（闲置服务器）', 'gray')

    cx = 820
    core, _ = pair(d, 'l3', [cx - 80, cx + 80], 270, ['HUAWEI S7706 #1', 'HUAWEI S7706 #2'], ['全院内网核心'] * 2,
                   COLOR['core'], 'CSS 集群 · 全院内网核心', COLOR['core'], BADGE_OLD)
    downlink_note(d, core['x'] - 200, 250, 192, '▼ 下联门诊楼及各楼宇<br>汇聚/接入（本图略）', 'right')

    agg, _ = pair(d, 'l3', [1910, 2070], 270, ['DPX8000 #1', 'DPX8000 #2'], ['楼宇汇聚'] * 2,
                  COLOR['agg'], '虚拟化 · 3号楼楼宇汇聚', COLOR['agg'], BADGE_OLD)
    downlink_note(d, agg['x'], 328, agg['w'], '▼ 下联 3号住院楼各楼层接入交换机（本图略）')
    d.e(core, (core['x'] + core['w'], 270), agg, (agg['x'], 270), 'gen')
    text(d, 1535, 238, 70, 26, '<b>跨楼互联</b>', 12, '#34495E', bg='#FFFFFF')
    text(d, 1160, 246, 300, 20, '楼宇汇聚上联全院内网核心（现网）', 11, '#5D6D7E')

    fw = dev(d, 'fw', cx, 480, 'H3C SecPath F1070', '服务器区防火墙', lab='right')
    parallel_v(d, core, fw, cx, n=2, gap=20, link='10g')
    text(d, cx + 28, 370, 220, 22, '<b>2×10GE 多模 · 链路聚合</b>', 12, '#D35400', 'left')

    sw = dev(d, 'sw', cx, 690, 'H3C S6520', '服务器区交换机', lab='right')
    parallel_v(d, fw, sw, cx, n=2, gap=20, link='1g')
    text(d, cx + 28, 578, 220, 22, '<b>2×1GE 多模 · 链路聚合</b>', 12, '#2E86C1', 'left')

    frame(d, cx - 310, 890, 620, 160, '#8E44AD', 'VMware 集群（4 节点）', bottom=True)
    srvs = [dev(d, 'srv', x, 950, 'ESXi 主机 0%d' % (i + 1), 'VMware ESXi')
            for i, x in enumerate([cx - 240, cx - 80, cx + 80, cx + 240])]
    fan_in(d, srvs, sw, per=2, link='10g')
    text(d, 250, 790, 220, 42, '<b>每台 ESXi 2×10GE 多模光纤</b><br>接入 H3C S6520', 12, '#D35400', 'left')
    note_box(d, 1170, 930, 340, 50, '<b>双活存储：两端均位于门诊楼 4F</b><br>存储及 FC 链路见独立拓扑图，本图不展示')

    text(d, 1640, 640, 700, 50, '现状：3 台 HP DL580 Gen10 服务器闲置，未接入数据中心虚拟化网络，未加入 VMware 集群',
         12, '#5D6D7E', 'left')
    frame(d, 1760, 890, 460, 160, '#7F8C8D', '闲置服务器（未加入 VMware 集群）')
    for i, x in enumerate([1830, 1990, 2150]):
        dev(d, 'srv', x, 950, 'HP DL580 Gen10 #%d' % (i + 1), '闲置', COLOR['idle'])

    bottom_panels(
        d, 1160, 380,
        ([('l3', '全院内网核心交换机（S7706）', COLOR['core']), ('l3', '楼宇汇聚交换机（DPX8000）', COLOR['agg']),
          ('sw', '服务器区交换机（H3C S6520）', COLOR['sw']), ('fw', '服务器区防火墙（H3C F1070）', COLOR['fw']),
          ('srv', 'ESXi 服务器（在网）', COLOR['srv']), ('srv', '闲置服务器', COLOR['idle']),
          ('frame', '虚拟化 / 集群设备组')],
         [('10g', '10GE 万兆多模光纤'), ('1g', '1GE 千兆多模光纤'), ('gen', '现网互联链路'),
          ('virt', 'CSS / 设备虚拟化互联'), ('agg', '链路聚合'), ('vm', 'VMware 集群关系')]),
        ('现状设备清单（数据中心区相关）', ['位置', '设备', '数量', '角色 / 现状'], [
            ['门诊楼 4F', 'HUAWEI S7706', '2', 'CSS 虚拟化，全院内网核心'],
            ['门诊楼 4F', 'H3C SecPath F1070', '1', '服务器区防火墙'],
            ['门诊楼 4F', 'H3C S6520', '1', '服务器区交换机'],
            ['门诊楼 4F', 'VMware ESXi 服务器', '4', '组成 VMware 集群'],
            ['门诊楼 4F', '双活存储', '2 端', '两端均在本机房（见独立拓扑图）'],
            ['3号住院楼 5F', 'DPX8000', '2', '虚拟化，楼宇汇聚，与 S7706 互联'],
            ['1号住院楼 3F', 'HP DL580 Gen10', '3', '闲置，未加入集群'],
        ]),
        ['门诊楼 4F 两台华为 S7706 通过 CSS 虚拟化，承担全院内网核心。',
         '数据中心虚拟化网络：4 台 ESXi → H3C S6520 → H3C F1070 → S7706 核心。',
         '每台 ESXi 以双万兆多模光纤接入 S6520；S6520 以 2 条千兆多模链路聚合上联 F1070；F1070 以 2 条万兆多模链路聚合上联 S7706。',
         '3号住院楼 5F 两台 DPX8000 已做虚拟化，作为楼宇汇聚与门诊楼 S7706 互联。',
         '双活存储两端均位于门诊楼 4F，存储及 FC 链路另见独立拓扑图。',
         '1号住院楼 3F 的 3 台 HP DL580 Gen10 目前闲置，尚未加入 VMware 集群。'])
    return d.save(os.path.join(out, '示例-数据中心区核心组网图-搬迁前.drawio'), '搬迁前')


def server_block(d, cx0, upl, srv_xs, srv_names, srv_subs, cl_x, cl_w, cl_tag):
    """主备防火墙 → 虚拟化服务器交换机 → 服务器双归属（一个机房的服务器区标准块）"""
    _, fws = pair(d, 'fw', [cx0 - 80, cx0 + 80], 480, ['FW1000-GA-X'] * 2, ['主用', '备用'],
                  COLOR['fw'], '主备 · 服务器区防火墙', COLOR['fw'], link=False)
    d.e(fws[0], (cx0 - 48, 480), fws[1], (cx0 + 48, 480), 'ha')
    text(d, cx0 - 20, 460, 40, 18, '<b>HA</b>', 11, '#27AE60')
    swf, sws = pair(d, 'sw', [cx0 - 80, cx0 + 80], 690, ['LSW6600 #1', 'LSW6600 #2'], ['服务器交换机'] * 2,
                    COLOR['sw'], '虚拟化 · 服务器交换', COLOR['sw'], BADGE_NEW)
    for k, dx in enumerate((-80, 80)):
        # 规格未给定 → 'gen'，且连到设备组框而非具体成员，避免暗示逐端口接线
        d.e(fws[k], (cx0 + dx, 456), upl, (cx0 + dx, upl['y'] + upl['h']), 'gen')
        d.e(fws[k], (cx0 + dx, 504), swf, (cx0 + dx, swf['y']), 'gen')
    frame(d, cl_x, 890, cl_w, 160, '#8E44AD', cl_tag, BADGE_MOVE, bottom=True)
    srvs = [dev(d, 'srv', x, 950, srv_names[i], srv_subs[i]) for i, x in enumerate(srv_xs)]
    dual_home(d, srvs, sws[0], sws[1], '10g')
    return swf


def after(out):
    d = Doc(2420, 1580)
    title(d, '示例医院内网数据中心区核心组网图-搬迁后',
          '门诊楼 4F 机房（门诊楼汇聚）⇄ 3号住院楼 5F 新机房（全院内网核心）｜ 跨机房 7 节点 VMware 集群')
    layers(d, ROWS)
    zone(d, 150, 110, 860, 1010, '门诊楼 4F 机房', '（原核心机房，搬迁后为门诊楼汇聚）', 'green')
    zone(d, 1090, 110, 1280, 1010, '3号住院楼 5F 新机房', '（搬迁后全院内网核心）', 'blue')

    s77, _ = pair(d, 'l3', [500, 660], 270, ['S7706 #1', 'S7706 #2'], ['门诊楼汇聚'] * 2,
                  COLOR['agg'], 'CSS 集群 · 门诊楼汇聚（原核心降级）', COLOR['agg'], BADGE_OLD)
    downlink_note(d, 160, 250, 175, '▼ 下联门诊楼各楼层<br>接入交换机（本图略）', 'right')

    core, _ = pair(d, 'l3', [1360, 1520], 270, ['DPX8000 #1', 'DPX8000 #2'], ['全院内网核心'] * 2,
                   COLOR['core'], '虚拟化 · 全院内网核心', COLOR['core'], BADGE_NEW)
    bagg, _ = pair(d, 'l3', [2030, 2190], 270, ['DPX8000 #1', 'DPX8000 #2'], ['楼宇汇聚'] * 2,
                   COLOR['agg'], '虚拟化 · 3号楼楼宇汇聚', COLOR['agg'], BADGE_OLD)
    downlink_note(d, bagg['x'], 328, bagg['w'], '▼ 下联 3号住院楼各楼层接入交换机（本图略）')
    d.e(bagg, (bagg['x'], 270), core, (core['x'] + core['w'], 270), 'gen')
    text(d, core['x'] + core['w'] + 4, 246, bagg['x'] - core['x'] - core['w'] - 8, 20, '上联', 12, '#34495E', bold=True)

    mid = parallel_h(d, s77, core, 270, n=4, gap=10, link='x10g')
    text(d, mid - 85, 222, 170, 24, '<b>4×10GE 链路聚合</b>', 14, '#D35400', bg='#FFFFFF')
    text(d, mid - 105, 296, 210, 20, '跨楼互联：门诊楼 4F ⇄ 3号楼 5F', 11, '#5D6D7E', bg='#FFFFFF')

    server_block(d, 580, s77, [420, 580, 740], ['HP DL580 Gen10 #%d' % i for i in range(1, 4)],
                 ['自1号楼 3F 迁入'] * 3, 350, 460, 'VMware ESXi 主机 ×3')
    text(d, 168, 790, 180, 42, '<b>每台 ESXi 2×10GE</b><br>分别接入两台 LSW6600', 12, '#D35400', 'left')
    note_box(d, 350, 1062, 460, 44, '<b>双活存储（其中一端，保留在门诊楼）</b><br>存储及 FC 链路见独立拓扑图，本图不展示')

    swA = server_block(d, 1440, core, [1200, 1360, 1520, 1680], ['ESXi 主机 0%d' % i for i in range(1, 5)],
                       ['原门诊楼迁入'] * 4, 1130, 620, 'VMware ESXi 主机 ×4')
    text(d, 1712, 790, 180, 42, '<b>每台 ESXi 2×10GE</b><br>分别接入两台 LSW6600', 12, '#D35400', 'left')
    _, l5 = pair(d, 'sw_s', [1960, 2160], 950, ['LSW5662 #1', 'LSW5662 #2'], ['服务器接入交换机'] * 2,
                 COLOR['sw_s'], '服务器接入交换机', COLOR['sw_s'], link=False, lab='bottom', tag_bottom=True)
    sxr = swA['x'] + swA['w']
    # 远端的折线放更高的 y，避免与近端竖线交叉
    d.e(swA, (sxr, 680), l5[1], (2160, l5[1]['y']), 'gen', pts=[(2160, 680)])
    d.e(swA, (sxr, 700), l5[0], (1960, l5[0]['y']), 'gen', pts=[(1960, 700)])
    note_box(d, 1872, 1062, 478, 44, '<b>双活存储（另一端，由门诊楼迁入）</b><br>存储及 FC 链路见独立拓扑图，本图不展示')

    d.fe((810, 970), (1130, 970), 'vm')
    text(d, 852, 948, 236, 44, '<b>跨机房 7 节点 VMware 集群</b><br>门诊楼 4F ×3 ＋ 3号楼 5F ×4', 12, '#8E44AD',
         bg='#FFFFFF', border='#8E44AD')

    bottom_panels(
        d, 1160, 380,
        ([('l3', '全院内网核心交换机（新增 DPX8000）', COLOR['core']), ('l3', '汇聚交换机（S7706 / 原有 DPX8000）', COLOR['agg']),
          ('sw', '服务器交换机（LSW6600）', COLOR['sw']), ('sw_s', '服务器接入交换机（LSW5662）', COLOR['sw_s']),
          ('fw', '服务器区防火墙（FW1000-GA-X）', COLOR['fw']), ('srv', 'ESXi 服务器', COLOR['srv']),
          ('frame', '虚拟化 / 主备 / 集群设备组'), ('badge', '设备状态', [BADGE_NEW, BADGE_OLD, BADGE_MOVE])],
         [('10g', '10GE 万兆链路'), ('x10g', '跨楼万兆链路（4 条聚合）'), ('gen', '设备互联链路'),
          ('ha', '防火墙主备（HA）'), ('virt', 'CSS / 设备虚拟化互联'), ('agg', '链路聚合'), ('vm', 'VMware 集群关系')]),
        ('设备变更说明', ['类别', '设备', '数量', '位置 / 说明'], [
            ['<b style="color:#E67E22">新增</b>', 'DPX8000', '2', '3号楼 5F，全院内网核心，虚拟化'],
            ['<b style="color:#E67E22">新增</b>', 'LSW6600', '4', '3号楼 5F、门诊楼 4F 各 2 台，本地虚拟化'],
            ['部署', 'FW1000-GA-X', '4', '3号楼 5F、门诊楼 4F 各 2 台，本地主备'],
            ['部署', 'LSW5662', '2', '3号楼 5F，接于 LSW6600 下'],
            ['原有·降级', 'HUAWEI S7706', '2', '门诊楼 4F，由全院核心降为门诊楼汇聚'],
            ['原有·改接', 'DPX8000（楼宇汇聚）', '2', '改为上联新增核心，断开与 S7706 的连接'],
            ['<b style="color:#8E44AD">迁移</b>', 'ESXi 服务器', '4', '门诊楼 4F → 3号楼 5F'],
            ['<b style="color:#8E44AD">迁移</b>', 'HP DL580 Gen10', '3', '1号楼 3F → 门诊楼 4F，加入集群'],
            ['<b style="color:#8E44AD">迁移</b>', '双活存储', '1 端', '门诊楼 4F → 3号楼 5F，另一端留门诊楼'],
            ['<b style="color:#7F8C8D">下架备用</b>', 'H3C S6520、H3C F1070', '—', '不再出现在运行拓扑中'],
        ]),
        ['3号住院楼 5F 共 4 台 DPX8000：2 台原有（楼宇汇聚）、2 台新增（全院内网核心），图中以颜色和标签区分。',
         '门诊楼 S7706 与新增全院内网核心之间采用 4 条万兆链路聚合互联；原 3号楼楼宇汇聚改为上联新增核心。',
         '两地服务器区结构一致：ESXi → 虚拟化 LSW6600 → 主备 FW1000-GA-X → 上联（门诊楼为 S7706，3号楼为新增核心）。',
         '7 台 ESXi 组成跨机房 VMware 集群；HP DL580 Gen10 在原 4 台 ESXi 搬迁完成后迁入门诊楼并加入集群。',
         '双活存储一端迁至 3号楼 5F，另一端保留在门诊楼 4F；存储及 FC 链路另见独立拓扑图。',
         '具体端口编号、防火墙逐端口接线以实施阶段确认为准。'])
    return d.save(os.path.join(out, '示例-数据中心区核心组网图-搬迁后.drawio'), '搬迁后')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = args[0] if args else '.'
    files = [before(out), after(out)]
    for f in files:
        print(f)
        if '--check' in sys.argv:
            check(f, preview_png=os.path.splitext(f)[0] + '.preview.png')
        if '--open' in sys.argv:
            print(open_in_drawio(f))
