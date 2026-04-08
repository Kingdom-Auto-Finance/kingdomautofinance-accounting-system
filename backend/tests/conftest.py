"""Shared pytest fixtures.

Provides a ``SupabaseShim`` that implements just enough of the Supabase Python
client API to let ``credit_report_service`` talk to a local Postgres database
during integration tests. This lets us run the real service against the real
migration SQL without needing a live Supabase instance.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import pytest

# Make the backend app importable when running pytest from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND = _REPO_ROOT / "backend"
for p in (str(_BACKEND), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Stub the ``supabase`` package so app.db.supabase_client can import cleanly
# under test. The real client is replaced by SupabaseShim in fixtures.
if "supabase" not in sys.modules:
    _stub = types.ModuleType("supabase")
    _stub.create_client = lambda *a, **k: None
    _stub.Client = type("Client", (), {})
    sys.modules["supabase"] = _stub


# Connection string pointing at the test Postgres database.
TEST_DSN = os.environ.get(
    "KAF_TEST_DSN",
    "host=localhost port=5432 dbname=kaf_test user=kaf password=kaf",
)


def _get_conn():
    return psycopg2.connect(TEST_DSN)


# ─── SupabaseShim ────────────────────────────────────────────────────────────
class _Result:
    def __init__(self, data: List[Dict[str, Any]], count: Optional[int] = None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, conn, table: str):
        self._conn = conn
        self._table = table
        self._op: Optional[str] = None  # 'select', 'insert', 'update', 'delete'
        self._select_cols: str = "*"
        self._filters: List[Tuple[str, str, Any]] = []  # (col, op, val)
        self._or_clauses: List[str] = []
        self._order: List[Tuple[str, bool]] = []  # (col, desc)
        self._limit_n: Optional[int] = None
        self._range: Optional[Tuple[int, int]] = None
        self._single: bool = False
        self._count_mode: Optional[str] = None
        self._insert_rows: Optional[List[Dict[str, Any]]] = None
        self._update_vals: Optional[Dict[str, Any]] = None

    # ── Builder methods ────────────────────────────────────────────────
    def select(self, cols: str = "*", count: Optional[str] = None):
        self._op = "select"
        self._select_cols = cols
        self._count_mode = count
        return self

    def insert(self, rows):
        self._op = "insert"
        if isinstance(rows, dict):
            rows = [rows]
        self._insert_rows = rows
        return self

    def update(self, values: Dict[str, Any]):
        self._op = "update"
        self._update_vals = values
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col: str, val: Any):
        self._filters.append((col, "=", val))
        return self

    def neq(self, col: str, val: Any):
        self._filters.append((col, "<>", val))
        return self

    def lt(self, col: str, val: Any):
        self._filters.append((col, "<", val))
        return self

    def lte(self, col: str, val: Any):
        self._filters.append((col, "<=", val))
        return self

    def gt(self, col: str, val: Any):
        self._filters.append((col, ">", val))
        return self

    def gte(self, col: str, val: Any):
        self._filters.append((col, ">=", val))
        return self

    def in_(self, col: str, values: List[Any]):
        self._filters.append((col, "IN", list(values)))
        return self

    def or_(self, clause: str):
        self._or_clauses.append(clause)
        return self

    def order(self, col: str, desc: bool = False):
        self._order.append((col, desc))
        return self

    def limit(self, n: int):
        self._limit_n = n
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    # ── Execution ──────────────────────────────────────────────────────
    def execute(self) -> _Result:
        if self._op == "select":
            return self._exec_select()
        if self._op == "insert":
            return self._exec_insert()
        if self._op == "update":
            return self._exec_update()
        if self._op == "delete":
            return self._exec_delete()
        raise RuntimeError(f"Unknown op {self._op}")

    def _build_where(self) -> Tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        for col, op, val in self._filters:
            if op == "IN":
                if not val:
                    clauses.append("FALSE")
                    continue
                placeholders = ",".join(["%s"] * len(val))
                clauses.append(f"{col} IN ({placeholders})")
                params.extend(val)
            else:
                clauses.append(f"{col} {op} %s")
                params.append(val)
        for raw in self._or_clauses:
            # Minimal or_() support: accept the two ilike clauses we actually use.
            # Example input: "deal_id.ilike.%q%,source_row->>clientName.ilike.%q%"
            # JSONB paths need their key wrapped in single quotes so PG does
            # not lowercase them: source_row->>clientName → source_row->>'clientName'.
            sub_clauses: List[str] = []
            for piece in raw.split(","):
                parts = piece.split(".", 2)
                if len(parts) != 3:
                    continue
                col, op_name, val = parts
                if "->>" in col:
                    base, key = col.split("->>", 1)
                    col_expr = f"{base}->>'{key}'"
                else:
                    col_expr = col
                if op_name == "ilike":
                    sub_clauses.append(f"{col_expr} ILIKE %s")
                    params.append(val)
                elif op_name == "eq":
                    sub_clauses.append(f"{col_expr} = %s")
                    params.append(val)
            if sub_clauses:
                clauses.append("(" + " OR ".join(sub_clauses) + ")")
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _jsonify_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DictRow with JSONB columns to plain dict."""
        out: Dict[str, Any] = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    def _exec_select(self) -> _Result:
        where, params = self._build_where()
        sql = f"SELECT {self._select_cols} FROM {self._table}{where}"
        if self._order:
            sql += " ORDER BY " + ", ".join(
                f"{c} {'DESC' if d else 'ASC'}" for c, d in self._order
            )
        if self._range:
            start, end = self._range
            sql += f" LIMIT {end - start + 1} OFFSET {start}"
        elif self._limit_n is not None:
            sql += f" LIMIT {self._limit_n}"

        count: Optional[int] = None
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if self._count_mode == "exact":
                count_sql = f"SELECT COUNT(*) AS c FROM {self._table}{where}"
                cur.execute(count_sql, params)
                count = cur.fetchone()["c"]
            cur.execute(sql, params)
            rows = [self._jsonify_row(r) for r in cur.fetchall()]

        if self._single:
            return _Result(data=rows[0] if rows else None, count=count)
        return _Result(data=rows, count=count)

    def _exec_insert(self) -> _Result:
        assert self._insert_rows is not None
        if not self._insert_rows:
            return _Result(data=[])

        inserted: List[Dict[str, Any]] = []
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for row in self._insert_rows:
                # Use each row's own keys so rows with heterogeneous shapes
                # (e.g. some with 'reason', some without) all round-trip.
                cols = list(row.keys())
                placeholders = ",".join(["%s"] * len(cols))
                sql = (
                    f"INSERT INTO {self._table} ({','.join(cols)}) "
                    f"VALUES ({placeholders}) RETURNING *"
                )
                values = []
                for c in cols:
                    v = row[c]
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v)
                    values.append(v)
                cur.execute(sql, values)
                inserted.append(self._jsonify_row(cur.fetchone()))
        self._conn.commit()
        return _Result(data=inserted)

    def _exec_update(self) -> _Result:
        assert self._update_vals is not None
        where, params = self._build_where()
        set_parts = []
        set_params = []
        for k, v in self._update_vals.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            set_parts.append(f"{k} = %s")
            set_params.append(v)
        sql = f"UPDATE {self._table} SET {','.join(set_parts)}{where} RETURNING *"
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, set_params + params)
            rows = [self._jsonify_row(r) for r in cur.fetchall()]
        self._conn.commit()
        return _Result(data=rows)

    def _exec_delete(self) -> _Result:
        where, params = self._build_where()
        sql = f"DELETE FROM {self._table}{where} RETURNING *"
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [self._jsonify_row(r) for r in cur.fetchall()]
        self._conn.commit()
        return _Result(data=rows)


class SupabaseShim:
    """Tiny drop-in replacement for the Supabase client, backed by psycopg2."""

    def __init__(self, conn):
        self._conn = conn

    def table(self, name: str) -> _Query:
        return _Query(self._conn, name)


# ─── Pytest fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def db_conn():
    """Open a shared psycopg2 connection to the test database."""
    conn = _get_conn()
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _clean_credit_report_tables(db_conn):
    """Truncate all credit_report_* tables before each test."""
    with db_conn.cursor() as cur:
        cur.execute(
            "TRUNCATE TABLE "
            "credit_report_validations, credit_report_run_items, "
            "credit_report_runs, credit_report_account_state, "
            "credit_report_uploads "
            "RESTART IDENTITY CASCADE"
        )
    db_conn.commit()
    yield


@pytest.fixture
def supabase_shim(db_conn, monkeypatch):
    """Patch get_supabase_client to return the shim."""
    shim = SupabaseShim(db_conn)
    from app.db import supabase_client

    monkeypatch.setattr(supabase_client, "get_supabase_client", lambda: shim)

    # The service imports get_supabase_client at module level via
    # ``from app.db.supabase_client import get_supabase_client``, so patch it
    # there too.
    from app.services import credit_report_service

    monkeypatch.setattr(credit_report_service, "get_supabase_client", lambda: shim)
    return shim
