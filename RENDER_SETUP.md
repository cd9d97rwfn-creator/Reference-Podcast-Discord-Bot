# Render 部署設定

在 Render 的 Settings → Build & Deploy 填入：

- Runtime: Python 3
- Build Command: `python -m pip install --upgrade pip && python -m pip install .`
- Start Command: `python start.py`
- Health Check Path: `/health`

不要在 Start Command 輸入 Dockerfile 語法，例如 `CMD ["reference-bot"]`。

Environment：

- `DISCORD_TOKEN`: Discord Bot Token
- `DATABASE_PATH`: `episodes.sqlite3`
- `DISCORD_GUILD_IDS`: 測試伺服器 ID，多個用逗號分隔（選填）

儲存後使用 Manual Deploy → Clear build cache & deploy。
