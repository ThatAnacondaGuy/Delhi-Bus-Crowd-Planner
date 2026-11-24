import duckdb


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open DuckDB (in-memory when path is None) pinned to Asia/Kolkata."""
    con = duckdb.connect(path if path is not None else ":memory:")
    con.execute("SET TimeZone='Asia/Kolkata'")
    return con
