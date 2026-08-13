#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — механическая проверка <name>.chart.js на контракт Proteus.

НАЗНАЧЕНИЕ: закрывает те пункты SELF_CHECK, которые проверяются формально.
НЕ заменяет SELF_CHECK: соответствие макету и смысл данных проверяет агент.

ЗАПУСК:
    python3 validate.py <path>.chart.js
    python3 validate.py <path>.chart.js --template   # режим пустой болванки

КОД ВОЗВРАТА: 0 — все PASS/WARN, 1 — есть FAIL.
"""

import re
import sys
import subprocess

BLOCKS = 7
R = []   # (id, status, msg)


def add(cid, ok, msg, warn=False, bad=None):
    st = 'WARN' if (warn and not ok) else ('PASS' if ok else 'FAIL')
    text = msg if ok or bad is None else bad
    R.append((cid, st, text))


# ── вырезаем комментарии и строковые литералы ──
def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def strip_strings(src):
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", src)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)



def function_body(src, name):
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return ''
    start = m.end() - 1
    depth = 0
    quote = None
    escaped = False
    for i in range(start, len(src)):
        ch = src[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == chr(92):
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in (chr(39), chr(34)):
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
    return ''


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    is_tpl = '--template' in sys.argv

    raw = open(path, encoding='utf-8').read()
    code = strip_comments(raw)          # код без комментариев
    bare = strip_strings(code)          # код без комментариев и строк
    lines = raw.splitlines()

    # ══ P5. Синтаксис ══
    try:
        p = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        add('P5', p.returncode == 0, 'node --check' if p.returncode == 0
            else p.stderr.strip().splitlines()[0] if p.stderr else 'syntax error')
    except FileNotFoundError:
        add('P5', True, 'node не найден — проверь вручную', warn=True)

    # ══ C1. Блоки 1..7 по порядку ══
    found = [int(m) for m in re.findall(r'БЛОК\s+(\d)', raw)]
    seq, seen = [], set()
    for n in found:
        if n not in seen:
            seen.add(n)
            seq.append(n)
    add('C1', seq == list(range(1, BLOCKS + 1)),
        'блоки 1-7 по порядку' if seq == list(range(1, BLOCKS + 1))
        else 'найдено ' + str(seq) + ', ожидалось [1..7]')

    # ══ S1. option глобально и в конце ══
    assigns = [i for i, l in enumerate(lines, 1)
               if re.match(r'^\s*(?:if\s*\(typeof\s+option|option\s*=)', l)]
    if not assigns:
        add('S1', False, 'option не присваивается')
    else:
        last = assigns[-1]
        at_col0 = bool(re.match(r'^option\s*=|^if\s*\(typeof\s+option', lines[last - 1]))
        tail_ok = all(not l.strip() or l.strip().startswith('//') or l.strip() in ('};', '}')
                      or not re.search(r'\w', l)
                      for l in lines[last:]) or (len(lines) - last) < 12
        add('S1', at_col0 and tail_ok,
            'option глобально, строка ' + str(last) + '/' + str(len(lines))
            if at_col0 else 'строка ' + str(last) + ': option внутри блока/функции (отступ)')

    # ══ D2. option пустой ══
    tail = '\n'.join(lines[assigns[-1] - 1:]) if assigns else ''
    add('D2', 'scatter' in tail and 'data: []' in tail.replace('data:[]', 'data: []'),
        'series — пустой scatter', bad='option не пуст: eCharts пытается рисовать свой график')

    # ══ S2/C3. Монтаж ══
    add('S2', '_echarts_instance_' in code and 'createElement' in code,
        'хост через [_echarts_instance_], overlay создаётся', bad='нет поиска хоста или createElement')
    add('C3a', bool(re.search(r'canvas', code)) and 'display' in code, 'canvas скрывается', bad='canvas НЕ скрыт — будет виден под overlay')
    add('C3b', 'removeChild' in code or '.remove()' in code, 'старый overlay удаляется', bad='старый overlay не удаляется — два графика друг на друге (RETRO 4)')
    add('C3c', "position = 'relative'" in code or 'position="relative"' in code
        or "position:relative" in code, 'host → position:relative', bad='host остался static — overlay уедет по странице')
    add('S2b', 'appendChild' in code, 'overlay монтируется в host', bad='нет appendChild — overlay не попадёт в DOM')

    # ══ S3. Монтаж РЕАЛЬНО вызван (главный баг KPI-кейса) ══
    iife = re.search(r'\(function\s*\w*\s*\([^)]*\)\s*\{.*?\}\s*\)\s*\(\s*\)\s*;', code, re.S)
    named = re.findall(r'function\s+(\w*[Oo]verlay\w*|mount\w*)\s*\(', code)
    called = any(re.search(r'(?<!function )\b' + re.escape(n) + r'\s*\(', code) for n in named)
    add('S3', bool(iife) or called,
        'монтаж вызван (IIFE)' if iife else
        'монтаж вызван' if called else
        'КРИТИЧНО: функция монтажа объявлена, но не вызвана — overlay останется null')

    # ══ C6. Ошибка видна ══
    add('C6', 'try' in bare and 'catch' in bare, 'try/catch вокруг монтажа', bad='нет try/catch — любой сбой даст пустой виджет')
    cat = re.search(r'catch\s*\([^)]*\)\s*\{(.*?)\n\}', code, re.S)
    catch_body = cat.group(1) if cat else ''
    catch_ok = bool(cat) and 'option' not in catch_body and (
        'innerHTML' in catch_body or 'textContent' in catch_body)
    add('C6b', catch_ok, 'catch выводит ошибку в overlay',
        bad='catch молчит или обращается к option до БЛОКА 7 (RETRO 24)')

    # ══ S9/S14-S17. Вызов render, префикс, слушатели, координаты тултипа ══
    render_body = function_body(code, 'render')
    add('S14', bool(re.search(r'^\s*render\(\)\s*;', code, re.M)),
        'render() вызывается',
        bad='render() объявлен, но не вызван — overlay останется пустым (RETRO 25)')

    html_body = function_body(code, 'buildHTML')
    dot_prefix = bool(re.search(r'var\s+P\s*=\s*[\'"]\.[\'"]\s*\+', html_body))
    add('S15', not (dot_prefix or 'class=".' in raw or "class='." in raw),
        'HTML-классы без ведущей точки',
        bad='buildHTML строит class=".ns-*" — стили и querySelector мертвы (RETRO 23)')

    add('S9', 'addEventListener' not in render_body, 'слушатели вне render()',
        bad='addEventListener внутри render() — дубли после каждого клика (RETRO 9)')

    add('S17', not re.search(r'(?:document|window)\.addEventListener', render_body),
        'глобальных слушателей внутри render() нет',
        bad='document/window.addEventListener внутри render() течёт и дублируется')

    tip_body = function_body(code, 'positionTooltip') or function_body(code, 'renderTip')
    add('S16', not ('hostRect' in tip_body or 'clientWidth' in tip_body),
        'fixed-тултип считает координаты от окна', warn=True,
        bad='fixed-тултип использует локальные координаты/clientWidth (RETRO 26)')

    # ══ C4. ResizeObserver не вызывает render ══
    ro = re.search(r'new\s+ResizeObserver\s*\(\s*function[^)]*\)\s*\{(.*?)\}\s*\)', code, re.S)
    add('C4', not (ro and re.search(r'\brender\s*\(', ro.group(1))),
        'observer только правит габариты' if not ro or not re.search(r'\brender\s*\(', ro.group(1))
        else 'ResizeObserver вызывает render() — риск бесконечного цикла (RETRO 3)')

    # ══ C7. Состояние ══
    add('C7', '__pvtState' in code, 'состояние в window.__pvtState', bad='нет __pvtState — состояние слетит на перерисовке (RETRO 2)')

    # ══ S5. Префикс селекторов в buildCSS ══
    css = re.search(r'function\s+buildCSS\s*\([^)]*\)\s*\{(.*?)\n\}', code, re.S)
    if not css:
        add('S5', is_tpl, 'buildCSS() не найдена')
    else:
        body = css.group(1)
        bad = []
        # Селектор валиден, если ЛИБО начинается с . / # в самой строке,
        # ЛИБО строка приклеена к переменной-префиксу: P + '-root{...}'.
        for m in re.finditer(r"(\+\s*)?(P|CFG\.ns)?\s*(\+\s*)?'([^']*\{[^']*)'", body):
            prefixed = bool(m.group(2) and m.group(3))
            chunk = m.group(4)
            for i, sel in enumerate(re.findall(r'([^{};]+)\{', chunk)):
                s = sel.strip()
                if not s or s.startswith('@') or s.startswith('<'):
                    continue
                # Первый селектор мог получить точку из переменной P = '.' + CFG.ns.
                if i == 0 and prefixed and re.match(r'^[-_a-z0-9]', s):
                    continue
                if not re.match(r'^[.#]', s):
                    bad.append(s[:40])
        # селекторы, собранные через P + '...' — проверяем наличие префикса
        has_prefix_var = bool(re.search(r"=\s*'\.'\s*\+\s*CFG\.ns", body)) or 'CFG.ns' in body
        add('S5', not bad and has_prefix_var,
            'все селекторы префиксованы' if not bad and has_prefix_var
            else ('голые селекторы: ' + ', '.join(bad[:5]) if bad else 'нет префикса через CFG.ns'))

    # ══ S6. Каждый класс разметки имеет CSS-правило ══
    html_fn = re.search(r'function\s+buildHTML\s*\([^)]*\)\s*\{(.*?)\n\}', code, re.S)
    if html_fn and css:
        used = set(re.findall(r'class=\\?"([a-z0-9_ -]+)', html_fn.group(1)))
        used |= set(re.findall(r"class=\"([a-z0-9_ -]+)", html_fn.group(1)))
        names = set()
        for grp in used:
            for c in grp.split():
                if len(c) > 2 and not c.startswith('+'):
                    names.add(c)
        styled = css.group(1)
        missing = [c for c in sorted(names) if c not in styled and c.split('-')[-1] not in styled]
        add('S6', not missing or is_tpl,
            'все классы со стилями' if not missing
            else 'классы без CSS: ' + ', '.join(missing[:6]), warn=is_tpl)
    else:
        add('S6', is_tpl, 'buildHTML()/buildCSS() не найдены', warn=is_tpl)

    # ══ S7. Тултип в body ══
    if 'tip' in code.lower() or 'tooltip' in code.lower():
        add('S7', 'document.body.appendChild' in code.replace(' ', ''),
            'тултип монтируется в body' if 'document.body.appendChild' in code.replace(' ', '')
            else 'тултип не в body — будет обрезан overflow (RETRO 7)', warn=True)

    # ══ T1. Узел тултипа НЕ в buildHTML (RETRO 19) ══
    if html_fn and re.search(r'-tip', html_fn.group(1)):
        add('T1', False, '', bad='узел тултипа в buildHTML() — innerHTML убьёт его (RETRO 19)')
    elif 'tip' in code.lower():
        add('T1', True, 'тултип вне пересобираемой разметки')

    # ══ T2. Тултип создаётся НЕ внутри render (RETRO 19/20) ══
    if render_body and 'tip' in code.lower():
        creates = bool(re.search(r'createElement', render_body))
        add('T2', not creates, 'тултип не пересоздаётся в render()',
            bad='render() создаёт узлы заново — тултип будет моргать (RETRO 19)')

    # ══ T3. Шрифт задан и в root, и в тултипе (RETRO 21) ══
    if css:
        cb = css.group(1)
        n_ff = len(re.findall(r'font-family', cb))
        tip_rule = re.search(r"-tip\{[^']*", cb)
        tip_has_ff = bool(tip_rule and 'font-family' in cb[tip_rule.start():tip_rule.start() + 400])
        if 'tip' in code.lower():
            add('T3', n_ff >= 2 and tip_has_ff, 'font-family задан и в root, и в тултипе',
                bad='тултип без своего font-family — будет другой шрифт (RETRO 21)')
        add('T4', 'font-family:inherit' in cb.replace(' ', ''),
            'font-family:inherit для дочерних',
            bad='нет font-family:inherit — button/input возьмут системный шрифт (RETRO 21)',
            warn=True)

    # ══ S8. Скрытие не через hidden ══
    hid = [i for i, l in enumerate(lines, 1) if re.search(r'\.hidden\s*=', l)]
    add('S8', not hid, 'скрытие через style' if not hid
        else 'строки ' + ','.join(map(str, hid[:5])) + ': .hidden ненадёжен (RETRO 8)')

    # ══ S10. Даты ══
    if re.search(r'_dt\b|date|month|period|\bdt\b', bare, re.I):
        add('S10', 'toDate' in code or re.search(r'\d{11,}|1e12', code),
            'есть универсальный парсер даты' if 'toDate' in code
            else 'даты без toDate(): epoch придёт числом (RETRO 10)', warn=True)

    # ══ S11. Запреты синтаксиса ══
    for cid, pat, msg in [
        ('S11a', r'`', 'backticks / template-literals'),
        ('S11b', r'=>', 'стрелочные функции'),
        ('S11c', r'\b(?:let|const)\s+\w', 'let / const'),
        ('S12', r'document\.getElementById', 'document.getElementById (RETRO 15)'),
        ('D1a', r'\b(?:import|require)\s*[\(\'"]', 'import / require'),
        ('D1b', r'\bfetch\s*\(', 'fetch'),
        ('D1c', r'https?://', 'внешний URL / CDN'),
    ]:
        hits = [i for i, l in enumerate(lines, 1)
                if re.search(pat, l) and not l.strip().startswith('//')]
        add(cid, not hits, 'нет ' + msg if not hits
            else msg + ' → строки ' + ','.join(map(str, hits[:5])))

    # ══ Гигиена: console.log ══
    cl = [i for i, l in enumerate(lines, 1) if 'console.log' in l and not l.strip().startswith('//')]
    add('H1', not cl, 'нет console.log' if not cl
        else 'console.log → строки ' + ','.join(map(str, cl[:5])), warn=True)

    # ══ M7. Всё data, не data[0] ══
    add('M7', not re.search(r'\bdata\s*\[\s*0\s*\]', bare),
        'читается весь data' if not re.search(r'\bdata\s*\[\s*0\s*\]', bare)
        else 'data[0] — остальные строки потеряны (RETRO 11)')
    add('M7b', 'Array.isArray' in code, 'вход защищён Array.isArray', bad='нет Array.isArray — падёт на пустом data')

    # ══ C8. esc() ══
    add('C8', 'function esc' in code or 'escapeHtml' in code, 'есть экранирование', bad='нет esc() — данные вставляются в HTML сырыми')

    # ══ C5. Пустые данные ══
    add('C5', 'noData' in code, 'есть ветка CFG.text.noData', bad='нет ветки «Нет данных»')

    # ══ M4. Заглушка не заполнена выдумками / боевой — заполнен ══
    fields = re.search(r'fields\s*:\s*\{(.*?)\}', code, re.S)
    n_fields = len(re.findall(r'\w+\s*:', fields.group(1))) if fields else 0
    if is_tpl:
        add('M4', n_fields == 0, 'болванка: CFG.fields пуст' if n_fields == 0
            else 'CFG.fields содержит ' + str(n_fields) + ' выдуманных полей')
    else:
        add('M4', n_fields > 0, 'CFG.fields: ' + str(n_fields) + ' полей' if n_fields
            else 'CFG.fields пуст — данные не привязаны к SQL')
        todo = [i for i, l in enumerate(lines, 1) if '[ЗАПОЛНИ]' in l or '[ЗАМЕНИ]' in l]
        add('M4b', not todo, 'нет незакрытых TODO' if not todo
            else 'остались плейсхолдеры → строки ' + ','.join(map(str, todo[:6])))

    # ── отчёт ──
    w = max(len(c) for c, _, _ in R)
    fails = sum(1 for _, s, _ in R if s == 'FAIL')
    warns = sum(1 for _, s, _ in R if s == 'WARN')
    print('\n' + path)
    print('-' * 72)
    for cid, st, msg in R:
        mark = {'PASS': 'v', 'FAIL': 'X', 'WARN': '!'}[st]
        print(' ' + mark + '  ' + cid.ljust(w) + '  ' + st.ljust(4) + '  ' + msg)
    print('-' * 72)
    total = len(R)
    print('Итог: ' + str(total - fails - warns) + '/' + str(total) + ' PASS, '
          + str(warns) + ' WARN, ' + str(fails) + ' FAIL')
    if fails:
        print('\nСДАВАТЬ НЕЛЬЗЯ. Исправь FAIL и запусти снова.')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
