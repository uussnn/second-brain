# Second Brain Autonomous Agent Skill (v4.0.0)

<!-- yarkr:badges:start -->
[![Indexed on Yarkr](https://api.yarkr.com/functions/v1/api/api/v1/badges/repos/uussnn/second-brain/version.svg)](https://yarkr.com/arks/uussnn/second-brain)
<!-- yarkr:badges:end -->

Полностью автономный on-device агент для управления знаниями по методологии PARA (Projects, Areas, Resources, Archives). Оптимизирован для моделей Gemma 4 (E2B/E4B) и работает 100% оффлайн, гарантируя абсолютную приватность ваших данных.

## Установка (Sideloading) в Google AI Edge Gallery

Для установки локальной версии выполните следующие шаги:

1. Установите приложение **Google AI Edge Gallery** (требуется Android 12+ или iOS 17+).
2. Скопируйте папку `second-brain` (включая все подпапки) во внутреннюю память вашего смартфона или планшета.
3. Откройте приложение Gallery и перейдите в раздел **Agent Skills**.
4. Выберите опцию **"Import from local file"** и укажите путь к скопированной папке навыка.
5. При активации навыка предоставьте ему запрошенные разрешения для доступа к файловой системе (`storage.read`, `storage.write`).

## Архитектура
- **SKILL.md** — L1 Метаданные и ролевые инструкции для LLM.
- **scripts/** — Изолированная среда выполнения (WebView) для базы данных SQLite WASM и бизнес-логики.
- **assets/** — JSON-схемы для вызова инструментов.

<!-- yarkr:install:start -->
## Install with Yarkr

This repo is indexed on [Yarkr](https://yarkr.com/arks/uussnn/second-brain) as the ark [uussnn/second-brain](https://yarkr.com/arks/uussnn/second-brain), so its skills install into Claude Code, Codex, Cursor and other agent harnesses with one command.

### CLI

Install the whole ark, which Yarkr keeps equal to this repo:

```bash
npx yarkr-cli sync uussnn/second-brain
```

Or add individual skills:

```bash
npx yarkr-cli add skill:uussnn/second-brain/second-brain
```

No Node.js? `curl -fsSL https://yarkr.com/install.sh | sh` (macOS, Linux) or `irm https://yarkr.com/install.ps1 | iex` (Windows PowerShell) installs `yarkr` as a standalone binary; then type `yarkr` in place of `npx yarkr-cli`.

### MCP

Connect your agent to the ark over MCP:

```bash
npx yarkr-cli mcp add uussnn/second-brain
```

Or point any MCP client at `https://api.yarkr.com/functions/v1/api/mcp/o/uussnn/second-brain`.
<!-- yarkr:install:end -->
