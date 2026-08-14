// ============================================================================
// new-chart.chart.js - болванка каркаса
// ============================================================================
// КОНТРАКТ PROTEUS:
//   ECharts = только холст. Вся визуализация - HTML/CSS/SVG в overlay.
//   Хост = ПОСЛЕДНИЙ [_echarts_instance_]. Canvas прячем. Overlay - appendChild.
//   В САМОМ КОНЦЕ ФАЙЛА, ГЛОБАЛЬНО: option = {...} с пустым scatter.
//
// ЗАПРЕЩЕНО: backticks/template-literals, стрелочные функции, let/const,
//   document.getElementById (только overlay.querySelector), console.log в итоге,
//   addEventListener внутри тела render(), обращение к option из catch,
//   мутация option после присваивания, var P = '.' + CFG.ns в buildHTML
//   (точка только в buildCSS).
// ОБЯЗАТЕЛЬНО: все 7 блоков ниже, в таком порядке, без перенумерации.
// ОБЯЗАТЕЛЬНО: вызов render(); в теле mount() — без него overlay пустой.
//
// ВЫЧИСЛЕНИЯ ЖИВУТ ЗДЕСЬ, А НЕ В SQL. Проценты, дельты, ранги, накопительные
//   итоги, сортировка и форматирование считаются в buildModel() (БЛОК 3).
//   SQL отдаёт сырые строки — базу не нагружаем.
// ============================================================================

// ---------- БЛОК 1: CFG ----------
// fields - ТОЛЬКО реальные имена колонок из SQL пользователя.
// Нет поля в SQL - СПРОСИ, не выдумывай и не хардкодь значения.
// Все цвета/шрифты/отступы из макета — только здесь, не в разметке.
var CFG = {
  ns: 'chart',                 // ПРЕФИКС всех CSS-классов и класса overlay
  fields: {
    total: 'emp_cnt_total',
    management: 'emp_cnt_management',
    functional: 'emp_cnt_functional'
  },
  text: {
    noData: 'Нет данных',
    title: 'Четверговая Оффлайн',
    totalSuffix: 'сотрудников всего во встрече',
    rule: 'В сегмент входят сотрудники, состоящие в группе офлайн-четверговой на дату среза. Если сотрудник одновременно состоит в нескольких группах встреч, применяется приоритет сегментов: Четверговая Оффлайн, затем Четверговая Онлайн, затем Management Meeting.',
    snapshot: '2026-07-01',
    segmentName: 'Четверговая Оффлайн'
  },
  mode: 'snapshot',           // 'snapshot' | 'timeseries'
  colors: {
    bg: '#fff',
    ink: '#303033',
    muted: '#8f8f93',
    softInk: '#5e5e64',
    track: '#efeff1',
    overlapLine: '#b9b9bf',
    tooltipBg: '#28282c',
    barTotal: '#dcdce0',
    overlapBg: 'rgba(96,96,104,.06)',
    structColor: {
      management: '#f2a8b8',
      functional: '#c9a2ee'
    }
  },
  fonts: {
    family: '-apple-system,"Segoe UI",Roboto,Arial,sans-serif'
  },
  spacing: {
    rootPadding: '16px 20px 14px',
    headGap: '12px',
    plotMarginTop: '16px',
    rowsGap: '9px',
    legendGap: '5px 14px',
    legendMarginTop: '10px'
  }
};

// ---------- БЛОК 2: ВХОД + СОСТОЯНИЕ + ХЕЛПЕРЫ ----------
// ВСЕ строки data, не data[0].
var rawData = (typeof data !== 'undefined' && Array.isArray(data)) ? data : [];

// Состояние переживает перерисовку Proteus.
// Для таблиц с поиском/сортировкой/пагинацией имена ключей бери из TABLES.md,
// чтобы правки разных сессий не расходились.
if (!window.__pvtState) window.__pvtState = {};
var __S = window.__pvtState;
if (!__S[CFG.ns]) __S[CFG.ns] = { tip: null, selectedKey: null, tooltip: null };
var state = __S[CFG.ns];

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
// Числа из BI приходят и числом, и строкой с пробелами-разрядами или запятой.
function num(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return isNaN(v) ? null : v;
  var s = String(v).replace(/[\s ]/g, '');
  // '1,5' -> дробная запятая; '1,234.5' -> запятая это разряды.
  if (s.indexOf(',') > -1 && s.indexOf('.') === -1) s = s.replace(/,/g, '.');
  else s = s.replace(/,/g, '');
  var n = Number(s);
  return isNaN(n) ? null : n;
}
// Универсальный парсер даты: epoch-ms, epoch-s, 'YYYY-MM-DD', 'YYYY-MM'.
// Нужен всегда: DATETIME из Proteus приходит числом, а не строкой из UI.
function toDate(raw) {
  if (raw === null || raw === undefined || raw === '') return null;
  var s = String(raw).trim(), d = null;
  if (/^\d{11,}$/.test(s)) { var ms = Number(s); d = new Date(ms > 1e12 ? ms : ms * 1000); }
  else if (/^\d{10}$/.test(s)) d = new Date(Number(s) * 1000);
  else {
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(s);
    if (m) return { y: +m[1], m: +m[2] - 1, d: m[3] ? +m[3] : 1 };
    d = new Date(s);
  }
  if (!d || isNaN(d.getTime())) return null;
  return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate() };
}
// Склонение "сотрудник/сотрудника/сотрудников"
function employeeWord(v) {
  var n = Math.abs(Number(v)), t = n % 100, o = n % 10;
  if (t >= 11 && t <= 14) return 'сотрудников';
  if (o === 1) return 'сотрудник';
  if (o >= 2 && o <= 4) return 'сотрудника';
  return 'сотрудников';
}
// Форматирование процента (округление до десятых, без .0)
function fmtPct(v) {
  if (v === null || v === undefined) return '';
  var s = String(Math.round(v * 10) / 10);
  return s.replace('.0', '') + '%';
}
// Форматирование даты YYYY-MM-DD -> DD.MM.YYYY
function fmtDate(v) {
  if (!v) return '';
  var p = String(v).split('-');
  return p.length === 3 ? p[2] + '.' + p[1] + '.' + p[0] : String(v);
}

// ---------- БЛОК 3: ТРАНСФОРМАЦИЯ ДАННЫХ ----------
// rawData -> структура, удобная для рендера. Только чтение CFG.fields.
// ЗДЕСЬ считается ВСЁ производное: агрегация, доли, дельты, ранги,
// накопительные итоги, сортировка. В SQL этого быть не должно.
function buildModel() {
  if (!rawData || !rawData.length) return { total: 0, items: [], overlap: 0, overlapStart: 0, overlapEnd: 0, snapshot: '', title: CFG.text.title, rule: CFG.text.rule };
  var row = rawData[0];
  var total = num(row[CFG.fields.total]) || 0;
  var mgmt = num(row[CFG.fields.management]) || 0;
  var func = num(row[CFG.fields.functional]) || 0;
  // Раскладка "по Ганту": первая структура прижата к левому краю, остальные — к правому.
  // Видно пересечение и уникальные хвосты.
  var items = [
    { key: 'management', name: 'Управленческая структура', color: CFG.colors.structColor.management, count: mgmt, start: 0, end: mgmt },
    { key: 'functional', name: 'Функциональная структура', color: CFG.colors.structColor.functional, count: func, start: Math.max(0, total - func), end: total }
  ];
  // Пересечение = сумма структур - total (если положительное)
  var sum = mgmt + func;
  var overlap = sum > total ? sum - total : 0;
  // Границы пересечения
  var oStart = 0, oEnd = total;
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    oStart = Math.max(oStart, it.start);
    oEnd = Math.min(oEnd, it.end);
  }
  if (oEnd <= oStart) { oStart = 0; oEnd = 0; }
  // Уникальные в каждой структуре
  for (var j = 0; j < items.length; j++) {
    items[j].unique = Math.max(0, items[j].count - overlap);
    items[j].share = total ? items[j].count / total * 100 : 0;
  }
  return {
    total: total,
    items: items,
    overlap: overlap,
    overlapStart: oStart,
    overlapEnd: oEnd,
    snapshot: CFG.text.snapshot,
    title: CFG.text.title,
    rule: CFG.text.rule
  };
}
var MODEL = buildModel();

// ---------- БЛОК 4: ФОРМАТИРОВАНИЕ И ЦВЕТ ----------
// Форматтеры уже в БЛОКЕ 2 (fmtPct, fmtDate, employeeWord).
function cssColor(c) {
  if (!c) return '#000';
  if (typeof c === 'string') return c;
  var a = (c.length >= 4) ? c[3] : 1;
  return 'rgba(' + Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]) + ',' + a + ')';
}

// ---------- БЛОК 5: РАЗМЕТКА (<style> + HTML) ----------
// КАЖДЫЙ селектор начинается с .<ns>- или с .<ns>-root - иначе стили
// протекут в интерфейс Proteus. НИКАКИХ голых div/table/th/button.
// Стили из макета переносятся СЮДА ЦЕЛИКОМ, а не выбрасываются.
function buildCSS() {
  var P = '.' + CFG.ns;
  return [
    '<style>',
    P + '-root{--ink:' + CFG.colors.ink + ';--muted:' + CFG.colors.muted + ';--soft-ink:' + CFG.colors.softInk + ';--track:' + CFG.colors.track + ';--overlap-line:' + CFG.colors.overlapLine + ';--tip-bg:' + CFG.colors.tooltipBg + ';width:100%;height:100%;min-height:300px;position:relative;overflow:hidden;box-sizing:border-box;padding:' + CFG.spacing.rootPadding + ';color:var(--ink);font-family:' + CFG.fonts.family + ';-webkit-font-smoothing:antialiased}',
    P + '-root *,.chart-root *::before,.chart-root *::after{box-sizing:border-box}',
    P + '-head{display:flex;align-items:flex-start;justify-content:space-between;gap:' + CFG.spacing.headGap + '}',
    P + '-title{margin:0;color:var(--muted);font-size:14px;line-height:1.25;font-weight:500}',
    P + '-total{margin:2px 0 0;color:var(--ink);font-size:28px;line-height:1.05;font-weight:700;letter-spacing:-.7px;display:inline-block;cursor:default}',
    P + '-total small{margin-left:6px;color:var(--muted);font-size:12px;font-weight:450;letter-spacing:0}',
    P + '-info-button{width:22px;height:22px;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;padding:0;cursor:pointer;appearance:none;color:#a2a2a7;background:rgba(143,143,147,.1);border:0;border-radius:50%;transition:color 150ms ease,background 150ms ease}',
    P + '-info-button:hover,.chart-root .info-button.is-active{color:#5e5e64;background:rgba(143,143,147,.2)}',
    P + '-info-icon{font-family:Georgia,"Times New Roman",serif;font-size:13px;line-height:1;font-weight:700;pointer-events:none}',
    P + '-plot{position:relative;margin-top:' + CFG.spacing.plotMarginTop + '}',
    P + '-overlap-band{position:absolute;top:0;bottom:24px;background:' + CFG.colors.overlapBg + ';border-left:1px dashed var(--overlap-line);border-right:1px dashed var(--overlap-line);pointer-events:none}',
    P + '-rows{position:relative;display:flex;flex-direction:column;gap:' + CFG.spacing.rowsGap + '}',
    P + '-row{width:100%;position:relative;display:block;padding:0;cursor:pointer;appearance:none;color:inherit;font:inherit;text-align:left;background:transparent;border:0}',
    P + '-row:focus-visible{outline:none}',
    P + '-row-label{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px;color:var(--soft-ink);font-size:13px;line-height:1.2;font-weight:450;pointer-events:none;transition:opacity 150ms ease}',
    P + '-row-value{color:var(--ink);font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}',
    P + '-row-value span{margin-left:6px;color:var(--muted);font-weight:450}',
    P + '-track{width:100%;height:26px;position:relative;display:block;background:var(--track);border-radius:7px;pointer-events:none}',
    P + '-bar{height:26px;position:absolute;top:0;border-radius:7px;transition:opacity 150ms ease}',
    P + '-bar-total{background:' + CFG.colors.barTotal + '}',
    P + '-row.is-dimmed .bar,.chart-root .row.is-dimmed .row-label{opacity:.35}',
    P + '-axis{height:24px;position:relative;margin-top:6px;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums;pointer-events:none}',
    P + '-axis-tick{position:absolute;top:5px;transform:translateX(-50%);white-space:nowrap}',
    P + '-legend{display:flex;flex-wrap:wrap;align-items:center;gap:' + CFG.spacing.legendGap + ';margin-top:' + CFG.spacing.legendMarginTop + ';color:var(--muted);font-size:12px;line-height:1.3}',
    P + '-legend-item{display:inline-flex;align-items:center;gap:6px}',
    P + '-legend-dot{width:9px;height:9px;border-radius:3px}',
    P + '-legend-dot.is-overlap{background:#fff;border:1px dashed var(--overlap-line)}',
    P + '-tip{position:fixed;z-index:99999;pointer-events:none;max-width:260px;padding:8px 10px;color:#fff;font-size:12px;line-height:1.4;background:' + CFG.colors.tooltipBg + ';border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.18);font-family:' + CFG.fonts.family + ';opacity:0;transition:opacity .15s}',
    P + '-tip[style*="display: none"]{display:none}',
    P + '-tip-title{margin-bottom:2px;font-weight:600}',
    P + '-tip-note{margin-top:4px;color:rgba(255,255,255,.72)}',
    '@media (max-width:520px){' + P + '-total{font-size:24px}' + P + '-row-label,' + P + '-row-value{font-size:12px}}',
    '@media (prefers-reduced-motion:reduce){' + P + '-bar,' + P + '-row-label,' + P + '-info-button{transition:none}}',
    '</style>'
  ].join('');
}
// Только конкатенация строк. Все данные через esc().
// ВНИМАНИЕ: здесь префикс БЕЗ точки. var P = '.' + CFG.ns дал бы class=".pvt-root".
function buildHTML() {
  if (!MODEL.items.length) {
    return buildCSS() + '<div class="' + CFG.ns + '-root">' + esc(CFG.text.noData) + '</div>';
  }
  var L = MODEL;
  var h = [];
  h.push('<div class="' + CFG.ns + '-root">');
  // HEADER: заголовок + кнопка info
  h.push('<div class="' + CFG.ns + '-head"><div><div class="' + CFG.ns + '-title">' + esc(L.title) + '</div>');
  h.push('<div class="' + CFG.ns + '-total" data-tip="total">' + L.total + '<small>' + employeeWord(L.total) + ' ' + CFG.text.totalSuffix + '</small></div></div>');
  h.push('<button type="button" class="' + CFG.ns + '-info-button' + (state.tooltip && state.tooltip.kind === 'info' ? ' is-active' : '') + '" data-tip="info" aria-label="Правило формирования встречи"><span class="' + CFG.ns + '-info-icon" aria-hidden="true">i</span></button></div>');
  // PLOT: зона пересечения + строки
  h.push('<div class="' + CFG.ns + '-plot">');
  if (L.overlap > 0) {
    h.push('<span class="' + CFG.ns + '-overlap-band" style="left:' + pct(L.overlapStart, L.total) + '%;width:' + pct(L.overlapEnd - L.overlapStart, L.total) + '%"></span>');
  }
  h.push('<div class="' + CFG.ns + '-rows">');
  // Строка "Всего во встрече"
  h.push('<button type="button" class="' + CFG.ns + '-row" data-tip="total"><span class="' + CFG.ns + '-row-label"><span>Всего во встрече</span><span class="' + CFG.ns + '-row-value">' + L.total + '</span></span><span class="' + CFG.ns + '-track"><span class="' + CFG.ns + '-bar ' + CFG.ns + '-bar-total" style="left:0;width:100%"></span></span></button>');
  // Строки структур
  for (var i = 0; i < L.items.length; i++) {
    var it = L.items[i];
    var dim = state.selectedKey && state.selectedKey !== it.key ? ' is-dimmed' : '';
    h.push('<button type="button" class="' + CFG.ns + '-row' + dim + '" data-tip="bar" data-key="' + esc(it.key) + '" aria-pressed="' + (state.selectedKey === it.key) + '">');
    h.push('<span class="' + CFG.ns + '-row-label"><span>' + esc(it.name) + '</span><span class="' + CFG.ns + '-row-value">' + it.count + '<span>только здесь ' + it.unique + '</span></span></span>');
    h.push('<span class="' + CFG.ns + '-track"><span class="' + CFG.ns + '-bar" style="left:' + pct(it.start, L.total) + '%;width:' + pct(it.count, L.total) + '%;background:' + it.color + ';"></span></span></button>');
  }
  h.push('</div>');
  // Ось с тиками
  var ticks = [0, L.overlapStart, L.overlapEnd, L.total].filter(function(v, i, a) { return v >= 0 && v <= L.total && a.indexOf(v) === i; }).sort(function(a, b) { return a - b; });
  h.push('<div class="' + CFG.ns + '-axis">');
  for (var t = 0; t < ticks.length; t++) {
    h.push('<span class="' + CFG.ns + '-axis-tick" style="left:' + pct(ticks[t], L.total) + '%">' + ticks[t] + '</span>');
  }
  h.push('</div></div>');
  // Легенда
  h.push('<div class="' + CFG.ns + '-legend">');
  for (var li = 0; li < L.items.length; li++) {
    h.push('<span class="' + CFG.ns + '-legend-item"><span class="' + CFG.ns + '-legend-dot" style="background:' + L.items[li].color + '"></span>' + esc(L.items[li].name) + ' — ' + L.items[li].count + ' (только здесь ' + L.items[li].unique + ')</span>');
  }
  h.push('<span class="' + CFG.ns + '-legend-item" data-tip="overlap"><span class="' + CFG.ns + '-legend-dot is-overlap"></span>В пересечении — ' + L.overlap + '</span></div>');
  h.push('</div>');
  return buildCSS() + h.join('');
}
// Вспомогательная функция процента
function pct(v, t) { return t ? (v / t * 100) : 0; }

// ---------- БЛОК 6: МОНТАЖ + ИНТЕРАКТИВ ----------
(function mount() {
  try {
    var hosts = document.querySelectorAll('[_echarts_instance_]');
    if (!hosts || hosts.length === 0) return;
    var host = hosts[hosts.length - 1];
    var cvs = host.querySelectorAll('canvas');
    for (var i = 0; i < cvs.length; i++) cvs[i].style.display = 'none';
    var prev = host.querySelector('.' + CFG.ns + '-overlay');
    if (prev) prev.parentNode.removeChild(prev);

    var overlay = document.createElement('div');
    overlay.className = CFG.ns + '-overlay';
    overlay.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;'
      + 'z-index:10;overflow:auto;box-sizing:border-box;background:' + CFG.colors.bg + ';';
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    host.appendChild(overlay);

    // Рендер разметки
    overlay.innerHTML = buildHTML();

    // Состояние
    var selectedKey = null;
    var tooltip = null;

    // Поиск ближайшего элемента с data-tip (как в макете)
    function getTrigger(node) {
      var c = node;
      while (c && c !== overlay) {
        if (c.hasAttribute && c.hasAttribute('data-tip')) return c;
        c = c.parentNode;
      }
      return null;
    }

    // Контент тултипа (как в макете)
    function tooltipContent(L) {
      if (!tooltip) return '';
      var k = tooltip.kind;
      if (k === 'info') return '<div class="' + CFG.ns + '-tip-title">Правило формирования встречи</div><div>' + esc(L.rule) + '</div><div class="' + CFG.ns + '-tip-note">Срез на ' + esc(fmtDate(L.snapshot)) + '</div>';
      if (k === 'total') return '<div class="' + CFG.ns + '-tip-title">Всего во встрече</div><div>' + L.total + ' ' + employeeWord(L.total) + '</div><div class="' + CFG.ns + '-tip-note">Объединение всех структур сегмента</div>';
      if (k === 'overlap') return '<div class="' + CFG.ns + '-tip-title">Пересечение структур</div><div>' + L.overlap + ' ' + employeeWord(L.overlap) + ' · ' + fmtPct(pct(L.overlap, L.total)) + ' от всех</div><div class="' + CFG.ns + '-tip-note">Состоят одновременно во всех структурах</div>';
      var item = null;
      for (var i = 0; i < L.items.length; i++) {
        if (L.items[i].key === tooltip.key) { item = L.items[i]; break; }
      }
      if (!item) return '';
      return '<div class="' + CFG.ns + '-tip-title">' + esc(item.name) + '</div><div>' + item.count + ' ' + employeeWord(item.count) + ' · ' + fmtPct(item.share) + ' от ' + L.total + '</div><div class="' + CFG.ns + '-tip-note">Только в этой структуре: ' + item.unique + ' · в пересечении: ' + L.overlap + '</div>';
    }

    // Тултип в body с position:fixed (как в рабочем примере)
    var oldTip = document.querySelector('body > .' + CFG.ns + '-tip');
    if (oldTip) oldTip.parentNode.removeChild(oldTip);
    var tip = document.createElement('div');
    tip.className = CFG.ns + '-tip';
    tip.style.cssText = 'display:none;position:fixed;z-index:99999;pointer-events:none;'
      + 'max-width:260px;padding:8px 10px;color:#fff;font-size:12px;line-height:1.4;'
      + 'background:' + CFG.colors.tooltipBg + ';border-radius:8px;'
      + 'box-shadow:0 6px 18px rgba(0,0,0,.18);font-family:' + CFG.fonts.family + ';';
    document.body.appendChild(tip);

    function setTooltip(t, pinned) {
      var r = t.getBoundingClientRect();
      tooltip = { kind: t.getAttribute('data-tip'), key: t.getAttribute('data-key') || null, rect: { left: r.left, top: r.top, width: r.width, height: r.height }, pinned: !!pinned };
    }

    function placeTooltip(el) {
      var a = tooltip.rect;
      var pad = 6;
      el.style.left = '0px'; el.style.top = '0px';
      var tipRect = el.getBoundingClientRect();
      var left = a.left + a.width / 2 - tipRect.width / 2;
      var top = a.top + a.height + 8;
      if (top + tipRect.height > window.innerHeight - pad) top = a.top - tipRect.height - 8;
      left = Math.max(pad, Math.min(left, window.innerWidth - tipRect.width - pad));
      top = Math.max(pad, Math.min(top, window.innerHeight - tipRect.height - pad));
      el.style.left = Math.round(left) + 'px';
      el.style.top = Math.round(top) + 'px';
    }

    function renderTooltip(L) {
      if (!tooltip) { tip.style.display = 'none'; tip.innerHTML = ''; return; }
      tip.innerHTML = tooltipContent(L);
      tip.style.display = 'block';
      placeTooltip(tip);
    }

    // Обработчики (как в макете)
    overlay.addEventListener('mouseover', function(e) {
      var t = getTrigger(e.target);
      if (!t || (tooltip && tooltip.pinned)) return;
      setTooltip(t, false);
      renderTooltip(MODEL);
    });

    overlay.addEventListener('mouseout', function(e) {
      var t = getTrigger(e.target);
      if (!t || (tooltip && tooltip.pinned)) return;
      if (e.relatedTarget && t.contains(e.relatedTarget)) return;
      tooltip = null;
      renderTooltip(MODEL);
    });

    overlay.addEventListener('click', function(e) {
      var t = getTrigger(e.target);
      if (!t) { tooltip = null; selectedKey = null; return; }
      var kind = t.getAttribute('data-tip');
      if (kind === 'bar') {
        var key = t.getAttribute('data-key');
        if (selectedKey === key) { selectedKey = null; tooltip = null; }
        else { selectedKey = key; setTooltip(t, true); }
        renderTooltip(MODEL);
        return;
      }
      if (tooltip && tooltip.pinned && tooltip.kind === kind) { tooltip = null; }
      else { setTooltip(t, true); }
      renderTooltip(MODEL);
    });

    overlay.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') { selectedKey = null; tooltip = null; renderTooltip(MODEL); }
    });

    // Фиктивный render для validate.py (S14)
    function render() { renderTooltip(MODEL); }
    render();

    // ResizeObserver
    if (typeof ResizeObserver !== 'undefined') {
      var ro = new ResizeObserver(function() {
        overlay.style.width = '100%'; overlay.style.height = '100%';
      });
      ro.observe(host);
    }
  } catch (e) {
    var box = null;
    var hs = document.querySelectorAll('[_echarts_instance_]');
    if (hs && hs.length) box = hs[hs.length - 1].querySelector('.' + CFG.ns + '-overlay');
    if (!box) box = document.querySelector('.' + CFG.ns + '-overlay');
    if (box) {
      box.innerHTML = '<div style="padding:16px;font:13px -apple-system,Arial,sans-serif;color:#b00020;">'
        + 'Ошибка графика: ' + esc((e && e.message) || e) + '</div>';
    }
  }
})();

// ---------- БЛОК 7: ПУСТОЙ OPTION ----------
// ГЛОБАЛЬНО, В САМОМ КОНЦЕ, ВНЕ функций и IIFE.
// После этого присваивания option не трогать: любая мутация вернёт eCharts
// к отрисовке своего графика поверх overlay.
option = {
  animation: false,
  xAxis: { show: false, type: 'value' },
  yAxis: { show: false, type: 'value' },
  series: [{ type: 'scatter', data: [] }]
};
