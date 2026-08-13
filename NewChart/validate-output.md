
/Users/r.kazantsev/Documents/Проекты Nessy/Макеты/NewChart/thursday-offline.chart.js
------------------------------------------------------------------------
 v  P5    PASS  node --check
 v  C1    PASS  блоки 1-7 по порядку
 v  S1    PASS  option глобально, строка 512/517
 v  D2    PASS  series — пустой scatter
 v  S2    PASS  хост через [_echarts_instance_], overlay создаётся
 v  C3a   PASS  canvas скрывается
 v  C3b   PASS  старый overlay удаляется
 v  C3c   PASS  host → position:relative
 v  S2b   PASS  overlay монтируется в host
 v  S3    PASS  монтаж вызван и содержит поиск хоста
 v  C6    PASS  try/catch вокруг монтажа
 v  C6b   PASS  catch выводит ошибку в overlay
 v  S14   PASS  render() вызывается
 v  S15   PASS  HTML-классы без ведущей точки
 v  S9    PASS  слушатели вне render()
 v  S17   PASS  глобальных слушателей внутри render() нет
 v  S16   PASS  fixed-тултип считает координаты от окна
 v  C4    PASS  observer только правит габариты
 v  C7    PASS  состояние в window.__pvtState
 v  S5    PASS  все селекторы префиксованы
 v  S6    PASS  все классы со стилями
 v  S7    PASS  тултип монтируется в body
 X  T1    FAIL  узел тултипа в buildHTML() — innerHTML убьёт его (RETRO 19)
 v  T2    PASS  тултип не пересоздаётся в render()
 v  T3    PASS  font-family задан и в root, и в тултипе
 v  T4    PASS  font-family:inherit для дочерних
 v  S8    PASS  скрытие через style
 v  S10   PASS  есть универсальный парсер даты
 v  S11a  PASS  нет backticks / template-literals
 v  S11b  PASS  нет стрелочные функции
 v  S11c  PASS  нет let / const
 v  S12   PASS  нет document.getElementById (RETRO 15)
 v  D1a   PASS  нет import / require
 v  D1b   PASS  нет fetch
 v  D1c   PASS  нет внешних URL / CDN
 v  H1    PASS  нет console.log
 v  M7    PASS  читается весь data
 v  M7b   PASS  вход защищён Array.isArray
 v  C8    PASS  есть экранирование
 v  C5    PASS  есть ветка CFG.text.noData
 v  M4    PASS  CFG.fields: 3 полей
 v  M4b   PASS  нет незакрытых TODO
------------------------------------------------------------------------
Итог: 41/42 PASS, 0 WARN, 1 FAIL

СДАВАТЬ НЕЛЬЗЯ. Исправь FAIL и запусти снова.
