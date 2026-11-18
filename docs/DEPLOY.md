# Деплой blubot на VPS

Бот — отдельный Docker Compose проект. VPN, который уже крутится на сервере, не входит в этот файл и свою сеть боту не отдаёт. Боту нужен исходящий HTTPS к Telegram с самого сервера.

## 1. Создать бота

1. Открыть [@BotFather](https://t.me/BotFather)
2. `/newbot` → получить `BOT_TOKEN`
3. Узнать `SUPERUSER_ID` через [@userinfobot](https://t.me/userinfobot)

## 2. Подготовка сервера

На сервере нужны Docker и Docker Compose plugin. Каталог бота не должен быть каталогом VPN.

```bash
git clone <repo-url> blubot && cd blubot
cp .env.example .env
nano .env
```

Заполнить `.env`:

```
BOT_TOKEN=...
SUPERUSER_ID=...
SUPERUSER_USERNAME=superuser_telegram
DB_PATH=data/blubot.db
CART_TTL_MINUTES=20
```

`DB_PATH` оставить `data/blubot.db`: этот каталог смонтирован в том `bot-data` и переживает пересоздание контейнера.

## 3. Запуск

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```

В журнале должно появиться `Bot started`. После изменений в коде:

```bash
docker compose up -d --build
```

`docker compose down` останавливает контейнер и не удаляет том с базой. Том удаляется только вместе с флагом `-v`.

## 4. Smoke-test

1. `/start` от супера — админ-меню, «Админы», «Статистика заказов» и «Статистика товаров»
2. Добавить админа → админ делает `/start` (чтобы пришёл `user_id`)
3. Добавить пользователя в whitelist
4. Добавить товар
5. Пользователь: забронировать → «Мои брони» → «Оформить заказ»
6. Админ получает уведомление; «Ожидают» → подтвердить
7. Товар исчез из каталога

Локальная база с проверочными товарами в образ не входит. На сервере база создаётся пустой, пока в том сами не положат файл `blubot.db`.
