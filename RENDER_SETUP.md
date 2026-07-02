# Render 部署設定

在 Render 的 Settings → Build & Deploy 填入：

- Runtime: Python 3
- Instance Type: Free
- Build Command: `python -m pip install --upgrade pip && python -m pip install .`
- Start Command: `python start.py`
- Health Check Path: `/health`

不要在 Start Command 輸入 Dockerfile 語法，例如 `CMD ["reference-bot"]`。

Environment：

- `DISCORD_TOKEN`: Discord Bot Token
- `DATABASE_PATH`: `data/episodes.sqlite3`
- `OPENAI_API_KEY`: 讓 `/ask` 使用 OpenAI 整理回答；沒有設定時會退回保守搜尋結果
- `OPENAI_ASK_MODEL`: `gpt-4.1-mini`
- `DISCORD_GUILD_IDS`: 要立即出現 slash commands 的伺服器 ID，多個用逗號分隔。例如 `引書店伺服器ID,私人伺服器ID`

儲存後使用 Manual Deploy → Clear build cache & deploy。

如果 bot 在線但 `/ask` 沒出現，最常見原因是 `DISCORD_GUILD_IDS` 沒有包含那個 Discord server。加入伺服器 ID 後重新 deploy，log 應該會出現 `Synced slash commands to guild ...`。
如果你已經把多個 ID 填在舊欄位 `DISCORD_GUILD_ID`，也可以先保留；新版程式會接受逗號分隔。不過 Render 上建議改成 `DISCORD_GUILD_IDS`，避免未來混淆。

## 免費 Keepalive

這個 repo 有 `.github/workflows/render-keepalive.yml`，會每 10 分鐘打一次：

```text
https://reference-podcast-discord-bot-l4bv.onrender.com/health
```

如果 Render 服務名稱不同，請在 GitHub repo 的 Settings → Secrets and variables → Actions → Variables 新增：

- `RENDER_KEEPALIVE_URL`: `https://你的-render-service.onrender.com/health`

這是省錢測試方案，不能保證像付費 instance 一樣常駐；Render 仍可能因用量、平台維護或 Free 限制重啟或暫停。
