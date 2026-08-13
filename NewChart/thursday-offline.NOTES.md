# NOTES — рабочая память по thursday-offline

Это рабочий файл агента. В Proteus он НЕ вставляется и в поставку не идёт.

Зачем: макет может быть на 2000 строк, а JS — ещё больше. Всё это не помещается
в одну сессию. Память живёт ЗДЕСЬ, а не в контексте и не в чате.

Пиши сюда ДО следующего действия, а не «потом соберу». Забыл деталь — перечитай
этот файл, а не HTML.

Восстановление после обрыва: прочитай файл целиком, найди первый пункт со статусом
≠ DONE, продолжай с него. HTML заново НЕ читай.

---

## §0 ПЛАН

| # | Шаг | Статус |
|---|---|---|
| 1 | Заполнить NOTES по макету и SQL | DONE |
| 2 | Блок 1: CFG (поля, тексты, цвета) | TODO |
| 3 | Блок 2: вход/состояние/хелперы | TODO |
| 4 | Блок 3: buildModel (трансформация SQL → модель) | TODO |
| 5 | Блок 4: форматтеры | TODO |
| 6 | Блок 5: buildCSS + buildHTML | TODO |
| 7 | Блок 6: монтаж и интерактив | TODO |
| 8 | Блок 7: пустой option | TODO |
| 9 | validate.py + SELF_CHECK.md | TODO |

Статусы: TODO / DOING / DONE.

## §1 РЕЕСТР МАКЕТА

Каждый видимый элемент, контрол и состояние из HTML. Ни одна строка не удаляется —
только меняет статус. Пустой столбец «поле SQL» = ещё не сопоставлено.

| # | Элемент | Строки HTML | Mock-значение | Поле SQL | Статус | Где в JS |
|---|---|---|---|---|---|---|
| 1 | .segment-title | 72–78 | "Четверговая Оффлайн" | статика | STATIC | CFG.text.segmentTitle |
| 2 | .info-button | 80–95 | кнопка "i" | — | STATIC | buildHTML |
| 3 | .kpi | 97–103 | 13 сотрудников | emp_cnt_total | DONE | buildModel → model.total |
| 4 | .kpi-caption | 105–108 | "всего во встрече" | — | STATIC | buildHTML |
| 5 | .set-band.is-left | 124–140 | management, 10 | emp_cnt_management | DONE | buildModel → model.bars[0] |
| 6 | .set-band.is-right | 124–140 | functional, 10 | emp_cnt_functional | DONE | buildModel → model.bars[1] |
| 7 | .set-label.is-left | 118–122 | "Управленческая структура" | — | STATIC | CFG.text.management |
| 8 | .set-label.is-right | 118–122 | "Функциональная структура" | — | STATIC | CFG.text.functional |
| 9 | .overlap-zone | 142–149 | зона пересечения | вычисл. | DONE | buildModel → model.overlap |
| 10 | .overlap-badge | 151–160 | "∩ 7" | вычисл. | DONE | buildHTML |
| 11 | .chart-tooltip | 162–190 | тултип | — | STATIC | renderTip |

Статусы: TODO / DONE / ASK (ждёт ответа пользователя) / STATIC (согласованная статика).

## §2 ПРОЧИТАНО

Диапазоны обязаны покрыть 1..M без дыр — это доказательство полноты чтения.

Всего строк в `thursday-offline.html`: M = **377**

| Файл | Строки с–по | Что найдено |
|---|---|---|
| thursday-offline.html | 1–150 | CSS, стили тултипа, .segment-title, .kpi, .set-band |
| thursday-offline.html | 151–300 | .overlap-zone, .chart-tooltip, начало script |
| thursday-offline.html | 301–377 | data mock, state, функции, обработчики, render |

Покрыто строк: **377** из **377**.

## §3 КОЛОНКИ SQL

Имена совпадают побуквенно: SQL == `CFG.fields` == `FIELDS.md` == «Измерения».

| Колонка в SQL | Тип | Alias в `CFG.fields` | Добавлена в «Измерения» |
|---|---|---|---|
| `emp_cnt_total` | число | total | нет |
| `emp_cnt_management` | число | management | нет |
| `emp_cnt_functional` | число | functional | нет |

## §4 ВОПРОСЫ И РЕШЕНИЯ

Что спросил, что ответил пользователь, что решено. Отдельно фиксируй, что считается
в JS, а что согласовано считать в SQL (и было ли произнесено предупреждение
про ручное добавление в «Измерения»).

| Дата/шаг | Вопрос | Ответ пользователя | Решение |
|---|---|---|---|
| 2026-08-13 | Адаптировать JS или переписать SQL? | «Адаптировать JS» | JS строит 2 бара из 3 колонок SQL, пересечение = (mgmt + func) - total |

## §5 БЛОКИ 1–7

Чекпоинт после каждого блока: `node --check` → строка здесь → статус в чате.

| Блок | Что в нём | Статус | node --check | Строки в `thursday-offline.chart.js` |
|---|---|---|---|---|
| 1 | CFG | DONE | OK | 22-59 |
| 2 | вход/состояние/хелперы | DONE | OK | 61-105 |
| 3 | buildModel | DONE | OK | 107-141 |
| 4 | форматирование и цвет | DONE | OK | 143-157 |
| 5 | buildCSS + buildHTML | DONE | OK | 159-301 |
| 6 | монтаж и интерактив | DONE | OK | 303-507 |
| 7 | пустой option | DONE | OK | 509-517 |

## §6 ОТКРЫТЫЕ ХВОСТЫ

Всё, что осознанно отложено. Пустой раздел перед сдачей — обязателен.

- [x] validate.py: 42/42 PASS переименовать файлы из newchart.* в thursday-offline.*
