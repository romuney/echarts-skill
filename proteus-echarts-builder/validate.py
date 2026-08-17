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
    python3 validate.py <path>.chart.js --accept 'T3=почему это ложная тревога'

Порядок аргументов любой. КОД ВОЗВРАТА: 0 — все PASS/WARN, 1 — есть FAIL,
2 — ошибка запуска (нет файла, не указан путь).

--accept — это ОСПАРИВАНИЕ проверки, а не способ закрыть сдачу. Правила и когда
им пользоваться — в SKILL.md, раздел «ОСПАРИВАНИЕ ПРОВЕРКИ».
"""

import os
import re
import sys
import subprocess

BLOCKS = 7
R = []        # (id, status, msg)
ACCEPTED = {}  # cid -> причина, по которой FAIL оспорен агентом


def add(cid, ok, msg, warn=False, bad=None):
    st = 'WARN' if (warn and not ok) else ('PASS' if ok else 'FAIL')
    text = msg if ok else (bad if bad is not None else msg)
    # Оспоренный FAIL не молчит и не зеленеет: он остаётся видимой строкой
    # в отчёте вместе с причиной — иначе оспаривание становится способом
    # закрыть сдачу вместо способа сообщить о ложной тревоге (RETRO 66).
    if st == 'FAIL' and cid in ACCEPTED:
        st = 'ОСПОР'
        text = text + '  ||  ОСПОРЕНО: ' + ACCEPTED[cid]
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


def string_spans(code, bare, start=0, end=None):
    """Границы строковых литералов: [(i_кавычка, i_кавычка, символ)].

    Кавычки лексер оставляет в ОБЕИХ проекциях, а содержимое и экранированные
    пары затирает только в bare — поэтому парная кавычка ищется в bare и не
    ловится ни на апостроф внутри строки, ни на смешение ' и " в одной функции.
    Разбор строк регуляркой по коду на таком смешении разъезжается и выдаёт
    куски КОДА за содержимое строк (RETRO 60).
    """
    if end is None:
        end = len(bare)
    out = []
    i = start
    while i < end:
        ch = bare[i]
        if ch in ('"', "'", '`'):
            j = bare.find(ch, i + 1)
            if j == -1 or j >= end:
                break
            out.append((i, j, ch))
            i = j + 1
            continue
        i += 1
    return out


def comments_of(src, code):
    """Тексты комментариев целиком, вместе с пробелами внутри.

    Начало комментария лексер затирает двумя пробелами, а строки и регулярки
    оставляет целыми — поэтому `//` внутри строки сюда не попадает.
    """
    out = []
    for m in re.finditer(r'//|/\*', src):
        i = m.start()
        if code[i:i + 2] != '  ':
            continue
        if src[i + 1] == '/':
            j = src.find('\n', i)
        else:
            j = src.find('*/', i + 2)
            j = -1 if j == -1 else j + 2
        out.append(src[i:len(src) if j == -1 else j])
    return out


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


def match_parens(bare, start):
    """От индекса открывающей '(' в bare вернуть индекс парной ')' или -1."""
    depth = 0
    for i in range(start, len(bare)):
        if bare[i] == '(':
            depth += 1
        elif bare[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def flat(txt):
    """Тело функции без пробелов — для сравнения «то же самое или переписано»."""
    return re.sub(r'\s+', '', txt or '')


_FN_FORMS = [
    r'function\s+{n}\s*\(',
    r'var\s+{n}\s*=\s*function\s*\w*\s*\(',
    r'\b{n}\s*[:=]\s*function\s*\w*\s*\(',
]


def find_span(code, bare, name):
    """Границы тела функции (i_после_{, i_}) или None."""
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
        return (br + 1, end)
    return None


def find_function(code, bare, name):
    """Тело функции по любой из форм объявления. None — функция не найдена."""
    sp = find_span(code, bare, name)
    return None if sp is None else code[sp[0]:sp[1]]


VAL = '\x01'   # место значения, склеенного из выражения: CFG.colors.bg и т.п.


def css_text(code, bare, span, ns):
    """CSS из buildCSS() СКЛЕЕННЫЙ — таким, каким он приедет в <style>.

    Одно и то же правило пишут двумя равноправными способами:

        var P = '.' + CFG.ns;         s += P + '-tip{font-family:...}'
        var P = '.' + CFG.ns + '-';   s += P + 'tip{font-family:...}'

    Проверка, которая ищет в ИСХОДНИКЕ литерал '-tip{', вторую форму не находит
    и говорит «тултип без своего font-family» — при том что font-family стоит
    ровно там, куда показывает сообщение. Чинить нечего, указано не туда,
    и «лечением» становится дублирующее мёртвое правило: в Test7 на это ушло
    четыре итерации, а в файл уехала лишняя строка CSS (RETRO 63).

    Поэтому строки сначала склеиваются: `P` и `CFG.ns` подставляются реально,
    значения-выражения становятся VAL, границы инструкций — переводом строки.
    Дальше проверки читают ГОТОВЫЙ CSS и не зависят от того, где в конкатенации
    стоял дефис.
    """
    if span is None:
        return ''
    a0, b0 = span
    body = code[a0:b0]

    pfx = '.' + ns
    mp = re.search(r"\bP\s*=\s*(['\"])\.\1\s*\+\s*CFG\.ns\s*(\+\s*(['\"])-\3)?", body)
    if mp:
        pfx = '.' + ns + ('-' if mp.group(2) else '')
    elif re.search(r"\bP\s*=\s*CFG\.ns\s*\+\s*(['\"])-\1", body):
        pfx = ns + '-'

    def head_token(g):
        """Что стоит слева от '+', открывающего новую склейку."""
        m = re.search(r'([\w.$]+)\s*\+\s*$', g)
        h = m.group(1) if m else ''
        return pfx if h == 'P' else (ns if h == 'CFG.ns' else '')

    out, prev = [], a0
    for (i, j, _q) in string_spans(code, bare, a0, b0):
        g = code[prev:i].strip()
        if g == '' or re.fullmatch(r'\++', g):
            pass                                   # чистая склейка строк
        elif g.startswith('+') and g.endswith('+'):
            inner = g[1:-1].strip()                # значение внутри склейки
            out.append(pfx if inner == 'P'
                       else ns if inner == 'CFG.ns' else VAL)
        else:
            # Инструкция кончилась: правила не должны слипаться в одно.
            out.append('\n' + head_token(g))
        out.append(code[i + 1:j])
        prev = j + 1
    return ''.join(out)


def css_rules(flat_css):
    """[(селектор, тело правила)] из склеенного CSS. @-правила и <style> мимо."""
    out = []
    for line in flat_css.splitlines():
        for m in re.finditer(r'([^{};]+)\{([^{}]*)\}?', line):
            sel = m.group(1).strip()
            if not sel or sel.startswith('@') or sel.startswith('<'):
                continue
            out.append((sel, m.group(2)))
    return out


def notes_section(txt, num):
    m = re.search(r'^##\s*§' + str(num) + r'\b.*?$(.*?)(?=^##\s*§|\Z)', txt, re.M | re.S)
    return m.group(1) if m else ''


# Комплект болванки: файл рядом с <name>.chart.js -> шаблон, из которого он
# обязан быть СКОПИРОВАН. None — файл пользовательский, его содержимое не наше
# дело (макет и SQL приносит пользователь, bootstrap кладёт лишь пустышку).
KIT = [
    ('{name}.html', None),
    ('{name}.data.sql', None),
    ('{name}.NOTES.md', 'TEMPLATE.NOTES.md'),
    ('FIELDS.md', 'TEMPLATE.FIELDS.md'),
]
KIT_CHART = 'TEMPLATE.chart.js'

# Служебные функции: копируются из шаблона ДОСЛОВНО (SKILL.md, правило 7).
# Делятся надвое по цене ошибки.
#
# CORE — чистые хелперы БЛОКА 2. Ни окружения, ни состояния, ни DOM: переписать
# их нельзя даже случайно, только заново сочинив. Расхождение здесь означает,
# что блок писался с нуля, а не заполнялся, — и тогда вместе с ним уезжают
# инварианты, которых по коду вокруг не видно (epoch-мс против epoch-с).
CORE_FNS = ('esc', 'num', 'toDate')
# TIP — машинерия тултипа из БЛОКА 6. Её могло не быть в задаче вовсе, поэтому
# WARN: сигнал важен, но приговором быть не может.
TIP_FNS = ('getTip', 'showTip', 'hideTip', 'trigger', 'onOut')


def _norm(txt):
    """Сравнение копии с шаблоном не должно падать из-за CRLF и хвостов пробелов."""
    return '\n'.join(l.rstrip() for l in txt.replace('\r\n', '\n').split('\n')).strip()


def check_kit(path, is_tpl):
    """K1/K2: болванка создана ЦЕЛИКОМ и СКОПИРОВАНА, а не написана по памяти.

    Реальный случай (RETRO 51): bootstrap.py заблокировала среда, агент собрал
    болванки вручную — и недосчитался <name>.html, зато выдумал mock.json,
    а NOTES/FIELDS сочинил своими словами. validate.py при этом отчитался
    «46/49 PASS»: он смотрел только на .chart.js и пропажи не видел.
    """
    if not path.endswith('.chart.js'):
        return   # файл назван не по контракту — комплекта вокруг него нет
    name = os.path.basename(path)[:-len('.chart.js')]
    if not name:
        return
    folder = os.path.dirname(os.path.abspath(path))
    tpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

    missing_hard, missing_soft = [], []
    for pattern, _ in KIT:
        fname = pattern.format(name=name)
        if os.path.isfile(os.path.join(folder, fname)):
            continue
        # Макет — единственный файл, которого может не быть по делу: правка
        # чужого графика без исходного HTML это не поломка комплекта.
        (missing_soft if (fname.endswith('.html') and not is_tpl)
         else missing_hard).append(fname)

    if missing_hard:
        # Файл под своим именем — не мелочь: NOTES ищется по имени чарта,
        # и «NOTES.md» вместо «<name>.NOTES.md» отключает все Z-проверки разом.
        renamed = [f for f in missing_hard
                   if os.path.isfile(os.path.join(folder, f.split('.', 1)[-1]))]
        add('K1', False, '',
            bad='комплект неполный, нет: ' + ', '.join(missing_hard)
                + ' — болванка создана не целиком (ШАГ 1)'
                + ('. Рядом лежит '
                   + ', '.join(f.split('.', 1)[-1] for f in renamed)
                   + ' — переименуй по имени чарта, иначе проверки его не видят'
                   if renamed else ''))
    elif missing_soft:
        add('K1', False, '', warn=True,
            bad='нет ' + ', '.join(missing_soft) + ' — перенос сверять не с чем')
    else:
        add('K1', True, 'комплект файлов проекта на месте')

    if not is_tpl or not os.path.isdir(tpl_dir):
        return

    # K2 только для болванки и только для файлов, которые скилл кладёт сам.
    diverged = []
    for pattern, tpl in [('{name}.chart.js', KIT_CHART)] + KIT:
        if not tpl:
            continue
        fname = pattern.format(name=name)
        dst, src = os.path.join(folder, fname), os.path.join(tpl_dir, tpl)
        if not (os.path.isfile(dst) and os.path.isfile(src)):
            continue
        try:
            a = open(dst, encoding='utf-8', errors='replace').read()
            b = open(src, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        if _norm(a) != _norm(b):
            diverged.append(fname)

    add('K2', not diverged, 'болванка совпадает с templates/',
        bad='не копия шаблона: ' + ', '.join(diverged)
            + ' — болванка написана по памяти, инварианты каркаса потеряны'
            + ' (RETRO 51). Возьми файл из templates/ как есть; если он уже'
            + ' заполняется — гоняй validate.py БЕЗ --template')


def check_service(code, bare):
    """K3/K3b: служебный каркас ЗАПОЛНЕН по шаблону, а не написан заново.

    Реальный случай (RETRO 63), Test7. `bootstrap.py` отработал и положил
    копию `TEMPLATE.chart.js`. Шапка файла осталась шаблонной — вплоть до
    строки «var P = '.' + CFG.ns в buildHTML», — а БЛОКИ 2, 5, 6, 7 переписаны
    заново своими словами: `showTip(x, y, html)` вместо `showTip(html, rect)`
    (клампинг по окну потерян), свой `toDate` без разбора epoch-мс (RETRO 10
    вернулся), `state` не в неймспейсе `CFG.ns`, поиск хоста по выдуманному
    `[data-key^="_echarts_instance_"]`.

    Дальше всё пошло по кругу: первый прогон дал 10 FAIL, и ВСЕ ДЕСЯТЬ — это
    машинерия, которая в шаблоне уже была и работала. Свежая болванка проходит
    валидатор целиком (52/52), а сессия потратила шесть циклов исправлений
    на возврат к тому, что ей выдали на ШАГЕ 1.

    Отличить это от честной сборки нельзя ни по одной проверке симптомов:
    K2 сверяет с шаблоном только болванку и выключается ровно тогда, когда
    файл начинают заполнять. Поэтому здесь сверяются ТОЛЬКО те функции,
    которые шаблон отдаёт готовыми, без [ЗАПОЛНИ] внутри.
    """
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', KIT_CHART)
    if not os.path.isfile(tpl):
        return
    try:
        traw = open(tpl, encoding='utf-8').read()
    except OSError:
        return
    tcode, tbare = scan(traw)

    def diff(names):
        changed, lost = [], []
        for nm in names:
            want = find_function(tcode, tbare, nm)
            if want is None or '[ЗАПОЛНИ]' in want:
                continue      # это место шаблон оставил под заполнение
            got = find_function(code, bare, nm)
            if got is None:
                lost.append(nm)
            elif flat(got) != flat(want):
                changed.append(nm)
        return changed, lost

    core_changed, core_lost = diff(CORE_FNS)
    add('K3', not core_changed and not core_lost,
        'чистые хелперы БЛОКА 2 — из шаблона',
        bad='БЛОК 2 написан заново, а не заполнен: '
            + ', '.join(sorted(x + '()' for x in core_changed + core_lost))
            + (' — переписан' if core_changed else ' — потерян')
            + ' (RETRO 63). Это хелперы без окружения и состояния: случайно они'
              ' не расходятся, значит блок сочинялся с нуля. Вместе с ними'
              ' уезжают инварианты, которых по коду вокруг не видно: у toDate()'
              ' это разбор epoch-мс против epoch-с (RETRO 10), у esc() —'
              ' экранирование кавычки. Возьми тела из templates/' + KIT_CHART
            + ' как есть. И перечитай, что ещё в файле писалось заново:'
              ' FAIL ниже, скорее всего, следствия — чинить их по одному значит'
              ' переизобретать шаблон под диктовку валидатора')

    tip_changed, tip_lost = diff(TIP_FNS)
    if tip_changed:
        add('K3b', False, '', warn=True,
            bad='машинерия тултипа переписана: '
                + ', '.join(x + '()' for x in tip_changed)
                + ' — в шаблонных телах заперты клампинг по окну (RETRO 26)'
                  ' и снятие ОБОИХ скрывающих свойств (RETRO 44). Если тултип'
                  ' в задаче есть — верни тела из templates/' + KIT_CHART)


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

    # Незаполненный §2 закрывает только проверки про полноту чтения. Остальные
    # Z гоняются всегда: раньше пустое M глушило и их — тем громче, чем меньше
    # агент вёл NOTES вообще (RETRO 52).
    if claimed is None:
        add('Z1', False, '', warn=True,
            bad='NOTES §2 не заполнен — полнота чтения макета не доказана')
    elif real is None:
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
    if target is not None:
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

    # §1 вообще не начат, а код уже пишется: память подменена контекстом чата.
    # Считаем только строки-данные: заголовок и разделитель таблицы не в счёт.
    filled = [r for r in re.findall(r'^\|(?!\s*[-:# ]*\|)(.*)$', s1, re.M)
              if len([c for c in r.split('|')[1:3] if c.strip()]) == 2]
    body = len([l for l in open(path, encoding='utf-8', errors='replace')
                if l.strip() and not l.strip().startswith('//')])
    add('Z2b', bool(filled) or body < 120,
        'NOTES §1 начат до кода',
        bad='реестр NOTES §1 пуст, а в чарте уже ' + str(body) + ' строк кода — '
            + 'макет переносится по памяти чата, возобновление после обрыва'
            + ' невозможно (RETRO 52)')

    # §5: все блоки DONE.
    s5 = notes_section(txt, 5)
    undone = re.findall(r'^\|\s*[1-7]\s*\|[^|]*\|\s*(TODO|DOING)\s*\|', s5, re.M)
    add('Z3', not undone, 'NOTES §5: все блоки DONE',
        bad='в NOTES §5 блоков не DONE: ' + str(len(undone)))

    # §4: вопрос задан, ответа нет, а сборка идёт дальше.
    # В Test6 три вопроса по SQL ушли пользователю и остались без ответа, после
    # чего в §4 появилось «Решено без ответа», а в готовый виджет приехали
    # прочерки «—» на месте среднего возраста и медианы. Вопрос без ответа
    # блокирует ровно тот элемент, о котором спрашивали (RETRO 62).
    s4 = notes_section(txt, 4)
    dangling = []
    for row in re.findall(r'^\|(.+)\|\s*$', s4, re.M):
        cells = [c.strip() for c in row.split('|')]
        if len(cells) < 4 or not cells[1]:
            continue
        if re.match(r'^[-: ]+$', cells[1]) or cells[1].lower().startswith('дата'):
            continue
        answer = cells[2]
        if not answer or answer in ('—', '-', '–', '?', 'нет', 'н/д'):
            dangling.append(cells[1][:50])
    if re.search(r'без ответа|не дожид|ответа нет', s4, re.I):
        dangling.append('в §4 записано «решено без ответа»')
    add('Z5b', not dangling, 'вопросов без ответа пользователя нет',
        bad='в NOTES §4 вопрос без ответа: «' + '», «'.join(dangling[:2])
            + '» — решение за пользователя означает виджет, собранный не по ТЗ '
              '(в Test6 так приехали прочерки «—» вместо среднего возраста). '
              'Дождись ответа; если спрашивать было не нужно — напиши это '
              'в колонке ответа словами, прочерк там читается как «спросил '
              'и не дождался» (RETRO 62)')

    # §6: открытые хвосты.
    s6 = notes_section(txt, 6)
    tails = re.findall(r'^\s*-\s*\[ \]\s*\S', s6, re.M)
    if tails:
        add('Z4', False, '', warn=True,
            bad='в NOTES §6 незакрытых хвостов: ' + str(len(tails))
                + ' — закрой или проговори их пользователю в финальном ответе')


def check_fields(path):
    """F1: FIELDS.md — сдаточный документ по шаблону, а не файл своего сочинения.

    Реальный случай (RETRO 52), артефакт сессии в NewChart/FIELDS.md: разделы
    свои («Поля данных», «Ручные настройки Proteus»), раздела «Настроить РУКАМИ
    в Proteus» нет вовсе, а две его галочки проставлены агентом за пользователя.
    Пользователь получил документ, по которому виджет НЕ настроить: без ручного
    добавления полей в «Измерения» их просто нет в `data`.
    """
    fields_path = os.path.join(os.path.dirname(os.path.abspath(path)), 'FIELDS.md')
    master = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'templates', 'TEMPLATE.FIELDS.md')
    if not os.path.isfile(fields_path) or not os.path.isfile(master):
        return   # отсутствие файла — забота K1
    need = re.findall(r'^##\s*(.+?)\s*$', open(master, encoding='utf-8').read(), re.M)
    if not need:
        return
    txt = open(fields_path, encoding='utf-8', errors='replace').read()
    # Заголовок ищем по первым двум словам: хвост в скобках агент вправе убрать.
    missing = [h for h in need
               if not re.search(r'^##\s*' + re.escape(' '.join(h.split()[:2])),
                                txt, re.M | re.I)]
    add('F1', not missing, 'FIELDS.md по шаблону: все ' + str(len(need)) + ' раздела',
        bad='в FIELDS.md нет разделов: ' + '; '.join(missing)
            + ' — документ написан в своём формате, чек-лист ручных настроек'
            + ' Proteus до пользователя не дошёл (RETRO 52)')

    # Галочка означает «в Proteus реально настроено» — это отметка ПОЛЬЗОВАТЕЛЯ.
    # Проставленная агентом, она прячет причину пустого виджета.
    ticked = re.findall(r'^\s*-\s*\[[xXvV]\]\s*(\S.*)$', txt, re.M)
    add('F2', not ticked, 'чек-лист ручных настроек не отмечен за пользователя',
        warn=True,
        bad='в FIELDS.md проставлено галочек: ' + str(len(ticked)) + ' («'
            + (ticked[0][:40] if ticked else '') + '...») — если это не отметил'
            + ' пользователь, ты расписался за него: настройки в Proteus'
            + ' никто не делал')


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

    # ── Z6b. N/A в разделе B — только по причине из СРЕДЫ ──
    # «smoke.mjs отсутствует в папке проекта» — не причина, а неверный вызов:
    # скрипты лежат в папке скилла, рядом с validate.py, который тем же
    # ответом отработал (RETRO 58). Такой N/A закрывает ВЕСЬ браузерный
    # раздел и выглядит в отчёте как «так и надо».
    env_ok = r'playwright|код\s*2|blocked|заблокирован|не установлен|среда'
    fake = []
    for ln in rep.splitlines():
        if not re.search(r'\bB[1-6]\b', ln):
            continue
        if not re.search(r'N/?A|Н/?Д', ln, re.I):
            continue
        if not re.search(env_ok, ln, re.I):
            fake.append(re.sub(r'\s+', ' ', ln.strip())[:80])
    add('Z6b', not fake, 'N/A в разделе B объяснён причиной из среды',
        bad='браузерная проверка отмечена N/A без причины из среды: «'
            + '»; «'.join(fake[:2]) + '» — единственная законная причина это '
              'код 2 от `node <папка-скилла>/smoke.mjs --env` (нет playwright '
              'или запуск заблокирован). Нет файла рядом с чартом — значит '
              'запускать надо из папки скилла, а не ставить N/A (RETRO 58)')


def selftest():
    """--selftest: проверка самого валидатора по фикстурам с ИЗВЕСТНЫМ вердиктом.

    Ложный FAIL дороже пропущенного бага: агент верит проверке и идёт править
    ЗДОРОВЫЙ код — так из чарта уехал защитный try/catch, а половина сессии
    ушла на перестановку кавычек (RETRO 60). Ловится это только фикстурой,
    где заранее известно, что валидатор ОБЯЗАН промолчать.

    K1 не в счёт: фикстуры лежат кучей, а не проектными папками.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    fx = os.path.join(here, 'fixtures')
    exp_path = os.path.join(fx, 'EXPECT.validate.json')
    if not os.path.isfile(exp_path):
        print('Нет ' + exp_path)
        return 2
    import json
    expect = json.load(open(exp_path, encoding='utf-8'))
    print('Самопроверка validate.py по фикстурам:')
    bad = 0
    for name in sorted(k for k in expect if not k.startswith('_')):
        want = sorted(expect[name]['fail'])
        p = subprocess.run([sys.executable, os.path.abspath(__file__),
                            os.path.join(fx, name), '--quiet'],
                           capture_output=True, text=True)
        got = sorted(set(re.findall(r'^\s*X\s+(\S+)\s+FAIL', p.stdout, re.M)) - {'K1'})
        ok = got == want
        bad += 0 if ok else 1
        print((' v  ' if ok else ' X  ') + name.ljust(24)
              + 'ждали FAIL [' + (', '.join(want) or '—')
              + '], получили [' + (', '.join(got) or '—') + ']')
        if not ok and expect[name].get('note'):
            print('      ' + expect[name]['note'])
    print('Итог: ' + ('валидатор судит фикстуры верно (код 0).' if not bad
                      else 'расхождений: ' + str(bad) + ' (код 1).'))
    return 1 if bad else 0


def parse_accept(args):
    """--accept КОД=причина — разобрать и в форме '--accept X=y', и '--accept=X=y'.

    Причина обязательна и не короче 12 символов: «ложное» или «ок» это не
    оспаривание, а способ закрыть сдачу. Такой --accept игнорируется молча
    для проверки, но громко для агента — строка ниже печатается всегда.
    """
    out, rest, i = {}, [], 0
    while i < len(args):
        a = args[i]
        val = None
        if a == '--accept':
            i += 1
            val = args[i] if i < len(args) else ''
        elif a.startswith('--accept='):
            val = a[len('--accept='):]
        else:
            rest.append(a)
            i += 1
            continue
        cid, _, why = (val or '').partition('=')
        cid, why = cid.strip(), why.strip()
        if not cid or len(why) < 12:
            print('--accept ' + (val or '') + ' — нужна форма КОД=причина,'
                  ' и причина словами, не короче 12 символов. Оспаривание'
                  ' не применено.')
        else:
            out[cid] = why
        i += 1
    return out, rest


def main():
    acc, args = parse_accept(sys.argv[1:])
    ACCEPTED.update(acc)
    flags = set(a for a in args if a.startswith('--'))
    paths = [a for a in args if not a.startswith('--')]
    unknown = flags - {'--template', '--quiet', '--selftest'}
    if unknown:
        print('Неизвестный флаг: ' + ', '.join(sorted(unknown)))
        return 2
    if '--selftest' in flags:
        return selftest()
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
    mns = re.search(r"\bns\s*:\s*['\"]([\w-]+)['\"]", code)
    ns = mns.group(1) if mns else 'pvt'

    # ══ P5. Синтаксис ══
    try:
        p = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        add('P5', p.returncode == 0, 'node --check' if p.returncode == 0
            else p.stderr.strip().splitlines()[0] if p.stderr else 'syntax error')
    except (FileNotFoundError, OSError):
        add('P5', False, 'node не найден — синтаксис НЕ проверен, проверь вручную', warn=True)

    # ══ H3. Это вообще каркас скилла? ══
    # Двадцать разрозненных FAIL агент чинит по одному и жжёт на этом контекст,
    # хотя чинить нечего: файл написан мимо шаблона, и правки симптомов его
    # туда не вернут. Один ранний вердикт вместо переборки (RETRO 52).
    marks = {
        'заголовков «// БЛОК N»': bool(re.search(r'^\s*//\s*-*\s*БЛОК\s+\d', raw, re.M)),
        'глобального option': bool(re.search(r'^option\s*=', code, re.M)),
        'window.__pvtState': '__pvtState' in bare,
        'CFG.ns': bool(re.search(r'\bns\s*:\s*[\'"]', bare)),
    }
    lost = [k for k, v in marks.items() if not v]
    add('H3', len(lost) < 2, 'каркас шаблона на месте',
        bad='нет ' + ', '.join(lost) + ' — файл собран мимо TEMPLATE.chart.js.'
            ' Остальные FAIL ниже — следствия: чинить их по одному бессмысленно,'
            ' пересобирай по шаблону блоками 1→7 (RETRO 52)')

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
    # Смотрим на ВСЕ catch, а не на первый попавшийся: свой try/catch вокруг
    # JSON.parse в обработчике стоит в файле раньше монтажного, и проверка «по
    # первому» роняла правильный код. Агент честно шёл чинить чарт и УДАЛЯЛ
    # защитный catch, чтобы позеленело (RETRO 60). Достаточно, чтобы хотя бы
    # один catch показывал ошибку в overlay и не трогал option.
    catches = []
    for mc in re.finditer(r'catch\s*\([^)]*\)\s*', bare):
        br3 = bare.find('{', mc.end())
        if br3 == -1:
            continue
        end3 = match_braces(bare, br3)
        if end3 == -1:
            continue
        catches.append(bare[br3 + 1:end3])
    if not catches:
        add('C6b', False, '', bad='не найден блок catch — ошибка монтажа будет молчаливой')
    else:
        ok = any('option' not in c and ('innerHTML' in c or 'textContent' in c)
                 for c in catches)
        add('C6b', ok, 'catch выводит ошибку в overlay',
            bad='ни один catch не показывает ошибку в overlay (или обращается '
                'к option до БЛОКА 7) — сбой монтажа останется молчаливым '
                '(RETRO 16, 24)')

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
    # Всё, что ниже, читает СКЛЕЕННЫЙ CSS (css_text): проверка не должна
    # зависеть от того, на каком куске конкатенации стоит дефис (RETRO 63).
    css_span = find_span(code, bare, 'buildCSS')
    css_body = None if css_span is None else code[css_span[0]:css_span[1]]
    flat_css = css_text(code, bare, css_span, ns)
    rules = css_rules(flat_css)
    if css_body is None:
        add('S5', is_tpl, 'buildCSS() не найдена', warn=is_tpl,
            bad='buildCSS() не найдена — стили макета не перенесены')
    else:
        bad_sel = [sel[:40] for sel, _ in rules if not re.match(r'^[.#]', sel)]
        has_prefix_var = bool(re.search(r"=\s*['\"]\.['\"]\s*\+\s*CFG\.ns", css_body)) \
            or bool(re.search(r"CFG\.ns\s*\+\s*['\"]-", css_body))
        add('S5', not bad_sel and has_prefix_var,
            'все селекторы префиксованы',
            bad=('голые селекторы: ' + ', '.join(bad_sel[:5])
                 + ' — правило без префикса утечёт в интерфейс Proteus. Холст '
                   'eCharts прячется из JS (host.querySelector(\'canvas\')), '
                   'а не правилом canvas{display:none} (RETRO 5, 63)' if bad_sel
                 else 'нет префикса через CFG.ns — стили утекут в дашборд (RETRO 5)'))

        # ── S5b. Префикс вписан руками вместо P ──
        # '.chart-row' в строке CSS работает ровно до тех пор, пока CFG.ns
        # равен 'chart'. Такие правила молча отваливаются при смене ns и
        # обычно появляются при копипасте макета кусками.
        # Смотрим на ИСХОДНИК, а не на склейку: в склейке префикс есть везде.
        lit = '.' + ns + '-'
        n_hard = css_body.count(lit)
        add('S5b', n_hard == 0, 'префикс в buildCSS только через P/CFG.ns', warn=True,
            bad='(RETRO 47) литерал "' + lit + '" вписан в CSS ' + str(n_hard)
                + ' раз вместо P — смена CFG.ns сломает эти правила')

        # ── S19. Корень резиновый ──
        # Макет — отдельная страница со своей рамкой: фикс-ширина, центрирование.
        # Перенесённая на корень, рамка замораживает виджет: ячейка дашборда
        # растёт, а график — нет. Фикс-размеры допустимы только у внутренних
        # элементов; min-width на корне не мешает тянуться и не считается.
        root_rule = ''
        for sel, body in rules:
            if re.search(r'-root\s*$', sel) or re.search(r'-root[.:\s]', sel + ' '):
                root_rule = body.replace(' ', '')
                break
        if root_rule:
            fixed = [m.group(0) for m in
                     re.finditer(r'(?<![a-z-])(?:max-)?width:\d+(?:\.\d+)?px', root_rule)]
            add('S19', not fixed, 'корень резиновый, без фиксированной ширины',
                bad='(RETRO 48) у .<ns>-root фиксированная ширина: '
                    + ', '.join(fixed[:3]) + ' — виджет не растянется за ячейкой '
                    'дашборда. Рамка макета не переносится: корень width:100%')
            if not fixed and 'width:100%' not in root_rule:
                add('S19b', False, '', warn=True,
                    bad='(RETRO 48) в правиле .<ns>-root нет width:100% — сверь '
                        'с шаблоном: корень обязан тянуться за хостом')

        # ── S20. Оконные @media ──
        # @media (max-width) меряет ОКНО, а виджет живёт в ячейке дашборда:
        # окно 1920px, ячейка 400px — «узкая» ветка не включится никогда.
        # Для тултипа в body оконная ширина законна — тогда объясни WARN строкой.
        medias = re.findall(r'@media[^{]*\(\s*(?:max|min)-width', flat_css)
        if medias:
            add('S20', False, '', warn=True,
                bad='(RETRO 49) @media по ширине ОКНА в buildCSS (правил: '
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

        # ── S6b. Класс СКЛЕЕН из CFG.ns, а правила под него нет ──
        # S6 читает только литерал внутри class="…", а в этом каркасе классы
        # почти всегда собираются конкатенацией — и она для S6 невидима.
        # Реальный случай (RETRO 64), Test7: разметка ставит панели
        # `CFG.ns + '-active'`, то есть class="pvt-pyr-view pvt-active",
        # а CSS показывает панель правилом `P + 'pyr-view.active'` — по классу
        # БЕЗ префикса. До первого клика ни одна из пяти пирамид не видна:
        # правая половина виджета пустая. Ни синтаксис, ни S6, ни браузерные
        # проверки этого не заметили — smoke кликает вкладки и меряет ПОСЛЕ
        # клика, когда обработчик уже дописал класс руками.
        # Ищем по ВСЕЙ разметке, а не внутри class="…": модификатор часто
        # приезжает переменной (var tActive = ' ' + CFG.ns + '-active'), и
        # разбор одного атрибута его не увидит — а это ровно случай Test7.
        # Имена АТРИБУТОВ сюда не относятся: их разбирает T7b.
        # Префикс в разметке зовут и CFG.ns, и P (var P = CFG.ns — без точки,
        # точка только в buildCSS, см. S15). Обе формы — один и тот же класс.
        pref_re = r"CFG\.ns"
        if re.search(r"\bP\s*=\s*CFG\.ns\b(?!\s*\+\s*['\"]\.)", html_body):
            pref_re = r"(?:CFG\.ns|\bP)"
        used_ns = set(m.group(1) for m in re.finditer(
            pref_re + r"\s*\+\s*['\"]-([a-z0-9][\w-]*)", html_body))
        used_ns = set(c for c in used_ns
                      if not c.startswith(('data-', 'aria-', 'role')))
        known = set(re.findall(r'\.' + re.escape(ns) + r'-([a-z0-9][\w-]*)',
                               flat_css, re.I))
        # Рассогласование доказуемо, когда правило под этот класс ЕСТЬ,
        # но без префикса: значит одна половина писалась через CFG.ns,
        # а вторая — руками, и в DOM они не встретятся.
        mismatch = sorted(c for c in used_ns - known
                          if re.search(r'\.' + re.escape(c) + r'(?![\w-])', flat_css))
        add('S6b', not mismatch or is_tpl, 'префикс класса в разметке и в CSS совпадает',
            warn=is_tpl,
            bad='разметка ставит .' + ns + '-' + (', .' + ns + '-').join(mismatch[:5])
                + ', а правило в buildCSS написано БЕЗ префикса: .'
                + '  .'.join(mismatch[:5]) + '. В DOM эти два класса не встретятся'
                + ' никогда (RETRO 64). Именно так в Test7 пропала правая половина'
                + ' виджета: разметка ставила class="' + ns + '-pyr-view ' + ns
                + '-active", а показывало панель правило .' + ns
                + '-pyr-view.active — до первого клика не была видна ни одна'
                + ' пирамида, и ни одна проверка этого не заметила, потому что'
                + ' браузерные меряют экран ПОСЛЕ клика, когда класс дописал'
                + ' обработчик. Выбери одну сторону: либо оба с префиксом,'
                + ' либо оба без')

        # Класс без правила ВООБЩЕ — может быть просто зацепкой для
        # querySelector, поэтому WARN, а не приговор.
        orphan = sorted(c for c in used_ns - known
                        if not re.search(r'\.' + re.escape(c) + r'(?![\w-])', flat_css))
        if orphan and not is_tpl:
            add('S6c', False, '', warn=True,
                bad='классы разметки без единого правила: .' + ns + '-'
                    + (', .' + ns + '-').join(orphan[:5])
                    + ' — если это зацепка для querySelector, так и должно быть;'
                      ' если элемент ждал стилей макета, они не перенесены (RETRO 6)')

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
        n_ff = len(re.findall(r'font-family', flat_css))
        # Правило тултипа ищем в СКЛЕЕННОМ CSS: в исходнике оно выглядит и как
        # P + '-tip{', и как P + 'tip{' — от этого зависело только сообщение
        # «тултип без font-family», выданное на код, где font-family есть
        # (RETRO 63).
        tip_body_css = ''
        for sel, rbody in rules:
            if re.search(r'-tip\s*$', sel) or re.search(r'-tip[.:\s,]', sel + ' '):
                tip_body_css = rbody
                break
        if has_tip:
            add('T3', n_ff >= 2 and 'font-family' in tip_body_css,
                'font-family задан и в root, и в тултипе',
                bad='тултип без своего font-family — будет другой шрифт (RETRO 21). '
                    'Ищется правило .' + ns + '-tip в СКЛЕЕННОМ CSS, так что форма '
                    'записи префикса тут ни при чём: проверь, что font-family '
                    'стоит именно в правиле тултипа, а не только у корня')
        add('T4', 'font-family:inherit' in flat_css.replace(' ', ''),
            'font-family:inherit для дочерних', warn=True,
            bad='нет font-family:inherit — button/input возьмут системный шрифт (RETRO 21)')

    # ══ T5. Симметрия: чем спрятали, тем и показываем ══
    # Правило тултипа в CSS прячет узел (opacity:0 / visibility:hidden /
    # display:none), а снять это обязан JS в момент показа. Нет снятия — тултип
    # честно строится, позиционируется и наполняется текстом, но остаётся
    # невидимым: ни ошибки, ни пустого экрана, ни зацепки в отладке (RETRO 44).
    if has_tip and css_body is not None:
        rule = tip_body_css.replace(' ', '')
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
        tight_css = flat_css.replace(' ', '')
        for name, hide_pat, show_pat, cls_pat in props:
            if not re.search(hide_pat, rule):
                continue
            if re.search(show_pat, code):
                continue
            # класс-переключатель — тоже законный способ показа
            if re.search(r'classList\.(?:add|toggle|remove)\s*\(', code) \
                    and re.search(cls_pat, tight_css):
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

    # ══ T7. Имя атрибута-триггера — часть контракта ══
    # smoke.mjs ищет интерактив селектором [data-tip],[data-kind],[data-action]:
    # это имена атрибутов ЦЕЛИКОМ, а не префиксы. Своё имя (data-tip-kind,
    # data-hint) он не находит, и браузерные проверки B1-B5 не падают,
    # а ПРОПУСКАЮТСЯ — отчёт выглядит полным, экрана никто не видел (RETRO 56).
    if html_body is not None:
        found = sorted(set(re.findall(r'\bdata-[\w-]+', html_body)))
        canon = [a for a in found if a in ('data-tip', 'data-kind', 'data-action')]
        add('T7', not found or bool(canon),
            'триггеры помечены именами, которые видит smoke.mjs',
            warn=True,
            bad='в разметке есть ' + ', '.join(found[:4])
                + ', но ни одного data-tip/data-kind/data-action — smoke.mjs ищет '
                  'ровно эти имена и интерактив не найдёт: проверки тултипа уйдут '
                  'в N/A вместо FAIL (RETRO 56)')

    # ══ T7b. Имя атрибута, СОБРАННОЕ из CFG.ns ══
    # `' + CFG.ns + '-data-tip="..."` выглядит в исходнике как data-tip и даже
    # проходит T7, а в DOM приезжает `pvt-data-tip`. Виджет при этом работает:
    # свой же onOver читает то же имя — поэтому баг незаметен до сдачи, где
    # ВЕСЬ тултиповый слой уходит в N/A и его не проверяет никто (RETRO 59).
    ns_attr = sorted(set(
        m.group(1) for m in re.finditer(
            r"""(?:CFG\.ns|\bP)\s*\+\s*['"]-(data-(?:tip|kind|action|view)[\w-]*)""", code)))
    add('T7b', not ns_attr, 'имена триггерных атрибутов не склеены с CFG.ns',
        bad='атрибут собран из CFG.ns: в DOM приедет "<ns>-' + (ns_attr[0] if ns_attr else '')
            + '" вместо "' + (ns_attr[0] if ns_attr else '') + '" — smoke.mjs ищет имя '
              'ЦЕЛИКОМ, тултипы и вкладки уйдут в N/A (RETRO 59). Префикс CFG.ns '
              'нужен КЛАССАМ, а не data-атрибутам')

    # ══ S21. Слушатели под флагом, который переживает перезапуск ══
    # Proteus перезапускает скрипт на КАЖДОЙ перерисовке. Монтаж при этом
    # создаёт НОВЫЙ overlay, а флаг «слушатели уже навешены» лежит в
    # window.__pvtState и перезапуск переживает. Итог (RETRO 65, Test7):
    # после первой же перерисовки новый overlay остаётся вообще без
    # обработчиков — ни тултипов, ни вкладок, при этом ни одной ошибки
    # в консоли и полностью правильная картинка. Дублей бояться нечего:
    # старый overlay удалён вместе со своими слушателями, поэтому в шаблоне
    # addEventListener стоит безусловно.
    guarded = []
    for m in re.finditer(r'\bif\s*\(', bare):
        op = m.end() - 1
        cp = match_parens(bare, op)
        if cp == -1:
            continue
        cond = code[op:cp + 1]
        if not re.search(r'\bstate\b', cond):
            continue
        br6 = bare.find('{', cp)
        if br6 == -1 or bare[cp + 1:br6].strip():
            continue
        end6 = match_braces(bare, br6)
        if end6 == -1:
            continue
        for ml in re.finditer(r'(\w+)\s*\.\s*addEventListener', code[br6:end6]):
            if ml.group(1) not in ('window', 'document'):
                guarded.append(ml.group(1) + ' (строка '
                               + str(line_of(raw, br6 + ml.start())) + ')')
    add('S21', not guarded, 'слушатели overlay навешиваются безусловно',
        bad='addEventListener на ' + ', '.join(sorted(set(guarded))[:3])
            + ' стоит под условием из state. Флаг переживает перезапуск скрипта,'
            ' а overlay пересоздаётся — после первой же перерисовки Proteus'
            ' новый overlay останется без обработчиков: тултипы и вкладки'
            ' умрут молча, без ошибок в консоли (RETRO 65). Старый overlay'
            ' удаляется вместе со слушателями, дублей не будет: вешай'
            ' безусловно, как в шаблоне. Флаг нужен ТОЛЬКО window/document —'
            ' они перезапуск переживают')

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

    # ══ Гигиена: console.* ══
    # Раньше ловился только console.log — и в сданный Test7 уехал
    # console.error из ветки catch. Для пользователя разницы нет: и то и другое
    # это отладочный вывод в консоли боевого дашборда. Ошибку монтажа показывает
    # overlay (C6b), консоль для этого не нужна.
    cl = [i for i, l in enumerate(code_lines, 1) if re.search(r'\bconsole\s*\.\s*\w', l)]
    add('H1', not cl, 'нет console.*', warn=True,
        bad='console.* → строки ' + ','.join(map(str, cl[:5]))
            + ' — отладочный вывод в боевом файле; ошибку показывает overlay (C6b)')

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
    # Форма важна: шаблон объявляет fields ОБЪЕКТОМ { alias: 'sql_column' }.
    # Массив имён — уже не он: по нему не построить ни автомок в smoke.mjs,
    # ни сверку alias'ов с FIELDS.md, а искать '{' дальше по файлу нельзя —
    # найдётся первый попавшийся объект и посчитается вместо полей.
    as_array = bool(mf and bare[mf.end():mf.end() + 1] == '[')
    if mf and not as_array:
        br5 = bare.find('{', mf.end())
        if br5 != -1 and not bare[mf.end():br5].strip():
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
        check_kit(path, True)
    else:
        check_kit(path, False)
        check_service(code, bare)
        add('M4', n_fields > 0, 'CFG.fields: ' + str(n_fields) + ' полей',
            bad='CFG.fields задан массивом имён, а шаблон ждёт объект'
                ' { alias: \'sql_column\' } — по массиву не работают ни автомок'
                ' smoke.mjs, ни сверка alias\'ов (RETRO 52)' if as_array else
                'CFG.fields пуст — данные не привязаны к SQL')
        todo = [i for i, l in enumerate(lines, 1) if '[ЗАПОЛНИ]' in l or '[ЗАМЕНИ]' in l]
        add('M4b', not todo, 'нет незакрытых TODO',
            bad='остались плейсхолдеры → строки ' + ','.join(map(str, todo[:6])))

        # ══ H3. Тихое упрощение ══
        # «Группировка не реализована для простоты — все бары подряд»: элемент
        # макета выброшен, решение оформлено комментарием в коде, пользователь
        # узнаёт об этом, глядя на картинку. Урезание объёма — это ВОПРОС,
        # а не заметка на полях (RETRO 61).
        # Регулярка описывает УРЕЗАНИЕ ОБЪЁМА, а не отдельные слова. Прежняя
        # ловила «пока не» и «заглушк» где угодно — и роняла сдачу на
        # `// идём вверх, пока не упрёмся в overlay` и на `// Заглушка при
        # пустых данных`, то есть на комментарии, описывающем ветку noData,
        # которую сам скилл и требует (C5). Агент тратил итерацию на
        # переписывание комментария, а не кода (RETRO 63).
        cut = []
        for c in comments_of(raw, code):
            low = c.lower()
            if re.search(r'нет данных|пуст|no ?data|данных нет', low):
                continue      # это про ветку CFG.text.noData, а не про урезание
            if re.search(r'не реализован|нереализован|для простоты|упрощ[её]н'
                         r'|в этой версии|\btodo\b|\bfixme\b'
                         r'|пока (?:что )?(?:не|нет)\s*(?:реализ|сдела|поддерж'
                         r'|работ|подключ|перенес|считае|учитыва)'
                         r'|пока только|пока без'
                         r'|временно\s*(?:не|отключ|убра|захардкож|заглуш)'
                         r'|заглушк\w*\s+(?:вместо|для|на месте|под)', low):
                cut.append(c.strip()[:60])
        add('H4', not cut, 'нет упрощений, спрятанных в комментарий',
            bad='код признаётся, что делает не то, что в макете: «' + '», «'.join(cut[:2])
                + '» — либо реализуй, либо СПРОСИ пользователя и запиши ответ '
                  'в NOTES §4; комментарий в коде решением не является (RETRO 61)')
        # ══ Z/F. Полнота чтения макета и формат сдачи ══
        check_notes(path)
        check_fields(path)
        check_report(path)

    # ── отчёт ──
    w = max(len(c) for c, _, _ in R)
    fails = sum(1 for _, s, _ in R if s == 'FAIL')
    warns = sum(1 for _, s, _ in R if s == 'WARN')
    disp = sum(1 for _, s, _ in R if s == 'ОСПОР')
    total = len(R)
    print('\n' + path)
    print('-' * 72)
    shown = 0
    for cid, st, msg in R:
        if quiet and st == 'PASS':
            continue
        shown += 1
        mark = {'PASS': 'v', 'FAIL': 'X', 'WARN': '!', 'ОСПОР': '?'}[st]
        print(' ' + mark + '  ' + cid.ljust(w) + '  ' + st.ljust(5) + '  ' + msg)
    if quiet and shown == 0:
        print(' всё чисто')
    print('-' * 72)
    print('Итог: ' + str(total - fails - warns - disp) + '/' + str(total) + ' PASS, '
          + str(warns) + ' WARN, ' + str(disp) + ' ОСПОР, ' + str(fails) + ' FAIL')
    # Про чужие коды не ворчим: check.py передаёт --accept обоим чекерам,
    # и E-коды принадлежат smoke.mjs.
    unused = sorted(set(k for k in ACCEPTED if not k.startswith('E'))
                    - set(c for c, s, _ in R if s == 'ОСПОР'))
    if unused:
        print('\n--accept на кодах, которые НЕ падали: ' + ', '.join(unused)
              + ' — проверь ID, оспаривание к ним не применилось.')
    if disp:
        print('\nОСПОРЕНО проверок: ' + str(disp) + '. Это не «пройдено»: каждую строку'
              '\nвыпиши в NOTES §6 и назови пользователю в финальном ответе словами.')
        if disp > 2:
            print('Оспорено больше двух проверок разом — так выглядит не серия ложных'
                  '\nтревог, а подгонка сдачи. Перечитай SKILL.md, «ОСПАРИВАНИЕ ПРОВЕРКИ».')
    if fails:
        print('\nСДАВАТЬ НЕЛЬЗЯ. Исправь FAIL и запусти снова.')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
