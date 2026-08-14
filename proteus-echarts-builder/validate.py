#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — механическая проверка <name>.chart.js на контракт Proteus.

НАЗНАЧЕНИЕ: закрывает те пункты SELF_CHECK, которые проверяются формально.
НЕ заменяет SELF_CHECK: соответствие макету и смысл данных проверяет агент.

ЗАПУСК:
    python3 validate.py <path>.chart.js
    python3 validate.py <path>.chart.js --template   # режим пустой болванки
    python3 validate.py <path>.chart.js --quiet      # только FAIL/WARN + итог

Порядок аргументов любой. КОД ВОЗВРАТА: 0 — все PASS/WARN, 1 — есть FAIL,
2 — ошибка запуска (нет файла, не указан путь).
"""

import os
import re
import sys
import subprocess

BLOCKS = 7
R = []   # (id, status, msg)


def add(cid, ok, msg, warn=False, bad=None):
    st = 'WARN' if (warn and not ok) else ('PASS' if ok else 'FAIL')
    text = msg if ok else (bad if bad is not None else msg)
    R.append((cid, st, text))


# ── лексический разбор ───────────────────────────────────────────────────────
# Возвращает две проекции исходника ТОЙ ЖЕ ДЛИНЫ, что и оригинал:
#   code — комментарии затёрты пробелами, строковые литералы целы;
#   bare — затёрты ещё и содержимое строк и регулярок.
# Совпадение длин даёт право резать любую из проекций одними индексами
# и считать номер строки как raw.count('\n', 0, i) + 1.

_RE_ALLOWED_PREV = set('(,=:[!&|?{};+-*%^~<>')


def scan(src):
    code, bare = [], []
    i, n = 0, len(src)
    state = None          # None | 'line' | 'block' | quote char | 'regex'
    in_class = False      # внутри [...] регулярки
    last = ''             # последний значимый символ до текущей позиции
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ''
        if state is None:
            if ch == '/' and nxt == '/':
                state = 'line'; code.append('  '); bare.append('  '); i += 2; continue
            if ch == '/' and nxt == '*':
                state = 'block'; code.append('  '); bare.append('  '); i += 2; continue
            if ch == '/' and (last == '' or last in _RE_ALLOWED_PREV):
                state = 'regex'; in_class = False
                code.append(ch); bare.append(' '); i += 1; continue
            if ch in ('"', "'", '`'):
                state = ch; code.append(ch); bare.append(ch); i += 1; continue
            code.append(ch); bare.append(ch)
            if not ch.isspace():
                last = ch
            i += 1; continue

        if state == 'line':
            if ch == '\n':
                state = None; code.append('\n'); bare.append('\n')
            else:
                code.append(' '); bare.append(' ')
            i += 1; continue

        if state == 'block':
            if ch == '*' and nxt == '/':
                state = None; code.append('  '); bare.append('  '); i += 2; continue
            c = '\n' if ch == '\n' else ' '
            code.append(c); bare.append(c); i += 1; continue

        if state == 'regex':
            if ch == '\\':
                code.append(src[i:i + 2]); bare.append('  '); i += 2; continue
            if ch == '[':
                in_class = True
            elif ch == ']':
                in_class = False
            elif ch == '/' and not in_class:
                state = None; last = '/'
                code.append(ch); bare.append(' '); i += 1; continue
            elif ch == '\n':      # незакрытая регулярка — значит это было деление
                state = None; code.append('\n'); bare.append('\n'); i += 1; continue
            code.append(ch); bare.append(' '); i += 1; continue

        # внутри строкового литерала
        if ch == '\\':
            code.append(src[i:i + 2]); bare.append('  '); i += 2; continue
        if ch == state:
            state = None; last = ch
            code.append(ch); bare.append(ch); i += 1; continue
        code.append(ch); bare.append('\n' if ch == '\n' else ' ')
        i += 1; continue
    return ''.join(code), ''.join(bare)


def line_of(src, idx):
    return src.count('\n', 0, idx) + 1


def match_braces(bare, start):
    """От индекса открывающей '{' в bare вернуть индекс парной '}' или -1."""
    depth = 0
    for i in range(start, len(bare)):
        if bare[i] == '{':
            depth += 1
        elif bare[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


_FN_FORMS = [
    r'function\s+{n}\s*\(',
    r'var\s+{n}\s*=\s*function\s*\w*\s*\(',
    r'\b{n}\s*[:=]\s*function\s*\w*\s*\(',
]


def find_function(code, bare, name):
    """Тело функции по любой из форм объявления. None — функция не найдена."""
    for form in _FN_FORMS:
        m = re.search(form.format(n=re.escape(name)), bare)
        if not m:
            continue
        br = bare.find('{', m.end())
        if br == -1:
            continue
        end = match_braces(bare, br)
        if end == -1:
            continue
        return code[br + 1:end]
    return None


def notes_section(txt, num):
    m = re.search(r'^##\s*§' + str(num) + r'\b.*?$(.*?)(?=^##\s*§|\Z)', txt, re.M | re.S)
    return m.group(1) if m else ''


def check_notes(path):
    """Z-проверки: реально ли прочитан макет и закрыт ли реестр.

    Гоняются автоматически, если рядом с <name>.chart.js лежит <name>.NOTES.md.
    Смысл: число M в NOTES §2 должно быть ИЗМЕРЕНО, а не вписано на глаз —
    иначе «покрыто M из M» доказывает само себя и макет читается наполовину.
    """
    base = re.sub(r'\.chart\.js$', '', path)
    notes_path = base + '.NOTES.md'
    html_path = base + '.html'
    if not os.path.isfile(notes_path):
        return
    txt = open(notes_path, encoding='utf-8', errors='replace').read()

    real = None
    if os.path.isfile(html_path):
        with open(html_path, encoding='utf-8', errors='replace') as fh:
            real = sum(1 for _ in fh)

    s2 = notes_section(txt, 2)
    mm = re.search(r'M\s*=\s*\*{0,2}\s*(\d+)', s2)
    claimed = int(mm.group(1)) if mm else None

    if claimed is None:
        add('Z1', False, '', warn=True,
            bad='NOTES §2 не заполнен — полнота чтения макета не доказана')
        return
    if real is None:
        add('Z1', False, '', warn=True,
            bad='нет ' + os.path.basename(html_path) + ' — M=' + str(claimed) + ' не с чем сверить')
    else:
        add('Z1', claimed == real,
            'NOTES §2: M=' + str(claimed) + ' совпадает с ' + os.path.basename(html_path),
            bad='NOTES §2 заявляет M=' + str(claimed) + ', а в '
                + os.path.basename(html_path) + ' реально ' + str(real)
                + ' строк — макет прочитан не полностью, ' + str(real - claimed)
                + ' строк не открывалось')

    # Диапазоны обязаны покрыть 1..real без дыр.
    target = real if real is not None else claimed
    spans = []
    for mr in re.finditer(r'(\d+)\s*[-–—]\s*(\d+)', s2):
        a, b = int(mr.group(1)), int(mr.group(2))
        if a <= b:
            spans.append((a, b))
    if spans:
        covered, cur = [], None
        for a, b in sorted(spans):
            if cur and a <= cur[1] + 1:
                cur = (cur[0], max(cur[1], b))
            else:
                if cur:
                    covered.append(cur)
                cur = (a, b)
        covered.append(cur)
        gaps = []
        pos = 1
        for a, b in covered:
            if a > pos:
                gaps.append(str(pos) + '-' + str(a - 1))
            pos = max(pos, b + 1)
        if pos <= target:
            gaps.append(str(pos) + '-' + str(target))
        add('Z1b', not gaps, 'диапазоны NOTES §2 покрывают 1..' + str(target) + ' без дыр',
            bad='непрочитанные строки макета: ' + ', '.join(gaps[:4]))

    # §1: реестр не должен содержать незакрытых строк.
    s1 = notes_section(txt, 1)
    open_rows = re.findall(r'^\|[^|]*\|[^|]*\|.*?\|\s*(TODO|ASK)\s*\|', s1, re.M)
    add('Z2', not open_rows, 'реестр NOTES §1 закрыт',
        bad='в реестре NOTES §1 осталось незакрытых строк: ' + str(len(open_rows))
            + ' (TODO/ASK) — элементы макета не перенесены')

    # §5: все блоки DONE.
    s5 = notes_section(txt, 5)
    undone = re.findall(r'^\|\s*[1-7]\s*\|[^|]*\|\s*(TODO|DOING)\s*\|', s5, re.M)
    add('Z3', not undone, 'NOTES §5: все блоки DONE',
        bad='в NOTES §5 блоков не DONE: ' + str(len(undone)))

    # §6: открытые хвосты.
    s6 = notes_section(txt, 6)
    tails = re.findall(r'^\s*-\s*\[ \]\s*\S', s6, re.M)
    if tails:
        add('Z4', False, '', warn=True,
            bad='в NOTES §6 незакрытых хвостов: ' + str(len(tails))
                + ' — закрой или проговори их пользователю в финальном ответе')


def check_report(path):
    """Z6: сданный отчёт должен быть по чек-листу скилла, а не в своём формате.

    Реальный случай: агент выдал красивый отчёт из собственных разделов, где не
    было ни одного ID из SELF_CHECK — то есть чек-лист не проходился вовсе,
    а «все элементы макета покрыты» стояло при непрочитанной трети макета.
    """
    report_path = os.path.join(os.path.dirname(os.path.abspath(path)), 'SELF_CHECK.md')
    if not os.path.isfile(report_path):
        return
    master = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SELF_CHECK.md')
    if not os.path.isfile(master) or os.path.samefile(master, report_path):
        return
    need = re.findall(r'^- \[ \] ([A-Z]\d+)\.', open(master, encoding='utf-8').read(), re.M)
    if not need:
        return
    rep = open(report_path, encoding='utf-8', errors='replace').read()
    missing = [c for c in need if not re.search(r'\b' + c + r'\b', rep)]
    add('Z6', not missing,
        'отчёт SELF_CHECK.md содержит все ' + str(len(need)) + ' пунктов',
        bad='в SELF_CHECK.md нет ' + str(len(missing)) + ' из ' + str(len(need))
            + ' обязательных пунктов (' + ', '.join(missing[:6])
            + '...) — отчёт написан в своём формате, чек-лист не пройден (RETRO 43)')


def main():
    args = [a for a in sys.argv[1:]]
    flags = set(a for a in args if a.startswith('--'))
    paths = [a for a in args if not a.startswith('--')]
    unknown = flags - {'--template', '--quiet'}
    if unknown:
        print('Неизвестный флаг: ' + ', '.join(sorted(unknown)))
        return 2
    if not paths:
        print(__doc__)
        return 2
    path = paths[0]
    is_tpl = '--template' in flags
    quiet = '--quiet' in flags
    if not os.path.isfile(path):
        print('Файл не найден: ' + path)
        return 2
    try:
        raw = open(path, encoding='utf-8').read()
    except (OSError, UnicodeDecodeError) as err:
        print('Не читается ' + path + ': ' + str(err))
        return 2

    code, bare = scan(raw)
    assert len(code) == len(raw) == len(bare), 'проекции разъехались с оригиналом'
    lines = raw.splitlines()
    code_lines = code.splitlines()

    # ══ P5. Синтаксис ══
    try:
        p = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        add('P5', p.returncode == 0, 'node --check' if p.returncode == 0
            else p.stderr.strip().splitlines()[0] if p.stderr else 'syntax error')
    except (FileNotFoundError, OSError):
        add('P5', False, 'node не найден — синтаксис НЕ проверен, проверь вручную', warn=True)

    # ══ C1. Блоки 1..7 по порядку ══
    # Только заголовки блоков вида "// ---------- БЛОК N", а не любое упоминание.
    found = [int(m) for m in re.findall(r'^\s*//\s*-*\s*БЛОК\s+(\d)', raw, re.M)]
    seq, seen = [], set()
    for nb in found:
        if nb not in seen:
            seen.add(nb)
            seq.append(nb)
    add('C1', seq == list(range(1, BLOCKS + 1)),
        'блоки 1-7 по порядку',
        bad='найдено ' + str(seq) + ', ожидалось [1..7]')

    # ══ S1. option глобально, в конце, без последующих мутаций ══
    assigns = [i for i, l in enumerate(code_lines, 1)
               if re.match(r'^\s*(?:if\s*\(typeof\s+option|option\s*=)', l)]
    opt_end = None
    if not assigns:
        add('S1', False, '', bad='option не присваивается')
    else:
        last = assigns[-1]
        at_col0 = bool(re.match(r'^option\s*=|^if\s*\(typeof\s+option', code_lines[last - 1]))
        # хвост после литерала option: любой исполняемый код запрещён
        idx = sum(len(l) + 1 for l in code_lines[:last - 1])
        br = code.find('{', idx)
        opt_end = match_braces(bare, br) if br != -1 else -1
        tail = code[opt_end + 1:] if opt_end and opt_end != -1 else ''
        tail_ok = not re.search(r'[A-Za-z0-9_$]', tail.replace(';', ''))
        add('S1', at_col0 and tail_ok,
            'option глобально (RETRO 14), строка ' + str(last) + '/' + str(len(lines)),
            bad=('строка ' + str(last) + ': option внутри блока/функции (отступ)'
                 if not at_col0 else
                 'после литерала option есть код (строка '
                 + str(line_of(raw, opt_end)) + '+): мутация вернёт eCharts к отрисовке'))

    # ══ D2. option пустой ══
    lit = code[br:opt_end + 1] if (assigns and br != -1 and opt_end and opt_end != -1) else ''
    empty_series = bool(re.search(r'series\s*:\s*\[\s*\{[^\]]*?data\s*:\s*\[\s*\]', lit, re.S))
    add('D2', 'scatter' in lit and empty_series,
        'series — пустой scatter',
        bad='option не пуст: eCharts пытается рисовать свой график')

    # ══ S2/C3. Монтаж ══
    add('S2', '_echarts_instance_' in code and 'createElement' in bare,
        'хост через [_echarts_instance_], overlay создаётся',
        bad='нет поиска хоста или createElement')
    add('C3a', 'canvas' in code and 'display' in code, 'canvas скрывается',
        bad='canvas НЕ скрыт — будет виден под overlay')
    add('C3b', 'removeChild' in bare or '.remove()' in bare, 'старый overlay удаляется',
        bad='старый overlay не удаляется — два графика друг на друге (RETRO 4)')
    add('C3c', bool(re.search(r'position\s*=\s*[\'"]relative|position:relative', code)),
        'host → position:relative',
        bad='host остался static — overlay уедет по странице')
    add('S2b', 'appendChild' in bare, 'overlay монтируется в host',
        bad='нет appendChild — overlay не попадёт в DOM')

    # ══ S3. Монтаж РЕАЛЬНО вызван ══
    # Недостаточно «где-то есть IIFE»: самовызов должен содержать сам монтаж.
    mounted = False
    for m in re.finditer(r'\(\s*function\s*\w*\s*\([^)]*\)\s*', bare):
        br2 = bare.find('{', m.end())
        if br2 == -1:
            continue
        end2 = match_braces(bare, br2)
        if end2 == -1:
            continue
        after = bare[end2 + 1:end2 + 12]
        body = code[br2:end2]
        if re.match(r'\s*\)\s*\(\s*\)', after) and '_echarts_instance_' in body:
            mounted = True
            break
    if not mounted:
        named = re.findall(r'function\s+(\w*[Oo]verlay\w*|mount\w*)\s*\(', bare)
        for nm in named:
            if re.search(r'(?<!function )\b' + re.escape(nm) + r'\s*\(\s*\)\s*;', bare):
                mounted = True
                break
    add('S3', mounted, 'монтаж вызван и содержит поиск хоста',
        bad='КРИТИЧНО: функция монтажа не вызвана либо самовызов не содержит монтаж — '
            'overlay останется null (RETRO 1)')

    # ══ C6. Ошибка видна ══
    add('C6', 'try' in bare and 'catch' in bare, 'try/catch вокруг монтажа',
        bad='нет try/catch — любой сбой даст пустой виджет')
    catch_body = None
    mc = re.search(r'catch\s*\([^)]*\)\s*', bare)
    if mc:
        br3 = bare.find('{', mc.end())
        if br3 != -1:
            end3 = match_braces(bare, br3)
            if end3 != -1:
                catch_body = code[br3 + 1:end3]
    if catch_body is None:
        add('C6b', False, '', bad='не найден блок catch — ошибка монтажа будет молчаливой')
    else:
        bare_catch = bare[br3 + 1:end3]
        ok = ('option' not in bare_catch
              and ('innerHTML' in bare_catch or 'textContent' in bare_catch))
        add('C6b', ok, 'catch выводит ошибку в overlay',
            bad='catch молчит или обращается к option до БЛОКА 7 (RETRO 16, 24)')

    # ══ S9/S14-S17. Вызов render, префикс, слушатели, координаты тултипа ══
    render_body = find_function(code, bare, 'render')
    add('S14', bool(re.search(r'^\s*render\(\)\s*;', code, re.M)),
        'render() вызывается',
        bad='render() объявлен, но не вызван — overlay останется пустым (RETRO 25)')

    html_body = find_function(code, bare, 'buildHTML')
    if html_body is None:
        add('S15', is_tpl, 'buildHTML() не найдена', warn=is_tpl,
            bad='buildHTML() не найдена — проверка префикса невозможна')
    else:
        dot_prefix = bool(re.search(r'var\s+P\s*=\s*[\'"]\.[\'"]\s*\+', html_body))
        add('S15', not (dot_prefix or 'class=".' in html_body or "class='." in html_body),
            'HTML-классы без ведущей точки',
            bad='buildHTML строит class=".ns-*" — стили и querySelector мертвы (RETRO 23)')

    if render_body is None:
        add('S9', False, '', warn=True,
            bad='render() не найдена — проверки S9/S17/T2 пропущены, проверь вручную')
    else:
        add('S9', 'addEventListener' not in render_body, 'слушатели вне render()',
            bad='addEventListener внутри render() — дубли после каждого клика (RETRO 9)')
        add('S17', not re.search(r'(?:document|window)\.addEventListener', render_body),
            'глобальных слушателей внутри render() нет',
            bad='document/window.addEventListener внутри render() течёт и дублируется')
        # S14 ловит только ФАКТ вызова. Пустой render(){} его проходит, поэтому
        # отдельно требуем, чтобы render действительно пересобирал разметку.
        add('S14b', 'buildHTML(' in render_body.replace(' ', ''),
            'render() пересобирает разметку через buildHTML()',
            bad='render() не вызывает buildHTML() — это заглушка ради проверки, '
                'после клика на экране ничего не изменится (RETRO 45)')

    has_tip = 'tip' in bare.lower() or 'tooltip' in bare.lower()

    # Имена тултип-функций — часть контракта шаблона: по ним ищет S16.
    # Переименовал — проверка не находит тело и МОЛЧА пропадает из отчёта.
    tip_body = (find_function(code, bare, 'positionTooltip')
                or find_function(code, bare, 'renderTip'))
    if tip_body is not None:
        add('S16', not ('hostRect' in tip_body or 'clientWidth' in tip_body),
            'fixed-тултип считает координаты от окна', warn=True,
            bad='fixed-тултип использует локальные координаты/clientWidth (RETRO 26, 31)')
    elif has_tip and not is_tpl:
        add('S16', False, '', warn=True,
            bad='функции renderTip()/positionTooltip() нет — проверка координат '
                'ПРОПУЩЕНА. Верни имя из шаблона (SKILL.md, правило 7)')

    # ══ C4. ResizeObserver не вызывает render ══
    ro_body = ''
    mro = re.search(r'new\s+ResizeObserver\s*\(\s*function\s*\w*\s*\([^)]*\)\s*', bare)
    if mro:
        br4 = bare.find('{', mro.end())
        if br4 != -1:
            end4 = match_braces(bare, br4)
            if end4 != -1:
                ro_body = bare[br4 + 1:end4]
    add('C4', not re.search(r'\brender\s*\(', ro_body),
        'observer только правит габариты',
        bad='ResizeObserver вызывает render() — риск бесконечного цикла (RETRO 3)')

    # ══ C7. Состояние ══
    add('C7', '__pvtState' in bare, 'состояние в window.__pvtState',
        bad='нет __pvtState — состояние слетит на перерисовке (RETRO 2)')

    # ══ S18. Разметка читает state — кто-то должен его писать ══
    # Классика: buildHTML() смотрит в state.selectedKey, а обработчики пишут
    # в локальную переменную внутри mount(). Синтаксис чист, валидатор чист,
    # интерактив мёртв: подсветка и активные состояния не включаются (RETRO 46).
    state_reads = set()
    for _body in (find_function(code, bare, 'buildHTML'),
                  find_function(code, bare, 'buildCSS')):
        if _body:
            state_reads |= set(re.findall(r'\bstate\.(\w+)\b', _body))
    if state_reads:
        unwritten = sorted(k for k in state_reads
                           if not re.search(r'\bstate\.' + k + r'\s*(?:=[^=]|\+\+|--)', code))
        # state[key] = ... доказать статически нельзя — понижаем до WARN
        dyn = bool(re.search(r'\bstate\s*\[', code))
        add('S18', not unwritten, 'состояние, которое читает разметка, обновляется',
            warn=dyn,
            bad='buildHTML/buildCSS читают state.' + ', state.'.join(unwritten[:4])
                + ', но никто их не присваивает — интерактив не включится (RETRO 46)')

    # ══ S5. Префикс селекторов в buildCSS ══
    css_body = find_function(code, bare, 'buildCSS')
    if css_body is None:
        add('S5', is_tpl, 'buildCSS() не найдена', warn=is_tpl,
            bad='buildCSS() не найдена — стили макета не перенесены')
    else:
        bad_sel = []
        # Строковые куски с CSS: и одинарные, и двойные кавычки.
        for m in re.finditer(r"""(\+\s*)?(P|CFG\.ns)?\s*(\+\s*)?(['"])((?:\\.|(?!\4)[^\\])*\{(?:\\.|(?!\4)[^\\])*)\4""",
                             css_body, re.S):
            prefixed = bool(m.group(2) and m.group(3))
            chunk = m.group(5)
            for i2, sel in enumerate(re.findall(r'([^{};]+)\{', chunk)):
                s = sel.strip()
                if not s or s.startswith('@') or s.startswith('<'):
                    continue
                if i2 == 0 and prefixed and re.match(r'^[-_a-z0-9]', s):
                    continue
                if not re.match(r'^[.#]', s):
                    bad_sel.append(s[:40])
        has_prefix_var = bool(re.search(r"=\s*['\"]\.['\"]\s*\+\s*CFG\.ns", css_body)) \
            or bool(re.search(r"CFG\.ns\s*\+\s*['\"]-", css_body))
        add('S5', not bad_sel and has_prefix_var,
            'все селекторы префиксованы',
            bad=('голые селекторы: ' + ', '.join(bad_sel[:5]) if bad_sel
                 else 'нет префикса через CFG.ns — стили утекут в дашборд (RETRO 5)'))

        # ── S5b. Префикс вписан руками вместо P ──
        # '.chart-row' в строке CSS работает ровно до тех пор, пока CFG.ns
        # равен 'chart'. Такие правила молча отваливаются при смене ns и
        # обычно появляются при копипасте макета кусками.
        mns = re.search(r"\bns\s*:\s*['\"]([\w-]+)['\"]", code)
        if mns:
            lit = '.' + mns.group(1) + '-'
            n_hard = css_body.count(lit)
            add('S5b', n_hard == 0, 'префикс в buildCSS только через P/CFG.ns', warn=True,
                bad='(RETRO 47) литерал "' + lit + '" вписан в CSS ' + str(n_hard)
                    + ' раз вместо P — смена CFG.ns сломает эти правила')

        # ── S19. Корень резиновый ──
        # Макет — отдельная страница со своей рамкой: фикс-ширина, центрирование.
        # Перенесённая на корень, рамка замораживает виджет: ячейка дашборда
        # растёт, а график — нет. Фикс-размеры допустимы только у внутренних
        # элементов; min-width на корне не мешает тянуться и не считается.
        mroot = re.search(r'-root\{', css_body)
        if mroot is not None:
            seg = css_body[mroot.end():mroot.end() + 800]
            cut = seg.find('}')
            rule = re.sub(r"['\"+\s]", '', seg if cut == -1 else seg[:cut])
            fixed = [m.group(0) for m in
                     re.finditer(r'(?<![a-z-])(?:max-)?width:\d+(?:\.\d+)?px', rule)]
            add('S19', not fixed, 'корень резиновый, без фиксированной ширины',
                bad='(RETRO 48) у .<ns>-root фиксированная ширина: '
                    + ', '.join(fixed[:3]) + ' — виджет не растянется за ячейкой '
                    'дашборда. Рамка макета не переносится: корень width:100%')
            if not fixed and 'width:100%' not in rule:
                add('S19b', False, '', warn=True,
                    bad='(RETRO 48) в правиле .<ns>-root нет width:100% — сверь '
                        'с шаблоном: корень обязан тянуться за хостом')

        # ── S20. Оконные @media ──
        # @media (max-width) меряет ОКНО, а виджет живёт в ячейке дашборда:
        # окно 1920px, ячейка 400px — «узкая» ветка не включится никогда.
        # Для тултипа в body оконная ширина законна — тогда объясни WARN строкой.
        medias = [line_of(css_body, m.start()) for m in
                  re.finditer(r'@media[^{\'"]*\(\s*(?:max|min)-width', css_body)]
        if medias:
            add('S20', False, '', warn=True,
                bad='(RETRO 49) @media по ширине ОКНА в buildCSS (строк: '
                    + str(len(medias)) + ') — в ячейке дашборда не сработает. '
                    'Брейкпоинт делается классом на корне по ширине хоста '
                    '(RECIPES.md, «Рамка макета ≠ рамка виджета»)')

    # ══ S6. Каждый класс разметки имеет CSS-правило ══
    if html_body is not None and css_body is not None:
        used = set(re.findall(r'class=\\?["\']([a-z0-9_ -]+)', html_body))
        names = set()
        for grp in used:
            for c in grp.split():
                if len(c) > 2 and not c.startswith('+'):
                    names.add(c)
        missing = [c for c in sorted(names)
                   if c not in css_body and c.split('-')[-1] not in css_body]
        add('S6', not missing or is_tpl,
            'все классы со стилями', warn=is_tpl,
            bad='классы без CSS: ' + ', '.join(missing[:6]) + ' (RETRO 6)')

    # ══ S7/T1-T5. Тултип ══
    if has_tip:
        add('S7', 'document.body.appendChild' in bare.replace(' ', ''),
            'тултип монтируется в body', warn=True,
            bad='тултип не в body — будет обрезан overflow (RETRO 7)')
        if html_body is not None:
            # Узел тултипа в разметке — это класс *-tip. Атрибуты data-tip/aria-tip
            # это делегирование событий, скилл сам его рекомендует: не путать.
            tip_nodes = []
            for mt in re.finditer(r'-tip\b', html_body):
                pre = html_body[max(0, mt.start() - 8):mt.start()]
                if re.search(r'(?:data|aria)$', pre):
                    continue
                tip_nodes.append(line_of(html_body, mt.start()))
            add('T1', not tip_nodes, 'тултип вне пересобираемой разметки',
                bad='узел тултипа в buildHTML() — innerHTML убьёт его (RETRO 19)')
        if render_body is not None:
            add('T2', 'createElement' not in render_body,
                'тултип не пересоздаётся в render()',
                bad='render() создаёт узлы заново — тултип будет моргать (RETRO 19)')
    if css_body is not None:
        n_ff = len(re.findall(r'font-family', css_body))
        tip_rule = re.search(r'-tip\{', css_body)
        tip_has_ff = bool(tip_rule and 'font-family'
                          in css_body[tip_rule.start():tip_rule.start() + 400])
        if has_tip:
            add('T3', n_ff >= 2 and tip_has_ff, 'font-family задан и в root, и в тултипе',
                bad='тултип без своего font-family — будет другой шрифт (RETRO 21)')
        add('T4', 'font-family:inherit' in css_body.replace(' ', ''),
            'font-family:inherit для дочерних', warn=True,
            bad='нет font-family:inherit — button/input возьмут системный шрифт (RETRO 21)')

    # ══ T5. Симметрия: чем спрятали, тем и показываем ══
    # Правило тултипа в CSS прячет узел (opacity:0 / visibility:hidden /
    # display:none), а снять это обязан JS в момент показа. Нет снятия — тултип
    # честно строится, позиционируется и наполняется текстом, но остаётся
    # невидимым: ни ошибки, ни пустого экрана, ни зацепки в отладке (RETRO 44).
    if has_tip and css_body is not None:
        mtip = re.search(r'-tip\{', css_body)
        rule = ''
        if mtip:
            seg = css_body[mtip.end():mtip.end() + 800]
            cut = seg.find('}')
            rule = (seg if cut == -1 else seg[:cut]).replace(' ', '')
        # ('свойство в CSS', 'что считаем снятием в JS')
        props = [
            ('opacity', r'opacity:0(?![.\d])',
             r"\.style\.opacity\s*=\s*['\"]\s*(?!0\s*['\"])[^'\"]+['\"]",
             r'opacity:1'),
            ('visibility', r'visibility:hidden',
             r"\.style\.visibility\s*=\s*['\"]\s*visible",
             r'visibility:visible'),
            ('display', r'display:none',
             r"\.style\.display\s*=\s*['\"]\s*(?!none)[^'\"]+['\"]",
             r'display:(?:block|flex|inline-block|grid)'),
        ]
        unset = []
        flat_css = css_body.replace(' ', '')
        for name, hide_pat, show_pat, cls_pat in props:
            if not re.search(hide_pat, rule):
                continue
            if re.search(show_pat, code):
                continue
            # класс-переключатель — тоже законный способ показа
            if re.search(r'classList\.(?:add|toggle|remove)\s*\(', code) \
                    and re.search(cls_pat, flat_css):
                continue
            unset.append(name)
        # ══ T6. hover не пересобирает разметку ══
        # Полный render() на наведении пересоздаёт DOM прямо под курсором:
        # тултип моргает, выделение слетает, на больших таблицах ещё и тормозит.
        # Для hover есть лёгкий renderTip() (RETRO 20).
        hover_body = find_function(code, bare, 'onOver')
        if hover_body is None:
            mh = re.search(r"addEventListener\s*\(\s*['\"]mouse(?:over|move|enter)['\"]"
                           r"\s*,\s*function\s*\w*\s*\([^)]*\)\s*", bare)
            if mh:
                brh = bare.find('{', mh.end())
                if brh != -1:
                    endh = match_braces(bare, brh)
                    if endh != -1:
                        hover_body = code[brh + 1:endh]
        if hover_body is not None:
            add('T6', not re.search(r'\brender\s*\(', hover_body),
                'hover не вызывает полный render()',
                bad='обработчик наведения вызывает render(): разметка пересобирается '
                    'под курсором, тултип будет мигать (RETRO 20)')

        add('T5', not unset, 'скрытие тултипа снимается при показе',
            bad='CSS прячет тултип через ' + ', '.join(unset)
                + ' — и ни одна строка JS это не снимает. Тултип отрисуется '
                  'невидимым: события, координаты и текст будут верные (RETRO 44)')

    # ══ S8. Скрытие не через hidden ══
    hid = [i for i, l in enumerate(code_lines, 1) if re.search(r'\.hidden\s*=', l)]
    add('S8', not hid, 'скрытие через style',
        bad='строки ' + ','.join(map(str, hid[:5])) + ': .hidden ненадёжен (RETRO 8)')

    # ══ S10. Даты ══
    if re.search(r'_dt\b|date|month|period|\bdt\b', bare, re.I):
        add('S10', 'toDate' in bare or bool(re.search(r'1e12', bare)),
            'есть универсальный парсер даты', warn=True,
            bad='даты без toDate(): epoch придёт числом (RETRO 10)')

    # ══ S11/S12/D1. Запреты синтаксиса ══
    # Проверяем по code: комментарии затёрты, ложных срабатываний нет.
    for cid, pat, msg in [
        ('S11a', r'`', 'backticks / template-literals (RETRO 13)'),
        ('S11b', r'=>', 'стрелочные функции (RETRO 13)'),
        ('S11c', r'\b(?:let|const)\s+\w', 'let / const (RETRO 13)'),
        ('S12', r'document\.getElementById', 'document.getElementById (RETRO 15)'),
        ('D1a', r'\b(?:import|require)\s*[\(\'"]', 'import / require'),
        ('D1b', r'\bfetch\s*\(', 'fetch'),
    ]:
        hits = [i for i, l in enumerate(code_lines, 1) if re.search(pat, l)]
        add(cid, not hits, 'нет ' + msg,
            bad=msg + ' → строки ' + ','.join(map(str, hits[:5])))

    # Внешние URL: пространства имён SVG (w3.org) легальны, CDN — нет.
    cdn = [i for i, l in enumerate(code_lines, 1)
           if re.search(r'https?://', l) and not re.search(r'https?://(?:www\.)?w3\.org', l)]
    add('D1c', not cdn, 'нет внешних URL / CDN',
        bad='внешний URL / CDN → строки ' + ','.join(map(str, cdn[:5])))

    # ══ Гигиена: console.log ══
    cl = [i for i, l in enumerate(code_lines, 1) if 'console.log' in l]
    add('H1', not cl, 'нет console.log', warn=True,
        bad='console.log → строки ' + ','.join(map(str, cl[:5])))

    # ══ H2. Код, написанный ради валидатора ══
    # Проверки описывают ПОВЕДЕНИЕ. Заглушка, поставленная «чтобы позеленело»,
    # снимает симптом и оставляет болезнь — а потом выглядит как доказательство,
    # что всё в порядке (RETRO 45). Ищем по комментариям: агент их подписывает.
    gaming = [i for i, l in enumerate(lines, 1)
              if re.search(r'(?://|/\*|^\s*\*)\s*.*?(?:для\s+validate|ради\s+(?:валидатор|проверк)'
                           r'|чтобы\s+(?:валидатор|проверка|позелен)|фиктивн|обойти\s+проверк'
                           r'|заглушка\s+для)', l, re.I)]
    add('H2', not gaming, 'нет кода, написанного ради валидатора',
        bad='строки ' + ','.join(map(str, gaming[:5]))
            + ': код подогнан под validate.py. Проверка описывает поведение — '
              'заглушка гасит сигнал, а баг остаётся (RETRO 42, 45)')

    # ══ M7. Всё data, не data[0] ══
    add('M7', not re.search(r'\bdata\s*\[\s*0\s*\]', bare), 'читается весь data',
        bad='data[0] — остальные строки потеряны (RETRO 11)')
    # rawData[0] — та же ошибка в обход M7. Но для агрегатного SQL из одной
    # строки это норма, поэтому WARN: агент обязан объяснить его одной строкой.
    first_only = [i for i, l in enumerate(code_lines, 1)
                  if re.search(r'\brawData\s*\[\s*0\s*\]', l)]
    if first_only:
        add('M7c', False, '', warn=True,
            bad='rawData[0] → строки ' + ','.join(map(str, first_only[:5]))
                + ': если SQL отдаёт одну агрегатную строку — норма, объясни это; '
                  'иначе остальные строки молча потеряны (RETRO 11, 41)')
    add('M7b', 'Array.isArray' in bare, 'вход защищён Array.isArray',
        bad='нет Array.isArray — падёт на пустом data')

    # ══ C8/C5 ══
    add('C8', 'function esc' in bare or 'escapeHtml' in bare, 'есть экранирование',
        bad='нет esc() — данные вставляются в HTML сырыми')
    add('C5', 'noData' in bare, 'есть ветка CFG.text.noData',
        bad='нет ветки «Нет данных»')

    # ══ V1-V4. Интерактивные таблицы (по PATTERNS/TABLES) ══
    is_copy = bool(re.search(r'clipboard|writeText|execCommand\s*\(\s*[\'"]copy', bare))
    has_page = bool(re.search(r'\bpageRows\b|\bpageSize\b|state\.page\b', bare))
    has_sort_ui = bool(re.search(r'sortKey|sortDir', bare))

    if is_copy:
        dom_export = bool(re.search(r'querySelectorAll\s*\(\s*[\'"](?:tr|td|th|tbody|table)', code)) \
            or 'innerText' in bare
        add('V1', not dom_export, 'экспорт строится из модели',
            bad='copy/export обходит DOM (querySelectorAll(\'tr\')/innerText) — '
                'скопируется только текущая страница (RETRO 28, 33)')
        if has_page:
            exp_body = None
            for nm in ('buildExportRows', 'buildCopyText', 'onCopy', 'doCopy', 'copyRows'):
                exp_body = exp_body or find_function(code, bare, nm)
            probe = exp_body if exp_body is not None else code
            add('V2', 'pageRows' not in probe, 'экспорт не завязан на pageRows', warn=True,
                bad='экспорт использует pageRows — скопируется только текущая страница (RETRO 28)')

    if has_sort_ui:
        # Проверяем ТЕЛО компаратора, а не весь файл: isNaN в хелперах не считается.
        cmps = []
        for m in re.finditer(r'\.sort\s*\(\s*function\s*\w*\s*\([^)]*\)\s*', bare):
            brs = bare.find('{', m.end())
            if brs == -1:
                continue
            ends = match_braces(bare, brs)
            if ends != -1:
                cmps.append(code[brs + 1:ends])
        for m in re.finditer(r'\.sort\s*\(\s*(\w+)\s*\)', bare):   # .sort(cmpByName)
            body = find_function(code, bare, m.group(1))
            if body is not None:
                cmps.append(body)
        if cmps:
            guard = all(re.search(r'isNaN|isFinite|[!=]==?\s*null|[!=]==?\s*[\'"]{2}'
                                  r'|Infinity|undefined', b) for b in cmps)
            add('V3', guard, 'comparator обрабатывает пустые значения', warn=True,
                bad='comparator без обработки null/\'\'/NaN — '
                    'пустые всплывут наверх при DESC (RETRO 29)')

    if has_page and html_body is not None:
        full_scan = bool(re.search(r'MODEL\.rows\s*\.\s*(?:forEach|map)', html_body)) \
            or bool(re.search(r'MODEL\.rows\.length', html_body))
        add('V4', not full_scan or 'slice' in html_body,
            'в DOM идёт срез страницы', warn=True,
            bad='есть пагинация, но buildHTML итерирует всю MODEL.rows — '
                'в DOM создаются все строки (RETRO 30, 40)')

    # ══ M4. Заглушка не заполнена выдумками / боевой — заполнен ══
    mf = re.search(r'fields\s*:\s*', bare)
    n_fields = 0
    if mf:
        br5 = bare.find('{', mf.end())
        if br5 != -1:
            end5 = match_braces(bare, br5)
            if end5 != -1:
                inner = bare[br5 + 1:end5]
                depth = 0
                top = []
                for chx in inner:
                    if chx == '{':
                        depth += 1
                    elif chx == '}':
                        depth -= 1
                    elif depth == 0:
                        top.append(chx)
                n_fields = len(re.findall(r'[\w\'"]+\s*:', ''.join(top)))
    if is_tpl:
        add('M4', n_fields == 0, 'болванка: CFG.fields пуст',
            bad='CFG.fields содержит ' + str(n_fields) + ' выдуманных полей')
    else:
        add('M4', n_fields > 0, 'CFG.fields: ' + str(n_fields) + ' полей',
            bad='CFG.fields пуст — данные не привязаны к SQL')
        todo = [i for i, l in enumerate(lines, 1) if '[ЗАПОЛНИ]' in l or '[ЗАМЕНИ]' in l]
        add('M4b', not todo, 'нет незакрытых TODO',
            bad='остались плейсхолдеры → строки ' + ','.join(map(str, todo[:6])))
        # ══ Z. Полнота чтения макета и формат сдачи ══
        check_notes(path)
        check_report(path)

    # ── отчёт ──
    w = max(len(c) for c, _, _ in R)
    fails = sum(1 for _, s, _ in R if s == 'FAIL')
    warns = sum(1 for _, s, _ in R if s == 'WARN')
    total = len(R)
    print('\n' + path)
    print('-' * 72)
    shown = 0
    for cid, st, msg in R:
        if quiet and st == 'PASS':
            continue
        shown += 1
        mark = {'PASS': 'v', 'FAIL': 'X', 'WARN': '!'}[st]
        print(' ' + mark + '  ' + cid.ljust(w) + '  ' + st.ljust(4) + '  ' + msg)
    if quiet and shown == 0:
        print(' всё чисто')
    print('-' * 72)
    print('Итог: ' + str(total - fails - warns) + '/' + str(total) + ' PASS, '
          + str(warns) + ' WARN, ' + str(fails) + ' FAIL')
    if fails:
        print('\nСДАВАТЬ НЕЛЬЗЯ. Исправь FAIL и запусти снова.')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
