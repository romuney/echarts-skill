#!/usr/bin/env node
// ============================================================================
// smoke.mjs — ПОВЕДЕНЧЕСКАЯ проверка <name>.chart.js в настоящем браузере.
//
// validate.py проверяет ФОРМУ кода: блоки, префиксы, запреты синтаксиса.
// Этот скрипт проверяет ПОВЕДЕНИЕ: смонтировался ли overlay, появляется ли
// тултип при наведении, ВИДЕН ли он на самом деле, гаснет ли, переживает ли
// перезапуск скрипта, что показывает пустой data.
//
// Он ловит ровно тот класс багов, который validate.py принципиально не видит:
// код формально верный, а на экране ничего нет (RETRO 44).
//
// ЗАПУСК:
//   node smoke.mjs <path>.chart.js
//   node smoke.mjs <path>.chart.js --mock rows.json   # свои данные вместо авто
//   node smoke.mjs <path>.chart.js --vs <path>.html   # сверка с макетом
//   node smoke.mjs <path>.chart.js --quiet            # только проблемы + итог
//   node smoke.mjs <path>.chart.js --keep             # не удалять временный стенд
//
// ДАННЫЕ. Берутся из <name>.mock.json рядом с чартом, либо из --mock,
// либо генерируются автоматически из CFG.fields. Автомок — грубый: он проверяет
// живость интерфейса, а не правильность цифр. Реальные значения кладите
// в <name>.mock.json (массив объектов в точной форме выдачи SQL).
//
// КОД ВОЗВРАТА: 0 — нет FAIL, 1 — есть FAIL, 2 — ошибка запуска.
// ============================================================================

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const R = [];
const pass = (id, m) => R.push([id, 'PASS', m]);
const fail = (id, m) => R.push([id, 'FAIL', m]);
const warn = (id, m) => R.push([id, 'WARN', m]);
const skip = (id, m) => R.push([id, 'N/A', m]);
const check = (id, ok, good, bad, asWarn) =>
  ok ? pass(id, good) : (asWarn ? warn(id, bad) : fail(id, bad));

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// ── аргументы ────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const flags = new Set();
const opts = {};
const paths = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--mock' || a === '--vs' || a === '--shots') { opts[a.slice(2)] = argv[++i]; continue; }
  if (a.startsWith('--')) { flags.add(a); continue; }
  paths.push(a);
}
const quiet = flags.has('--quiet');
const keep = flags.has('--keep');

if (!paths.length) {
  console.log('Укажи путь: node smoke.mjs <path>.chart.js [--mock rows.json] [--vs макет.html]');
  process.exit(2);
}
const chartPath = path.resolve(paths[0]);
if (!fs.existsSync(chartPath)) {
  console.log('Файл не найден: ' + chartPath);
  process.exit(2);
}

// ── playwright ───────────────────────────────────────────────────────────────
async function loadChromium() {
  for (const m of ['playwright', 'playwright-core']) {
    try { return (await import(m)).chromium; } catch { /* дальше */ }
  }
  try {
    const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
    for (const m of ['playwright', 'playwright-core']) {
      for (const f of ['index.mjs', 'index.js']) {
        const p = path.join(root, m, f);
        if (fs.existsSync(p)) return (await import(pathToFileURL(p).href)).chromium;
      }
    }
  } catch { /* нет npm — сдаёмся ниже */ }
  return null;
}

// ── мок-данные ───────────────────────────────────────────────────────────────
// Имена колонок берём из CFG.fields: это единственное место, где чарт
// объявляет, какие ключи он ждёт в data.
function extractFieldNames(src) {
  const m = /fields\s*:\s*\{/.exec(src);
  if (!m) return [];
  const open = src.indexOf('{', m.index + m[0].length - 1);
  let depth = 0, end = -1;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (!depth) { end = j; break; } }
  }
  if (end < 0) return [];
  const body = src.slice(open + 1, end);
  const out = [];
  for (const mm of body.matchAll(/['"]([\w.]+)['"]/g)) {
    if (!out.includes(mm[1])) out.push(mm[1]);
  }
  return out;
}

const NUMS = [13, 10, 9, 7, 6, 5, 4, 3, 2, 1];
const COLORS = ['#f2a8b8', '#c9a2ee', '#8fd3c7', '#f6c177'];
const DATES = ['2026-07-01', '2026-06-01', '2026-05-01'];

function mockValue(name, idx, row) {
  const n = name.toLowerCase();
  if (/colou?r/.test(n)) return COLORS[(idx + row) % COLORS.length];
  if (/(_dt$|date|month|period|_day|time)/.test(n)) return DATES[row % DATES.length];
  if (/(_nm$|name|title|label|_txt$|text|rule|descr|comment)/.test(n)) {
    return 'Значение ' + (idx + 1) + '.' + (row + 1);
  }
  if (/(_id$|_key$|_code$|key|code)/.test(n)) return 'k' + (row + 1);
  return Math.max(1, NUMS[idx % NUMS.length] - row);
}

function autoMock(fieldNames, rows) {
  const out = [];
  for (let r = 0; r < rows; r++) {
    const o = {};
    fieldNames.forEach((f, i) => { o[f] = mockValue(f, i, r); });
    out.push(o);
  }
  return out;
}

// ── стенд ────────────────────────────────────────────────────────────────────
// Повторяет окружение Proteus: хост с атрибутом [_echarts_instance_], canvas
// внутри, глобальные data и option. Ничего больше чарту не полагается.
function hostHTML(dataJson, chartHref) {
  return '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
    + '<style>html,body{margin:0;padding:0;background:#fff}</style></head><body>'
    + '<div _echarts_instance_="ec_smoke" style="width:820px;height:420px;position:relative">'
    + '<canvas width="820" height="420"></canvas></div>'
    + '<script>var data = ' + dataJson + '; var option = null;<\/script>'
    + '<script src="' + chartHref + '"><\/script>'
    + '</body></html>';
}

// ── зонд, который живёт в странице ───────────────────────────────────────────
// Ключевой момент — eff(): считает ЭФФЕКТИВНУЮ прозрачность с учётом предков.
// Наивный getComputedStyle(node).opacity врёт: у ребёнка внутри прозрачного
// родителя он вернёт '1', и невидимый тултип будет засчитан за видимый.
const PROBE = `(function () {
  function eff(el) {
    var op = 1, n = el;
    while (n && n.nodeType === 1) {
      var cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      var o = parseFloat(cs.opacity);
      if (!isNaN(o)) op *= o;
      n = n.parentElement;
    }
    return op;
  }
  function slice(x) { return Array.prototype.slice.call(x); }
  function tipish(el) {
    if (el.getAttribute && el.getAttribute('role') === 'tooltip') return true;
    var c = (el.className && el.className.toString()) || '';
    return /(^|[\\s_-])(tip|tooltip)([\\s_-]|$)/i.test(c);
  }
  function candidates() {
    var all = slice(document.querySelectorAll('[role="tooltip"],[class*="tip"],[class*="tooltip"]'))
      .filter(tipish);
    // берём только внешние узлы: .ns-tip-title внутри .ns-tip — не отдельный тултип
    return all.filter(function (n) {
      return !all.some(function (m) { return m !== n && m.contains(n); });
    });
  }
  window.__smoke = {
    tipNodes: function () { return candidates().length; },
    tip: function () {
      var best = null;
      candidates().forEach(function (n) {
        var r = n.getBoundingClientRect();
        var op = eff(n);
        var txt = (n.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!(op > 0.01 && r.width > 0 && r.height > 0 && txt.length > 0)) return;
        var cand = {
          op: Math.round(op * 100) / 100,
          w: Math.round(r.width), h: Math.round(r.height),
          x: Math.round(r.left), y: Math.round(r.top),
          cx: Math.round(r.left + r.width / 2), cy: Math.round(r.top + r.height / 2),
          text: txt.slice(0, 100),
          cls: ((n.className && n.className.toString()) || '').slice(0, 60)
        };
        if (!best || cand.w * cand.h > best.w * best.h) best = cand;
      });
      return best;
    },
    triggers: function (rootSel) {
      var root = rootSel ? document.querySelector(rootSel) : document;
      if (!root) return [];
      return slice(root.querySelectorAll('[data-tip],[data-kind],[data-action]')).map(function (n, i) {
        var r = n.getBoundingClientRect();
        return {
          i: i,
          label: (n.getAttribute('data-tip') || n.getAttribute('data-kind')
                  || n.getAttribute('data-action') || '?')
                 + (n.getAttribute('data-key') ? ':' + n.getAttribute('data-key') : ''),
          cx: Math.round(r.left + r.width / 2), cy: Math.round(r.top + r.height / 2),
          w: Math.round(r.width), h: Math.round(r.height),
          tag: n.tagName.toLowerCase()
        };
      }).filter(function (t) { return t.w > 0 && t.h > 0; });
    },
    overlay: function (ns) {
      var host = document.querySelector('[_echarts_instance_]');
      var ovs = document.querySelectorAll('.' + ns + '-overlay');
      var ov = ovs[0] || null;
      var cvs = slice(document.querySelectorAll('canvas'));
      // textContent тянет в себя содержимое <style> — это не видимый текст.
      var visibleText = '';
      if (ov) {
        var clone = ov.cloneNode(true);
        slice(clone.querySelectorAll('style,script')).forEach(function (s) {
          s.parentNode.removeChild(s);
        });
        visibleText = (clone.textContent || '').replace(/\\s+/g, ' ').trim();
      }
      return {
        count: ovs.length,
        inHost: !!(ov && host && host.contains(ov)),
        html: ov ? ov.innerHTML.length : 0,
        text: visibleText.slice(0, 200),
        rootFound: !!document.querySelector('.' + ns + '-root'),
        canvasHidden: cvs.length === 0 || cvs.every(function (c) {
          return getComputedStyle(c).display === 'none';
        }),
        tipInBody: !!document.querySelector('body > [class*="tip"]')
      };
    },
    overlayHTML: function (ns) {
      var ov = document.querySelector('.' + ns + '-overlay');
      return ov ? ov.innerHTML : '';
    },
    // Инвентарь видимого: то, что можно сравнить у макета и у чарта, не зная
    // ни их имён классов, ни их данных. Цифры в текстах маскируются (13 -> ##),
    // поэтому подписи сравниваются, а значения — нет.
    inventory: function (rootSel) {
      var root = rootSel ? document.querySelector(rootSel) : document.body;
      if (!root) return null;
      var els = slice(root.querySelectorAll('*'));
      var texts = {}, colors = {}, kinds = {};
      var colored = 0, buttons = 0, shown = 0;
      els.forEach(function (el) {
        var tag = el.tagName.toLowerCase();
        if (tag === 'style' || tag === 'script') return;
        var cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        shown++;
        if (tag === 'button') buttons++;
        var k = el.getAttribute('data-tip') || el.getAttribute('data-kind')
                || el.getAttribute('data-action');
        if (k) kinds[k] = 1;
        var bg = cs.backgroundColor;
        var r = el.getBoundingClientRect();
        if (bg && bg !== 'transparent' && bg.replace(/ /g, '') !== 'rgba(0,0,0,0)'
            && r.width > 2 && r.height > 2) {
          colored++;
          colors[bg] = 1;
        }
        var own = '';
        slice(el.childNodes).forEach(function (n) {
          if (n.nodeType === 3) own += n.nodeValue;
        });
        own = own.replace(/\\s+/g, ' ').trim();
        if (own) texts[own.replace(/\\d+([.,]\\d+)?/g, '#')] = 1;
      });
      return {
        texts: Object.keys(texts).sort(),
        colors: Object.keys(colors).sort(),
        kinds: Object.keys(kinds).sort(),
        colored: colored, buttons: buttons, shown: shown
      };
    }
  };
})()`;

// ── прогон ───────────────────────────────────────────────────────────────────
async function newPage(browser, errs) {
  const page = await browser.newPage({ viewport: { width: 1000, height: 620 } });
  page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  return page;
}

async function probeTooltips(page, prefix, rootSel) {
  await page.evaluate(PROBE);
  const triggers = await page.evaluate(
    (s) => window.__smoke.triggers(s), rootSel || null);

  if (!triggers.length) {
    skip(prefix + '1', 'триггеров тултипа ([data-tip]/[data-kind]/[data-action]) в разметке нет');
    return { triggers: [], visible: 0, results: [] };
  }

  const CAP = 12;
  const used = triggers.slice(0, CAP);
  if (triggers.length > CAP) {
    warn(prefix + '0', 'триггеров ' + triggers.length + ', проверены первые ' + CAP
      + ' — остальные НЕ проверялись');
  }

  const results = [];
  for (const t of used) {
    await page.mouse.move(2, 2);
    await wait(60);
    await page.mouse.move(t.cx, t.cy);
    await page.mouse.move(t.cx + 1, t.cy); // добираем mousemove-реализации
    await wait(220);
    const tip = await page.evaluate(() => window.__smoke.tip());
    results.push({ t, tip });
  }

  const visible = results.filter((r) => r.tip).length;
  const dead = results.filter((r) => !r.tip).map((r) => r.t.label);

  check(prefix + '1', visible > 0,
    'тултип появляется при наведении (' + visible + ' из ' + used.length + ' триггеров)',
    'НИ ОДИН из ' + used.length + ' триггеров не показал видимый тултип. '
      + 'Узел мог отрисоваться, но быть прозрачным/нулевого размера/без текста');

  check(prefix + '2', dead.length === 0,
    'тултип показан на всех проверенных триггерах',
    'без тултипа: ' + dead.slice(0, 6).join(', '), true);

  // T3/T4 имеют смысл, только если хоть что-то показалось: иначе они «проходят»
  // на пустом месте и создают ложную зелёную картину.
  if (!visible) {
    skip(prefix + '3', 'позиция не проверялась: видимого тултипа не было');
    skip(prefix + '4', 'гашение не проверялось: видимого тултипа не было');
    return { triggers: used, visible, results };
  }

  // Тултип обязан помещаться во вьюпорт целиком (RETRO 26).
  const vp = await page.viewportSize();
  const out = results.filter((r) => r.tip && (
    r.tip.x < 0 || r.tip.y < 0
    || r.tip.x + r.tip.w > vp.width + 1 || r.tip.y + r.tip.h > vp.height + 1));
  check(prefix + '3', out.length === 0,
    'тултип не выходит за вьюпорт',
    'вылезает за экран (RETRO 26, 31): ' + out.map((r) => r.t.label).join(', '));

  // Гаснет ли после ухода курсора.
  await page.mouse.move(2, 2);
  await wait(250);
  const lingering = await page.evaluate(() => window.__smoke.tip());
  check(prefix + '4', !lingering,
    'тултип гаснет после ухода курсора',
    'тултип остался висеть после mouseout: "' + (lingering ? lingering.text : '') + '"');

  return { triggers: used, visible, results };
}

async function main() {
  const chromium = await loadChromium();
  if (!chromium) {
    console.log('\n' + chartPath);
    console.log('-'.repeat(72));
    console.log(' -  B0   N/A   playwright не найден — поведенческая проверка ПРОПУЩЕНА');
    console.log('-'.repeat(72));
    console.log('ЭТО НЕ ПРОВАЛ ПРОВЕРКИ. Код возврата 2 = «не запускалась»;');
    console.log('1 = «провалена»; 0 = «пройдена». Сдачу это не блокирует.');
    console.log('');
    console.log('Что остаётся в силе: статические проверки validate.py. Класс багов');
    console.log('«код верный, а на экране пусто» они закрывают частично — T5 (скрытие');
    console.log('снимается), T6 (hover не пересобирает), S14b (render рисует),');
    console.log('S18 (состояние связано). Полностью его видит только браузер.');
    console.log('');
    console.log('Включить, один раз, ~150 МБ:');
    console.log('    npm i -D playwright && npx playwright install chromium');
    console.log('  или глобально:');
    console.log('    npm i -g playwright && npx playwright install chromium');
    console.log('');
    console.log('В отчёте SELF_CHECK проставь B1-B5 = N/A с причиной «нет playwright»');
    console.log('и скажи об этом пользователю прямо: часть проверок не выполнялась.');
    return 2;
  }

  const src = fs.readFileSync(chartPath, 'utf8');
  const nsM = /\bns\s*:\s*['"]([\w-]+)['"]/.exec(src);
  const ns = nsM ? nsM[1] : 'pvt';
  const noDataM = /noData\s*:\s*['"]([^'"]*)['"]/.exec(src);
  const noDataText = noDataM ? noDataM[1] : null;

  // данные
  const base = chartPath.replace(/\.chart\.js$/, '');
  let rows = null, mockSource = '';
  const mockPath = opts.mock ? path.resolve(opts.mock) : base + '.mock.json';
  if (fs.existsSync(mockPath)) {
    try {
      rows = JSON.parse(fs.readFileSync(mockPath, 'utf8'));
      mockSource = path.basename(mockPath);
    } catch (e) {
      console.log('Не разобрался в ' + mockPath + ': ' + e.message);
      return 2;
    }
  }
  if (!rows) {
    const fieldNames = extractFieldNames(src);
    if (!fieldNames.length) {
      console.log('CFG.fields пуст и мока нет — проверять не на чем. '
        + 'Заполни CFG.fields или положи ' + path.basename(base) + '.mock.json');
      return 2;
    }
    rows = autoMock(fieldNames, 2);
    mockSource = 'автомок из CFG.fields (' + fieldNames.length + ' колонок)';
  }
  if (!Array.isArray(rows) || !rows.length) {
    console.log('Мок пуст — нужен непустой массив строк.');
    return 2;
  }

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pvt-smoke-'));
  const chartHref = pathToFileURL(chartPath).href;
  const hostPath = path.join(tmp, 'host.html');
  const emptyPath = path.join(tmp, 'empty.html');
  fs.writeFileSync(hostPath, hostHTML(JSON.stringify(rows), chartHref), 'utf8');
  fs.writeFileSync(emptyPath, hostHTML('[]', chartHref), 'utf8');

  const browser = await chromium.launch();
  try {
    // ── ФАЗА 1: обычные данные ───────────────────────────────────────────────
    const errs = [];
    const page = await newPage(browser, errs);
    await page.goto(pathToFileURL(hostPath).href);
    await wait(400);
    await page.evaluate(PROBE);

    const ov = await page.evaluate((n) => window.__smoke.overlay(n), ns);

    check('E1', errs.length === 0, 'ошибок в консоли нет',
      'ошибки в браузере: ' + errs.slice(0, 3).join(' | '));
    check('E2', ov.count === 1 && ov.inHost && ov.html > 50,
      'overlay смонтирован в хост, разметка не пустая (' + ov.html + ' символов)',
      'overlay не смонтирован как надо: найдено ' + ov.count
        + ', внутри хоста: ' + ov.inHost + ', длина разметки: ' + ov.html);
    check('E3', !/Ошибка графика/i.test(ov.text),
      'ветка catch не сработала',
      'в overlay текст аварийного catch: ' + ov.text.slice(0, 120));
    check('E4', ov.canvasHidden, 'canvas скрыт',
      'canvas виден — eCharts рисует поверх/под overlay');
    check('E5', ov.rootFound, 'корень .' + ns + '-root отрисован',
      'корня .' + ns + '-root в DOM нет — разметка не построена');

    // Снимаем инвентарь ДО кликов: клик меняет состояние и картину.
    const invChart = await page.evaluate(
      (s) => window.__smoke.inventory(s), '.' + ns + '-overlay');
    if (opts.shots) {
      fs.mkdirSync(opts.shots, { recursive: true });
      await page.screenshot({ path: path.join(opts.shots, 'chart.png'), fullPage: false });
    }

    // ── тултипы ──────────────────────────────────────────────────────────────
    const tipNodes = await page.evaluate(() => window.__smoke.tipNodes());
    const t = tipNodes > 0
      ? await probeTooltips(page, 'ET', '.' + ns + '-overlay')
      : (skip('ET1', 'узлов тултипа на странице нет — в этом графике тултипа не предусмотрено'),
         { triggers: [], visible: 0, results: [] });

    // ── B6: тултип виден В ПИКСЕЛЯХ ──────────────────────────────────────────
    // Единственная проверка, которую нельзя обмануть вычисленными стилями:
    // снимаем один и тот же кусок экрана с тултипом и без. Одинаковые байты —
    // значит на экран ничего не легло.
    const firstVisible = t.results.find((r) => r.tip);
    if (firstVisible) {
      const vp = await page.viewportSize();
      const cx = Math.min(Math.max(firstVisible.tip.cx, 5), vp.width - 6);
      const cy = Math.min(Math.max(firstVisible.tip.cy, 5), vp.height - 6);
      const clip = { x: cx - 4, y: cy - 4, width: 8, height: 8 };
      await page.mouse.move(2, 2); await wait(250);
      const off = await page.screenshot({ clip });
      await page.mouse.move(firstVisible.t.cx, firstVisible.t.cy);
      await page.mouse.move(firstVisible.t.cx + 1, firstVisible.t.cy);
      await wait(300);
      const on = await page.screenshot({ clip });
      check('E6', !off.equals(on),
        'тултип реально отрисован на экране (пиксели изменились)',
        'пиксели в центре тултипа не изменились — узел есть, а на экране его нет');
      await page.mouse.move(2, 2); await wait(150);
    } else if (t.triggers.length) {
      fail('E6', 'нечего снимать: ни один тултип не стал видимым');
    } else {
      skip('E6', 'тултипов нет');
    }

    // ── E12: hover не пересобирает разметку ──────────────────────────────────
    // Полный render() на наведении пересоздаёт DOM под курсором — тултип
    // моргает (RETRO 20). Проверяем до кликов: клик состояние меняет законно.
    if (t.triggers.length) {
      await page.mouse.move(2, 2);
      await wait(160);
      const beforeHover = await page.evaluate((n) => window.__smoke.overlayHTML(n), ns);
      const tg = t.triggers[t.triggers.length - 1];
      await page.mouse.move(tg.cx, tg.cy);
      await page.mouse.move(tg.cx + 1, tg.cy);
      await wait(260);
      const afterHover = await page.evaluate((n) => window.__smoke.overlayHTML(n), ns);
      check('E12', beforeHover === afterHover,
        'hover не пересобирает разметку',
        'наведение изменило разметку overlay. Если это подсветка через classList — '
          + 'норма; если полный render() — тултип будет мигать (RETRO 20)', true);
      await page.mouse.move(2, 2);
      await wait(160);
    } else {
      skip('E12', 'триггеров нет');
    }

    // ── E7: клик пересобирает разметку ───────────────────────────────────────
    // Ловит «фиктивный render()», который не вызывает buildHTML(): интерактив
    // формально есть, но на экране после клика ничего не меняется (RETRO 45).
    const clickable = t.triggers.filter((x) => x.tag === 'button' || /:/.test(x.label));
    if (clickable.length) {
      let changed = false;
      const before = await page.evaluate((n) => window.__smoke.overlayHTML(n), ns);
      for (const c of clickable.slice(0, 3)) {
        await page.mouse.click(c.cx, c.cy);
        await wait(200);
        const after = await page.evaluate((n) => window.__smoke.overlayHTML(n), ns);
        if (after !== before) { changed = true; break; }
      }
      check('E7', changed, 'клик перерисовывает разметку',
        'ни один клик не изменил разметку overlay — вероятно, render() не вызывает '
          + 'buildHTML() либо состояние пишется мимо state (RETRO 45, 46)', true);
      await page.keyboard.press('Escape');
      await page.mouse.click(4, 600);
      await wait(150);
    } else {
      skip('E7', 'кликабельных триггеров нет');
    }

    // ── B8: перезапуск скрипта (Proteus делает это на каждой перерисовке) ────
    const errsBefore = errs.length;
    await page.addScriptTag({ path: chartPath });
    await wait(400);
    const ov2 = await page.evaluate((n) => window.__smoke.overlay(n), ns);
    const tipNodes2 = await page.evaluate(() => window.__smoke.tipNodes());
    check('E8', ov2.count === 1 && errs.length === errsBefore,
      'повторный запуск скрипта не плодит overlay и не роняет',
      'после повторного запуска overlay: ' + ov2.count + ' шт., новых ошибок: '
        + (errs.length - errsBefore) + ' — старый overlay не удаляется (RETRO 4)');
    check('E9', tipNodes === 0 || tipNodes2 <= tipNodes,
      'узел тултипа не дублируется при перезапуске',
      'узлов тултипа было ' + tipNodes + ', стало ' + tipNodes2 + ' — старый не удаляется');

    // ── B10: ресайз ──────────────────────────────────────────────────────────
    const errsResize = errs.length;
    await page.setViewportSize({ width: 520, height: 420 });
    await wait(350);
    const ov3 = await page.evaluate((n) => window.__smoke.overlay(n), ns);
    check('E10', errs.length === errsResize && ov3.html > 50,
      'ресайз переживается без ошибок',
      'после ресайза ошибок: ' + (errs.length - errsResize) + ', разметка: ' + ov3.html);

    await page.close();

    // ── ФАЗА 2: пустые данные ────────────────────────────────────────────────
    const errsEmpty = [];
    const page2 = await newPage(browser, errsEmpty);
    await page2.goto(pathToFileURL(emptyPath).href);
    await wait(350);
    await page2.evaluate(PROBE);
    const ovE = await page2.evaluate((n) => window.__smoke.overlay(n), ns);
    const emptyOk = errsEmpty.length === 0
      && (!noDataText || ovE.text.indexOf(noDataText) !== -1);
    check('E11', emptyOk, 'пустой data показывает "' + (noDataText || '—') + '" без ошибок',
      'пустой data: ошибок ' + errsEmpty.length + ', текст overlay: "'
        + ovE.text.slice(0, 80) + '"' + (noDataText ? ' (ждали "' + noDataText + '")' : ''));
    await page2.close();

    // ── ФАЗА 3: сверка с макетом ─────────────────────────────────────────────
    if (opts.vs) {
      const vsPath = path.resolve(opts.vs);
      if (!fs.existsSync(vsPath)) {
        warn('EV1', 'макет не найден: ' + vsPath);
      } else {
        const errsVs = [];
        const page3 = await newPage(browser, errsVs);
        await page3.goto(pathToFileURL(vsPath).href);
        await wait(400);
        await page3.evaluate(PROBE);
        const invMock = await page3.evaluate(() => window.__smoke.inventory(null));
        if (opts.shots) {
          await page3.screenshot({ path: path.join(opts.shots, 'mockup.png'), fullPage: false });
        }
        const m = await probeTooltips(page3, 'EM', null);
        await page3.close();

        const nChart = t.triggers.length, nMock = m.triggers.length;
        check('EV1', nChart >= nMock,
          'триггеров тултипа не меньше, чем в макете (' + nChart + ' vs ' + nMock + ')',
          'в макете ' + nMock + ' триггеров, в чарте ' + nChart
            + ' — часть интерактива макета потеряна', true);
        check('EV2', !(m.visible > 0 && t.visible === 0),
          'тултип работает там же, где в макете',
          'в макете тултип показывается (' + m.visible + '), в чарте — ни разу: '
            + 'перенос интерактива сломан');

        // ── инвентарь: что есть в макете и чего нет в чарте ──────────────────
        // Проверяет не «похоже ли», а «не потеряно ли»: молча выпавший элемент
        // макета не ломает ни синтаксис, ни валидатор, и всплывает у пользователя
        // (RETRO 41). Сравниваем структуру, а не значения.
        if (invChart && invMock) {
          const lostKinds = invMock.kinds.filter((k) => invChart.kinds.indexOf(k) === -1);
          check('EV3', lostKinds.length === 0,
            'все виды триггеров макета есть в чарте',
            'в чарте нет триггеров макета: ' + lostKinds.join(', '));

          check('EV4', invChart.colored >= invMock.colored,
            'цветных элементов не меньше, чем в макете ('
              + invChart.colored + ' vs ' + invMock.colored + ')',
            'в макете ' + invMock.colored + ' цветных элементов, в чарте '
              + invChart.colored + ' — часть баров/плашек не перенесена', true);

          const lostColors = invMock.colors.filter((c) => invChart.colors.indexOf(c) === -1);
          check('EV5', lostColors.length === 0,
            'палитра макета перенесена полностью',
            'цвета макета, которых нет в чарте: ' + lostColors.slice(0, 6).join(' '), true);

          // Тексты: цифры замаскированы, поэтому расходятся либо подписи
          // интерфейса (это потеря), либо строки из данных (это норма).
          const lostTexts = invMock.texts.filter((x) => invChart.texts.indexOf(x) === -1);
          const extraTexts = invChart.texts.filter((x) => invMock.texts.indexOf(x) === -1);
          check('EV6', lostTexts.length === 0,
            'все подписи макета встречаются в чарте',
            'нет в чарте (' + lostTexts.length + '): '
              + lostTexts.slice(0, 5).map((s) => '«' + s.slice(0, 40) + '»').join(', ')
              + '. Строки из данных здесь — норма, подписи интерфейса — потеря', true);
          if (extraTexts.length) {
            warn('EV7', 'есть в чарте, но нет в макете (' + extraTexts.length + '): '
              + extraTexts.slice(0, 5).map((s) => '«' + s.slice(0, 40) + '»').join(', ')
              + '. Проверь, не выдуманный ли это текст (RETRO 12)');
          } else {
            pass('EV7', 'в чарте нет текстов, которых не было бы в макете');
          }
        }
      }
    }
  } finally {
    await browser.close();
    if (!keep) fs.rmSync(tmp, { recursive: true, force: true });
  }

  // ── отчёт ──────────────────────────────────────────────────────────────────
  const w = Math.max(...R.map(([id]) => id.length));
  const fails = R.filter(([, s]) => s === 'FAIL').length;
  const warns = R.filter(([, s]) => s === 'WARN').length;
  const nas = R.filter(([, s]) => s === 'N/A').length;
  const mark = { PASS: 'v', FAIL: 'X', WARN: '!', 'N/A': '-' };

  console.log('\n' + chartPath);
  console.log('данные: ' + mockSource);
  console.log('-'.repeat(72));
  let shown = 0;
  for (const [id, st, msg] of R) {
    if (quiet && st === 'PASS') continue;
    shown++;
    console.log(' ' + mark[st] + '  ' + id.padEnd(w) + '  ' + st.padEnd(4) + '  ' + msg);
  }
  if (quiet && !shown) console.log(' всё чисто');
  console.log('-'.repeat(72));
  console.log('Итог: ' + (R.length - fails - warns - nas) + '/' + R.length
    + ' PASS, ' + warns + ' WARN, ' + nas + ' N/A, ' + fails + ' FAIL');
  if (fails) console.log('\nСДАВАТЬ НЕЛЬЗЯ: график не работает в браузере, а не «на вид».');
  if (keep) console.log('Стенд оставлен: ' + tmp);
  return fails ? 1 : 0;
}

main().then((c) => process.exit(c)).catch((e) => {
  console.log('smoke.mjs упал: ' + (e && e.stack || e));
  process.exit(2);
});
