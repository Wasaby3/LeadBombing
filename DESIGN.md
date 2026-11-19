---
name: LeadBombing
description: Локальный инструмент оператора — найти лиды в 2ГИС, разобрать их и написать владельцу
colors:
  bg: "#f7f7f8"
  surface: "#ffffff"
  surface-2: "#f2f2f4"
  line: "#e4e4e8"
  text: "#17171c"
  muted: "#6b6b76"
  accent: "#5656d0"
  accent-hover: "#4b4bc4"
  on-accent: "#ffffff"
  danger: "#c93434"
  on-danger: "#ffffff"
  ok: "#1f9d55"
  owner: "#b7791f"
  channel-wa: "#1fa855"
  channel-tg: "#2a9bd8"
  channel-vk: "#3f6fd8"
  status-client: "#1f9d55"
  status-waiting: "#a88400"
  status-no-answer: "#dd6b20"
  status-lost: "#d93f3f"
  dark-bg: "#0e0f11"
  dark-surface: "#16171a"
  dark-surface-2: "#1d1e22"
  dark-line: "#2a2b31"
  dark-text: "#ececf1"
  dark-muted: "#8e8e99"
  dark-accent: "#7c7cf0"
  dark-accent-fill: "#5b5bd6"
  dark-accent-fill-hover: "#6262de"
  dark-danger: "#f06060"
typography:
  page-title:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "22px"
    fontWeight: 650
    letterSpacing: "-0.01em"
  section-title:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "18px"
    fontWeight: 650
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "11.5px"
    fontWeight: 500
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "12.5px"
rounded:
  sm: "8px"
  control: "9px"
  card: "12px"
  dialog: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-ghost:
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    height: "36px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-danger}"
    rounded: "{rounded.control}"
    height: "36px"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "0 12px"
  chip:
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    height: "30px"
    padding: "0 12px"
  chip-on:
    textColor: "{colors.accent}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "18px"
  dialog:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.dialog}"
    padding: "22px"
    width: "min(560px, 100vw - 32px)"
  drawer:
    backgroundColor: "{colors.surface}"
    width: "min(540px, 100vw)"
---

# Design System: LeadBombing

Источник правды — CSS-переменные и классы в `leadbombing/web/static/app/app.css`. Этот файл описывает, что в
системе есть и как это применять; правила поведения и текстов — в [docs/UX-RULES.md](docs/UX-RULES.md), история
решений — в [docs/UX-AUDIT.md](docs/UX-AUDIT.md). Новая фича строится из того, что перечислено здесь; новый токен
или класс добавляется, только когда повторяется трижды с одним смыслом.

## Overview

**Creative North Star: «Рабочий стол оператора»** — тихий, плотный интерфейс, где на виду результат и следующее
действие, а не оформление.

Режим поверхности — Operate: оператор запускает поиск, ждёт, разбирает лиды и пишет владельцам. Интерфейс
нейтральный (серые поверхности, один индиговый акцент), плотность средняя, иерархия держится на весе шрифта и
расстоянии, а не на цвете. Цвет появляется только там, где несёт смысл: главное действие, выбранное, ошибка,
канал связи, статус лида, руководитель.

**Key Characteristics:**
- одна primary-кнопка на область, остальное — secondary, ghost или меню «Ещё ⋯»;
- светлая и тёмная тема на одних токенах, плюс «Как в системе»;
- иконки только Lucide из локального спрайта, без эмодзи и символов вместо иконок;
- без сборки: статичные `index.html`, `app.css`, `app.js` (Alpine.js), офлайн через `sw.js`.

## Colors

Все цвета — переменные на `:root`; тёмная тема переопределяет их дважды: в `@media (prefers-color-scheme: dark)`
под `:root:not([data-theme="light"])` и в `:root[data-theme="dark"]`. Новый токен добавляется во **все три** блока.

| Токен | Роль | Где можно |
|---|---|---|
| `--bg` | фон страницы и полей ввода | `body`, `input`, `.select` |
| `--surface` | карточки, панели, таблица, окна | `.panel`, `.table-wrap`, `.modal`, `.card` |
| `--surface-2` | вторичная заливка: hover, сегменты, код, сообщение | hover строк, `.segmented`, `.message` |
| `--line` | все рамки и разделители | 1px |
| `--text` / `--muted` | основной / вторичный текст | подписи полей, счётчики, подсказки — `--muted` |
| `--accent` | текст и рамки акцента: ссылки, выбранный чип, пункт меню, фокус | **не** под белым текстом |
| `--accent-fill`, `--accent-fill-hover` | заливка под белым текстом (`--on-accent`) | только `.btn.primary` |
| `--danger` | текст ошибок, `.danger-ghost`, опасный пункт меню | не для обратимых действий |
| `--danger-fill` | заливка под белым текстом (`--on-danger`) | только `.btn.danger` в подтверждении |
| `--ok` | успешное состояние (точка «Поиск завершён») | — |
| `--wa`, `--tg`, `--vk` | метка канала связи | только точка `.channel`; кнопки этими цветами не красятся |
| `--st-good`, `--st-wait`, `--st-active`, `--st-warm`, `--st-bad` | статус лида («Купил», «Написал», «В работе», «Почти купил», «Отказался») и клиента («Всё ок», «Есть вопрос», «Срочный баг»); «Ещё не написал» — `--muted` | `.st`, `.st-btn` |
| `--owner` | руководитель (корона, бейдж) | `.owner-badge`, `.contact.owner` |
| `--prio-cold`, `--prio-hot`, `--prio-tint` | раскраска строк по приоритету: холодный (1) → горячий (5), сила заливки | только `tr.tint-*` |

- Контраст: текст ≥ 4,5:1 на своём фоне в обеих темах. Поэтому у акцента и красного по два токена: текстовый
  (светлее в тёмной теме) и заливка (темнее, под белым текстом).
- Оттенки — через `color-mix(in srgb, var(--token) N%, transparent)`, а не новыми hex: 9–13% для фона выбранного,
  18% для кольца фокуса, 25–35% для рамки.
- Не использовать hex прямо в правилах. Исключения уже есть и не множатся: звезда рейтинга `#f5a524`, фон героя
  карточки (цвет фирмы из 2ГИС).

## Typography

Один шрифтовой стек (Inter → системный sans) и моноширинный для путей и кода.

| Роль | Размер / вес | Класс или место |
|---|---|---|
| Заголовок страницы | 22px / 650 (на поиске и «Лидах» 18px в `.top-title`) | `.page h1`, `.top-title` |
| Заголовок окна | 18px / 650, `text-wrap: balance` | `.modal h2` |
| Заголовок панели | 14px / 650 | `.panel h2` |
| Раздел карточки | 11.5px / 600, капс, `letter-spacing: .06em`, `--muted` | `.block h3` |
| Основной текст | 14px / 1.45 | `body` |
| Подпись поля, заголовок таблицы | 11.5px / 500–550, `--muted` | `.field > span`, `th` |
| Мелкий текст | 12–12.5px | `.small`, `.subbar`, `.run-bar` |
| Числа в таблицах и счётчиках | `font-variant-numeric: tabular-nums` | `.num`, `.counters b`, `.badge` |

Вес — главный инструмент иерархии: 550 для кнопок и пунктов меню, 600–650 для заголовков. Новых размеров не
вводить, брать из таблицы.

## Layout

- **Каркас:** `.workspace` = боковое меню 232px + `.main` (до 1280px, поля 28px). На ≤ 760px меню становится нижней
  панелью, поля 16px, `.main` получает отступ снизу под панель.
- **Зоны экрана** (подробно — UX-RULES §3):
  1. шапка приложения `.side`: бренд и кнопка темы, навигация, профиль и «Выйти»;
  2. шапка страницы `.top`: только `h1` (липкая, с размытием фона);
  3. панель параметров (`.search`): поля, в конце строки главная кнопка;
  4. строка статуса процесса `.run-bar` — над результатами;
  5. заголовок результатов `.results-head`: слева счётчики, справа `.results-actions` (фильтр, secondary,
     primary, «Ещё ⋯»);
  6. содержимое: `.table-wrap` или `.panel`.
- **Ритм:** шаг 4px; внутри групп 6–10px, между группами 12–18px, внутри панели 14px (`gap`), padding панели 18px,
  окна 22px. Используйте `gap`, а не margin у детей.
- **Телефон (375):** нет горизонтальной прокрутки страницы — широкое содержимое прокручивается внутри
  `.table-wrap`. Ряды кнопок переносятся или раскладываются сеткой (см. `.results-actions` в `@media`), второстепенные
  колонки таблицы получают класс `.col-extra` и скрываются. Короткие подписи меню — `.nav-short`.
- **Слои (`z-index`):** липкая шапка 5, меню 6 (15 на телефоне), кнопка темы на телефоне 16, поповеры и меню 10,
  затемнение 20, карточка и окна 21, окно поверх карточки 22–23, toast 30, skip link 40. Новые слои — в эти ступени.
- Фокус не прячется под липкими панелями: `html { scroll-padding-top / -bottom }` уже заданы.

## Elevation & Depth

Плоская система с двумя тенями:
- `--shadow` — лёгкая, для поверхностей на фоне: `.panel`, `.search`, `.table-wrap`, выбранный сегмент;
- `--shadow-lg` — для того, что над страницей: поповеры, меню, окна, карточка, toast.

Элемент получает либо рамку `--line`, либо тень `--shadow-lg`, либо обе только в уже принятых местах (панель,
окно). Новых теней и цветных свечений не добавлять.

## Shapes

| Радиус | Где |
|---|---|
| 999px (`pill`) | чипы, бейджи, статусы, метки поиска; аватар — 50% |
| 16px | панель поиска, окна |
| 12px (`--radius`) | панели, таблица, поповеры, меню |
| 9–10px | кнопки, поля, пункты меню, `.alert`, сообщения |
| 7–8px | мелкие элементы внутри: сегменты, пункты списка, миниатюры |

Рамка — всегда 1px `--line`. Цветная полоса слева шире 1px допустима только у `.contact.owner` (уже есть), в новых
местах не использовать.

## Components

Компоненты — это классы в `app.css`. Новый экран собирается из них; если нужен вариант — модификатор к
существующему классу.

**Кнопки** (`.btn` + модификатор): `primary` — одна на область; без модификатора — secondary; `ghost` —
третьестепенное и «Отмена»; `danger` — только кнопка подтверждения необратимого; `danger-ghost` — кнопка,
открывающая такое подтверждение. Высота 36px (40px в форме поиска — `.btn.go`). Иконка 16px слева от текста,
`gap: 8px`. Счётчик — `.badge` внутри кнопки. `.icon-btn` — кнопка только с иконкой (32–36px), всегда с
`aria-label` и `title`. `.link` — действие в строке текста.

**Поля:** `.field` (подпись `<span>` сверху + `input`/`select`), `.path-row` (поле + кнопка «Выбрать папку»,
переносится), `.select` (кнопка-выпадашка с иконкой `chevron-down` + `.popover`), `.check` (чекбокс с подписью),
`.toggle`. Ошибка поля: `aria-invalid="true"` на поле (красная рамка) + `.field-error` с `role="alert"` и `id`,
на который ссылается `aria-describedby`. Подсказка под полем (например, какая ссылка получится) — `.muted.small.field-note`.

**Выбор одного из нескольких:** `.chip` в контейнере `.spheres` (сферы, папки), `.segmented` (тема, приоритет,
режим сохранения), `.st-btn` (статус лида). Контейнер — `role="radiogroup"` с `aria-label` и
`@keydown="radioKeys($event)"`, элементы — `role="radio"` + `:aria-checked`, выбранный — класс `on`.

**Окна:**
- `.card` — панель справа для просмотра и правки, не теряя список (карточка лида);
- `.modal` — центральный диалог для короткого решения или подтверждения; `role="dialog"` или `alertdialog`,
  `aria-labelledby` на `h2`, `x-ref`, `@keydown.tab="trapTab($event)"`; кнопки в `.modal-actions`:
  ghost «Отмена» слева, действие справа и названо глаголом с объектом;
- `.scrim` — затемнение под окном, клик закрывает;
- `.menu` + `.menu-item` в `.more` — меню «Ещё ⋯» для второстепенных действий (`role="menu"` / `menuitem`,
  опасный пункт — `.menu-item.danger`);
- `.popover` — выпадающая панель у поля (города).

**Обратная связь:**
- `.toast` (`role="status"`) — итог действия, исчезает сам: `notify('…')`;
- `.alert` (`role="alert"`) — ошибка процесса над результатами;
- `.field-error` — ошибка у поля;
- `.run-bar` — состояние длительного процесса: точка `.dot` (цвет по состоянию), текст с `role="status"`, ход,
  параметры;
- `.empty` — пустое состояние: заголовок, одна фраза, кнопка следующего шага.

**Данные:** `.table-wrap > table` (заголовки 11.5px `--muted`, строки 9×14px, hover `--surface-2`, название —
кнопка `.row-open`, выбор — `.pick-hit` с чекбоксом), `.counters`, `.pill`, `.badge`, `.st` (статус), `.prio-stars`
(приоритет 0–5: столько маленьких звёзд `--accent` внахлёст, сколько приоритет, вплотную слева от фото; раскраска
строк `tr.tint-1…5` по переключателю «Раскрасить по приоритету» — шкала от `--prio-cold` к `--prio-hot`),
`.channel` (точка цвета канала), `.owner-badge`, `.thumb`, `.kv` (пары «ключ — значение»), `.block` и `.sub-sec`
со сворачиваемым заголовком `.sec-btn` (`aria-expanded`).

**Иконки:** `<svg class="icon" aria-hidden="true"><use href="/static/app/vendor/icons.svg#name"/></svg>`. Спрайт —
Lucide, stroke 2, `currentColor`, 16px (18px в меню и `.icon-btn`). Новая иконка: добавить `<symbol id="name"
viewBox="0 0 24 24">` с путями из Lucide в `vendor/icons.svg` (только нужные); одна иконка = одно действие
(таблица в UX-RULES §5); поднять `CACHE` в `sw.js`.

**Движение:** переходы 0.15s по `color`, `background`, `border-color`, `box-shadow` (не `all`); появление строк —
`appear()`; выезд карточки — `.slide-in`. Всё, что движется, отключается в `@media (prefers-reduced-motion: reduce)`
и в `appear()` — состояние при этом остаётся видимым.

**JS-помощники в `app.js`** (использовать, а не писать заново):
- `WINDOWS` + `focusWindow` / `returnFocus` / `trapTab` — фокус в окнах; новое окно — строка в `WINDOWS`
  (флаг → `[x-ref окна, x-ref запасной кнопки]`) и `data-autofocus` на первом поле;
- `showFormError(field, text)` / `clearFormError()` — ошибка у поля с фокусом;
- `notify(text)` — toast;
- `plural(n, [один, два, пять])`, `leadsWord(n)` — склонение;
- `formatDate(value)` — даты по-русски через `Intl`;
- `radioKeys(e)` — стрелки в radiogroup;
- `toggleMore()` / `closeMore()` — меню «Ещё»;
- `setTheme('light' | 'dark' | '')`, `toggleTheme()` — тема.

## Do's and Don'ts

**Do**
- Собирать экран из классов выше и токенов; проверять обе темы и ширину 375.
- Одна primary-кнопка на область; главное действие — иконка + текст «глагол + объект».
- Окно выбирать по задаче: панель справа — смотреть и править; диалог — решить или подтвердить; toast — итог;
  ошибка — у поля.
- Давать каждому экрану состояния загрузки, пусто и ошибки.
- Держать тексты в словаре UX-RULES §4 и синхронизировать встроенную «Документацию» с `docs/LOGIC.md`.

**Don't**
- Не добавлять hex-цвета, тени, размеры шрифта и радиусы вне таблиц выше.
- Не красить кнопки цветами каналов и статусов; не делать красной обратимую кнопку («Остановить»).
- Не ставить эмодзи и текстовые символы (✕, ↗, ↓) вместо иконок; не тянуть иконки и шрифты с CDN.
- Не прятать причину неактивной кнопки только в `title`.
- Не открывать `tel:` и `mailto:` в новой вкладке; не класть статус процесса и «Остановить» в шапку.
- Не добавлять `transition: all` и анимации без варианта для `prefers-reduced-motion`.
