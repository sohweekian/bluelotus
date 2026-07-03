# BlueLotus V2 macOS Deployment Security Protocol

This installer is for research, data collection, reporting, and archive generation.

## Broker Safety Doctrine

Allowed:

- Moomoo quote snapshots through `OpenQuoteContext.get_market_snapshot`.
- Moomoo historical bars through quote/history APIs.
- Moomoo read-only portfolio extraction through:
  - `OpenSecTradeContext.position_list_query`
  - `OpenSecTradeContext.accinfo_query`

Not allowed:

- `unlock_trade`
- `place_order`
- `modify_order`
- `cancel_order`
- working-order setup
- broker order routing
- storing a Moomoo trade password

Execution authority remains with the CIO.

## Secrets Handling

- The package includes `.env.template`, not `.env`.
- Completed `.env` files must be created privately for each Mac.
- Do not commit, email, or share completed `.env` files.
- Do not place Moomoo trade passwords in `.env`.

## Database Handling

- The package includes schema only.
- It does not include production rows.
- It does not include portfolio history.
- It does not include generated reports or archive snapshots.

## Package Exclusions

The build script excludes:

- `.env`
- Python cache files
- runtime JSON
- generated reports
- Excel/Word output files
- archive/temp development folders
- `moomoo_trader.py` legacy order helper

## Validation

After installation:

```bash
~/bluelotus2/.venv/bin/python <installer>/scripts/validate_environment_macos.py \
  --root "$HOME/bluelotus2"
```

After Moomoo OpenD is running:

```bash
~/bluelotus2/.venv/bin/python <installer>/scripts/validate_environment_macos.py \
  --root "$HOME/bluelotus2" \
  --check-moomoo
```
