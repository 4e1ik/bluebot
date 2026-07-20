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
├── config.py            # env config
├── db.py                # SQLite CRUD
├── keyboards.py         # reply/inline keyboards
├── middlewares/
│   └── access.py        # whitelist check
├── handlers/
│   ├── common.py        # /start, main menu
│   ├── catalog.py       # catalog, item card
│   ├── booking.py       # book, cancel, my bookings
│   └── admin.py         # add item FSM, carts, whitelist
└── tasks/
    └── expiry.py        # 12h auto-cancel
```

## Схема БД

### whitelist
- `id`, `username` (lowercase, без @), `added_at`

### items
- `id`, `name`, `price`, `photo_file_id`, `status`, `created_at`
- status: `available` | `pending` | `hidden`

### bookings
- `id`, `item_id`, `user_id`, `username`, `status`, `created_at`, `expires_at`
- status: `pending` | `confirmed` | `rejected` | `expired` | `cancelled`

## Потоки

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

## Доступ

`AccessMiddleware` пропускает:
- `user.id == ADMIN_ID`
- `user.username` в whitelist (lowercase)

Иначе — «Нет доступа».
