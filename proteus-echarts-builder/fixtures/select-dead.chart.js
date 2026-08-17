// ФИКСТУРА для `node smoke.mjs --selftest`. В Proteus не вставляется.
//
// МЁРТВАЯ ВЫПАДАШКА. Вкладки исправны, но <select> ни к чему не подключён:
// обработчика change нет вовсе. Классика — контрол нарисован по макету
// и забыт. Ожидание самопроверки: E17 = FAIL, E15 = PASS.

// ---------- БЛОК 1: CFG ----------
var CFG = {
  ns: 'pvt',
  fields: { cat: 'cat', val: 'val' },
  text: { noData: 'Нет данных' },
  mode: 'snapshot',
  colors: { bg: '#fff', ink: '#1f1f1f', blue: '#3B6FE0' },
  fonts: { family: 'Arial,sans-serif', size: { body: 13 } }
};

// ---------- БЛОК 2: ВХОД + СОСТОЯНИЕ + ХЕЛПЕРЫ ----------
var rawData = (typeof data !== 'undefined' && Array.isArray(data)) ? data : [];
window.__pvtState = window.__pvtState || {};
window.__pvtState[CFG.ns] = window.__pvtState[CFG.ns] || { view: 'a', bound: false };
var state = window.__pvtState[CFG.ns];
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
function num(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return isNaN(v) ? null : v;
  var s = String(v).replace(/[\s ]/g, '');
  // '1,5' -> дробная запятая; '1,234.5' -> запятая это разряды.
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

// ---------- БЛОК 3: buildModel ----------
function buildModel() {
  var rows = [];
  for (var i = 0; i < rawData.length; i++) {
    rows.push({ cat: rawData[i][CFG.fields.cat], val: num(rawData[i][CFG.fields.val]) });
  }
  return { rows: rows, sum: rows.length };
}
var MODEL = buildModel();

// ---------- БЛОК 4: ФОРМАТИРОВАНИЕ ----------
function fmtInt(n) { return String(Math.round(num(n))); }
var VIEWS = ['a', 'b', 'c'];

// ---------- БЛОК 5: CSS + HTML ----------
function buildCSS() {
  var P = '.' + CFG.ns;
  return '<style>'
    + P + '-root{width:100%;font-family:' + CFG.fonts.family + ';color:' + CFG.colors.ink + ';}'
    + P + '-acts{display:flex;gap:4px;margin-bottom:6px;}'
    + P + '-tabs{display:flex;gap:4px;margin-bottom:8px;}'
    + P + '-tab{border:0;background:#eee;padding:6px 12px;cursor:pointer;}'
    + P + '-tab.active{background:' + CFG.colors.blue + ';color:#fff;}'
    + P + '-view{display:none;opacity:0;padding:8px;border:1px solid #ddd;}'
    + P + '-view.active{display:block;opacity:1;}'
    + P + '-tip{position:fixed;display:none;opacity:0;background:#222;color:#fff;'
    + 'padding:6px 8px;font-family:' + CFG.fonts.family + ';z-index:99;}'
    + '</style>';
}
function buildHTML() {
  var P = CFG.ns, h = [], i;
  h.push('<div class="' + P + '-root">');
  // кнопки-действия: НЕ переключалка, признака выбора у них нет
  h.push('<div class="' + P + '-acts">');
  h.push('<button type="button" data-action="export">Экспорт CSV</button>');
  h.push('<button type="button" data-action="print">Печать</button>');
  h.push('<button type="button" data-action="reset">Сброс</button>');
  h.push('</div>');
  h.push('<select class="' + P + '-pick" name="metric">'
    + '<option value="x">Метрика X</option><option value="y">Метрика Y</option>'
    + '<option value="z">Метрика Z</option></select>');
  h.push('<div class="' + P + '-tabs" role="tablist">');
  for (i = 0; i < VIEWS.length; i++) {
    h.push('<button type="button" role="tab" class="' + P + '-tab'
      + (state.view === VIEWS[i] ? ' active' : '') + '" aria-selected="'
      + (state.view === VIEWS[i] ? 'true' : 'false')
      + '" data-action="tab:' + VIEWS[i] + '">Вкладка ' + VIEWS[i].toUpperCase() + '</button>');
  }
  h.push('</div>');
  for (i = 0; i < VIEWS.length; i++) {
    h.push('<div class="' + P + '-view' + (VIEWS[i] === state.view ? ' active' : '')
      + '" data-view="' + VIEWS[i] + '">');
    h.push('<span data-tip="row:' + VIEWS[i] + '">Экран ' + VIEWS[i].toUpperCase()
      + ': строк ' + fmtInt(MODEL.sum) + ', метрика ' + VIEWS[i] + '</span>');
    h.push('</div>');
  }
  h.push('</div>');
  return buildCSS() + h.join('');
}

// ---------- БЛОК 6: МОНТАЖ ----------
(function mount() {
  try {
    var hosts = document.querySelectorAll('[_echarts_instance_]');
    var host = hosts[hosts.length - 1];
    if (!host) { return; }
    host.style.position = 'relative';
    var cvs = host.querySelectorAll('canvas');
    for (var c = 0; c < cvs.length; c++) { cvs[c].style.display = 'none'; }
    var old = host.querySelector('.' + CFG.ns + '-overlay');
    if (old) { host.removeChild(old); }
    var overlay = document.createElement('div');
    overlay.className = CFG.ns + '-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;width:100%;overflow:auto;background:'
      + CFG.colors.bg;
    host.appendChild(overlay);

    var tip = document.querySelector('body > .' + CFG.ns + '-tip');
    if (!tip) {
      tip = document.createElement('div');
      tip.className = CFG.ns + '-tip';
      tip.style.cssText = 'position:fixed;display:none;opacity:0;background:#222;color:#fff;'
        + 'padding:6px 8px;font-family:' + CFG.fonts.family + ';z-index:99;';
      document.body.appendChild(tip);
    }
    function showTip(html, rect) {
      tip.innerHTML = html;
      tip.style.display = 'block';
      tip.style.opacity = '1';
      tip.style.left = Math.max(4, Math.min(rect.left + 12, window.innerWidth - 160)) + 'px';
      tip.style.top = Math.max(4, Math.min(rect.top + 12, window.innerHeight - 40)) + 'px';
    }
    function hideTip() { tip.style.display = 'none'; tip.style.opacity = '0'; }
    function getTip(el) { return el.getAttribute('data-tip'); }

    function render() {
      if (!MODEL.rows.length) {
        overlay.innerHTML = '<div style="padding:12px">' + CFG.text.noData + '</div>';
        return;
      }
      overlay.innerHTML = buildHTML();
    }
    function renderTip(el) { showTip(esc(getTip(el)), el.getBoundingClientRect()); }

    // Слушатели вешаются БЕЗУСЛОВНО: overlay только что создан заново,
    // а старый удалён вместе со своими обработчиками. Флаг из state
    // переживает перезапуск скрипта и оставил бы новый overlay
    // без единого слушателя (RETRO 65, validate.py S21).
    overlay.addEventListener('mouseover', function (e) {
      var t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (t) { renderTip(t); }
    });
    overlay.addEventListener('mouseout', function (e) {
      var t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!t || t.contains(e.relatedTarget)) { return; }
      hideTip();
    });
    overlay.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-action]') : null;
      if (!b) { return; }
      var act = b.getAttribute('data-action').split(':');
      if (act[0] !== 'tab') { return; }   // действия экран не переключают
      state.view = act[1];
      render();
    });
    render();
  } catch (err) {
    var h2 = document.querySelectorAll('[_echarts_instance_]');
    var hh = h2[h2.length - 1];
    if (hh) {
      hh.innerHTML = '<div style="padding:12px;color:#c00">Ошибка графика: '
        + err.message + '</div>';
    }
  }
})();

// ---------- БЛОК 7: OPTION ----------
option = { xAxis: { show: false }, yAxis: { show: false }, series: [{ type: 'scatter', data: [] }] };
