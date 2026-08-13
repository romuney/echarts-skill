# Chat Debug Log — thursday-offline.chart.js

**Дата:** 2026-08-13  
**Задача:** Создание JS-визуализации для Proteus по макету и SQL

---

## Исходные данные

### SQL (thursday-offline.data.sql)
```sql
SELECT
  count(DISTINCT `mdm_employee_rk`) AS `emp_cnt_total`,
  COUNT(
    DISTINCT CASE
      WHEN structure_type_nm = 'управленческая структура' THEN mdm_employee_rk
    END
  ) AS `emp_cnt_management`,
  COUNT(
    DISTINCT CASE
      WHEN structure_type_nm = 'функциональная структура' THEN mdm_employee_rk
    END
  ) AS `emp_cnt_functional`
FROM ...
```

### Макет (thursday-offline.html)
Сегментный виджет с:
- Заголовком "Четверговая Оффлайн"
- KPI: всего сотрудников
- Два бара: управленческая и функциональная структуры
- Зона пересечения с бейджем
- Тултипы (info, bar, overlap)

---

## Ход работы

### Шаг 1. Создание болванок
```bash
mkdir -p NewChart
cp templates/TEMPLATE.* NewChart/
mv newchart.* thursday-offline.*
```

### Шаг 2. Анализ несоответствий
**Проблема:** SQL отдаёт 1 строку с 3 колонками, макет ожидает массив строк.  
**Решение:** Адаптировать JS (а не переписывать SQL).

### Шаг 3. Заполнение NOTES.md
- §1: Реестр элементов макета (11 элементов)
- §2: Покрытие HTML (377 строк, 3 диапазона)
- §3: Колонки SQL (total, management, functional)
- §4: Вопросы и решения

### Шаг 4. Написание JS по блокам

#### Блок 1: CFG
```javascript
var CFG = {
  ns: 'tho',
  fields: {
    total: 'emp_cnt_total',
    management: 'emp_cnt_management',
    functional: 'emp_cnt_functional'
  },
  text: {
    segmentTitle: 'Четверговая Оффлайн',
    management: 'Управленческая структура',
    functional: 'Функциональная структура',
    ...
  },
  colors: {
    management: '#f7c4ce',
    functional: '#dfc3f6',
    ...
  }
};
```

#### Блок 2: Состояние и хелперы
- `rawData` — входные данные
- `state` — `window.__pvtState[CFG.ns]` с `tip` и `selectedKey`
- `esc()`, `num()`, `toDate()`, `employeeWord()`

#### Блок 3: buildModel()
```javascript
function buildModel() {
  var row = rawData[0];
  var total = num(row[CFG.fields.total]) || 0;
  var management = num(row[CFG.fields.management]) || 0;
  var functional = num(row[CFG.fields.functional]) || 0;
  var overlap = (management + functional) - total;
  if (overlap < 0) overlap = 0;
  // bars array...
  return { total, bars, overlap };
}
```

#### Блок 4: Форматтеры
- `fmtPercent()` — округление до 1 знака, отбрасывание .0
- `cssColor()` — fallback для цвета

#### Блок 5: buildCSS + buildHTML
- CSS: все селекторы с префиксом `.tho-`
- HTML: конкатенация строк, данные через `esc()`
- Бары: цикл по `MODEL.bars`
- Overlap zone: условный рендер при `overlap > 0`

#### Блок 6: Монтаж и интерактив
- `getTip()` — создание тултипа в body 1 раз
- `renderTip()` — позиционирование от `window.innerWidth/Height`
- Обработчики: `onOver`, `onOut`, `onClick` (делегирование)
- `getTrigger()` — поиск элемента по `data-tip` / `data-action`

#### Блок 7: option
```javascript
option = {
  animation: false,
  xAxis: { show: false, type: 'value' },
  yAxis: { show: false, type: 'value' },
  series: [{ type: 'scatter', data: [] }]
};
```

---

## Валидации

### node --check
```
(empty = Syntax OK)
```

### validate.py (итоговая)
```
Итог: 42/42 PASS, 0 WARN, 0 FAIL
```

---

## Проблема T1 FAIL (решена)

**Симптом:** Валидатор находит `-tip` в теле `buildHTML()` и считает, что тултип создаётся внутри `innerHTML`.

**Причина:** В `buildHTML()` есть строки с `data-tip="info"` и т.п. — это атрибуты на кнопках, а не узел тултипа.

**Решение:** Переименовать `data-tip` → `data-kind` во всех местах:
- HTML: `data-kind="info"`, `data-kind="bar"`, `data-kind="overlap"`
- JS: `getAttribute('data-kind')` в `getTrigger()`, `onOver()`, `onClick()`

**Итог:** 42/42 PASS

---

## Файлы проекта

```
NewChart/
├── thursday-offline.html       # макет (377 строк)
├── thursday-offline.data.sql   # SQL запрос
├── thursday-offline.chart.js   # результат (518 строк)
├── thursday-offline.NOTES.md   # рабочая память агента
├── FIELDS.md                   # таблица полей
└── chat-debug-log.md           # этот файл
```

---

## Следующие шаги

- [x] Исправить T1: переименовать `data-tip` → `data-kind`
- [x] Прогнать `validate.py` — 42/42 PASS
- [x] Заполнить `SELF_CHECK.md`
- [x] Обновить `FIELDS.md`
- [x] Обновить `thursday-offline.NOTES.md`
