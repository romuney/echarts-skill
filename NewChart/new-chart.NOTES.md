# NOTES — рабочая память по new-chart

Это рабочий файл агента. В Proteus он НЕ вставляется и в поставку не идёт.

Зачем: макет может быть на 2000 строк, а JS — ещё больше. Всё это не помещается
в одну сессию. Память живёт ЗДЕСЬ, а не в контексте и не в чате.

Пиши сюда ДО следующего действия, а не «потом соберу». Забыл деталь — перечитай
этот файл, а не HTML.

Восстановление после обрыва: прочитай файл целиком, найди первый пункт со статусом
≠ DONE, продолжай с него. HTML заново НЕ читай.

---

## §0 ПЛАН

Только КРУПНЫЕ этапы. Блоки 1–7 живут в §5 — здесь их НЕ дублируй, иначе две
таблицы разъедутся и возобновление пойдёт не с того места.

| # | Этап | Статус |
|---|---|---|
| 1 | Макет прочитан целиком, заполнены §1 и §2 | DONE |
| 2 | SQL прочитан, заполнен §3, поля сверены с макетом | DONE |
| 3 | Расхождения макет↔SQL закрыты (§4) | DONE |
| 4 | `.chart.js` собран (детали — в §5) | DOING |
| 5 | `validate.py` без FAIL, пройден SELF_CHECK | TODO |

Статусы: TODO / DOING / DONE.

## §1 РЕЕСТР МАКЕТА

| # | Элемент | Строки HTML | Mock-значение | Поле SQL | Статус | Где в JS |
|---|---|---|---|---|---|---|
| 1 | Заголовок графика (.chart-title) | 36 | "Четверговая Оффлайн" | segment_nm | DONE | buildHTML |
| 2 | Всего во встрече (.chart-total) | 37-38 | 13 сотрудников | emp_cnt_total | DONE | buildHTML |
| 3 | Кнопка info (.info-button) | 39-40 | "i" | rule_txt | DONE | buildHTML + onClick |
| 4 | Строка "Всего во встрече" (.row) | 57-59 | total_cnt | emp_cnt_total | DONE | buildHTML |
| 5 | Строки структур (.row) | 57-59 | struct_nm, struct_cnt | emp_cnt_management/functional | DONE | buildHTML |
| 6 | Полоса-трек (.track) | 60 | width по % | struct_cnt / total | DONE | buildHTML |
| 7 | Бары (.bar) | 60 | цвет struct_color | struct_color | DONE | buildHTML |
| 8 | Ось с тиками (.axis) | 61-62 | 0, overlap, total | вычисляется | DONE | buildHTML |
| 9 | Легенда (.legend) | 63-64 | struct_nm + count | struct_nm, struct_cnt | DONE | buildHTML |
| 10 | Зона пересечения (.overlap-band) | 43 | rgba + dashed | вычисляется | DONE | buildHTML |
| 11 | Тултип (.chart-tooltip) | 65 | pinned tooltip | state.tooltip | DONE | renderTooltip |
| 12 | CSS стили | 6-32 | все цвета/шрифты | — | DONE | buildCSS |

Статусы: TODO / DONE / ASK / STATIC.

## §2 ПРОЧИТАНО

Всего строк в `new-chart.html`: M = **146**

| Файл | Строки с–по | Что найдено |
|---|---|---|
| new-chart.html | 1-73 | `<head>`, `<style>` (CSS макета) |
| new-chart.html | 74-146 | `<body>`, `<script>` (mock-данные, логика), FIELDS-комментарий |

Покрыто строк: **146** из **146**.

## §3 ПОЛЯ: ЧТО ЖДЁТ МАКЕТ ↔ ЧТО ДАЁТ SQL

**Макет ждёт (из mock-данных строки 75-78):**
| Поле | Тип | Есть в SQL | Решение |
|---|---|---|---|
| snapshot_dt | YYYY-MM-DD | нет | STATIC "2026-07-01" |
| segment_id | string | нет | STATIC "thursday_offline" |
| segment_nm | string | нет | STATIC "Четверговая Оффлайн" |
| total_cnt | int | emp_cnt_total | map |
| struct_key | string | нет | generate: management/functional |
| struct_nm | string | structure_type_nm (в подзапросе) | STATIC по ключу |
| struct_cnt | int | emp_cnt_management / emp_cnt_functional | unpivot в buildModel |
| struct_color | HEX | нет | STATIC #f2a8b8 / #c9a2ee |
| rule_txt | string | нет | STATIC (длинный текст из макета) |

**Форма данных:** Макет ждёт массив строк (1 строка = 1 структура). SQL отдаёт 1 строку с 3 колонками.
**Решение:** `buildModel()` делает unpivot: одна входная строка → две выходных (management + functional).

**CFG.fields:**
| Колонка в SQL | Тип | Alias в CFG.fields |
|---|---|---|
| emp_cnt_total | BigInt | total |
| emp_cnt_management | BigInt | management |
| emp_cnt_functional | BigInt | functional |

## §4 ВОПРОСЫ И РЕШЕНИЯ

| Дата/шаг | Вопрос | Ответ | Решение |
|---|---|---|---|
| 2026-08-14 | snapshot_dt, segment_id, segment_nm, struct_color, rule_txt отсутствуют в SQL | — | Зафиксировать статикой в JS (макет предоставляет значения) |

## §5 БЛОКИ 1–7

| Блок | Что в нём | Статус | node --check | Строки |
|---|---|---|---|---|
| 1 | CFG | DONE | OK | 23-68 |
| 2 | вход/состояние/хелперы | DONE | OK | 70-133 |
| 3 | buildModel (unpivot) | DONE | OK | 135-177 |
| 4 | форматирование и цвет | DONE | OK | 179-185 |
| 5 | buildCSS + buildHTML | DONE | OK | 187-283 |
| 6 | монтаж и интерактив | DONE | OK | 285-439 |
| 7 | пустой option | DONE | OK | 438-448 |

## §6 ОТКРЫТЫЕ ХВОСТЫ

- [x] validate.py — 45/48 PASS, 0 FAIL (3 WARN объяснены)
- [x] SELF_CHECK.md — заполнен, PASS (59/59)
