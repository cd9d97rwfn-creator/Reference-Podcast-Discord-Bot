# Render 緊急部署設定

這個專案是 **Python 3.12**，不是 Rust。請勿使用 `cargo build --release`。

## 現有 Render 服務

在 Render 的 **Settings → Build & Deploy** 填入：

- Build Command: `pip install .`
- Start Command: `reference-bot`
- Health Check Path: `/health`

在 **Environment** 至少設定：

- `DISCORD_TOKEN`: Discord Developer Portal 的 Bot Token
- `DATABASE_PATH`: `episodes.sqlite3`

選用設定：

- `DISCORD_GUILD_ID`: 測試伺服器 ID，可讓該伺服器立即看到 slash commands
- `DISCORD_GUILD_IDS`: 多個伺服器 ID，以逗號分隔

儲存後執行 **Manual Deploy → Clear build cache & deploy**。

成功的 Logs 應包含：

```text
Using database: episodes.sqlite3
Health server listening on port ...
Synced 6 global slash commands
Bot is ready as ...
```

## 如果 Render 不允許把原服務改成 Python

建立新的 **Web Service**：

1. 選擇同一個 GitHub repository。
2. Runtime 選 Python 3。
3. Build Command 填 `pip install .`。
4. Start Command 填 `reference-bot`。
5. Health Check Path 填 `/health`。
6. 加入上述環境變數。

專案也附有 `render.yaml`，可以用 Render Blueprint 建立服務。

## Discord 測試

部署成功後，在 Discord 的文字頻道輸入 `/`，應看到：

- `/ping`
- `/episodes`
- `/book`
- `/topic`
- `/mentioned`
- `/ask`

直接輸入一般文字 `ping` 不等於 slash command；請使用 `/ping`。
