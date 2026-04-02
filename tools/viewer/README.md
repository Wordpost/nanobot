# Nanobot Session Viewer 🧬 (Forensic Edition)

> **High-speed diagnostic interface for monitoring and debugging Nanobot agent sessions.**

---

## 🔍 Overview

**Session Viewer** — специализированная панель для анализа логов и сессий автономных агентов Nanobot.

Интерфейс выполнен в эстетике **Forensic Orange**: высокая контрастность, моноширинные шрифты, чёткое разделение между системными процессами и ответами агента.

**Viewer полностью портабелен** — можно разместить в любой директории, и он автоматически найдёт папку `.nanobot/workspace/sessions`, поднимаясь по дереву каталогов.

---

## ✨ Features

- 🧠 **Thought Transparency** — интерактивные блоки для reasoning и tool_calls
- ⚡ **Turbo Streaming Parser** — обработка JSONL файлов 500MB+ без зависаний
- 🩺 **Docker Logs** — стриминг логов контейнера в реальном времени
- 📍 **Auto-detect** — автоматический поиск `.nanobot` папки (работает из любого расположения)

---

## 🚀 Quick Start

### 1. Setup
```bash
cd tools/viewer
python3 -m venv venv
source venv/bin/activate      # Linux/macOS
# или: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Launch
```bash
./run.sh      # Linux/macOS
# или
run.bat       # Windows
```

Откройте [http://127.0.0.1:2003](http://127.0.0.1:2003) в браузере.

---

## ⚙️ Configuration

Viewer подхватывает конфигурацию в следующем приоритете:

1. **`.env` файл** в папке viewer (скопируйте из `.env.example`)
2. **Переменные окружения**
3. **Автодетект** — viewer поднимается по дереву каталогов и ищет `.nanobot/workspace/sessions`

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NANOBOT_SESSIONS_DIR` | Абсолютный путь к сессиям | *auto-detect* |
| `NANOBOT_PORT` | Порт сервера | `2003` |
| `NANOBOT_HOST` | Хост сервера | `127.0.0.1` |
| `NANOBOT_CONTAINER` | Docker контейнер для логов | `nanobot-gateway` |

### Пример `.env` для VPS
```env
NANOBOT_SESSIONS_DIR=/opt/nanobot/.nanobot/workspace/sessions
NANOBOT_HOST=0.0.0.0
```

---

## 📂 Deployment Layout

```text
/opt/nanobot/                        ← deployment root
├── docker-compose.yml               ← compose (поднимает бота)
├── .env                             ← API keys, tokens
├── .nanobot/                        ← bot workspace (volume)
│   └── workspace/sessions/          ← ← ← viewer читает отсюда
└── nanobot/                         ← git clone форка
    ├── Dockerfile
    ├── nanobot/
    ├── tools/
    │   └── viewer/                  ← Session Viewer
    └── ...
```

---

## 🎨 Aesthetics
- **Accent Color**: `#FF5C00` (Signal Orange)
- **Typography**: Inter (UI), JetBrains Mono (Code/Logs)
- **Borders**: Sharp 1px (Solid Forensic style)

---
*Created with 🧡 for the Nanobot Ecosystem.*
