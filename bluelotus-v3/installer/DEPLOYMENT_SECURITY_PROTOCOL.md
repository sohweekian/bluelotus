# BlueLotus V2 Deployment Security Protocol

This installer is designed for research, intelligence extraction, reporting, and archive generation.

## Broker Safety Doctrine

Allowed:

- Moomoo quote snapshots through `OpenQuoteContext.get_market_snapshot`.
- Moomoo historical bars through quote/history APIs.
- Moomoo read-only portfolio extraction through:
  - `OpenSecTradeContext.position_list_query`
  - `OpenSecTradeContext.accinfo_query`

Not allowed in this deployment:

- `unlock_trade`
- `place_order`
- `modify_order`
- `cancel_order`
- working-order setup
- broker order routing
- storage of Moomoo trade password

Execution authority remains with the CIO.

## Secrets Handling

- The package includes `.env.template`, not `.env`.
- Completed `.env` files must be created privately for each machine.
- Do not commit or share completed `.env` files.
- Do not place trade passwords in `.env`.

## Database Handling

- The package includes schema only.
- It does not include production rows.
- It does not include private portfolio history.
- It does not include reports or archive snapshots unless generated locally after install.

## Package Exclusions

The build script excludes:

- `.env`
- Python cache files
- runtime outputs under `data`, `logs`, `reports`, and `temp`
- archive/temp development folders
- `moomoo_trader.py` legacy order helper

## Validation

After installation:

```powershell
C:\bluelotus3\.venv\Scripts\python.exe <installer>\scripts\validate_environment.py --root C:\bluelotus3
```

After Moomoo OpenD is running:

```powershell
C:\bluelotus3\.venv\Scripts\python.exe <installer>\scripts\validate_environment.py --root C:\bluelotus3 --check-moomoo
```

The validator scans the installed runner for execution terms and confirms the runner is the read-only production pipeline.

