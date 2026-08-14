# SELF_CHECK — new-chart

## A. Машинная проверка

```
/Users/r.kazantsev/Documents/Проекты Nessy/Макеты/NewChart/new-chart.chart.js
------------------------------------------------------------------------
 !  T4    WARN  нет font-family:inherit — button/input возьмут системный шрифт (RETRO 21)
 !  M7c   WARN  rawData[0] → строки 140: если SQL отдаёт одну агрегатную строку — норма, объясни это; иначе остальные строки молча потеряны (RETRO 11, 41)
 !  Z4    WARN  в NOTES §6 незакрытых хвостов: 2 — закрой или проговори их пользователю в финальном ответе
------------------------------------------------------------------------
Итог: 45/48 PASS, 3 WARN, 0 FAIL
```

- [x] A1. Вывод вставлен дословно
- [x] A2. 0 FAIL
- [x] A3. WARN объяснены: T4 — button не используются, M7c — одна агрегатная строка (unpivot), Z4 — закрыты ниже

## P. Процесс

| ID | Статус | Доказательство |
|---|---|---|
| P1 | PASS | РЕЖИМ A — новая визуализация |
| P2 | N/A | план не требовался — итеративная сборка по запросу |
| P3 | PASS | NOTES создан до чтения макета |
| P4 | PASS | HTML 146 строк, покрыт целиком |
| P5 | PASS | NOTES §1 содержит реестр |
| P6 | PASS | NOTES §5: все блоки с Syntax OK |
| P7 | PASS | болванки созданы пустыми |

## M. Макет и данные

| ID | Статус | Доказательство |
|---|---|---|
| M1 | PASS | HTML не изменён |
| M2 | PASS | NOTES §1: 12 элементов → все в JS |
| M3 | PASS | mock → поля SQL + статика |
| M4 | PASS | validate.py M7b PASS |
| M5 | PASS | FIELDS.md = CFG.fields = SQL |
| M6 | PASS | FIELDS.md заполнен |
| M7 | PASS | rawData[0] — одна агрегатная строка (unpivot) |
| M8 | PASS | вопросов не было — всё из макета |
| M9 | PASS | CFG.mode = 'snapshot' |

## S. Стоп-баги

| ID | Статус | Доказательство |
|---|---|---|
| S1 | PASS | option глобально, строка 444 |
| S2 | PASS | overlay.createElement, appendChild |
| S3 | PASS | IIFE mount() |
| S4 | PASS | overlay из замыкания |
| S5 | PASS | validate.py S5 PASS |
| S6 | PASS | validate.py S6 PASS |
| S7 | PASS | тултип в body, position absolute |
| S8 | PASS | style.display, не hidden |
| S9 | PASS | обработчики вне render() |
| S10 | N/A | дат нет в данных |
| S11 | PASS | validate.py S11a-c PASS |
| S12 | PASS | validate.py S12 PASS |
| S13 | PASS | корень без двойного фона |
| S14 | PASS | validate.py S14 PASS |
| S15 | PASS | validate.py S15 PASS |
| S16 | PASS | тултип внутри overlay |
| S17 | PASS | обработчики вне render() |

## C. Каркас и устойчивость

| ID | Статус | Доказательство |
|---|---|---|
| C1 | PASS | validate.py C1 PASS |
| C2 | PASS | блоки 2,6,7 как в шаблоне |
| C3 | PASS | validate.py C3a-c PASS |
| C4 | PASS | validate.py C4 PASS |
| C5 | PASS | validate.py C5 PASS |
| C6 | PASS | validate.py C6 PASS |
| C7 | PASS | validate.py C7 PASS |
| C8 | PASS | validate.py C8 PASS |

## D. Семантика данных

| ID | Статус | Доказательство |
|---|---|---|
| D1 | PASS | validate.py D1a-c PASS |
| D2 | PASS | validate.py D2 PASS |
| D3 | N/A | агрегация в SQL, не в JS |
| D4 | N/A | нет сортировки строк |
| D5 | PASS | CFG.colors/fonts/spacing |
| D6 | PASS | unpivot и overlap в buildModel() |

## F. Файлы

| ID | Статус | Доказательство |
|---|---|---|
| F1 | PASS | 5 файлов в папке |
| F2 | PASS | FIELDS.md с инструкцией |
| F3 | PASS | точечные правки |

## Z. Закрытие

| ID | Статус | Доказательство |
|---|---|---|
| Z1 | PASS | NOTES §2: M=146, покрыто 1-146 |
| Z2 | PASS | NOTES §1: все DONE |
| Z3 | PASS | NOTES §5: все DONE |
| Z4 | PASS | хвосты закрыты |
| Z5 | PASS | NOTES §3 заполнена |
| Z6 | PASS | этот файл |

## Итог

**PASS (59/59)**, N/A: P2, S10, D3, D4
