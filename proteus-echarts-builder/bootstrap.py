#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap.py — создать папку проекта и болванки одной командой.

ЗАЧЕМ. ШАГ 1 не требует ни одного решения: пять файлов копируются из templates/
с переименованием. Если агент делает это чтением и перезаписью, он тратит ~32 КБ
контекста на файлы, которые не меняет ни на символ, — и упирается в лимит
ещё до того, как увидит макет. Копирование должно стоить один вызов и ноль чтений.

ЗАПУСК:
    python3 bootstrap.py <папка> [<имя>]

<имя> — префикс файлов. По умолчанию берётся из имени папки в нижнем регистре
с дефисами вместо пробелов и подчёркиваний.

Создаёт: <имя>.html, <имя>.data.sql, <имя>.chart.js, <имя>.NOTES.md, FIELDS.md
Существующие файлы НЕ перезаписывает — сообщает и пропускает.
Затем сам гоняет validate.py --template.

КОД ВОЗВРАТА: 0 — болванки готовы, 1 — валидатор недоволен, 2 — ошибка запуска.
"""

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, 'templates')

# шаблон -> как назвать в папке проекта ('' = подставить <имя>)
FILES = [
    ('TEMPLATE.html', '{name}.html'),
    ('TEMPLATE.data.sql', '{name}.data.sql'),
    ('TEMPLATE.chart.js', '{name}.chart.js'),
    ('TEMPLATE.NOTES.md', '{name}.NOTES.md'),
    ('TEMPLATE.FIELDS.md', 'FIELDS.md'),
]


def slug(s):
    s = re.sub(r'[\s_]+', '-', s.strip())
    s = re.sub(r'[^\w-]', '', s, flags=re.U)
    return s.lower() or 'chart'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    folder = os.path.abspath(args[0])
    name = slug(args[1]) if len(args) > 1 else slug(os.path.basename(folder))

    if not os.path.isdir(TPL):
        print('Не найдена папка templates/ рядом с bootstrap.py: ' + TPL)
        return 2

    os.makedirs(folder, exist_ok=True)

    made, skipped = [], []
    for src, pattern in FILES:
        src_path = os.path.join(TPL, src)
        if not os.path.isfile(src_path):
            print('Нет шаблона ' + src + ' — проверь templates/')
            return 2
        dst_path = os.path.join(folder, pattern.format(name=name))
        if os.path.exists(dst_path):
            skipped.append(os.path.basename(dst_path))
            continue
        shutil.copyfile(src_path, dst_path)
        made.append(os.path.basename(dst_path))

    print('\nПапка: ' + folder)
    print('Имя:   ' + name)
    print('-' * 72)
    for f in made:
        print(' +  ' + f)
    for f in skipped:
        print(' =  ' + f + '  (уже был, не тронут)')
    print('-' * 72)

    chart = os.path.join(folder, name + '.chart.js')
    rc = 0
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(HERE, 'validate.py'), chart, '--template', '--quiet'],
            capture_output=True, text=True)
        print(p.stdout.strip() or p.stderr.strip())
        rc = p.returncode
    except OSError as err:
        print('validate.py не запустился: ' + str(err))
        rc = 2

    # Уровень проверки объявляется пользователю СРАЗУ, а не при сдаче (RETRO 50).
    # Результат не влияет на код возврата: болванки готовы в любом случае.
    env_rc = None
    try:
        q = subprocess.run(['node', os.path.join(HERE, 'smoke.mjs'), '--env'],
                           capture_output=True, text=True, timeout=90)
        print('\n' + (q.stdout.strip() or q.stderr.strip()))
        env_rc = q.returncode
    except (OSError, subprocess.TimeoutExpired) as err:
        print('\nsmoke.mjs --env не запустился: ' + str(err))

    print('\nДальше: СТОП и сообщи пользователю — «болванки готовы, пришли HTML-макет и SQL».')
    if env_rc == 2:
        print('Заодно скажи, что браузерная проверка недоступна, и предложи установку')
        print('командой из блока выше. Ставить — только после явного «да».')
    print('Ничего не заполняй: ни CFG.fields, ни FIELDS.md, ни макет, ни SQL.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
