#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan-layout.py — структурный дайджест макета ДО его чтения.

ЗАЧЕМ. Макет большой не потому, что в нём много РАЗНОГО, а потому, что в нём
много ОДИНАКОВОГО. В реальном Test5: 64 КБ файла, из них 23 КБ (37%) — payload
атрибутов data-tip, ещё 12 КБ — 24 копии одного и того же <g class="bar">.
Прочитать это построчно значит вбить в контекст 35 КБ мок-текста, который
всё равно будет выброшен: тултипы пересобираются из данных, а бары — из формулы.
После такого чтения на сборку JS контекста уже не остаётся (RETRO 53).

Дайджест отвечает на три вопроса ДО первого Read:
  1. из чего состоит файл по весу — где CSS, где разметка, где <script>;
  2. что в нём повторяется — какие блоки читать образцом, а не целиком;
  3. какие диапазоны читать подряд, а какие можно закрыть двумя штуками.

Полнота покрытия при этом НЕ падает: диапазон остаётся покрытым, просто
из 24 одинаковых баров прочитано 2, а в NOTES §2 записано «по образцу 24×».
Это честная запись, и она сильнее пересказа: формулу геометрии выводят
из двух образцов, а не из двадцати четырёх (RETRO 55).

ЗАПУСК:
    python3 scan-layout.py <макет>.html
    python3 scan-layout.py <макет>.html --plan    # только план чтения

Читать сам скрипт не нужно — только запускать.
КОД ВОЗВРАТА: 0 — дайджест построен, 2 — файл не открылся.
"""

import os
import re
import sys

MAX_RANGE = 300           # правило 4 SKILL.md: диапазон чтения ≤300 строк
REPEAT_MIN = 4            # с какого числа копий блок считается повторяющимся
SAMPLE = 2                # сколько копий читать глазами


def die(msg):
    sys.stderr.write(msg + '\n')
    sys.exit(2)


def kb(n):
    return str(int(round(n / 1024.0))) + ' КБ'


def pct(part, whole):
    return str(int(round(100.0 * part / whole))) + '%' if whole else '0%'


# ---------------------------------------------------------------- разбор

def find_section(lines, tag):
    """Границы <tag>...</tag> по номерам строк (1-based, включительно)."""
    start = end = None
    for i, ln in enumerate(lines, 1):
        low = ln.lower()
        if start is None and '<' + tag in low:
            start = i
        if start is not None and '</' + tag + '>' in low:
            end = i
            break
    return (start, end) if start and end else (None, None)


def signature(tag, cls):
    """Подпись блока: тег + классы без числовых модификаторов.

    h1/h2/h5 у ячеек heatmap — это ОДИН вид ячейки в пяти оттенках, а не пять
    разных элементов, поэтому хвостовые цифры из имени класса убираются.
    """
    names = [c for c in re.split(r'\s+', cls.strip()) if c]
    names = [re.sub(r'\d+$', '', c) for c in names]
    names = sorted(set(n for n in names if n))
    return tag + ('.' + '.'.join(names) if names else '')


VOID = set('br meta link img input hr col area base source track wbr'.split())


def line_index(text):
    """Смещения начал строк — чтобы переводить позицию в номер строки."""
    idx, pos = [0], 0
    for ln in text.split('\n')[:-1]:
        pos += len(ln) + 1
        idx.append(pos)
    return idx


def line_of(idx, off):
    lo, hi = 0, len(idx) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if idx[mid] <= off:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def element_span(text, start, tag):
    """Конец элемента с учётом вложенности — а не «до следующего такого же».

    Без этого копия бара захватывает идущий следом заголовок группы, и блок
    выглядит неоднородным там, где он однороден.
    """
    rx = re.compile(r'<(/?)' + re.escape(tag) + r'\b([^>]*?)(/?)>', re.I)
    depth = 0
    for m in rx.finditer(text, start):
        if m.group(1) == '/':
            depth -= 1
            if depth <= 0:
                return m.end()
        else:
            if m.group(3) == '/' or tag in VOID:
                if m.start() == start:
                    return m.end()
            else:
                depth += 1
    return len(text)


def scan_tags(text, idx):
    """Открывающие теги с классами: подпись -> [(строка, позиция, тег)]."""
    hits = {}
    rx = re.compile(r'<([a-zA-Z][\w-]*)\b([^>]*)>')
    rx_cls = re.compile(r'\bclass\s*=\s*(["\'])(.*?)\1', re.S)
    for m in rx.finditer(text):
        tag = m.group(1).lower()
        if tag in ('html', 'head', 'body') or tag in VOID:
            continue
        mc = rx_cls.search(m.group(2))
        sig = signature(tag, mc.group(2) if mc else '')
        hits.setdefault(sig, []).append((line_of(idx, m.start()), m.start(), tag))
    return hits


def scan_data_attrs(text):
    """data-* атрибуты: имя -> (сколько раз, сколько байт вместе со значением)."""
    out = {}
    for m in re.finditer(r'\b(data-[\w-]+)\s*=\s*(["\'])(.*?)\2', text, re.S):
        name = m.group(1)
        cnt, size = out.get(name, (0, 0))
        out[name] = (cnt + 1, size + len(m.group(0).encode('utf-8')))
    return out


def scan_css_vars(text):
    """Переменные из :root — они едут в CFG почти дословно."""
    m = re.search(r':root\s*\{(.*?)\}', text, re.S)
    if not m:
        return []
    return re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', m.group(1))


# ---------------------------------------------------------------- вывод

def repeated_blocks(hits):
    """Повторы с РОВНЫМ шагом: подряд идущие копии одного блока.

    Пять `span` на весь файл — не повтор, а совпадение имени тега: между ними
    по сотне строк другого содержимого, и «читать образцом» там нечего.
    Настоящий повтор идёт с ровным шагом: 24 бара через каждые 8 строк.
    """
    out = []
    for sig, occ in hits.items():
        if len(occ) < REPEAT_MIN:
            continue
        occ = sorted(occ)
        ls = [o[0] for o in occ]
        gaps = sorted(ls[i + 1] - ls[i] for i in range(len(ls) - 1))
        pitch = gaps[len(gaps) // 2]                      # медианный шаг
        if pitch < 1 or pitch > 40:
            continue
        tight = [g for g in gaps if g <= pitch * 2 + 1]   # копии идут подряд
        if len(tight) < len(gaps) * 0.7:
            continue
        out.append({'n': len(occ), 'sig': sig, 'lo': ls[0], 'hi': ls[-1],
                    'pitch': pitch, 'at': occ, 'tag': occ[0][2]})
    out.sort(key=lambda b: -b['n'])
    return out


def copy_chunks(text, zone):
    """Точный текст каждой копии — от открывающего тега до его закрывающего."""
    return [text[off:element_span(text, off, tag)]
            for _, off, tag in zone['at']]


def homogeneity(text, zone):
    """Доля копий с одинаковым внутренним устройством.

    Восемь `span.pb-lbl` идут ровным шагом, но копия 1 — это воронка,
    а копия 4 — SVG-пирамида. Такие «повторы» взаимозаменяемыми НЕ являются,
    и прочитать 2 из 8 значит молча потерять шесть разделов макета.
    Однородность отличает настоящий повтор от совпадения ритма.
    """
    shapes = {}
    for chunk in copy_chunks(text, zone):
        tags = tuple(t.lower() for t in re.findall(r'<([a-zA-Z][\w-]*)', chunk))
        shapes[tags] = shapes.get(tags, 0) + 1
    return (max(shapes.values()) / float(len(zone['at']))) if shapes else 0.0


def dense_zones(text, blocks):
    """Непересекающиеся зоны повторов. Из вложенных берётся ВНЕШНЯЯ.

    В таблице `td.hm` встречается 45 раз, а `tr.det-row` — 15: ячейки лежат
    ВНУТРИ строк. Читать надо строку целиком, поэтому при пересечении
    выигрывает блок с бо́льшим шагом — он и есть внешний. Но однородный
    повтор всегда важнее неоднородного: только его можно читать образцом.
    """
    cand = []
    for b in blocks:
        if b['hi'] - b['lo'] < 3 * b['pitch']:
            continue
        chunks = copy_chunks(text, b)
        b['size'] = sum(c.count('\n') + 1 for c in chunks) / float(len(chunks))
        # копии обязаны ЗАПОЛНЯТЬ зону: 8 однострочных заголовков, разбросанных
        # по 300 строкам, — не блок для чтения образцом, а просто частый тег
        b['fill'] = b['size'] * b['n'] / float(b['hi'] - b['lo'] + b['size'])
        if b['fill'] < 0.5:
            continue
        b['homog'] = homogeneity(text, b)
        cand.append(b)
    # внешний блок узнаётся по РАЗМЕРУ копии: <g class="bar"> содержит текст
    # и rect внутри себя, поэтому его копия длиннее, чем копия любого из них
    cand.sort(key=lambda b: (b['homog'] < 0.7, -b['size'], -b['n']))
    zones = []
    for b in cand:
        if any(not (b['hi'] < z['lo'] or b['lo'] > z['hi']) for z in zones):
            continue
        zones.append(b)
    zones.sort(key=lambda z: z['lo'])
    return zones


def copy_texts(text, zone, limit=48):
    """Видимый текст каждой копии — весь смысл повтора в 1 КБ вместо 12 КБ.

    Из 24 одинаковых баров различаются ровно три вещи: подпись, число, доля.
    Здесь они выписываются В ПОРЯДКЕ МАКЕТА — а порядок категорий и есть то,
    что теряется при пересказе и потом всплывает как «отсортировал по величине»
    (RETRO 54).
    """
    chunks = copy_chunks(text, zone)
    out = []
    for chunk in chunks[:limit]:
        chunk = re.sub(r'\b(?:data-[\w-]+|style|class|aria-\w+|role)\s*=\s*'
                       r'(["\']).*?\1', ' ', chunk, flags=re.S)
        chunk = re.sub(r'<[^>]*>', ' ', chunk)
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        out.append(chunk[:190])
    return out, len(chunks) > limit


def read_plan(total, style, script, zones):
    """План чтения: подряд ≤300 строк, повторы — двумя копиями и последней."""
    plan = []
    cuts = [1]
    for z in zones:
        cuts += [z['lo'], z['hi2'] + 1]
    for a, b in (style, script):
        if a:
            cuts += [a, b + 1]
    cuts = sorted(set(c for c in cuts if 1 <= c <= total)) + [total + 1]

    for a, b in zip(cuts, cuts[1:]):
        b -= 1
        if b < a:
            continue
        zone = next((z for z in zones
                     if z['lo'] <= a and b <= z['hi2'] and z['homog'] >= 0.7), None)
        if zone:
            at = [o[0] for o in zone['at']]
            head = at[SAMPLE] - 1 if len(at) > SAMPLE else b
            last = at[-1]
            plan.append((a, b, 'ОБРАЗЕЦ',
                         str(zone['n']) + '× ' + zone['sig'],
                         'геометрия: ' + str(a) + '-' + str(head)
                         + ' и последняя копия ' + str(last) + '-' + str(b)))
            continue
        what = 'разметка'
        if style[0] and a >= style[0] and b <= style[1]:
            what = '<style> → CFG + buildCSS()'
        elif script[0] and a >= script[0] and b <= script[1]:
            what = '<script> макета → NOTES §3, ФОРМА данных'
        pos = a
        while pos <= b:
            end = min(b, pos + MAX_RANGE - 1)
            plan.append((pos, end, 'ЦЕЛИКОМ', what, ''))
            pos = end + 1
    return plan


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    only_plan = '--plan' in sys.argv
    if not args:
        die('ЗАПУСК: python3 scan-layout.py <макет>.html [--plan]')
    path = args[0]
    if not os.path.isfile(path):
        die('нет файла: ' + path)
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    total = len(lines)
    if total == 0:
        die('файл пуст: ' + path)
    size = len(text.encode('utf-8'))

    idx = line_index(text)
    style = find_section(lines, 'style')
    script = find_section(lines, 'script')
    hits = scan_tags(text, idx)
    blocks = repeated_blocks(hits)
    zones = dense_zones(text, blocks)
    for z in zones:
        # конец зоны — конец ПОСЛЕДНЕЙ копии, а не её первая строка
        last_off, last_tag = z['at'][-1][1], z['at'][-1][2]
        z['hi2'] = min(total, line_of(idx, element_span(text, last_off, last_tag) - 1))
    zones = [z for z in zones if z['hi2'] - z['lo'] >= 8]
    plan = read_plan(total, style, script, zones)

    name = os.path.basename(path)
    print('СКАН МАКЕТА: ' + name)
    print('M = ' + str(total) + ' строк, ' + kb(size)
          + '   (M для NOTES §2 — это число)')

    if not only_plan:
        print('')
        print('ВЕС ПО ЧАСТЯМ')
        used = 0
        for label, (a, b) in (('<style>', style), ('<script>', script)):
            if a:
                part = len('\n'.join(lines[a - 1:b]).encode('utf-8'))
                used += part
                print('  %-9s строки %d-%d  %8s  %s'
                      % (label, a, b, kb(part), pct(part, size)))
        print('  %-9s %-14s %8s  %s'
              % ('разметка', 'остальное', kb(size - used), pct(size - used, size)))

        data = scan_data_attrs(text)
        if data:
            print('')
            print('data-АТРИБУТЫ — payload НЕ переписывай в реестр, это мок')
            for nm, (cnt, sz) in sorted(data.items(), key=lambda x: -x[1][1]):
                print('  %-16s %4d шт  %8s  %s файла' % (nm, cnt, kb(sz), pct(sz, size)))
            trig = [n for n in data if n in ('data-tip', 'data-kind', 'data-action')]
            if not trig:
                print('  ! ни одного data-tip/data-kind/data-action:')
                print('    это ИМЕНА-ТРИГГЕРЫ, по ним smoke.mjs находит интерактив.')
                print('    Свои имена (data-tip-kind и подобные) он не видит,')
                print('    и проверки тултипа молча уходят в N/A (RETRO 56).')

        if zones:
            print('')
            print('ПОВТОРЫ: СОДЕРЖИМОЕ ПО КОПИЯМ — В ПОРЯДКЕ МАКЕТА')
            print('Это весь смысл повторяющегося блока. Порядок строк ниже —')
            print('порядок категорий в макете, он ЧАСТЬ ТЗ: по величине не пересортировывай.')
            for z in zones:
                texts, more = copy_texts(text, z)
                if not any(texts):
                    continue
                print('')
                print('  %d× %s   строки %d-%d, шаг %d   %s'
                      % (z['n'], z['sig'], z['lo'], z['hi2'], z['pitch'],
                         'ОДНОРОДНЫЕ → можно образцом' if z['homog'] >= 0.7
                         else 'РАЗНЫЕ ВНУТРИ → читать ВСЕ, образцом нельзя'))
                for i, t in enumerate(texts, 1):
                    print('   %3d. %s' % (i, t or '(без текста)'))
                if more:
                    print('    …остальные копии того же вида')
            print('')
            print('Геометрию (координаты, ширины, шаг) выводи из ДВУХ полных копий')
            print('и ПРОВЕРЯЙ на последней: масштаб, origin и шаг обязаны сойтись')
            print('на обоих концах, иначе последний элемент уедет за viewBox (RETRO 55).')

        cssv = scan_css_vars(text)
        if cssv:
            print('')
            print('CSS-ПЕРЕМЕННЫЕ :root (' + str(len(cssv)) + ') → CFG.colors / CFG.fonts')
            for k, v in cssv:
                print('  %-14s %s' % (k, v.strip()))

    print('')
    print('ПЛАН ЧТЕНИЯ — эти диапазоны в NOTES §2')
    for a, b, mode, what, hint in plan:
        line = '  %-11s %-9s %s' % (str(a) + '-' + str(b), mode, what)
        print(line + ('   [' + hint + ']' if hint else ''))
    smp = next((p for p in plan if p[2] == 'ОБРАЗЕЦ'), None)
    if smp:
        print('')
        print('В NOTES §2 диапазон-образец пиши как:')
        print('  | ' + name + ' | ' + str(smp[0]) + '-' + str(smp[1])
              + ' | по образцу: ' + smp[3] + ', прочитано ' + str(SAMPLE)
              + ' + последняя |')
        print('Диапазон закрыт честно: он покрыт, а мок-разметка в контекст не попала.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
