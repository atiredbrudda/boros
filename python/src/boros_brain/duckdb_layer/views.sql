-- INFRA-04 — Parquet + SQLite analytical views.
-- Path placeholder {parquet_root} is substituted by setup.py before execute.
-- All views are read-only; DuckDB enforces via the sqlite_scanner READ_ONLY
-- attach mode + parquet-file immutability.
--
-- Views are registered lazily: when a subdirectory has no .parquet files the
-- corresponding view is replaced with a zero-row stub (see setup.py).

CREATE OR REPLACE VIEW market_trades AS
SELECT * FROM read_parquet('{parquet_root}/market_trades/**/*.parquet', hive_partitioning=true);

CREATE OR REPLACE VIEW order_book_raw AS
SELECT * FROM read_parquet('{parquet_root}/order_book_raw/**/*.parquet', hive_partitioning=true);

CREATE OR REPLACE VIEW order_book_combined AS
SELECT * FROM read_parquet('{parquet_root}/order_book_combined/**/*.parquet', hive_partitioning=true);

CREATE OR REPLACE VIEW underlying_apr AS
SELECT * FROM read_parquet('{parquet_root}/underlying_apr/**/*.parquet', hive_partitioning=true);

CREATE OR REPLACE VIEW market_data AS
SELECT * FROM read_parquet('{parquet_root}/market_data/**/*.parquet', hive_partitioning=true);

CREATE OR REPLACE VIEW settlement AS
SELECT * FROM read_parquet('{parquet_root}/settlement/**/*.parquet', hive_partitioning=true);
