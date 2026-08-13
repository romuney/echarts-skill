// ============================================================================
// <NAME>.chart.js - болванка каркаса
// ============================================================================
// КОНТРАКТ PROTEUS:
//   ECharts = только холст. Вся визуализация - HTML/CSS/SVG в overlay.
//   Хост = ПОСЛЕДНИЙ [_echarts_instance_]. Canvas прячем. Overlay - appendChild.
//   В САМОМ КОНЦЕ ФАЙЛА, ГЛОБАЛЬНО: option = {...} с пустым scatter.
//
// ЗАПРЕЩЕНО: backticks/template-literals, стрелочные функции, let/const,
//   document.getElementById (только overlay.querySelector), console.log в итоге,
//   addEventListener внутри тела render(), обращение к option из catch,
//   var P = '.' + CFG.ns в buildHTML (точка только в buildCSS).
// ОБЯЗАТЕЛЬНО: все 7 блоков ниже, в таком порядке, без перенумерации.
// ОБЯЗАТЕЛЬНО: вызов render(); в теле mount() — без него overlay пустой.
// ============================================================================

// ---------- БЛОК 1: CFG ----------
// fields - ТОЛЬКО реальные имена колонок из SQL пользователя.
// Нет поля в SQL - СПРОСИ, не выдумывай и не хардкодь значения.
// Все цвета/шрифты/отступы из макета — только здесь, не в разметке.
var CFG = {
  ns: 'pvt',                  // ПРЕФИКС всех CSS-классов и класса overlay
  fields: {},                 // [ЗАПОЛНИ] { alias: 'sql_column_name', ... }
  text: { noData: 'Нет данных' },
  // СНИМОК или ДИНАМИКА. 'snapshot' = состояние на текущую дату,
  // поле-период НЕ НУЖНО и спрашивать про дату ЗАПРЕЩЕНО.
  mode: 'snapshot',           // 'snapshot' | 'timeseries'
  colors: {},                 // [ЗАПОЛНИ] из макета
  fonts: {
    // ЕДИНЫЙ стек для ВСЕГО виджета, включая тултип в body.
    // Шрифт не наследуется в body — его НАДО задать явно в правиле тултипа.
    family: '-apple-system,"Segoe UI",Roboto,Arial,sans-serif'
    // [ЗАПОЛНИ] размеры из макета (px)
  },
  spacing: {}                 // [ЗАПОЛНИ] из макета
};

// ---------- БЛОК 2: ВХОД + СОСТОЯНИЕ + ХЕЛПЕРЫ ----------
// ВСЕ строки data, не data[0].
var rawData = (typeof data !== 'undefined' && Array.isArray(data)) ? data : [];

// Состояние переживает перерисовку Proteus.
if (!window.__pvtState) window.__pvtState = {};
var __S = window.__pvtState;
if (!__S[CFG.ns]) __S[CFG.ns] = { tip: null };  // [ЗАПОЛНИ] остальные ключи
var state = __S[CFG.ns];

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
function num(v) {
  if (v === null || v === undefined || v === '') return null;
  var n = Number(String(v).replace(',', '.'));
  return isNaN(n) ? null : n;
}
// Универсальный парсер даты: epoch-ms, epoch-s, 'YYYY-MM-DD', 'YYYY-MM'.
// Нужен всегда: DATETIME из Proteus приходит числом, а не строкой из UI.
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

// ---------- БЛОК 3: ТРАНСФОРМАЦИЯ ДАННЫХ ----------
// rawData -> структура, удобная для рендера. Только чтение CFG.fields.
function buildModel() {
  // [ЗАПОЛНИ] группировка/агрегация/сортировка по rawData
  return { rows: [] };
}
var MODEL = buildModel();

// ---------- БЛОК 4: ФОРМАТИРОВАНИЕ И ЦВЕТ ----------
// [ЗАПОЛНИ] fmtPct / fmtInt / шкалы цвета — только если нужны макету.
function cssColor(c) {
  if (!c) return '#000';
  if (typeof c === 'string') return c;
  var a = (c.length >= 4) ? c[3] : 1;
  return 'rgba(' + Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]) + ',' + a + ')';
}

// ---------- БЛОК 5: РАЗМЕТКА (<style> + HTML) ----------
// КАЖДЫЙ селектор начинается с .<ns>- или с .<ns>-root - иначе стили
// протекут в интерфейс Proteus. НИКАКИХ голых div/table/th/button.
// Стили из макета переносятся СЮДА ЦЕЛИКОМ, а не выбрасываются.
function buildCSS() {
  var P = '.' + CFG.ns;
  return [
    '<style>',
    P + '-root{width:100%;height:100%;box-sizing:border-box;'
            + 'font-family:' + CFG.fonts.family + ';}',
    P + '-root *{box-sizing:border-box;font-family:inherit;}',
    // ТУЛТИП живёт В BODY, вне -root — шрифт ему НЕ наследуется.
    // Повторяем font-family и position:fixed явно, иначе будет другой шрифт.
    P + '-tip{position:fixed;z-index:99999;pointer-events:none;opacity:0;'
           + 'font-family:' + CFG.fonts.family + ';box-sizing:border-box;'
           + 'transition:opacity .08s;}',
    // [ЗАПОЛНИ] остальные правила макета, все с префиксом P
    '</style>'
  ].join('');
}
// Только конкатенация строк. Все данные через esc().
function buildHTML() {
  if (!MODEL.rows.length) {
    return buildCSS() + '<div class="' + CFG.ns + '-root">' + esc(CFG.text.noData) + '</div>';
  }
  var h = [];
  h.push('<div class="' + CFG.ns + '-root">');
  // [ЗАПОЛНИ] разметка макета: тулбар, тело, SVG
  h.push('</div>');
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
    overlay.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;z-index:10;background:#fff;overflow:auto;box-sizing:border-box;';
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    host.appendChild(overlay);

    // ── ТУЛТИП ──
    // Создаётся РОВНО ОДИН РАЗ и кэшируется в tipEl.
    // НИКОГДА не создавай его внутри render() и НИКОГДА не клади
    // его разметку в buildHTML(): innerHTML убьёт узел, и тултип перестанет
    // работать после первого же перерисовывания.
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

    // Показ/скрытие тултипа НЕ требует полного render():
    // тултип лежит в body с position:fixed: координаты getBoundingClientRect()
    // используются КАК ЕСТЬ. Не вычитать rect корня/overlay; клампинг только
    // по window.innerWidth / window.innerHeight, не по clientWidth контейнера.
    function renderTip() {
      var tip = getTip();
      if (!state.tip) { tip.style.opacity = '0'; tip.style.display = 'none'; return; }
      // [ЗАПОЛНИ] innerHTML и left/top в координатах окна
      tip.style.display = 'block';
      tip.style.opacity = '1';
    }

    // render ТОЛЬКО пересобирает разметку. Делегированные обработчики
    // навешиваются ОДИН РАЗ СНАРУЖИ render(): overlay не пересоздаётся.
    // Любой addEventListener внутри render() ЗАПРЕЩЁН — он создаёт дубли.
    function render() {
      overlay.innerHTML = buildHTML();
      renderTip();
    }

    // [ЗАПОЛНИ] обработчики: hover → renderTip(); click → state + render().
    function onOver(e) {}
    function onOut(e) {}
    function onClick(e) {}

    overlay.addEventListener('mouseover', onOver);
    overlay.addEventListener('mouseout', onOut);
    overlay.addEventListener('click', onClick);
    window.addEventListener('resize', function() { if (state.tip) renderTip(); });
    // Escape при необходимости вешай здесь один раз, не внутри render().

    render();

    // ResizeObserver только правит габариты. НЕ вызывать render() — зациклит.
    if (typeof ResizeObserver !== 'undefined') {
      var ro = new ResizeObserver(function() {
        overlay.style.width = '100%'; overlay.style.height = '100%';
      });
      ro.observe(host);
    }
  } catch (e) {
    // option присваивается позже, в БЛОКЕ 7: из catch к нему не обращаться.
    var box = document.querySelector('.' + CFG.ns + '-overlay');
    if (box) {
      box.innerHTML = '<div style="padding:16px;font:13px -apple-system,Arial,sans-serif;color:#b00020;">'
        + 'Ошибка графика: ' + esc((e && e.message) || e) + '</div>';
    }
  }
})();

// ---------- БЛОК 7: ПУСТОЙ OPTION ----------
// ГЛОБАЛЬНО, В САМОМ КОНЦЕ, ВНЕ функций и IIFE.
option = {
  animation: false,
  xAxis: { show: false, type: 'value' },
  yAxis: { show: false, type: 'value' },
  series: [{ type: 'scatter', data: [] }]
};
