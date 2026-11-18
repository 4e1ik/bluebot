# Tasks: Статистика заказов и товаров

**Input**: Design documents from `/specs/002-admin-order-stats/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/stats.md, quickstart.md

**Tests**: Проверки в `tests/test_stats.py` пишутся до поведения в `bot/db.py` и `bot/stats.py`. Критерий готовности требует прогон путей и запуск бота.

**Organization**: Общие файлы `bot/db.py` и `bot/stats.py` не дают параллелить истории. Порядок: схема, заказы, товары, сравнения, диаграмма, удаление, прогон.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Добавить локальную библиотеку картинки, не меняя каркас бота.

- [x] T001 Добавить Pillow в `requirements.txt`

---

## Phase 2: Foundational

**Purpose**: `Order`, `OrderLine` и `Booking.order_id` из `data-model.md`. Без них ни один отчёт не считается.

- [x] T002 Написать падающие проверки снимка заказа в `tests/test_stats.py`
- [x] T003 Добавить таблицы и колонку в `bot/db.py`, не затирая старые брони и товары

**Checkpoint**: Старая база открывается, новое оформление получает один заказ.

---

## Phase 3: User Story 1 - Сводка заказов (Priority: P1)

**Goal**: Семь окон заказов и кнопка «Статистика заказов».

**Independent Test**: Два оформления дают два заказа. Позднее подтверждение не двигает дату и увеличивает сумму. Окно «сегодня» считается по Минску.

- [x] T004 [US1] Считать окна заказов в `bot/stats.py` по `Order.confirmed_at` и `OrderLine.price`
- [x] T005 [US1] Кнопка и ответ в `bot/keyboards.py` и `bot/handlers/stats.py`

**Checkpoint**: Админ видит семь пар «число и сумма». Отклонённая позиция не входит.

---

## Phase 4: User Story 2 - Разрезы и статистика товаров (Priority: P1)

**Goal**: Отдельная кнопка «Статистика товаров». Категории, подкатегории и «Без категории» в обоих отчётах.

**Independent Test**: Сумма категорий окна равна сводке. Товар, подтверждённый позже, попадает в более позднее товарное окно и в более раннюю сумму заказа. Число заказов одной корзины в двух категориях не складывается в одно.

- [x] T006 [US2] Агрегаты категорий и товаров в `bot/stats.py` по полям `OrderLine.category_id`, `OrderLine.subcategory_id`, `OrderLine.parent_category_id`, `OrderLine.confirmed_at`
- [x] T007 [US2] Второй отчёт в `bot/handlers/stats.py`

**Checkpoint**: Два отчёта расходятся на позднем подтверждении.

---

## Phase 5: User Story 3 - Сравнение (Priority: P2)

**Goal**: Категории и подкатегории по убыванию числа и суммы, нули внизу.

**Independent Test**: Лидер по числу не совпадает с лидером по сумме. Пустая категория последняя среди нулей и видна.

- [x] T008 [US3] Сортировки в `bot/stats.py` и их строки в тексте отчёта

**Checkpoint**: При равном значении порядок имён как в каталоге.

---

## Phase 6: User Story 4 - Средняя (Priority: P2)

**Goal**: Средняя сумма заказа и средняя сумма товара за 30 суток.

**Independent Test**: Ручное деление совпадает. При нуле текст «средней нет», без числа.

- [x] T009 [US4] Средняя с одним знаком в `bot/stats.py`

**Checkpoint**: Заказ старше 30 суток в среднюю не входит.

---

## Phase 7: User Story 5 - Диаграмма (Priority: P3)

**Goal**: Столбцы сумм категорий за всё время, если картинка собирается локально.

**Independent Test**: Ненулевые суммы дают PNG. Все нули не дают фото. Сбой картинки оставляет текст.

- [x] T010 [US5] Рисунок в `bot/chart.py` и отправка в `bot/handlers/stats.py`

**Checkpoint**: Без Pillow отчёт всё равно текстовый.

---

## Phase 8: User Story 6 - Удаление пустых (Priority: P2)

**Goal**: Удалить только пустую категорию или подкатегорию.

**Independent Test**: Непустая запись остаётся с объяснением. После удаления товара и пустой категории снимок суммы на месте.

- [x] T011 [US6] `delete_category` и `delete_subcategory` в `bot/db.py` по правилам пустоты из `data-model.md`
- [x] T012 [US6] Кнопки и ответы в `bot/keyboards.py` и `bot/handlers/categories.py`

**Checkpoint**: Скрытый товар тоже не даёт удалить категорию.

---

## Phase 9: Polish

**Purpose**: Прогон путей, проверочные данные и описание поведения.

- [x] T013 Пройти создание, правку и удаление и засеять 5 категорий и 50 товаров в `scripts/verify_stats_paths.py`
- [x] T014 Обновить описание меню и удаления в `docs/SPEC.md` и `docs/ARCHITECTURE.md`
- [x] T015 Прогнать `tests/test_categories.py`, `tests/test_stats.py` и локальный запуск бота

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup никого не блокирует, кроме картинки.
- Foundational блокирует все истории.
- US2 зависит от US1, потому что делит строки заказа.
- US3 и US4 зависят от агрегатов US2.
- US5 зависит от сравнения US3.
- US6 зависит от снимка US1, чтобы удаление не стирало суммы.
- Polish зависит от всех историй.

### User Story Dependencies

- US1 после схемы.
- US2 после US1.
- US3 и US4 после US2, между собой независимы по смыслу, но правят один `bot/stats.py`.
- US5 после US3.
- US6 после снимка.

### Parallel Opportunities

- T010 может писаться отдельно от текста, пока известен список сумм.
- Истории нельзя параллелить: одни и те же `bot/db.py` и `bot/stats.py`.

### Parallel Example: User Story 5

```bash
# После того как отчёт уже возвращает суммы категорий:
# править только bot/chart.py, не меняя расчёт окон
```

---

## Implementation Strategy

MVP — US1: кнопка заказов и семь окон. Дальше товары и разрезы, затем сравнение, средняя, диаграмма и удаление пустых. Готово после T015.

## Notes

- Проверки T002 должны падать до T003.
- Поля с ограничениями цитируются как `data-model.md`: `Order.confirmed_at`, `OrderLine.price`, `OrderLine.confirmed_at`, `OrderLine.category_id`, `OrderLine.subcategory_id`, `OrderLine.parent_category_id`, `Booking.order_id`.
