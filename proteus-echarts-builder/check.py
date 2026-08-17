#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check.py — ОДНА команда сдачи: validate.py + smoke.mjs + один вердикт.

ЗАЧЕМ. Проверки две, и они смотрят на разное: validate.py на форму кода,
smoke.mjs на экран. Пока их гоняли по очереди, правка под вторую ломала первую
и наоборот. В Test7 это видно построчно: smoke стал зелёным на 10-й итерации,
следующий прогон validate упал с 58 до 56 (S5 и H4 вернулись), дальше цикл
пошёл на второй круг. Из 13 прогонов ни один не был про макет.

Здесь оба чекера гоняются подряд, выводы печатаются ДОСЛОВНО (их всё равно надо
вставлять в ответ), а внизу — один вердикт по обоим. Плюс журнал прогонов:
скрипт помнит, что падало в прошлые разы, и ГРОМКО говорит, когда один и тот же
код падает повторно после того, как был починен. Это признак не «почти
доделали», а ложной тревоги либо правки, которая чинит одно и ломает другое —
и повод остановиться, а не пойти на следующий круг (SKILL.md, ОСПАРИВАНИЕ).

ЗАПУСК:
    python3 <скилл>/check.py <name>.chart.js
    python3 <скилл>/check.py <name>.chart.js --vs <name>.html    # сверка с макетом
    python3 <скилл>/check.py <name>.chart.js --quiet             # только проблемы
    python3 <скилл>/check.py <name>.chart.js --accept 'T3=почему ложная тревога'

Флаги --vs / --mock / --shots уходят в smoke.mjs, --template — в validate.py,
--accept и --quiet — в оба.

КОД ВОЗВРАТА: 0 — сдавать можно, 1 — есть FAIL, 2 — ошибка запуска.
Код 2 от smoke.mjs (нет playwright) вердикт НЕ роняет: это «не запускалась».
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = '.check-history.json'
KEEP_RUNS = 12


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def verdicts(out):
    """{ID: статус} из вывода любого из двух чекеров."""
    got = {}
    for m in re.finditer(r'^\s*[v!X?-]\s+(\S+)\s+(PASS|FAIL|WARN|N/A|ОСПОР)\s',
                         out, re.M):
        got[m.group(1)] = m.group(2)
    return got


def load(path):
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def cycles(history, now):
    """Коды, которые падают ПОВТОРНО после того, как были починены.

    Именно это агент видит как «57 → 55 → 57» и принимает за прогресс.
    Один и тот же код, побывавший зелёным и снова красным, означает ровно два
    возможных диагноза, и оба требуют остановки: либо проверка ложная, либо
    правка под неё ломает что-то ещё.
    """
    out = []
    for cid in sorted(k for k, v in now.items() if v == 'FAIL'):
        seen = [h.get(cid) for h in history if cid in h]
        # Хотя бы раз позеленел и снова красный — это круг, а не «дожимаем».
        # Кричим, пока код действительно не станет зелёным: пять прогонов
        # подряд с одним и тем же FAIL выглядят как прогресс только изнутри.
        if any(a == 'FAIL' and b != 'FAIL' for a, b in zip(seen, seen[1:])):
            out.append((cid, sum(1 for s in seen if s == 'FAIL') + 1))
    return out


def main():
    args = sys.argv[1:]
    if not args or all(a.startswith('--') for a in args):
        print(__doc__)
        return 2
    chart = next(a for a in args if not a.startswith('--'))
    if not os.path.isfile(chart):
        print('Файл не найден: ' + chart)
        return 2

    # Раскладываем флаги по чекерам. --accept и --quiet идут в оба.
    v_extra, s_extra, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a in ('--vs', '--mock', '--shots'):
            s_extra += [a, args[i + 1] if i + 1 < len(args) else '']
            i += 2
            continue
        if a == '--accept':
            val = args[i + 1] if i + 1 < len(args) else ''
            v_extra += ['--accept', val]
            s_extra += ['--accept', val]
            i += 2
            continue
        if a.startswith('--accept='):
            v_extra.append(a)
            s_extra.append(a)
        elif a == '--quiet':
            v_extra.append(a)
            s_extra.append(a)
        elif a in ('--template', '--selftest'):
            v_extra.append(a)
        elif a in ('--keep',):
            s_extra.append(a)
        elif a.startswith('--'):
            print('Неизвестный флаг: ' + a)
            return 2
        i += 1

    print('=' * 72)
    print('1/2  validate.py — форма кода')
    print('=' * 72)
    v_rc, v_out = run([sys.executable, os.path.join(HERE, 'validate.py'), chart] + v_extra)
    print(v_out.rstrip())

    print('\n' + '=' * 72)
    print('2/2  smoke.mjs — поведение в браузере')
    print('=' * 72)
    s_rc, s_out = run(['node', os.path.join(HERE, 'smoke.mjs'), chart] + s_extra)
    print(s_out.rstrip())

    now = verdicts(v_out)
    now.update(verdicts(s_out))
    fails = sorted(k for k, v in now.items() if v == 'FAIL')
    warns = sorted(k for k, v in now.items() if v == 'WARN')
    disp = sorted(k for k, v in now.items() if v == 'ОСПОР')

    # ── журнал прогонов ──
    jpath = os.path.join(os.path.dirname(os.path.abspath(chart)), JOURNAL)
    history = load(jpath)
    loops = cycles(history, now)
    history.append(now)
    try:
        with open(jpath, 'w', encoding='utf-8') as fh:
            json.dump(history[-KEEP_RUNS:], fh, ensure_ascii=False)
    except OSError:
        pass

    print('\n' + '=' * 72)
    print('ВЕРДИКТ (обе проверки, прогон ' + str(len(history)) + ')')
    print('=' * 72)
    print('validate.py: код ' + str(v_rc) + '    smoke.mjs: код ' + str(s_rc)
          + ('  (2 = не запускалась, сдачу не блокирует)' if s_rc == 2 else ''))
    print('FAIL: ' + (', '.join(fails) if fails else '—'))
    print('WARN: ' + (', '.join(warns) if warns else '—'))
    if disp:
        print('ОСПОР: ' + ', '.join(disp) + ' — не «пройдено»: выпиши в NOTES §6'
              ' и скажи пользователю словами')
    ghosts = [a.split('=', 1)[0].strip() for a in
              [x[len('--accept='):] if x.startswith('--accept=') else x
               for x in v_extra] if '=' in a]
    ghosts = sorted(set(g for g in ghosts if g and g not in disp))
    if ghosts:
        print('--accept на кодах, которые не падали: ' + ', '.join(ghosts)
              + ' — проверь ID, оспаривание к ним не применилось')

    if loops:
        print('\n' + '!' * 72)
        print('ХОЖДЕНИЕ ПО КРУГУ. Эти коды уже были починены и упали снова:')
        for cid, n in loops:
            print('    ' + cid + ' — падал ' + str(n) + '-й раз за сессию')
        print('Дальше по кругу идти НЕЛЬЗЯ. Диагнозов ровно два, и оба требуют')
        print('остановки:')
        print('  1) правка под одну проверку ломает другую — тогда чини причину,')
        print('     а не строку отчёта: посмотри, что изменилось между прогонами;')
        print('  2) проверка ложная — тогда ОСПОРЬ её (SKILL.md, «ОСПАРИВАНИЕ»):')
        print('     --accept ' + loops[0][0] + '=\'<почему это ложная тревога>\',')
        print('     строка в NOTES §6 и фраза пользователю. Молча подгонять код')
        print('     под проверку запрещено (правило 12).')
        print('!' * 72)

    if fails:
        print('\nСДАВАТЬ НЕЛЬЗЯ.')
        return 1
    print('\nОбе проверки пройдены. Дальше — SELF_CHECK.md, и ПОСЛЕ него')
    print('прогони check.py ещё раз: Z5/Z6/Z6b/F1 смотрят на отчёт и NOTES.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
