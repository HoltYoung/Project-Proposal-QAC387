"""Data utilities for Build 3."""
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dirs(report_dir: Path) -> None:
    """Create report directories if they don't exist."""
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "tool_outputs").mkdir(exist_ok=True)
    (report_dir / "tool_figures").mkdir(exist_ok=True)


def read_data(data_path: Path) -> pd.DataFrame:
    """Read CSV data file."""
    df = pd.read_csv(data_path)
    return df


def basic_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Generate basic dataset profile."""
    return {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
    }
