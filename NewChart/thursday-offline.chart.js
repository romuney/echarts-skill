// ============================================================================
// <NAME>.chart.js - болванка каркаса
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
var CFG = {
  ns: 'tho',
  fields: {
    total: 'emp_cnt_total',
    management: 'emp_cnt_management',
    functional: 'emp_cnt_functional'
  },
  text: {
    noData: 'Нет данных',
    segmentTitle: 'Четверговая Оффлайн',
    kpiCaption: 'всего во встрече',
    management: 'Управленческая структура',
    functional: 'Функциональная структура',
    overlapBadge: 'Пересечение структур',
    rule: 'Сотрудники группы офлайн-четверговой на дату среза. При участии в нескольких группах приоритет: Оффлайн → Онлайн → Management Meeting.'
  },
  mode: 'snapshot',
  colors: {
    bg: 'transparent',
    ink: '#303033',
    muted: '#8f8f93',
    softInk: '#5e5e64',
    hairline: '#c9c9cb',
    focus: '#595a60',
    management: '#f7c4ce',
    functional: '#dfc3f6',
    tipBg: '#ffffff',
    tipInk: '#303033',
    tipNote: '#6a6a70'
  },
  fonts: {
    family: '-apple-system,"Segoe UI",Roboto,Arial,sans-serif'
  },
  spacing: {
    kpiMarginTop: 14,
    setVisualMarginTop: 22
  }
};

// ---------- БЛОК 2: ВХОД + СОСТОЯНИЕ + ХЕЛПЕРЫ ----------
var rawData = (typeof data !== 'undefined' && Array.isArray(data)) ? data : [];

if (!window.__pvtState) window.__pvtState = {};
var __S = window.__pvtState;
if (!__S[CFG.ns]) __S[CFG.ns] = { tip: null, selectedKey: null };
var state = __S[CFG.ns];

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function num(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return isNaN(v) ? null : v;
  var s = String(v).replace(/[\s\u00A0]/g, '');
  if (s.indexOf(',') > -1 && s.indexOf('.') === -1) s = s.replace(/,/g, '.');
  else s = s.replace(/,/g, '');
  var n = Number(s);
  return isNaN(n) ? null : n;
}

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

function employeeWord(value) {
  var number = Math.abs(Number(value));
  var lastTwo = number % 100;
  var lastOne = number % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return 'сотрудников';
  if (lastOne === 1) return 'сотрудник';
  if (lastOne >= 2 && lastOne <= 4) return 'сотрудника';
  return 'сотрудников';
}

// ---------- БЛОК 3: ТРАНСФОРМАЦИЯ ДАННЫХ ----------
function buildModel() {
  if (!rawData || rawData.length === 0) return { total: 0, bars: [], overlap: 0 };

  var row = rawData[0];
  var total = num(row[CFG.fields.total]) || 0;
  var management = num(row[CFG.fields.management]) || 0;
  var functional = num(row[CFG.fields.functional]) || 0;

  var overlap = (management + functional) - total;
  if (overlap < 0) overlap = 0;

  var bars = [
    {
      key: 'management',
      label: CFG.text.management,
      count: management,
      color: CFG.colors.management,
      share: total > 0 ? (management / total * 100) : 0
    },
    {
      key: 'functional',
      label: CFG.text.functional,
      count: functional,
      color: CFG.colors.functional,
      share: total > 0 ? (functional / total * 100) : 0
    }
  ];

  return { total: total, bars: bars, overlap: overlap };
}
var MODEL = buildModel();

// ---------- БЛОК 4: ФОРМАТИРОВАНИЕ И ЦВЕТ ----------
function fmtPercent(value) {
  var rounded = Math.round(value * 10) / 10;
  var s = String(rounded);
  if (s.indexOf('.') >= 0 && s.endsWith('0')) {
    s = s.substring(0, s.length - 2);
  }
  return s + '%';
}

function cssColor(c) {
  if (!c) return '#000';
  if (typeof c === 'string') return c;
  var a = (c.length >= 4) ? c[3] : 1;
  return 'rgba(' + Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]) + ',' + a + ')';
}

// ---------- БЛОК 5: РАЗМЕТКА (<style> + HTML) ----------
function buildCSS() {
  var P = '.' + CFG.ns;
  return [
    '<style>',
    P + '-root{width:100%;position:relative;box-sizing:border-box;' +
      'font-family:' + CFG.fonts.family + ';color:' + CFG.colors.ink + ';}',
    P + '-root *{box-sizing:border-box;font-family:inherit;}',
    P + '-stage{width:100%;display:flex;align-items:center;justify-content:center;' +
      'padding:8px 4px;box-sizing:border-box;background:transparent;}',
    P + '-body{width:min(100%,470px);position:relative;display:flex;' +
      'flex-direction:column;align-items:center;padding:0;background:transparent;}',
    P + '-header{width:100%;display:flex;align-items:baseline;justify-content:center;gap:8px;}',
    P + '-title{margin:0;color:' + CFG.colors.muted + ';font-size:30px;line-height:1.15;' +
      'font-weight:450;letter-spacing:-0.6px;}',
    P + '-info-btn{width:22px;height:22px;flex:0 0 auto;display:inline-flex;' +
      'align-items:center;justify-content:center;padding:0;cursor:pointer;' +
      'appearance:none;color:#a9a9ad;background:rgba(143,143,147,0.10);border:0;' +
      'border-radius:50%;transition:color 150ms ease,background 150ms ease;}',
    P + '-info-btn:hover,' + P + '-info-btn:focus-visible,' + P + '-info-btn.is-active{' +
      'color:#6c6c72;background:rgba(143,143,147,0.20);}',
    P + '-info-btn:focus-visible{outline:2px solid rgba(89,90,96,0.40);outline-offset:2px;}',
    P + '-info-icon{display:block;font-family:Georgia,"Times New Roman",serif;' +
      'font-size:14px;line-height:1;font-weight:700;pointer-events:none;}',
    P + '-kpi{margin-top:' + CFG.spacing.kpiMarginTop + 'px;color:' + CFG.colors.ink + ';' +
      'font-size:32px;line-height:1.05;font-weight:750;letter-spacing:-0.9px;' +
      'text-align:center;cursor:default;}',
    P + '-kpi-caption{margin-top:3px;color:' + CFG.colors.softInk + ';font-size:12px;' +
      'line-height:1.3;font-weight:450;text-align:center;}',
    P + '-set-visual{width:100%;margin-top:' + CFG.spacing.setVisualMarginTop + 'px;position:relative;}',
    P + '-set-row{width:100%;position:relative;height:56px;}',
    P + '-set-band{height:32px;position:absolute;top:24px;display:flex;align-items:center;' +
      'box-sizing:border-box;padding:0 11px;cursor:pointer;appearance:none;color:inherit;' +
      'font:inherit;border:0;border-radius:7px;box-shadow:0 0 0 0 rgba(89,90,96,0);' +
      'transition:opacity 140ms ease,box-shadow 140ms ease,filter 140ms ease;}',
    P + '-set-band.is-left{left:0;justify-content:flex-start;}',
    P + '-set-band.is-right{right:0;justify-content:flex-end;}',
    P + '-set-band:hover,' + P + '-set-band:focus-visible{filter:brightness(0.96);' +
      'box-shadow:0 0 0 3px rgba(89,90,96,0.14);outline:none;}',
    P + '-set-band.is-selected{box-shadow:0 0 0 2px ' + CFG.colors.focus + ';}',
    P + '-set-band.is-muted{opacity:0.34;}',
    P + '-set-label{position:absolute;top:0;color:' + CFG.colors.softInk + ';' +
      'font-size:16px;line-height:1.25;font-weight:450;pointer-events:none;' +
      'transition:color 140ms ease,opacity 140ms ease;}',
    P + '-set-label.is-left{left:1px;}' + P + '-set-label.is-right{right:1px;}',
    P + '-set-label.is-strong{color:' + CFG.colors.ink + ';font-weight:600;}',
    P + '-set-label.is-muted{opacity:0.34;}',
    P + '-set-value{color:#55545b;font-size:18px;line-height:1;font-weight:550;' +
      'pointer-events:none;}',
    P + '-overlap-zone{position:absolute;top:24px;bottom:24px;box-sizing:border-box;' +
      'border-left:1px dashed ' + CFG.colors.hairline + ';border-right:1px dashed ' +
      CFG.colors.hairline + ';background:rgba(143,143,147,0.07);pointer-events:none;}',
    P + '-overlap-badge{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);' +
      'padding:4px 11px;white-space:nowrap;color:' + CFG.colors.ink + ';background:#ffffff;' +
      'border:1px solid ' + CFG.colors.hairline + ';border-radius:999px;font-size:13px;' +
      'font-weight:650;pointer-events:auto;cursor:pointer;' +
      'transition:box-shadow 140ms ease,border-color 140ms ease;}',
    P + '-overlap-badge:hover,' + P + '-overlap-badge:focus-visible{' +
      'border-color:#a9a9ad;box-shadow:0 0 0 3px rgba(89,90,96,0.12);outline:none;}',
    P + '-tip{position:fixed;z-index:60;pointer-events:none;opacity:0;' +
      'font-family:' + CFG.fonts.family + ';box-sizing:border-box;' +
      'transition:opacity 0.08s;display:none;}',
    P + '-tip[hidden]{display:none;}',
    P + '-tip-content{min-width:260px;max-width:min(360px,calc(100vw - 20px));' +
      'padding:9px 12px;color:' + CFG.colors.tipInk + ';background:' + CFG.colors.tipBg + ';' +
      'border:1px solid rgba(0,0,0,0.06);border-radius:8px;' +
      'box-shadow:0 6px 20px rgba(24,24,28,0.14),0 1px 3px rgba(24,24,28,0.10);' +
      'font-size:12px;line-height:1.4;}',
    P + '-tip-title{display:block;margin:0;color:' + CFG.colors.tipInk + ';' +
      'font-size:12px;line-height:1.3;font-weight:600;}',
    P + '-tip-value{display:block;margin:3px 0 0;color:' + CFG.colors.tipInk + ';' +
      'font-size:13px;line-height:1.3;font-weight:700;}',
    P + '-tip-note{display:block;margin:3px 0 0;color:' + CFG.colors.tipNote + ';' +
      'font-size:11px;line-height:1.4;font-weight:400;}',
    P + '-empty{width:100%;padding:20px;box-sizing:border-box;color:' + CFG.colors.softInk + ';' +
      'text-align:center;background:transparent;}',
    '</style>'
  ].join('');
}

function buildHTML() {
  var P = CFG.ns;
  if (!MODEL || MODEL.total === 0) {
    return buildCSS() + '<div class="' + P + '-root"><div class="' + P + '-empty">' +
      esc(CFG.text.noData) + '</div></div>';
  }

  var h = [];
  h.push('<div class="' + P + '-root">');
  h.push('<div class="' + P + '-stage">');
  h.push('<div class="' + P + '-body" aria-label="' + esc(CFG.text.segmentTitle) + '">');

  // Header
  h.push('<div class="' + P + '-header">');
  h.push('<h2 class="' + P + '-title">' + esc(CFG.text.segmentTitle) + '</h2>');
  h.push('<button type="button" class="' + P + '-info-btn" data-action="info" data-kind="info" aria-label="Правило формирования встречи">');
  h.push('<span class="' + P + '-info-icon" aria-hidden="true">i</span>');
  h.push('</button>');
  h.push('</div>');

  // KPI
  h.push('<div class="' + P + '-kpi">' + esc(MODEL.total) + ' ' + employeeWord(MODEL.total) + '</div>');
  h.push('<div class="' + P + '-kpi-caption">' + esc(CFG.text.kpiCaption) + '</div>');

  // Bars
  h.push('<div class="' + P + '-set-visual" aria-label="Пересечение структур сотрудников">');

  for (var i = 0; i < MODEL.bars.length; i++) {
    var bar = MODEL.bars[i];
    var side = (i === 0) ? 'is-left' : 'is-right';
    var isSelected = state.selectedKey === bar.key;
    var isMuted = state.selectedKey !== null && state.selectedKey !== bar.key;
    var width = Math.max(24, Math.min(100, bar.share));

    h.push('<div class="' + P + '-set-row">');
    h.push('<span class="' + P + '-set-label ' + side + (isSelected ? ' is-strong' : '') + (isMuted ? ' is-muted' : '') + '">' + esc(bar.label) + '</span>');
    h.push('<button type="button" class="' + P + '-set-band ' + side + (isSelected ? ' is-selected' : '') + (isMuted ? ' is-muted' : '') + '" data-action="select" data-kind="bar" data-key="' + esc(bar.key) + '" aria-pressed="' + String(isSelected) + '" style="width:' + width + '%;background:' + bar.color + ';" aria-label="' + esc(bar.label + ': ' + bar.count + ' ' + employeeWord(bar.count) + ', ' + fmtPercent(bar.share) + ' от ' + MODEL.total) + '">');
    h.push('<span class="' + P + '-set-value">' + esc(bar.count) + '</span>');
    h.push('</button>');
    h.push('</div>');
  }

  // Overlap zone
  if (MODEL.overlap > 0 && MODEL.total > 0) {
    var leftShare = Math.max(24, Math.min(100, MODEL.bars[0].share));
    var rightShare = Math.max(24, Math.min(100, MODEL.bars[1].share));
    var zoneLeft = 100 - rightShare;
    var zoneWidth = leftShare - zoneLeft;

    if (zoneWidth > 0) {
      h.push('<div class="' + P + '-overlap-zone" style="left:' + zoneLeft + '%;width:' + zoneWidth + '%;">');
      h.push('<button type="button" class="' + P + '-overlap-badge" data-action="overlap" data-kind="overlap" aria-label="Пересечение структур: ' + MODEL.overlap + ' ' + employeeWord(MODEL.overlap) + '">∩ ' + esc(MODEL.overlap) + '</button>');
      h.push('</div>');
    }
  }

  h.push('</div>'); // set-visual
  h.push('</div>'); // body
  h.push('</div>'); // stage
  h.push('</div>'); // root

  return buildCSS() + h.join('');
}

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
    overlay.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;' +
      'z-index:10;overflow:auto;box-sizing:border-box;background:' + CFG.colors.bg + ';';
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    host.appendChild(overlay);

    var tipEl = null;
    function getTip() {
      if (tipEl && tipEl.parentNode) return tipEl;
      var old = document.querySelector('body > .' + CFG.ns + '-tip');
      if (old) old.parentNode.removeChild(old);
      tipEl = document.createElement('div');
      tipEl.className = CFG.ns + '-tip';
      document.body.appendChild(tipEl);
      return tipEl;
    }
    getTip();

    function renderTip() {
      var tip = getTip();
      if (!state.tip) {
        tip.style.opacity = '0';
        tip.style.display = 'none';
        return;
      }
      var rect = state.tip.rect;
      var kind = state.tip.kind;
      var key = state.tip.key;

      var title = '', value = '', note = '';

      if (kind === 'info') {
        title = 'Правило формирования';
        note = CFG.text.rule;
      } else if (kind === 'bar') {
        for (var i = 0; i < MODEL.bars.length; i++) {
          if (MODEL.bars[i].key === key) {
            var bar = MODEL.bars[i];
            title = bar.label;
            value = bar.count + ' ' + employeeWord(bar.count);
            note = fmtPercent(bar.share) + ' от ' + MODEL.total;
            break;
          }
        }
      } else if (kind === 'overlap') {
        title = CFG.text.overlapBadge;
        value = MODEL.overlap + ' ' + employeeWord(MODEL.overlap);
        note = 'В обеих структурах · ' + fmtPercent(MODEL.overlap / MODEL.total * 100) + ' от ' + MODEL.total;
      }

      var html = '<div class="' + CFG.ns + '-tip-content">' +
        '<span class="' + CFG.ns + '-tip-title">' + esc(title) + '</span>';
      if (value) {
        html += '<span class="' + CFG.ns + '-tip-value">' + esc(value) + '</span>';
      }
      if (note) {
        html += '<span class="' + CFG.ns + '-tip-note">' + esc(note) + '</span>';
      }
      html += '</div>';

      tip.innerHTML = html;
      tip.style.display = 'block';
      tip.style.opacity = '1';

      var tipRect = tip.getBoundingClientRect();
      var pad = 6;
      var left = rect.left + rect.width / 2 - tipRect.width / 2;
      var top = rect.top - tipRect.height - 8;

      if (left + tipRect.width > window.innerWidth - pad) left = window.innerWidth - tipRect.width - pad;
      if (left < pad) left = pad;
      if (top < pad) top = rect.bottom + 8;

      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }

    function render() {
      overlay.innerHTML = buildHTML();
      renderTip();
    }

    function getTrigger(node) {
      var current = node;
      while (current && current !== overlay && current !== document) {
        if (current.hasAttribute && (current.hasAttribute('data-kind') || current.hasAttribute('data-action'))) {
          return current;
        }
        current = current.parentNode;
      }
      return null;
    }

    function onOver(e) {
      var trigger = getTrigger(e.target);
      if (!trigger || !trigger.getAttribute('data-kind')) return;
      if (state.tip && state.tip.pinned) return;
      state.tip = {
        kind: trigger.getAttribute('data-kind'),
        key: trigger.getAttribute('data-key') || null,
        rect: trigger.getBoundingClientRect(),
        pinned: false
      };
      renderTip();
    }

    function onOut(e) {
      if (state.tip && state.tip.pinned) return;
      var trigger = getTrigger(e.target);
      if (!trigger) return;
      var related = e.relatedTarget;
      if (related && trigger.contains(related)) return;
      state.tip = null;
      renderTip();
    }

    function onClick(e) {
      var trigger = getTrigger(e.target);
      if (!trigger) {
        state.tip = null;
        state.selectedKey = null;
        render();
        return;
      }

      var action = trigger.getAttribute('data-action');

      if (action === 'info') {
        var pinnedInfo = state.tip && state.tip.kind === 'info' && state.tip.pinned;
        state.tip = pinnedInfo ? null : {
          kind: 'info',
          key: null,
          rect: trigger.getBoundingClientRect(),
          pinned: true
        };
        render();
        return;
      }

      if (action === 'select') {
        var key = trigger.getAttribute('data-key');
        state.selectedKey = state.selectedKey === key ? null : key;
        state.tip = {
          kind: 'bar',
          key: key,
          rect: trigger.getBoundingClientRect(),
          pinned: false
        };
        render();
        return;
      }

      if (action === 'overlap') {
        var pinnedOverlap = state.tip && state.tip.kind === 'overlap' && state.tip.pinned;
        state.tip = pinnedOverlap ? null : {
          kind: 'overlap',
          key: null,
          rect: trigger.getBoundingClientRect(),
          pinned: true
        };
        render();
      }
    }

    overlay.addEventListener('mouseover', onOver);
    overlay.addEventListener('mouseout', onOut);
    overlay.addEventListener('click', onClick);

    if (state.onWinResize) window.removeEventListener('resize', state.onWinResize);
    state.onWinResize = function () { if (state.tip) renderTip(); };
    window.addEventListener('resize', state.onWinResize);

    render();

    if (typeof ResizeObserver !== 'undefined') {
      if (state.ro && state.ro.disconnect) state.ro.disconnect();
      var ro = new ResizeObserver(function() {
        overlay.style.width = '100%';
        overlay.style.height = '100%';
      });
      ro.observe(host);
      state.ro = ro;
    }
  } catch (e) {
    var box = null;
    var hs = document.querySelectorAll('[_echarts_instance_]');
    if (hs && hs.length) box = hs[hs.length - 1].querySelector('.' + CFG.ns + '-overlay');
    if (!box) box = document.querySelector('.' + CFG.ns + '-overlay');
    if (box) {
      box.innerHTML = '<div style="padding:16px;font:13px -apple-system,Arial,sans-serif;color:#b00020;">' +
        'Ошибка графика: ' + esc((e && e.message) || e) + '</div>';
    }
  }
})();

// ---------- БЛОК 7: ПУСТОЙ OPTION ----------
option = {
  animation: false,
  xAxis: { show: false, type: 'value' },
  yAxis: { show: false, type: 'value' },
  series: [{ type: 'scatter', data: [] }]
};
