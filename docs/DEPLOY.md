# Деплой blubot на VPS

## 1. Создать бота

1. Открыть [@BotFather](https://t.me/BotFather)
2. `/newbot` → получить `BOT_TOKEN`
3. Узнать свой `ADMIN_ID` через [@userinfobot](https://t.me/userinfobot)

## 2. Подготовка сервера

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
git clone <repo-url> blubot && cd blubot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Заполнить `.env`:
```
BOT_TOKEN=...
ADMIN_ID=...
ADMIN_USERNAME=your_telegram_username
DB_PATH=data/blubot.db
BOOKING_TTL_HOURS=12
```

## 3. Первый запуск

```bash
mkdir -p data
python -m bot.main
```

## 4. systemd (автозапуск)

```bash
sudo nano /etc/systemd/system/blubot.service
```

```ini
[Unit]
Description=BluBot Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/blubot
ExecStart=/home/ubuntu/blubot/.venv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable blubot
sudo systemctl start blubot
sudo systemctl status blubot
```

## 5. Smoke-test

1. `/start` от админа — видно админ-меню
2. `/adduser @friend` — добавить пользователя
3. Добавить товар через «Добавить товар»
4. От пользователя: забронировать → инструкция → «Мои брони»
5. От админа: «Ожидают» → корзина → подтвердить
6. Товар исчез из каталога

## Логи

```bash
sudo journalctl -u blubot -f
```
