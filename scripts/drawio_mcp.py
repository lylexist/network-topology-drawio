# -*- coding: utf-8 -*-
"""
drawio_mcp —— 官方 draw.io MCP 的极简命令行客户端（无第三方依赖）。

当 Agent 环境已直接挂载 draw.io MCP 工具时，优先直接调用 MCP 工具；
未挂载时用本脚本调用同一套官方工具：
  本地 stdio：npx -y @drawio/mcp           （默认；工具：open_drawio_xml / search_shapes / list_pages / get_page / set_page / get_drawio_reference）
  托管 HTTP ：https://mcp.draw.io/mcp      （--hosted；工具：create_diagram / search_shapes / get_drawio_reference）

用法：
  python drawio_mcp.py tools [--hosted]
  python drawio_mcp.py open  a.drawio [--lightbox] [--browser] [--hosted]   # 生成 draw.io 编辑器链接
  python drawio_mcp.py search cisco layer 3 switch [--limit 10] [--hosted] # 查图形 style
  python drawio_mcp.py pages a.drawio
  python drawio_mcp.py get   a.drawio 0
  python drawio_mcp.py set   a.drawio 0 page.xml                           # 用 page.xml(<mxGraphModel>) 替换该页
  python drawio_mcp.py reference xml|mermaid

重要：本 skill 的图依赖精确坐标与直线连线，open 时绝不传 postLayout / routing（会重排布局、改成正交走线）。

可选环境变量（或写入 skill 根目录 .env）：
  DRAWIO_MCP_CMD   本地 MCP 启动命令，默认 "npx -y @drawio/mcp"
  DRAWIO_MCP_URL   托管 MCP 地址，默认 https://mcp.draw.io/mcp
  DRAWIO_BASE_URL  自建 draw.io 地址（传给本地 MCP）
  DRAWIO_BROWSER   on/off，本地 MCP 是否自动打开浏览器；本脚本默认 off，--browser 时 on
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
FORBIDDEN = ('postLayout', 'routing', 'direction')


def load_dotenv():
    p = os.path.join(os.path.dirname(HERE), '.env')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    if v.strip():
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class StdioMCP:
    """通过 stdio 与 @drawio/mcp 交互（JSON-RPC，每行一条消息）"""

    def __init__(self, browser=False):
        cmd = shlex.split(os.environ.get('DRAWIO_MCP_CMD', 'npx -y @drawio/mcp'), posix=(os.name != 'nt'))
        exe = shutil.which(cmd[0]) or shutil.which(cmd[0] + '.cmd') or cmd[0]
        env = dict(os.environ)
        env['DRAWIO_BROWSER'] = 'on' if browser else env.get('DRAWIO_BROWSER_FORCE', 'off')
        self.p = subprocess.Popen([exe] + cmd[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env, text=True, encoding='utf-8', bufsize=1)
        self.n = 0
        self._rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                 'clientInfo': {'name': 'topo-skill', 'version': '1'}})
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + '\n')
        self.p.stdin.flush()

    def _rpc(self, method, params=None):
        self.n += 1
        msg = {'jsonrpc': '2.0', 'id': self.n, 'method': method}
        if params is not None:
            msg['params'] = params
        self._send(msg)
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError('MCP 进程退出：' + self.p.stderr.read())
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('id') == self.n:
                if 'error' in r:
                    raise RuntimeError(r['error'])
                return r['result']

    def tools(self):
        return self._rpc('tools/list')['tools']

    def call(self, name, args):
        return self._rpc('tools/call', {'name': name, 'arguments': args})

    def close(self):
        try:
            self.p.kill()
        except Exception:
            pass


class HttpMCP:
    """托管 MCP（Streamable HTTP）"""

    def __init__(self):
        self.url = os.environ.get('DRAWIO_MCP_URL', 'https://mcp.draw.io/mcp')
        self.sid = None
        self.n = 0
        self._rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                 'clientInfo': {'name': 'topo-skill', 'version': '1'}})
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def _post(self, body):
        h = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'User-Agent': UA}
        if self.sid:
            h['mcp-session-id'] = self.sid
        req = urllib.request.Request(self.url, data=json.dumps(body).encode('utf-8'), method='POST', headers=h)
        with urllib.request.urlopen(req, timeout=60) as resp:
            self.sid = resp.headers.get('mcp-session-id') or self.sid
            return resp.read().decode('utf-8')

    def _rpc(self, method, params=None):
        self.n += 1
        msg = {'jsonrpc': '2.0', 'id': self.n, 'method': method}
        if params is not None:
            msg['params'] = params
        b = self._post(msg)
        for line in b.splitlines():
            if line.startswith('data:'):
                b = line[5:]
        r = json.loads(b)
        if 'error' in r:
            raise RuntimeError(r['error'])
        return r['result']

    def tools(self):
        return self._rpc('tools/list')['tools']

    def call(self, name, args):
        return self._rpc('tools/call', {'name': name, 'arguments': args})

    def close(self):
        pass


def text_of(result):
    return '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')


def open_link(path, lightbox=False, browser=False, hosted=False):
    with open(path, encoding='utf-8') as f:
        xml = f.read()
    m = HttpMCP() if hosted else StdioMCP(browser=browser)
    try:
        if hosted:
            r = m.call('create_diagram', {'xml': xml})
        else:
            args = {'content': xml}
            if lightbox:
                args['lightbox'] = True
            r = m.call('open_drawio_xml', args)
        t = text_of(r)
        import re
        urls = re.findall(r'https://[^\s"\)<>]+', t)
        urls = [u for u in urls if '#' in u] or urls
        return ('Draw.io Editor URL:\n' + urls[0]) if urls else t
    finally:
        m.close()


def main(argv):
    load_dotenv()
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    hosted = '--hosted' in argv
    browser = '--browser' in argv
    lightbox = '--lightbox' in argv
    limit = 10
    if '--limit' in argv:
        limit = int(argv[argv.index('--limit') + 1])
    pos = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i - 1] != '--limit')]
    if any(a.lstrip('-') in FORBIDDEN for a in argv if a.startswith('--')):
        print('拒绝：本风格不使用 postLayout / routing / direction')
        return 2
    cmd = pos[0]
    if cmd == 'open':
        print(open_link(pos[1], lightbox, browser, hosted))
        return 0
    m = HttpMCP() if hosted else StdioMCP()
    try:
        if cmd == 'tools':
            for t in m.tools():
                print('-', t['name'], list(t.get('inputSchema', {}).get('properties', {}).keys()))
        elif cmd == 'search':
            print(text_of(m.call('search_shapes', {'query': ' '.join(pos[1:]), 'limit': limit})))
        elif cmd == 'reference':
            print(text_of(m.call('get_drawio_reference', {'format': pos[1]})))
        elif cmd == 'pages':
            print(text_of(m.call('list_pages', {'path': os.path.abspath(pos[1])})))
        elif cmd == 'get':
            page = int(pos[2]) if pos[2].isdigit() else pos[2]
            print(text_of(m.call('get_page', {'path': os.path.abspath(pos[1]), 'page': page})))
        elif cmd == 'set':
            page = int(pos[2]) if pos[2].isdigit() else pos[2]
            with open(pos[3], encoding='utf-8') as f:
                content = f.read()
            print(text_of(m.call('set_page', {'path': os.path.abspath(pos[1]), 'page': page, 'content': content})))
        else:
            print(__doc__)
            return 2
    finally:
        m.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
