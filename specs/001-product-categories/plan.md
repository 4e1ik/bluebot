# Implementation Plan: Категории и подкатегории товаров

**Branch**: `001-product-categories` | **Date**: 2026-11-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-product-categories/spec.md`

## Summary

Админ заводит категории и подкатегории, переименовывает их и переносит подкатегорию на другую категорию. Новый товар сохраняется только с одной привязкой: к категории или к подкатегории. Эту привязку можно сменить. Старые товары без привязки остаются в каталоге. Каталог открывается деревом, карточка показывает текущую привязку. Бронь, белый список, 🆕 и запрет пересылки не меняются.

## Technical Context

**Language/Version**: Python 3.11+ (venv проекта; системный 3.9 не использовать)

**Primary Dependencies**: aiogram 3, aiosqlite

**Storage**: SQLite, файл из `DB_PATH` (по умолчанию `data/blubot.db`)

**Testing**: unittest в `tests/test_categories.py` против временной базы. Живой прогон — локальный запуск бота и сценарии админа.

**Target Platform**: macOS, long polling Telegram

**Project Type**: Telegram-бот, один пакет `bot/`

**Performance Goals**: Каталог магазина, списки целиком в одном сообщении. Отдельный бюджет задержки не задан.

**Constraints**: Не удалять категории. Не добавлять поля товара. Не включать `PRAGMA foreign_keys`, потому что текущий код на это не рассчитан. Пустое имя не сохранять. Повтор имён разрешён. Сортировка имён по `casefold`, чтобы кириллица не ломалась на `COLLATE NOCASE`.

**Scale/Scope**: Текущий каталог одного магазина. Два уровня. Один админский сценарий создания, правки и переноса.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- I. Сохранять текущее поведение: бронь, whitelist, 🆕 от `created_at`, `protect_content` не трогаем. Правка товара не меняет `created_at`.
- II. Каталог меняет только админ: новые действия вешаются на `admin_router`.
- III. Не выдумывать: удаления категорий нет, третьего уровня нет, служебная категория для старых товаров не создаётся.
- IV. Существующие данные: колонки привязки добавляются как NULL, старые строки читаются.
- V. Две таблицы и одна привязка на товар. Перенос подкатегории меняет только её родителя.

После Phase 1 нарушений нет. Таблица Complexity Tracking не нужна.

## Project Structure

### Documentation (this feature)

```text
specs/001-product-categories/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── catalog.md
└── tasks.md
```

### Source Code (repository root)

```text
bot/
├── db.py                 # таблицы, миграция, привязки
├── catalog_nav.py        # подпись привязки и сборка экранов каталога
├── keyboards.py          # меню и клавиатуры дерева
├── handlers/
│   ├── catalog.py        # просмотр дерева
│   ├── categories.py     # создание, имена, перенос подкатегории
│   ├── admin.py          # товар: привязка при создании и при правке
│   └── booking.py        # возврат в корень каталога
└── main.py               # импорт handlers.categories

tests/
└── test_categories.py
```

**Structure Decision**: Логика остаётся в текущем пакете `bot/`. Новые экраны категорий — отдельный модуль обработчиков на уже существующем `admin_router`. Отдельный сервис и новая база не нужны.

## Complexity Tracking

Нарушений конституции нет.
