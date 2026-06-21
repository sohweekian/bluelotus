# BlueLotus3 Sandbox Note

Created from `C:\bluelotus2` as an experimental workspace for multi-agent AI architecture work.

Isolation changes already applied:

- Hardcoded runtime paths were rewritten from `C:\bluelotus2` to `C:\bluelotus3`.
- `.env` now points `MYSQL_DATABASE` to `bluelotus3`.
- `.env` uses `AGENT_VERSION=bluelotus_v3_multiagency_experimental`.
- GitHub and Telegram publishing credentials were blanked to avoid accidental V2 dashboard or alert pollution.
- Old nested installer build/dist artifacts were removed from the V3 clone.

Important safety note:

- `moomoo_trader.py` exists because it was present in the raw V2 source folder, but the June 15 V2 installer excluded it.
- Multi-agent experiments should treat broker execution as disabled unless the CIO explicitly approves a separate execution sandbox.
- Keep the V2 doctrine intact: agents may analyze, critique, vote, and route recommendations, but they must not place trades.

Recommended next setup before running pipelines:

1. Create a separate MySQL database named `bluelotus3`.
2. Create a fresh `C:\bluelotus3\.venv`.
3. Run smoke checks from `C:\bluelotus3`, not `C:\bluelotus2`.
4. Only re-enable GitHub/Telegram publishing after a V3-specific dashboard/repo/channel has been chosen.
