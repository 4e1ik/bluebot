# Tasks: Категории и подкатегории товаров

**Input**: Design documents from `/specs/001-product-categories/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/catalog.md, quickstart.md

**Tests**: Правила привязки проверяются в `tests/test_categories.py` до изменения `bot/db.py`.

**Organization**: Сначала общая схема, затем истории. Истории делят `bot/db.py` и обработчики, поэтому идут по порядку, не параллельно.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Проверить, что текущий проект уже подходит, без нового каркаса.

- [x] T001 Убедиться, что пакет `bot/` и `.venv` уже есть, и не добавлять зависимости в `requirements.txt`

---

## Phase 2: Foundational

**Purpose**: Схема и миграция, без которых нельзя сохранить привязку. Поля `Category.name`, `Subcategory.name`, `Subcategory.category_id`, `Item.category_id`, `Item.subcategory_id` из `data-model.md`.

- [x] T002 Написать падающие проверки миграции и одной привязки в `tests/test_categories.py`
- [x] T003 Добавить таблицы и колонки в `bot/db.py`, не затирая старые товары

**Checkpoint**: Старый товар читается без привязки, новый без цели не создаётся.

---

## Phase 3: User Story 1 - Создать категорию (Priority: P1)

**Goal**: Админ создаёт категорию с непустым именем и видит список.

**Independent Test**: Две категории в списке по имени, пустое имя не создаётся.

- [x] T004 [US1] Методы создания и списка категорий в `bot/db.py`
- [x] T005 [US1] Кнопка «Категории» и сценарий нового имени в `bot/keyboards.py` и `bot/handlers/categories.py`

**Checkpoint**: Категория создаётся только админом.

---

## Phase 4: User Story 2 - Подкатегория и перенос (Priority: P1)

**Goal**: Подкатегория привязана к одной категории и переносится вместе со своими товарами.

**Independent Test**: Перенос меняет родителя и не меняет `subcategory_id` товара.

- [x] T006 [US2] Создание, список и перенос подкатегории в `bot/db.py`
- [x] T007 [US2] Выбор родителя и перенос в `bot/handlers/categories.py`

**Checkpoint**: Перенос на ту же категорию ничего не меняет.

---

## Phase 5: User Story 3 - Имена (Priority: P2)

**Goal**: Правка названия не меняет привязку.

**Independent Test**: После нового имени родитель подкатегории прежний.

- [x] T008 [US3] Переименование категории и подкатегории в `bot/db.py` и `bot/handlers/categories.py`

**Checkpoint**: Пустое имя оставляет старое.

---

## Phase 6: User Story 4 - Привязка товара (Priority: P1)

**Goal**: Новый товар имеет одну цель. Админ меняет фото, имя, цену и цель.

**Independent Test**: Перенос с категории на подкатегорию оставляет одну цель и прежний `created_at`.

- [x] T009 [US4] Создание и смена привязки товара в `bot/db.py`
- [x] T010 [US4] Шаг выбора цели при создании и кнопка привязки в правке в `bot/handlers/admin.py` и `bot/keyboards.py`

**Checkpoint**: Без категорий новый товар не сохраняется.

---

## Phase 7: User Story 5 - Каталог деревом (Priority: P1)

**Goal**: Покупатель идёт категория → подкатегория → товар. Старый товар виден как «Без категории».

**Independent Test**: Карточка показывает одну подпись, назад ведёт в свой список.

- [x] T011 [US5] Сборка экранов в `bot/catalog_nav.py` и `bot/keyboards.py`
- [x] T012 [US5] Обработчики дерева в `bot/handlers/catalog.py` и возврат из `bot/handlers/booking.py` и удаления в `bot/handlers/admin.py`

**Checkpoint**: Плоского списка всех товаров в каталоге нет.

---

## Phase 8: Polish

**Purpose**: Документация текущего поведения и живой прогон.

- [x] T013 Обновить разделы каталога и правки товара в `docs/SPEC.md` и структуру в `docs/ARCHITECTURE.md`
- [x] T014 Дописать `.gitignore` шаблоном `.DS_Store`
- [x] T015 Запустить `tests/test_categories.py`, затем бота, и пройти `specs/001-product-categories/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 не блокирует код: проект уже есть.
- Phase 2 блокирует истории.
- US2 зависит от категорий US1.
- US3 зависит от записей US1 и US2.
- US4 зависит от целей US1 и US2.
- US5 зависит от привязки US4 и списков US1–US2.
- Phase 8 после историй.

### User Story Dependencies

- US1 после фундамента.
- US2 после US1.
- US3 после US1 и US2.
- US4 после US1 и US2.
- US5 после US4.

### Parallel Opportunities

Параллельных задач нет: истории пишут в одни и те же `bot/db.py` и `bot/handlers/categories.py`.

---

## Parallel Example: User Story 1

```text
Нет параллельного запуска: T004 и T005 идут по очереди, тест T002 уже написан.
```

---

## Implementation Strategy

Сначала падающий тест и схема, затем админские истории, затем дерево каталога, затем живой бот по quickstart. MVP для проверки данных — US1–US4. US5 нужен, потому что просмотр каталога выбран деревом.

## Notes

- Удаление категорий не делать.
- `created_at` товара не обновлять.
- Коммит не создавать, пока его не попросят.
