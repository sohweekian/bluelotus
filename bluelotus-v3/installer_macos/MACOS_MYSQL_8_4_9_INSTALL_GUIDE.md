# MySQL 8.4.9 LTS Installation Guide For BlueLotus V2 macOS Collector

BlueLotus V2 production reference database:

- Product: MySQL Community Server
- Version: `8.4.9`
- Database name: `bluelotus2`
- Character set: `utf8mb4`
- Collation: `utf8mb4_unicode_ci`
- Required schema table count: `44`
- Required raw archive immutability triggers: `2`

Official references:

- MySQL Community Server 8.4 download page: <https://dev.mysql.com/downloads/mysql/8.4.html>
- MySQL 8.4 installing packages on macOS: <https://docs.oracle.com/cd/E17952_01/mysql-8.4-en/macos-installation-pkg.html>

## Recommended Method

Use Oracle's official macOS package for MySQL Community Server `8.4.9 LTS`.

Homebrew may install a newer patch version depending on when the formula updates. For exact match with the Windows production system, use the official Oracle package for `8.4.9`.

## Install Steps

1. Go to:

   ```text
   https://dev.mysql.com/downloads/mysql/8.4.html
   ```

2. Select:

   ```text
   Operating System: macOS
   Version: MySQL Community Server 8.4.9 LTS
   ```

3. Download the correct package for the Mac:

   - Apple Silicon: ARM64 package
   - Intel Mac: x86_64 package

4. Install the `.pkg`.

5. Start MySQL from System Settings or with the bundled service scripts.

6. Confirm version:

   ```bash
   mysql --version
   ```

   Expected:

   ```text
   8.4.9
   ```

7. Initialize BlueLotus schema through the macOS installer:

   ```bash
   bash install_bluelotus_v2_macos.sh \
     --init-db \
     --mysql-admin-user root \
     --mysql-admin-password "ROOT_PASSWORD" \
     --app-db-user bluelotus_app \
     --app-db-password "APP_PASSWORD"
   ```

8. Validate:

   ```bash
   ~/bluelotus2/.venv/bin/python scripts/validate_environment_macos.py \
     --root "$HOME/bluelotus2"
   ```

Expected:

```text
MySQL connected: 8.4.9
Schema table count: 44
Raw archive immutability triggers present: 2
```

## Manual Database Creation Alternative

```sql
CREATE DATABASE IF NOT EXISTS bluelotus2
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'bluelotus_app'@'localhost'
  IDENTIFIED BY 'APP_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX,
      REFERENCES, TRIGGER, EXECUTE
ON bluelotus2.*
TO 'bluelotus_app'@'localhost';

FLUSH PRIVILEGES;
```

Then apply:

```text
schema/bluelotus2_schema_mysql_8_4_9.sql
```

The Python initializer is preferred because it does not require the `mysql` CLI to be on PATH.

## Notes

- Do not use MariaDB for the reference collector.
- Do not use MySQL 5.7 or 8.0 for the institutional reference setup.
- MySQL `8.4.9` is the documented production match.
- The installer applies schema only, not private production rows.
