// Folds dist-offline/ (built with vite.offline.config.ts) into one self-contained HTML file: release/orka-offline.html.
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dist = path.join(root, 'dist-offline');
let html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
const read = (rel) => fs.readFileSync(path.join(dist, rel.replace(/^\.?\//, '')), 'utf8');

const scripts = [...html.matchAll(/<script type="module" crossorigin src="([^"]+)"><\/script>/g)];
const styles = [...html.matchAll(/<link rel="stylesheet" crossorigin href="([^"]+)">/g)];
if (scripts.length !== 1) throw new Error(`expected exactly one module script, found ${scripts.length}`);
const assets = fs.readdirSync(path.join(dist, 'assets'));
const extra = assets.filter((f) => !scripts.some((m) => m[1].endsWith(f)) && !styles.some((m) => m[1].endsWith(f)));
if (extra.length) throw new Error(`build left files that would not be inlined: ${extra.join(', ')}`);

let js = read(scripts[0][1]);
// Inside an inline <script>, "</script" would end the element and "<!--" … "<script" would change how it is parsed.
// "<\/script" means the same in JS strings, templates and regular expressions; "<!--" is checked, not rewritten.
js = js.replace(/<\/script/gi, '<\\/script');
if (/<!--/.test(js) && /<script/i.test(js)) throw new Error('bundle contains "<!--" and "<script": inline parsing would be unsafe');

html = html.replace(scripts[0][0], () => `<script type="module">${js}</script>`);
for (const m of styles) html = html.replace(m[0], () => `<style>${read(m[1])}</style>`);
// The web-app manifest and service worker need a server; a file opened from disk uses neither.
html = html.replace(/\s*<link rel="manifest"[^>]*>/, '');
if (/(src|href)="\.?\/?assets\//.test(html)) throw new Error('a reference to assets/ remains');

fs.mkdirSync(path.join(root, 'release'), { recursive: true });
const out = path.join(root, 'release', 'orka-offline.html');
fs.writeFileSync(out, html);
console.log(`${path.relative(root, out)}: ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
