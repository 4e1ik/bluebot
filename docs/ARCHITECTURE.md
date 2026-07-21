# Архитектура blubot

## Стек

- Python 3.11+
- aiogram 3 (long polling)
- aiosqlite
- python-dotenv

## Структура

```
bot/
├── main.py              # entry point, protect_content default
├── config.py            # SUPERUSER_*, CART_TTL_MINUTES
├── db.py
├── notify.py            # notify_admins (без супера)
├── filters.py
├── keyboards.py
├── middlewares/access.py
├── handlers/
│   ├── common.py        # /start, Помощь
│   ├── catalog.py
│   ├── booking.py       # корзина, оформить/очистить
│   └── admin.py
└── tasks/expiry.py      # 20 мин pending → expired
```

## Брони: статусы

`pending` → `submitted` (оформить) → `confirmed`/`rejected`  
`pending` → `cancelled` / `expired`

## Каталог

Список кнопок → клик → фото карточки. Альбома нет.

## Уведомления

`notify_admins`: только `admins.user_id`, после `cart:submit`.

## Env

```
BOT_TOKEN=
SUPERUSER_ID=
SUPERUSER_USERNAME=
DB_PATH=data/blubot.db
CART_TTL_MINUTES=20
```
