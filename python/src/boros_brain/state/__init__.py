"""SQLite WAL state spine — INFRA-03.

Layout:
  db.py              — WAL connection helpers + chmod 600 + PRAGMA foreign_keys=ON
  schemas.sql        — canonical 8-table DDL (source of truth)
  writers/           — one module per table; the ONLY place with write SQL for that table
  migrations/        — Alembic; version 0001 replays schemas.sql

Single-writer-per-table discipline is enforced by scripts/sqlite_writer_lint.py
(greps for INSERT/UPDATE outside the designated owner file).
"""
