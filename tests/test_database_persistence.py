"""Unit tests for SQLite database persistence, WAL mode, and connection lifecycle."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

from backend.data.storage import Database, get_db_file_path
from config.settings import Settings


def test_database_absolute_path_resolution() -> None:
    """Verify SQLite database URL resolves to canonical absolute paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        abs_target = str(Path(tmpdir) / "app" / "data" / "finova.db")
        settings = Settings(DATABASE_URL=f"sqlite:///{abs_target}")
        resolved = get_db_file_path(settings)

        assert Path(resolved).is_absolute()
        assert Path(resolved).name == "finova.db"


def test_database_parent_directory_creation() -> None:
    """Verify parent directory is created automatically if non-existent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_dir = Path(tmpdir) / "deep" / "nested" / "path"
        assert not nested_dir.exists()

        db_file = str(nested_dir / "test.db")
        settings = Settings(DATABASE_URL=f"sqlite:///{db_file}")
        resolved = get_db_file_path(settings)

        assert nested_dir.exists()
        assert Path(resolved).parent.is_dir()


def test_database_restart_persistence() -> None:
    """Verify records survive application restart across separate Database instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "restart_test.db")

        # Session 1: Create DB and insert record
        db1 = Database(db_path)
        with db1.connection() as conn:
            conn.execute(
                "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                ("0000320193", "AAPL", "Apple Inc.", "2026-01-01T00:00:00Z"),
            )

        # Reopen in Session 2
        db2 = Database(db_path)
        with db2.connection() as conn:
            row = conn.execute(
                "SELECT ticker, name FROM companies WHERE cik = ?", ("0000320193",)
            ).fetchone()
            assert row is not None
            assert row["ticker"] == "AAPL"
            assert row["name"] == "Apple Inc."


def test_database_transaction_rollback() -> None:
    """Verify failed transaction rolls back cleanly without persisting partial state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "rollback_test.db")
        db = Database(db_path)

        with db.connection() as conn:
            conn.execute(
                "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                ("0000789019", "MSFT", "Microsoft", "2026-01-01T00:00:00Z"),
            )

        # Attempt failing transaction
        with pytest.raises(RuntimeError):
            with db.connection() as conn:
                conn.execute(
                    "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                    ("0001045810", "NVDA", "NVIDIA", "2026-01-01T00:00:00Z"),
                )
                raise RuntimeError("Abort transaction midway")

        # Confirm NVDA was NOT committed, but MSFT remains intact
        with db.connection() as conn:
            msft = conn.execute(
                "SELECT name FROM companies WHERE ticker = 'MSFT'"
            ).fetchone()
            nvda = conn.execute(
                "SELECT name FROM companies WHERE ticker = 'NVDA'"
            ).fetchone()

            assert msft is not None
            assert nvda is None


def test_database_wal_mode_and_concurrent_reads() -> None:
    """Verify WAL mode is enabled and permits concurrent read operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "wal_test.db")
        settings = Settings(DATABASE_WAL_MODE=True, DATABASE_BUSY_TIMEOUT_MS=10000)
        db = Database(db_path, settings=settings)

        with db.connection() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert mode.upper() == "WAL"

            conn.execute(
                "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                ("0001318605", "TSLA", "Tesla", "2026-01-01T00:00:00Z"),
            )

        # Concurrent read execution
        read_results: list[str] = []

        def _reader() -> None:
            with db.connection() as conn:
                r = conn.execute(
                    "SELECT name FROM companies WHERE ticker = 'TSLA'"
                ).fetchone()
                if r:
                    read_results.append(r[0])

        threads = [threading.Thread(target=_reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(read_results) == 5
        assert all(n == "Tesla" for n in read_results)
