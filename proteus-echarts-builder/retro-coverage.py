#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retro-coverage.py — карта покрытия: какие RETRO закрыты автопроверкой, а какие
держатся только на внимательности агента.

ЗАЧЕМ. PATTERNS.md и TABLES.md — это реестр реальных падений. Но совет, который
модель читает и забывает под давлением контекста, защищает слабо; совет,
скомпилированный в проверку, работает всегда. Разница между этими двумя
состояниями и есть настоящее здоровье скилла.

Карта СЧИТАЕТСЯ, а не пишется руками: покрытие выводится из того, что проверки
сами ссылаются на номера RETRO в своих сообщениях. Поэтому она не устаревает —
добавил проверку с «(RETRO N)» в тексте, и N сразу считается закрытым.

ЗАПУСК:
    python3 retro-coverage.py            # вся карта
    python3 retro-coverage.py --gaps     # только незакрытые
    python3 retro-coverage.py --quiet    # только итоговая строка

КОД ВОЗВРАТА: всегда 0 — это отчёт, а не приёмка.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Файлы с реестром RETRO и диапазоны, за которые они отвечают.
REGISTRIES = [('PATTERNS.md', 'каркас и overlay'), ('TABLES.md', 'таблицы')]
# Файлы с проверками. ID проверки узнаём по форме самого идентификатора
# ('S14b', 'T5', 'EV3'), а не по форме вызова: часть проверок объявлена
# списком кортежей, а не прямым add(), и по вызову они не находятся.
CHECK_ID = r"'([A-Z]{1,2}\d+[a-z]?)'"
CHECKERS = [('validate.py', CHECK_ID), ('smoke.mjs', CHECK_ID)]

# RETRO, которые машиной не проверяются в принципе: они про процесс, диалог
# с пользователем и смысл данных. Помечаем явно, чтобы «непокрытые» не были
# свалкой из «ещё не сделали» и «сделать нельзя».
HUMAN_ONLY = {
    12: 'выдуманные значения в CFG — видно только сверкой с макетом и SQL',
    17: 'имена полей ↔ «Измерения» Proteus — вне досягаемости скрипта',
    18: 'смысл порядка строк — что именно сортировать, знает только человек',
    22: 'лишние вопросы пользователю — свойство диалога, не кода',
    41: 'полнота чтения макета частично закрыта Z1/Z1b; смысл модели — нет',
    50: 'объявление режима словами и уровня проверки — свойство диалога;'
        ' сам замер окружения делает smoke.mjs --env',
}


def read(name):
    p = os.path.join(HERE, name)
    return open(p, encoding='utf-8').read() if os.path.isfile(p) else ''


def retro_registry():
    """Номер RETRO -> (симптом, файл)."""
    out = {}
    for fname, _ in REGISTRIES:
        txt = read(fname)
        for m in re.finditer(r'^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|', txt, re.M):
            num = int(m.group(1))
            if num not in out:
                out[num] = (m.group(2).strip(), fname)
    return out


def checks_by_retro():
    """Номер RETRO -> список проверок, которые на него ссылаются."""
    out = {}
    for fname, id_pat in CHECKERS:
        txt = read(fname)
        if not txt:
            continue
        ids = sorted((txt.count('\n', 0, m.start()), m.group(1))
                     for m in re.finditer(id_pat, txt))
        if not ids:
            continue
        tag = '/' + fname.split('.')[0]
        for m in re.finditer(r'RETRO\s*(\d+(?:\s*,\s*\d+)*)', txt):
            line = txt.count('\n', 0, m.start())
            before = [x for x in ids if x[0] <= line]
            after = [x for x in ids if x[0] > line]
            # Ссылка внутри самого вызова (та же строка или парой ниже) —
            # это проверка выше. Ссылка в комментарии стоит НАД своей
            # проверкой, поэтому при разрыве смотрим вперёд.
            if before and line - before[-1][0] <= 3:
                cid = before[-1][1]
            elif after and after[0][0] - line <= 20:
                cid = after[0][1]
            elif before:
                cid = before[-1][1]
            else:
                continue
            for part in re.split(r'\s*,\s*', m.group(1)):
                out.setdefault(int(part), set()).add(cid + tag)
    return out


def main():
    flags = set(a for a in sys.argv[1:] if a.startswith('--'))
    gaps_only = '--gaps' in flags
    quiet = '--quiet' in flags

    registry = retro_registry()
    covered = checks_by_retro()
    if not registry:
        print('Реестр RETRO не найден — проверь PATTERNS.md рядом со скриптом.')
        return 0

    rows = []
    for num in sorted(registry):
        symptom, src = registry[num]
        checks = sorted(covered.get(num, []))
        if checks:
            status, note = 'АВТО', ', '.join(checks)
        elif num in HUMAN_ONLY:
            status, note = 'ГЛАЗА', HUMAN_ONLY[num]
        else:
            status, note = 'ДЫРА', 'проверки нет — падение поймает только пользователь'
        rows.append((num, status, symptom, note, src))

    auto = sum(1 for r in rows if r[1] == 'АВТО')
    human = sum(1 for r in rows if r[1] == 'ГЛАЗА')
    holes = [r for r in rows if r[1] == 'ДЫРА']

    if not quiet:
        w = max(len(r[2]) for r in rows)
        w = min(w, 52)
        print('\nПокрытие RETRO проверками')
        print('-' * 108)
        for num, status, symptom, note, _src in rows:
            if gaps_only and status == 'АВТО':
                continue
            mark = {'АВТО': 'v', 'ГЛАЗА': '~', 'ДЫРА': 'X'}[status]
            print(' ' + mark + '  ' + str(num).rjust(3) + '  ' + status.ljust(5)
                  + '  ' + symptom[:w].ljust(w) + '  ' + note[:44])
        print('-' * 108)

    print('Итог: ' + str(len(rows)) + ' RETRO — ' + str(auto) + ' с автопроверкой, '
          + str(human) + ' только глазами, ' + str(len(holes)) + ' без защиты')
    if holes:
        print('Без защиты: ' + ', '.join(str(h[0]) for h in holes))
    return 0


if __name__ == '__main__':
    sys.exit(main())
