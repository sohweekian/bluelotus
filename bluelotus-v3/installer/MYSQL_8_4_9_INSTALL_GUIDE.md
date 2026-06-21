# MySQL 8.4.9 LTS Installation Guide For BlueLotus V2

BlueLotus V2 production reference database:

- Product: MySQL Community Server
- Version: `8.4.9`
- Platform: Win64
- Database name: `bluelotus2`
- Character set: `utf8mb4`
- Collation: `utf8mb4_unicode_ci`
- Current production table count: `44`

Official references:

- MySQL Community Server 8.4 download page: <https://dev.mysql.com/downloads/mysql/8.4.html>
- MySQL 8.4 Windows package guidance: <https://docs.oracle.com/cd/E17952_01/mysql-8.4-en/windows-choosing-package.html>

The official MySQL download page lists `MySQL Community Server 8.4.9 LTS` and the Windows MSI package `mysql-8.4.9-winx64.msi`.

## Recommended Install Method

Use the Windows MSI package:

```text
mysql-8.4.9-winx64.msi
```

The MSI includes MySQL Server and MySQL Configurator, which is the easiest path for normal Windows machines.

## Install Steps

1. Download MySQL Community Server `8.4.9 LTS`.

   Go to:

   ```text
   https://dev.mysql.com/downloads/mysql/8.4.html
   ```

   Select:

   ```text
   Operating System: Microsoft Windows
   OS Version: Windows (x86, 64-bit)
   Package: Windows (x86, 64-bit), MSI Installer
   File: mysql-8.4.9-winx64.msi
   ```

2. Run the MSI as Administrator.

3. Choose one of these install profiles:

   ```text
   Server Only
   ```

   or:

   ```text
   Developer Default
   ```

   `Server Only` is enough for BlueLotus. `Developer Default` is useful if you also want MySQL Workbench.

4. Configure MySQL Server:

   ```text
   Type: Standalone MySQL Server
   Port: 3306
   Authentication: Strong Password Encryption
   Windows Service: enabled
   Start at system startup: enabled
   Service name: MySQL84 or MySQL
   ```

5. Set and save the root password privately.

6. After installation, confirm the service is running:

   ```powershell
   Get-Service *mysql*
   ```

7. Install BlueLotus V2 and initialize the database:

   ```powershell
   cd <extracted BlueLotus installer folder>
   .\Install-BlueLotusV2.ps1 `
     -InitializeDatabase `
     -MySQLAdminUser root `
     -MySQLAdminPassword "ROOT_PASSWORD" `
     -AppMySQLUser bluelotus_app `
     -AppMySQLPassword "APP_PASSWORD"
   ```

8. Confirm schema:

   ```powershell
   C:\bluelotus3\.venv\Scripts\python.exe .\scripts\validate_environment.py --root C:\bluelotus3
   ```

Expected validation:

```text
MySQL connected: 8.4.9
Schema table count: 44
Raw archive immutability triggers present: 2
```

## Manual Database Creation Alternative

If you prefer to create the database and user yourself, use equivalent SQL:

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
schema\bluelotus2_schema_mysql_8_4_9.sql
```

The Python initializer is preferred because it does not require `mysql.exe` to be on PATH.

## Important Notes

- Do not use MariaDB for the production reference install.
- Do not use MySQL 5.7 or 8.0 for the reference install.
- MySQL 8.4.9 is the documented production match.
- The installer applies schema only, not private BlueLotus production data.

