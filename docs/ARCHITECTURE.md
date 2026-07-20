# Архитектура blubot

## Стек

- Python 3.11+
- aiogram 3 (long polling)
- aiosqlite
- python-dotenv

## Структура

```
bot/
├── main.py              # entry point
├── config.py            # SUPERUSER_* / MAINADMIN_* from env
├── db.py                # SQLite CRUD
├── filters.py           # IsAdmin, IsSuper
├── keyboards.py         # reply/inline keyboards
├── middlewares/
│   └── access.py        # super / admin / whitelist
├── handlers/
│   ├── common.py        # /start, main menu
│   ├── catalog.py       # catalog, item card
│   ├── booking.py       # book, cancel, my bookings
│   └── admin.py         # items, carts, whitelist, admins (super)
└── tasks/
    └── expiry.py        # 12h auto-cancel
```

## Схема БД

### whitelist
- `id`, `username` (lowercase, без @), `added_at`

### admins
- `id`, `username` (UNIQUE), `user_id` (UNIQUE, nullable), `added_at`
- `user_id` заполняется при первом сообщении админа боту

### items
- `id`, `name`, `price`, `photo_file_id`, `status`, `created_at`
- status: `available` | `pending` | `hidden`

### bookings
- `id`, `item_id`, `user_id`, `username`, `status`, `created_at`, `expires_at`
- status: `pending` | `confirmed` | `rejected` | `expired` | `cancelled`

## Роли (доступ)

| Роль | Проверка | Права |
|------|----------|-------|
| Супер | `user.id == SUPERUSER_ID` | Всё + «Админы» |
| Админ | таблица `admins` | Товары, брони, whitelist |
| User | `whitelist` | Каталог, брони |

`MAINADMIN_USERNAME` — только для текста «напишите админу @…», без прав доступа.

## Потоки

### Каталог
1. User → «Каталог»
2. Бот шлёт альбом фото (по 10 в группе) + сообщение с inline-кнопками
3. Клик по кнопке → карточка товара (фото + действия)

### Бронирование
1. User → «Забронировать» на `available` товаре
2. `bookings.status = pending`, `items.status = pending`
3. Сообщение с инструкцией написать админу

### Отмена пользователем
1. User → «Отменить» на своей брони
2. `bookings.status = cancelled`, `items.status = available`

### Подтверждение админом
1. Admin → «Ожидают» → выбор пользователя → корзина
2. Confirm all / per item
3. `bookings.status = confirmed`, `items.status = hidden`

### Автоотмена
1. Task каждые 5 мин: `expires_at < now` AND `status = pending`
2. `bookings.status = expired`, `items.status = available`
3. Уведомление пользователю

## Callback data

| Pattern | Действие |
|---------|----------|
| `item:{id}` | Карточка товара |
| `book:{id}` | Забронировать |
| `cancel:{booking_id}` | Отменить бронь |
| `my_bookings` | Мои брони |
| `admin:pending` | Список корзин |
| `admin:cart:{user_id}` | Корзина пользователя |
| `admin:confirm_all:{user_id}` | Подтвердить всё |
| `admin:reject_all:{user_id}` | Отклонить всё |
| `admin:confirm:{booking_id}:{user_id}` | Подтвердить товар |
| `admin:reject:{booking_id}:{user_id}` | Отклонить товар |
| `admin:user_add` / `admin:user_remove` | Whitelist FSM |
| `super:admin_add` / `super:admin_remove` | Admins FSM (только супер) |

## Доступ

`AccessMiddleware` пропускает:
- `user.id == SUPERUSER_ID` (супер)
- username / user_id в таблице `admins`
- `user.username` в whitelist (lowercase)

Иначе — «Нет доступа».
При апдейте от username из `admins` — привязка `user_id`.
В инструкциях пользователям показывается `@MAINADMIN_USERNAME`.
