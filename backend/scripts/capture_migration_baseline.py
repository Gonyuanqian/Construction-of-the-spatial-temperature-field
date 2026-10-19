"""采集迁移基线与只读模型备份，数据仅写入被 Git 忽略的本机目录。

从仓库根目录运行：
    python backend/scripts/capture_migration_baseline.py --include-model-store --export-contracts

默认不提交训练、不切换模型、不改变当前数据集、不推进实时帧。
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[2]


def _json_default(value):
    if isinstance(value, bytes):
        return {"__type__": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (datetime, date)):
        return {"__type__": type(value).__name__, "iso": value.isoformat()}
    raise TypeError(f"Unsupported backup value: {type(value).__name__}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                               default=_json_default) + "\n", encoding="utf-8")


def _get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urlopen(base.rstrip("/") + path, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _export_contracts(schema: dict) -> int:
    routes = []
    for path, methods in sorted(schema["paths"].items()):
        if not path.startswith("/api/"):
            continue
        for method in sorted(methods):
            if method not in {"get", "post", "delete"}:
                continue
            compute = (path.startswith("/api/field/") and path != "/api/field/arch"
                       or path == "/api/live/prepare"
                       or path.startswith("/api/live/frame/")
                       or path.startswith("/api/live/volume/")
                       or path == "/api/calibration/diagnostics"
                       or path == "/api/models" and method == "post")
            routes.append({"method": method.upper(), "path": path, "compute": compute})
    _write_json(PROJECT / "docs/development/contracts/legacy-openapi.json", schema)
    _write_json(PROJECT / "backend-java/src/main/resources/legacy-api-routes.json", {
        "source": "docs/development/contracts/legacy-openapi.json",
        "api_version": schema["info"]["version"], "routes": routes,
    })
    return len(routes)


def _backup_models(destination: Path) -> int:
    import pymysql
    from pymysql.cursors import DictCursor

    conn = pymysql.connect(
        host=os.environ.get("TFIELD_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("TFIELD_MYSQL_PORT", "3306")),
        user=os.environ.get("TFIELD_MYSQL_USER", "root"),
        password=os.environ.get("TFIELD_MYSQL_PASSWORD", "123456"),
        database=os.environ.get("TFIELD_MYSQL_DB", "tfield_models"),
        charset="utf8mb4", cursorclass=DictCursor,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SHOW CREATE TABLE model")
            ddl = cursor.fetchone()["Create Table"]
            cursor.execute("SELECT * FROM model ORDER BY id")
            rows = cursor.fetchall()
            registry = []
            for table in ("dataset_record", "training_job", "live_session", "live_operation",
                          "workspace_context", "tfield_java_schema_history"):
                cursor.execute("SHOW TABLES LIKE %s", (table,))
                if cursor.fetchone() is None:
                    continue
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                table_ddl = cursor.fetchone()["Create Table"]
                cursor.execute(f"SHOW COLUMNS FROM `{table}`")
                generated = [row["Field"] for row in cursor.fetchall()
                             if any(kind in row["Extra"].upper()
                                    for kind in ("VIRTUAL GENERATED", "STORED GENERATED"))]
                order = "installed_rank" if table == "tfield_java_schema_history" else "id"
                cursor.execute(f"SELECT * FROM `{table}` ORDER BY `{order}`")
                registry.append({"table": table, "create_table_sql": table_ddl,
                                 "rows": cursor.fetchall(), "generated_columns": generated})
        _write_json(destination / "model-store.json", {
            "format_version": 1,
            "database": os.environ.get("TFIELD_MYSQL_DB", "tfield_models"),
            "table": "model", "create_table_sql": ddl, "rows": rows,
        })
        # 标准 SQL 可恢复到新建的空库，保留原 ID、JSON 和二进制产物。
        # 字符串使用 UTF-8 十六进制，避免恢复端转义模式影响内容。
        def literal(value):
            if isinstance(value, bytes):
                return "X'" + value.hex() + "'"
            if isinstance(value, str):
                return "CONVERT(X'" + value.encode("utf-8").hex() + "' USING utf8mb4)"
            return conn.escape(value)

        sql = ["-- Restore into a NEW EMPTY database; do not overwrite the active model store.",
               "SET NAMES utf8mb4;", "SET time_zone = '+00:00';", ddl + ";", "START TRANSACTION;"]
        for row in rows:
            columns = ", ".join("`" + name.replace("`", "``") + "`" for name in row)
            values = ", ".join(literal(value) for value in row.values())
            sql.append(f"INSERT INTO `model` ({columns}) VALUES ({values});")
        sql.append("COMMIT;")
        (destination / "model-store.sql").write_text("\n".join(sql) + "\n", encoding="utf-8")
        if registry:
            _write_json(destination / "dataset-workspace-store.json", {
                "format_version": 1, "tables": registry,
            })
            registry_sql = ["-- Restore into the same NEW EMPTY database as model-store.sql.",
                            "SET NAMES utf8mb4;", "SET time_zone = '+00:00';"]
            registry_sql.extend(table["create_table_sql"] + ";" for table in registry)
            registry_sql.append("START TRANSACTION;")
            for table in registry:
                for row in table["rows"]:
                    row = {key: value for key, value in row.items() if key not in table["generated_columns"]}
                    columns = ", ".join("`" + name.replace("`", "``") + "`" for name in row)
                    values = ", ".join(literal(value) for value in row.values())
                    registry_sql.append(f"INSERT INTO `{table['table']}` ({columns}) VALUES ({values});")
            registry_sql.append("COMMIT;")
            (destination / "dataset-workspace-store.sql").write_text(
                "\n".join(registry_sql) + "\n", encoding="utf-8")
        return len(rows)
    finally:
        conn.rollback()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8503")
    parser.add_argument("--business-api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--include-model-store", action="store_true")
    parser.add_argument("--export-contracts", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S-%f")
    destination = PROJECT / ".local/migration" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    status, raw = _get(args.api_url, "/openapi.json")
    if status != 200:
        raise RuntimeError(f"OpenAPI request failed: HTTP {status}")
    schema = json.loads(raw)
    _write_json(destination / "openapi.json", schema)
    snapshot = {}
    for path in ("/api/health", "/api/models", "/api/dataset", "/api/field/arch", "/api/live/status"):
        code, body = _get(args.api_url, path)
        snapshot[path] = {"status": code, "body": json.loads(body)}
    _write_json(destination / "responses.json", snapshot)
    business_snapshot = {}
    for path in ("/ops/health", "/ops/info", "/api/dataset", "/api/datasets",
                 "/api/workspaces/default", "/api/models", "/api/calibration", "/api/live/status"):
        try:
            code, body = _get(args.business_api_url, path)
            business_snapshot[path] = {"status": code, "body": json.loads(body)}
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            business_snapshot[path] = {"unavailable": type(exc).__name__}
    _write_json(destination / "business-responses.json", business_snapshot)
    files = []
    config = PROJECT / "backend/configs"
    candidates = {*config.rglob("*.xlsx"), *config.glob("bundle_*.json"),
                  *(PROJECT / "backend").glob("*.xlsx"),
                  *(p for folder in ("training-jobs", "live-sessions")
                    for p in (config / folder).rglob("*") if p.is_file())}
    for source in sorted(candidates):
        relative = source.relative_to(PROJECT)
        target = destination / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append({"path": relative.as_posix(), "size": source.stat().st_size,
                      "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    model_count = _backup_models(destination) if args.include_model_store else None
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    _write_json(destination / "manifest.json", {
        "format_version": 1, "code_commit": commit, "api_url": args.api_url,
        "python": sys.version, "model_rows": model_count, "files": files,
        "note": "Worktree may contain changes; inspect git diff when restoring.",
    })
    packages = sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions()
                      if d.metadata.get("Name"))
    (destination / "python-packages.txt").write_text("\n".join(packages) + "\n", encoding="utf-8")
    if args.export_contracts:
        print(f"Exported compatible API routes: {_export_contracts(schema)}")
    print(f"Local baseline: {destination}")
    print(f"Copied files: {len(files)}; model rows: {model_count}")


if __name__ == "__main__":
    main()
