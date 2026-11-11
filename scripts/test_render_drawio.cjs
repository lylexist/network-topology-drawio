'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const r = require('./render_drawio.cjs');
const cwd = path.resolve('/test/render');
const parse = (args, env = {}) => r.parseArgs(args, env, cwd);
function temporary(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'drawio-unit-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('require is side-effect free; help requires neither Playwright nor browser', () => {
  const script = path.join(__dirname, 'render_drawio.cjs');
  const required = spawnSync(process.execPath, ['-e', `require(${JSON.stringify(script)})`], { encoding: 'utf8' });
  assert.equal(required.status, 0); assert.equal(required.stdout, ''); assert.equal(required.stderr, '');
  const help = spawnSync(process.execPath, [script, '--help'], { encoding: 'utf8', env: { ...process.env, DRAWIO_PLAYWRIGHT_MODULE: '/nonexistent-module' } });
  assert.equal(help.status, 0); assert.match(help.stdout, /Usage:/);
});

test('defaults and multiple input destinations', () => {
  const opts = parse(['a.drawio', '中文.drawio']);
  assert.equal(opts.scale, 1); assert.equal(opts.dpr, 2); assert.equal(opts.border, 20);
  assert.equal(opts.timeout, 120000); assert.equal(opts.page, '0');
  assert.equal(opts.baseUrl, 'https://app.diagrams.net/');
  assert.deepEqual(r.planOutputs(opts), [
    { source: path.join(cwd, 'a.drawio'), png: path.join(cwd, 'a.png'), report: path.join(cwd, 'a.render.json') },
    { source: path.join(cwd, '中文.drawio'), png: path.join(cwd, '中文.png'), report: path.join(cwd, '中文.render.json') }
  ]);
});

test('PNG dimensions detect silent viewport clipping despite successful screenshot', () => {
  const png = (w, h) => {
    const b = Buffer.alloc(24); Buffer.from('89504e470d0a1a0a', 'hex').copy(b);
    b.writeUInt32BE(w, 16); b.writeUInt32BE(h, 20); return b;
  };
  const clip = { x: 0, y: 0, width: 2501, height: 1330 };
  assert.deepEqual(r.validatePng(png(5002, 2660), clip, 2), { width: 5002, height: 2660 });
  assert.throws(() => r.validatePng(png(2000, 1600), clip, 2), /clipped or resized/);
  assert.throws(() => r.validatePng(Buffer.from('not png'), clip, 2), /valid PNG/);
});

test('all value options and environment precedence', () => {
  const opts = parse(['a.drawio', '-o', 'out/a.png', '--report', 'out/report.json', '--scale', '1.5', '--dpr', '3', '--border', '0', '--timeout', '500', '--page', 'page-xyz', '--browser', './chrome', '--base-url', 'http://localhost:8080/drawio', '--asset-dir', 'assets', '--overwrite'], { DRAWIO_RENDER_BASE_URL: 'https://wrong.test/', DRAWIO_RENDER_BROWSER: 'msedge' });
  assert.equal(opts.scale, 1.5); assert.equal(opts.border, 0); assert.equal(opts.dpr, 3);
  assert.equal(opts.timeout, 500); assert.equal(opts.page, 'page-xyz'); assert.equal(opts.overwrite, true);
  assert.equal(opts.baseUrl, 'http://localhost:8080/drawio/'); assert.equal(opts.browser, path.join(cwd, 'chrome'));
  assert.equal(opts.assetDir, path.join(cwd, 'assets'));
  assert.equal(r.planOutputs(opts)[0].report, path.join(cwd, 'out/report.json'));
  for (const browser of ['chromium', 'chrome', 'msedge']) assert.equal(parse(['a.drawio', '--browser', browser]).browser, browser);
  assert.equal(parse(['a.drawio'], { DRAWIO_RENDER_BROWSER: 'msedge' }).browser, 'msedge');
});

test('illegal and conflicting CLI options fail', () => {
  for (const args of [[], ['--unknown'], ['a.drawio', '--scale'], ['a.drawio', '--dpr', '--border', '2'],
    ['a.drawio', '--scale', 'NaN'], ['a.drawio', '--scale', '0'], ['a.drawio', '--dpr', 'Infinity'],
    ['a.drawio', '--border', '-1'], ['a.drawio', '--timeout', '1.5'], ['a.drawio', '--timeout', '2147483648'],
    ['a.drawio', '--dpr', '9'], ['a.drawio', '--scale', '101'], ['a.drawio', '--border', '10001'],
    ['a.drawio', '--scale', ''], ['a.drawio', '--page', '-1'], ['a.drawio', '--page', ''],
    ['a.drawio', '--page', '9007199254740993'], ['a.drawio', '--base-url', 'file:///tmp/'],
    ['a.drawio', '--base-url', 'https://user:pass@example.com/'], ['a.drawio', '--base-url', 'https://example.com/#secret'],
    ['a.drawio', '--base-url', 'https://example.com/?x=1'], ['a.drawio', '--browser', ''],
    ['a.drawio', '--scale', '1', '--scale', '2'], ['a.drawio', '-o', 'a.png', '--out-dir', 'out'],
    ['a.drawio', 'b.drawio', '-o', 'a.png'], ['a.drawio', 'b.drawio', '--report', 'r.json']]) {
    assert.throws(() => parse(args), undefined, JSON.stringify(args));
  }
  assert.equal(parse(['--doctor']).doctor, true);
  assert.deepEqual(parse(['--', '-a.drawio']).inputs, [path.join(cwd, '-a.drawio')]);
});

test('output paths, extensions, duplicates and batch basename collisions', () => {
  const jobs = r.planOutputs(parse(['x/a.drawio', 'y/b.DRAWIO', '--out-dir', 'out']));
  assert.equal(jobs[1].png, path.join(cwd, 'out/b.png'));
  for (const args of [['x/a.drawio', 'y/a.drawio', '--out-dir', 'out'], ['a.drawio', './a.drawio'],
    ['a.xml'], ['a.drawio', '-o', 'out.jpg'], ['a.drawio', '--report', 'a.drawio'],
    ['a.drawio', '--report', 'a.png'], ['a.drawio', 'b.drawio', '--out-dir', '.']]) {
    if (args[0] === 'a.drawio' && args[1] === 'b.drawio') { assert.equal(r.planOutputs(parse(args)).length, 2); continue; }
    assert.throws(() => r.planOutputs(parse(args)), undefined, JSON.stringify(args));
  }
});

test('safe dotenv literals and environment override; relative .env paths use root', t => {
  const root = temporary(t);
  const literal = r.dotenv('DRAWIO_RENDER_BROWSER="chrome"\nDRAWIO_RENDER_ASSET_DIR=assets # comment\nDRAWIO_PLAYWRIGHT_MODULE=\'$(do-not-execute)\'\nUNRELATED=x\n');
  assert.equal(literal.DRAWIO_PLAYWRIGHT_MODULE, '$(do-not-execute)');
  assert.equal(literal.DRAWIO_RENDER_ASSET_DIR, 'assets'); assert.equal(literal.UNRELATED, undefined);
  assert.throws(() => r.dotenv('DRAWIO_RENDER_BROWSER="oops'));
  fs.writeFileSync(path.join(root, '.env'), 'DRAWIO_RENDER_BROWSER=chrome\nDRAWIO_RENDER_ASSET_DIR=assets\nDRAWIO_PLAYWRIGHT_MODULE=modules/playwright\n');
  const config = r.configuration({ DRAWIO_RENDER_BROWSER: 'msedge' }, root);
  assert.equal(config.DRAWIO_RENDER_BROWSER, 'msedge');
  assert.equal(config.DRAWIO_RENDER_ASSET_DIR, path.join(root, 'assets'));
  assert.equal(config.DRAWIO_PLAYWRIGHT_MODULE, path.join(root, 'modules/playwright'));
});

test('dimension boundaries reject empty, huge, negative and non-finite graphs', () => {
  const bounds = { x: 0, y: 0, width: 100, height: 200 };
  assert.deepEqual(r.checkDimensions(bounds, 2), { width: 200, height: 400 });
  assert.deepEqual(r.checkDimensions({ ...bounds, width: 10000, height: 10000 }, 1), { width: 10000, height: 10000 });
  assert.deepEqual(r.checkDimensions({ ...bounds, width: 32767, height: 1 }, 1), { width: 32767, height: 1 });
  for (const invalid of [null, { ...bounds, x: -1 }, { ...bounds, width: 0 }, { ...bounds, height: NaN },
    { ...bounds, width: Infinity }, { ...bounds, width: 32768 }, { ...bounds, width: 10001, height: 10000 }]) assert.throws(() => r.checkDimensions(invalid, 1));
  assert.throws(() => r.checkDimensions(bounds, 0));
  assert.throws(() => r.checkDimensions(bounds, Infinity));
});

test('asset matching is origin/base scoped; missing, traversal and symlinks fall through', t => {
  const dir = temporary(t), root = path.join(dir, 'assets');
  fs.mkdirSync(path.join(root, 'js'), { recursive: true });
  fs.writeFileSync(path.join(root, 'js/app.min.js'), 'test');
  fs.writeFileSync(path.join(dir, 'secret'), 'secret');
  fs.symlinkSync(path.join(dir, 'secret'), path.join(root, 'js/link.js'));
  const base = 'https://example.test/drawio/';
  assert.equal(r.assetPath(root, base + 'js/app.min.js?v=1', base), fs.realpathSync(path.join(root, 'js/app.min.js')));
  for (const url of [base + 'js/missing.js', 'https://other.test/drawio/js/app.min.js',
    'https://example.test/js/app.min.js', base + '%2e%2e%2fsecret', base + 'js/link.js', base + '%invalid']) assert.equal(r.assetPath(root, url, base), null);
});

test('atomic publication refuses overwrite, cleans staging and preserves existing data', t => {
  const dir = temporary(t), a = path.join(dir, 'a.png'), b = path.join(dir, 'b.json');
  fs.writeFileSync(b, 'original');
  assert.throws(() => r.publish([[a, 'png'], [b, 'report']], false));
  assert.equal(fs.existsSync(a), false); assert.equal(fs.readFileSync(b, 'utf8'), 'original');
  assert.deepEqual(fs.readdirSync(dir), ['b.json']);
  r.publish([[a, Buffer.from('png')], [b, 'report']], true);
  assert.equal(fs.readFileSync(a, 'utf8'), 'png'); assert.equal(fs.readFileSync(b, 'utf8'), 'report');
  r.publish([[path.join(dir, 'sub/c'), 'new']], false);
  assert.equal(fs.readFileSync(path.join(dir, 'sub/c'), 'utf8'), 'new');
});

test('diagnostics redact URL query/fragment and classify noncritical font/CSS', () => {
  assert.equal(r.safeMessage('HTTP https://example.test/file?xml=secret#secret failed'), 'HTTP https://example.test/file failed');
  assert.equal(r.resourceSeverity({ resourceType: () => 'stylesheet' }), 'warning');
  assert.equal(r.resourceSeverity({ resourceType: () => 'font' }), 'warning');
  for (const type of ['script', 'image', 'xhr', 'document']) assert.equal(r.resourceSeverity({ resourceType: () => type }), 'error');
  assert.deepEqual(r.launchOptions({ browser: 'chromium', timeout: 10 }), { headless: true, timeout: 10 });
  assert.equal(r.launchOptions({ browser: 'msedge', timeout: 10 }).channel, 'msedge');
  assert.equal(r.launchOptions({ browser: '/browser', timeout: 10 }).executablePath, '/browser');
});
