# Архитектура blubot

## Стек

- Python 3.11+
- aiogram 3 (long polling)
- aiosqlite
- python-dotenv
- Pillow (локальная диаграмма статистики)

## Структура

```
bot/
├── main.py              # entry point, protect_content default
├── config.py            # SUPERUSER_*, CART_TTL_MINUTES
├── db.py
├── stats.py             # окна и агрегаты заказов и товаров
├── chart.py             # PNG столбцов категорий
├── catalog_nav.py       # дерево каталога и подпись привязки
├── notify.py            # notify_admins (без супера)
├── filters.py
├── keyboards.py
├── middlewares/access.py
├── handlers/
│   ├── common.py        # /start, Помощь
│   ├── catalog.py
│   ├── categories.py    # категории и подкатегории, удаление пустых
│   ├── stats.py         # статистика заказов и товаров
│   ├── booking.py       # корзина, оформить/очистить
│   └── admin.py
└── tasks/expiry.py      # 20 мин pending → expired
```

## Брони: статусы

`pending` → `submitted` (оформить) → `confirmed`/`rejected`  
`pending` → `cancelled` / `expired`

## Каталог

Корень категорий → категория или «Без категории» → подкатегория → фото карточки. Альбома нет.

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
