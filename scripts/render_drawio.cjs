'use strict';

// No work is performed on require(). No dependency or browser is downloaded.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const MAX_PIXELS = 100_000_000;
const MAX_SIDE = 32767;
const MAX_XML_BYTES = 50 * 1024 * 1024;
const HELP = `Usage: node render_drawio.cjs [options] input.drawio [...]
  -o, --output FILE     Single input PNG destination
  --out-dir DIR        Output directory (all inputs)
  --page INDEX|ID      Zero-based index or diagram id (default: 0)
  --scale NUMBER       Graph scale (default: 1)
  --dpr NUMBER         Device pixel ratio (default: 2)
  --border NUMBER      Border in graph units (default: 20)
  --timeout MS         Per-file deadline (default: 120000)
  --browser PATH|CHANNEL  Chrome executable or chromium/chrome/msedge
  --base-url URL       Official export3.html host (default: https://app.diagrams.net/)
  --asset-dir DIR      Override only existing same-origin resources by relative path
  --report FILE        Single input JSON destination (default: PNG stem.render.json)
  --overwrite          Allow replacing PNG and report
  --doctor             Diagnose only; no render, install or browser download
  -h, --help           Show help

Environment (CLI > environment > skill-root .env > defaults):
DRAWIO_RENDER_BASE_URL, DRAWIO_RENDER_BROWSER, DRAWIO_RENDER_ASSET_DIR,
DRAWIO_PLAYWRIGHT_MODULE (module directory/file; relative paths use current directory).
.env supports literal KEY=value or quoted values, no expansion or shell execution.
Relative .env paths use the skill root. Install dependencies explicitly in scripts/.
Rendering loads official engine/resources over the network, but does not upload XML.
Limits: 50 MiB XML, 100 million output pixels, 32767 pixels per side.
Numeric --page always means index. CSS/font load failures are warnings; all other
resource failures, missing images/stencils and page exceptions fail the render.
`;

function dotenv(text) {
  const result = {};
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*(DRAWIO_(?:RENDER_(?:BASE_URL|BROWSER|ASSET_DIR)|PLAYWRIGHT_MODULE))\s*=\s*(.*?)\s*$/);
    if (!m) continue;
    let value = m[2];
    if (value.startsWith('"') || value.startsWith("'")) {
      if (value.at(-1) !== value[0]) throw new Error(`Unclosed quote in .env: ${m[1]}`);
      value = value.slice(1, -1);
    } else value = value.replace(/\s+#.*$/, '');
    result[m[1]] = value;
  }
  return result;
}

function configuration(env = process.env, root = path.resolve(__dirname, '..')) {
  const file = path.join(root, '.env');
  const local = fs.existsSync(file) ? dotenv(fs.readFileSync(file, 'utf8')) : {};
  for (const key of ['DRAWIO_RENDER_ASSET_DIR', 'DRAWIO_PLAYWRIGHT_MODULE', 'DRAWIO_RENDER_BROWSER']) {
    if (local[key] && (key !== 'DRAWIO_RENDER_BROWSER' || !['chrome', 'chromium', 'msedge'].includes(local[key]))) {
      local[key] = path.resolve(root, local[key]);
    }
  }
  return { ...local, ...env };
}

function parseArgs(args, env = {}, cwd = process.cwd()) {
  const opts = { inputs: [], page: '0', scale: 1, dpr: 2, border: 20, timeout: 120000,
    baseUrl: env.DRAWIO_RENDER_BASE_URL || 'https://app.diagrams.net/',
    browser: env.DRAWIO_RENDER_BROWSER || 'chrome', assetDir: env.DRAWIO_RENDER_ASSET_DIR,
    playwrightModule: env.DRAWIO_PLAYWRIGHT_MODULE, overwrite: false };
  const values = { '-o': 'output', '--output': 'output', '--out-dir': 'outDir', '--page': 'page',
    '--scale': 'scale', '--dpr': 'dpr', '--border': 'border', '--timeout': 'timeout',
    '--browser': 'browser', '--base-url': 'baseUrl', '--asset-dir': 'assetDir', '--report': 'report' };
  const seen = new Set();
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--') { opts.inputs.push(...args.slice(i + 1)); break; }
    if (['--help', '-h', '--doctor', '--overwrite'].includes(arg)) {
      opts[arg === '-h' ? 'help' : arg.slice(2)] = true; continue;
    }
    if (values[arg]) {
      const key = values[arg];
      if (seen.has(key)) throw new Error(`Repeated option: ${arg}`);
      seen.add(key);
      if (++i >= args.length || args[i].startsWith('--')) throw new Error(`Missing value: ${arg}`);
      opts[key] = args[i];
    } else if (arg.startsWith('-')) throw new Error(`Unknown option: ${arg}`);
    else opts.inputs.push(arg);
  }
  if (opts.help) return opts;
  for (const key of ['scale', 'dpr', 'border', 'timeout']) {
    const value = Number(opts[key]);
    if (!String(opts[key]).trim() || !Number.isFinite(value) || value < 0 || (key !== 'border' && value === 0)) {
      throw new Error(`--${key} must be a finite ${key === 'border' ? 'nonnegative' : 'positive'} number`);
    }
    opts[key] = value;
  }
  if (!Number.isSafeInteger(opts.timeout) || opts.timeout > 2147483647) throw new Error('--timeout must be an integer <= 2147483647');
  if (opts.scale > 100 || opts.dpr > 8 || opts.border > 10000) throw new Error('Limits: scale <= 100, dpr <= 8, border <= 10000');
  if (!opts.page || /^-\d/.test(opts.page) || (/^\d+$/.test(opts.page) && !Number.isSafeInteger(Number(opts.page)))) throw new Error('Invalid --page index/id');
  let url;
  try { url = new URL(opts.baseUrl); } catch { throw new Error('--base-url must be an HTTP(S) URL'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('--base-url must be HTTP(S), without credentials, query or fragment');
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  opts.baseUrl = url.href;
  for (const key of ['output', 'outDir', 'report', 'assetDir']) if (opts[key]) opts[key] = path.resolve(cwd, opts[key]);
  if (!opts.browser) throw new Error('--browser must not be empty');
  if (!['chromium', 'chrome', 'msedge'].includes(opts.browser)) opts.browser = path.resolve(cwd, opts.browser);
  opts.inputs = opts.inputs.map(p => path.resolve(cwd, p));
  if (opts.output && opts.outDir) throw new Error('--output and --out-dir conflict');
  if ((opts.output || opts.report) && opts.inputs.length !== 1) throw new Error('--output/--report require exactly one input');
  if (!opts.doctor && !opts.inputs.length) throw new Error('No input .drawio files; use --help');
  return opts;
}

function planOutputs(opts) {
  const reserved = new Set(opts.inputs);
  if (reserved.size !== opts.inputs.length) throw new Error('Duplicate input paths');
  return opts.inputs.map(source => {
    if (!/\.drawio$/i.test(source)) throw new Error(`Input must end in .drawio: ${source}`);
    const png = opts.output || path.join(opts.outDir || path.dirname(source), path.basename(source).replace(/\.drawio$/i, '.png'));
    if (!/\.png$/i.test(png)) throw new Error('--output must end in .png');
    const report = opts.report || png.replace(/\.png$/i, '.render.json');
    for (const dest of [png, report]) {
      if (reserved.has(dest)) throw new Error(`Input/output path collision: ${dest}`);
      reserved.add(dest);
    }
    return { source, png, report };
  });
}

function checkDimensions(bounds, dpr) {
  if (!bounds || !['x', 'y', 'width', 'height'].every(k => Number.isFinite(bounds[k])) || bounds.x < 0 || bounds.y < 0 || bounds.width <= 0 || bounds.height <= 0) throw new Error('Invalid/empty graph bounds');
  const width = Math.ceil(bounds.width * dpr), height = Math.ceil(bounds.height * dpr);
  if (!Number.isFinite(dpr) || dpr <= 0 || width > MAX_SIDE || height > MAX_SIDE || width * height > MAX_PIXELS) throw new Error(`Output exceeds pixel limit (${MAX_PIXELS} pixels, ${MAX_SIDE} per side); reduce --scale/--dpr`);
  return { width, height };
}

function validatePng(png, clip, dpr) {
  if (!Buffer.isBuffer(png) || png.length < 24 || png.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') throw new Error('Browser did not produce a valid PNG');
  const pixels = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
  const expected = checkDimensions(clip, dpr);
  if (Math.abs(pixels.width - expected.width) > 1 || Math.abs(pixels.height - expected.height) > 1) {
    throw new Error(`Screenshot was clipped or resized: expected ${expected.width}x${expected.height}, got ${pixels.width}x${pixels.height}`);
  }
  checkDimensions({ x: 0, y: 0, ...pixels }, 1);
  return pixels;
}

function assetPath(root, requestUrl, baseUrl) {
  const u = new URL(requestUrl), base = new URL(baseUrl);
  if (u.origin !== base.origin || !u.pathname.startsWith(base.pathname)) return null;
  let relative;
  try { relative = decodeURIComponent(u.pathname.slice(base.pathname.length)); } catch { return null; }
  const candidate = path.resolve(root, relative);
  const realRoot = fs.realpathSync(root);
  if (!candidate.startsWith(path.resolve(root) + path.sep) || !fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) return null;
  const real = fs.realpathSync(candidate);
  return real.startsWith(realRoot + path.sep) ? real : null;
}

function safeMessage(value) {
  return String(value).replace(/https?:\/\/[^\s"'<>]+/g, raw => {
    try { const u = new URL(raw); return u.origin + u.pathname; } catch { return '[URL]'; }
  });
}
function resourceSeverity(request) {
  return ['font', 'stylesheet'].includes(request.resourceType()) ? 'warning' : 'error';
}
function loadPlaywright(opts) {
  try {
    const moduleName = opts.playwrightModule;
    return moduleName ? require(path.isAbsolute(moduleName) ? moduleName : path.resolve(moduleName)) : createRequire(__filename)('playwright');
  } catch (e) { throw new Error(`Playwright unavailable. Run npm install in ${__dirname}, or set DRAWIO_PLAYWRIGHT_MODULE to an installed module. ${safeMessage(e.message)}`); }
}
function launchOptions(opts) {
  return { headless: true, timeout: opts.timeout,
    ...(['chromium', 'chrome', 'msedge'].includes(opts.browser) ? (opts.browser === 'chromium' ? {} : { channel: opts.browser }) : { executablePath: opts.browser }) };
}
function validateAssets(opts) {
  if (opts.assetDir && (!fs.existsSync(opts.assetDir) || !fs.statSync(opts.assetDir).isDirectory())) throw new Error(`--asset-dir is not a directory: ${opts.assetDir}`);
}

// Stage in destination directories, then publish using rename (overwrite) or
// exclusive hard links. Each file is atomic; two files cannot be a filesystem transaction.
function publish(items, overwrite) {
  const staged = [], published = [];
  try {
    for (const [dest, data] of items) {
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      const temp = path.join(path.dirname(dest), `.${path.basename(dest)}.${crypto.randomUUID()}.tmp`);
      fs.writeFileSync(temp, data, { flag: 'wx' });
      staged.push([temp, dest]);
    }
    for (const [temp, dest] of staged) {
      if (overwrite) fs.renameSync(temp, dest);
      else { fs.linkSync(temp, dest); published.push(dest); fs.unlinkSync(temp); }
    }
  } catch (e) {
    if (!overwrite) for (const dest of published) fs.rmSync(dest, { force: true });
    throw e;
  } finally { for (const [temp] of staged) fs.rmSync(temp, { force: true }); }
}

async function renderFile(browser, opts, job) {
  const context = await browser.newContext({ viewport: { width: 1000, height: 800 }, deviceScaleFactor: opts.dpr });
  const page = await context.newPage();
  const warnings = [], errors = [];
  const deadline = Date.now() + opts.timeout;
  const remaining = () => { const ms = deadline - Date.now(); if (ms <= 0) throw new Error('Per-file render deadline exceeded'); return ms; };
  const timed = async task => {
    let timer;
    try { return await Promise.race([task, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Per-file render deadline exceeded')), remaining()); })]); }
    finally { clearTimeout(timer); }
  };
  page.on('pageerror', e => errors.push(`JavaScript: ${safeMessage(e.message)}`));
  page.on('requestfailed', r => (resourceSeverity(r) === 'warning' ? warnings : errors).push(`Request failed: ${safeMessage(r.url())} (${safeMessage(r.failure()?.errorText)})`));
  page.on('response', r => { if (r.status() >= 400) (resourceSeverity(r.request()) === 'warning' ? warnings : errors).push(`HTTP ${r.status()}: ${safeMessage(r.url())}`); });
  try {
    await page.route('**/*', async route => {
      const req = route.request();
      if (!['GET', 'HEAD'].includes(req.method())) {
        errors.push(`Blocked non-read network request (${req.method()}); XML is never uploaded`);
        return route.abort();
      }
      try {
        const local = opts.assetDir && assetPath(opts.assetDir, req.url(), opts.baseUrl);
        return await (local ? route.fulfill({ path: local }) : route.continue());
      } catch (e) {
        errors.push(`Resource routing: ${safeMessage(e.message)}`);
        await route.abort().catch(() => {});
      }
    });
    await page.goto(new URL('export3.html', opts.baseUrl).href, { waitUntil: 'domcontentloaded', timeout: remaining() });
    await page.waitForFunction(() => typeof render === 'function' && typeof Graph !== 'undefined' && typeof Editor !== 'undefined', null, { timeout: remaining() });
    const xml = fs.readFileSync(job.source, 'utf8');
    const selected = await timed(page.evaluate(({ xml, selector, scale, border, maxPixels, maxSide, dpr }) => {
      const doc = new DOMParser().parseFromString(xml, 'application/xml');
      if (doc.querySelector('parsererror')) throw new Error('Invalid XML');
      const root = doc.documentElement;
      const pages = root.tagName === 'mxfile' ? Array.from(root.children).filter(n => n.tagName === 'diagram') : [];
      let model, id = null, name = null, index = 0;
      if (pages.length) {
        index = /^\d+$/.test(selector) ? Number(selector) : pages.findIndex(n => n.getAttribute('id') === selector);
        if (!pages[index]) throw new Error(`Page not found: ${selector}`);
        const selected = pages[index]; id = selected.getAttribute('id'); name = selected.getAttribute('name');
        // Official parser handles compressed diagrams. Only the selected model is rendered.
        const parsed = Editor.parseDiagramNode(selected);
        model = parsed?.documentElement || parsed;
      } else {
        if (root.tagName !== 'mxGraphModel' || selector !== '0') throw new Error('No matching diagram/mxGraphModel');
        model = root;
      }
      if (!model || model.tagName !== 'mxGraphModel') throw new Error('Could not decode selected diagram');
      // Reject extreme coordinates before the engine creates a huge document.
      for (const n of model.querySelectorAll('mxGeometry, mxPoint')) for (const a of ['x', 'y', 'width', 'height']) {
        if (n.hasAttribute(a) && (!Number.isFinite(Number(n.getAttribute(a))) || Math.abs(Number(n.getAttribute(a))) * scale * dpr > maxSide)) throw new Error('Geometry exceeds safe render limits; reduce --scale/--dpr');
      }
      if ((border * scale * dpr * 2) ** 2 > maxPixels) throw new Error('Border exceeds pixel limit');
      window.__drawioGraph = render({ xml: new XMLSerializer().serializeToString(model), format: 'png', scale, border, bg: '#ffffff' });
      if (!window.__drawioGraph?.getGraphBounds) throw new Error('Official render() did not return a graph');
      return { id, name, index };
    }, { xml, selector: opts.page, scale: opts.scale, border: opts.border, dpr: opts.dpr, maxPixels: MAX_PIXELS, maxSide: MAX_SIDE }));
    await page.waitForSelector('#LoadingComplete', { state: 'attached', timeout: remaining() });
    await timed(page.evaluate(async () => {
      await document.fonts.ready;
      const sources = new Set();
      for (const img of document.querySelectorAll('img')) if (img.currentSrc || img.src) sources.add(img.currentSrc || img.src);
      for (const img of document.querySelectorAll('svg image')) {
        const src = img.getAttribute('href') || img.getAttributeNS('http://www.w3.org/1999/xlink', 'href');
        if (src) sources.add(src);
      }
      for (const el of document.querySelectorAll('*')) {
        const bg = getComputedStyle(el).backgroundImage;
        for (const m of bg.matchAll(/url\(["']?(.*?)["']?\)/g)) sources.add(m[1]);
      }
      await Promise.all([...sources].map(src => new Promise((resolve, reject) => {
        const img = new Image(); img.onload = resolve; img.onerror = () => reject(new Error('An image could not be decoded/loaded (see resource diagnostics)')); img.src = src;
      })));
      const graph = window.__drawioGraph;
      const cells = Object.values(graph.getModel().cells);
      for (const cell of cells) {
        const shape = graph.getCellStyle(cell)?.shape;
        if (typeof shape === 'string' && shape.startsWith('mxgraph.')) {
          const registeredShape = typeof mxCellRenderer !== 'undefined' && mxCellRenderer.defaultShapes?.[shape];
          const stencil = typeof mxStencilRegistry !== 'undefined' && mxStencilRegistry.getStencil(shape);
          if (!registeredShape && !stencil) throw new Error(`Missing stencil/shape: ${shape}`);
        }
      }
      // Font metrics can change HTML label extents after initial render.
      graph.refresh();
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }));
    const geometry = await timed(page.evaluate(({ border, scale }) => {
      const graph = window.__drawioGraph;
      const b = graph.getGraphBounds();
      const c = graph.container.getBoundingClientRect();
      let left = b.x + c.left + scrollX, top = b.y + c.top + scrollY;
      let right = left + b.width, bottom = top + b.height;
      // Include label bounding boxes, particularly foreignObject/HTML labels.
      for (const state of Object.values(graph.view.states.map || {})) {
        const bb = state?.text?.boundingBox;
        if (bb) { left = Math.min(left, c.left + scrollX + bb.x); top = Math.min(top, c.top + scrollY + bb.y); right = Math.max(right, c.left + scrollX + bb.x + bb.width); bottom = Math.max(bottom, c.top + scrollY + bb.y + bb.height); }
      }
      for (const node of graph.container.querySelectorAll('foreignObject, .mxCellEditor, svg text')) {
        const r = node.getBoundingClientRect();
        if (r.width && r.height) { left = Math.min(left, r.left + scrollX); top = Math.min(top, r.top + scrollY); right = Math.max(right, r.right + scrollX); bottom = Math.max(bottom, r.bottom + scrollY); }
      }
      const pad = border * scale;
      const x = Math.floor(left - pad), y = Math.floor(top - pad);
      // render normally translates content to a positive border. If labels extend
      // farther, shift the graph container rather than silently clipping them.
      const dx = Math.max(0, -x), dy = Math.max(0, -y);
      if (dx || dy) { graph.container.style.position = 'relative'; graph.container.style.left = `${dx}px`; graph.container.style.top = `${dy}px`; }
      return { bounds: { x: b.x, y: b.y, width: b.width, height: b.height },
        clip: { x: x + dx, y: y + dy, width: Math.ceil(right + pad) - x, height: Math.ceil(bottom + pad) - y } };
    }, opts));
    checkDimensions(geometry.clip, opts.dpr);
    checkDimensions({ x: 0, y: 0, width: geometry.clip.x + geometry.clip.width, height: geometry.clip.y + geometry.clip.height }, opts.dpr);
    // Some Chrome/Playwright combinations silently clamp screenshots to the
    // viewport despite captureBeyondViewport. Fit the viewport too, and verify
    // the PNG header below; a successful API call alone is not evidence.
    await page.setViewportSize({ width: Math.ceil(geometry.clip.x + geometry.clip.width), height: Math.ceil(geometry.clip.y + geometry.clip.height) });
    await timed(page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
    if (errors.length) throw new Error(errors.join('\n'));
    const png = await page.screenshot({ type: 'png', clip: geometry.clip, captureBeyondViewport: true, timeout: remaining(), animations: 'disabled' });
    if (errors.length) throw new Error(errors.join('\n'));
    const pixels = validatePng(png, geometry.clip, opts.dpr);
    const report = { source: job.source, sourceSha256: crypto.createHash('sha256').update(xml).digest('hex'), output: job.png, page: selected, bounds: geometry.bounds, clip: geometry.clip,
      pixels, scale: opts.scale, dpr: opts.dpr, border: opts.border,
      browser: { selection: opts.browser, version: browser.version() }, warnings: [...new Set(warnings)], errors: [], renderedAt: new Date().toISOString() };
    return [[job.png, png], [job.report, JSON.stringify(report, null, 2) + '\n']];
  } catch (e) {
    throw new Error(`${job.source}: ${safeMessage(e.message)}${errors.length ? '\nResource/page diagnostics:\n' + [...new Set(errors)].join('\n') : ''}\nCheck network, --browser, --asset-dir and --timeout. No output published.`);
  } finally { await context.close(); }
}

async function main(args = process.argv.slice(2)) {
  const opts = parseArgs(args, configuration());
  if (opts.help) { console.log(HELP); return; }
  validateAssets(opts);
  const jobs = planOutputs(opts);
  if (!opts.doctor) for (const job of jobs) {
    const stat = fs.statSync(job.source);
    if (!stat.isFile() || stat.size > MAX_XML_BYTES) throw new Error(`Input must be a file <= 50 MiB: ${job.source}`);
    for (const dest of [job.png, job.report]) {
      if (fs.existsSync(dest) && (!opts.overwrite || !fs.lstatSync(dest).isFile())) throw new Error(`Destination exists (use --overwrite for regular files): ${dest}`);
      // Catch symlinked directory aliases and source/output collisions as well.
      let ancestor = path.dirname(dest);
      while (!fs.existsSync(ancestor)) ancestor = path.dirname(ancestor);
      const physical = path.resolve(fs.realpathSync(ancestor), path.relative(ancestor, dest));
      if (jobs.some(j => fs.realpathSync(j.source) === physical)) throw new Error(`Destination aliases an input: ${dest}`);
      job[dest === job.png ? 'physicalPng' : 'physicalReport'] = physical;
    }
  }
  if (!opts.doctor) {
    const physical = jobs.flatMap(j => [j.physicalPng, j.physicalReport]);
    if (new Set(physical).size !== physical.length) throw new Error('Output paths alias each other');
  }
  const pw = loadPlaywright(opts);
  let browser;
  try {
    browser = await pw.chromium.launch(launchOptions(opts));
    if (opts.doctor) {
      console.log(JSON.stringify({ node: process.version, playwright: 'available', browser: { selection: opts.browser, version: browser.version() }, assetDir: opts.assetDir || null,
        assets: opts.assetDir ? ['js/app.min.js', 'js/export.js', 'js/extensions.min.js'].map(file => ({ file, present: fs.existsSync(path.join(opts.assetDir, file)) })) : [],
        note: 'No rendering/network probe or installation performed; absent asset overrides use the network.' }, null, 2));
      return;
    }
    // All inputs must render successfully before publishing any output.
    const outputs = [];
    for (const job of jobs) outputs.push(...await renderFile(browser, opts, job));
    publish(outputs, opts.overwrite);
    for (const job of jobs) console.log(`${job.png}\n${job.report}`);
  } finally { if (browser) await browser.close(); }
}

module.exports = { parseArgs, planOutputs, checkDimensions, validatePng, dotenv, configuration, assetPath, safeMessage, resourceSeverity, launchOptions, publish, main, MAX_PIXELS, MAX_SIDE };
if (require.main === module) main().catch(e => { console.error(`drawio render: ${safeMessage(e.message)}`); process.exitCode = 1; });
