"""Tool registry for Build 3 - Build0-style analysis tools."""
from pathlib import Path
from typing import Any, Union

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats


def summarize_numeric(df: pd.DataFrame, columns: list[str] = None, **kwargs) -> dict[str, Any]:
    """Generate numeric summary statistics.
    
    Args:
        df: Input dataframe
        columns: List of numeric columns to summarize (default: all numeric)
        
    Returns:
        Dict with summary statistics
    """
    if columns is None:
        numeric_df = df.select_dtypes(include=[np.number])
    else:
        numeric_df = df[columns]
    
    summary = numeric_df.describe().to_dict()
    
    text_lines = ["=== Numeric Summary ==="]
    for col, stats_dict in summary.items():
        text_lines.append(f"\n{col}:")
        for stat, value in stats_dict.items():
            text_lines.append(f"  {stat}: {value:.4f}" if isinstance(value, float) else f"  {stat}: {value}")
    
    return {
        "text": "\n".join(text_lines),
        "summary": summary
    }


def summarize_categorical(df: pd.DataFrame, column: str = None, cat_cols: list[str] = None, **kwargs) -> dict[str, Any]:
    """Generate frequency tables for categorical columns.
    
    Args:
        df: Input dataframe
        column: Single column to summarize
        cat_cols: Multiple columns to summarize
        
    Returns:
        Dict with frequency tables
    """
    columns = []
    if column:
        columns = [column]
    elif cat_cols:
        columns = cat_cols
    else:
        columns = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    text_lines = ["=== Categorical Summary ==="]
    results = {}
    
    for col in columns:
        if col not in df.columns:
            continue
        value_counts = df[col].value_counts()
        results[col] = value_counts.to_dict()
        
        text_lines.append(f"\n{col}:")
        for val, count in value_counts.head(10).items():
            pct = 100 * count / len(df)
            text_lines.append(f"  {val}: {count} ({pct:.1f}%)")
    
    return {
        "text": "\n".join(text_lines),
        "frequencies": results
    }


def missingness_table(df: pd.DataFrame, **kwargs) -> dict[str, Any]:
    """Show missing value counts and percentages.
    
    Args:
        df: Input dataframe
        
    Returns:
        Dict with missingness info
    """
    missing = df.isnull().sum()
    missing_pct = 100 * missing / len(df)
    
    text_lines = ["=== Missingness Summary ==="]
    text_lines.append(f"Total rows: {len(df)}")
    text_lines.append("")
    
    for col in df.columns:
        if missing[col] > 0:
            text_lines.append(f"{col}: {missing[col]} missing ({missing_pct[col]:.2f}%)")
    
    if missing.sum() == 0:
        text_lines.append("No missing values found.")
    
    return {
        "text": "\n".join(text_lines),
        "missing_counts": missing.to_dict(),
        "missing_pcts": missing_pct.to_dict()
    }


def pearson_correlation(df: pd.DataFrame, x: str, y: str, **kwargs) -> dict[str, Any]:
    """Calculate Pearson correlation between two numeric columns.
    
    Args:
        df: Input dataframe
        x: First column name
        y: Second column name
        
    Returns:
        Dict with correlation results
    """
    corr, p_value = stats.pearsonr(df[x].dropna(), df[y].dropna())
    
    text = f"""=== Pearson Correlation ===
Variables: {x} vs {y}
Correlation coefficient: {corr:.4f}
P-value: {p_value:.4f}
Significance: {'Significant' if p_value < 0.05 else 'Not significant'} at α=0.05
"""
    
    return {
        "text": text,
        "correlation": corr,
        "p_value": p_value
    }


def plot_histograms(df: pd.DataFrame, numeric_cols: list[str], fig_dir: Path = None, **kwargs) -> dict[str, Any]:
    """Create histograms for numeric columns.
    
    Args:
        df: Input dataframe
        numeric_cols: List of numeric columns to plot
        fig_dir: Directory to save figures
        
    Returns:
        Dict with plot info
    """
    n_cols = len(numeric_cols)
    fig, axes = plt.subplots(1, n_cols, figsize=(5*n_cols, 4))
    if n_cols == 1:
        axes = [axes]
    
    for i, col in enumerate(numeric_cols):
        df[col].hist(ax=axes[i], bins=30, edgecolor='black')
        axes[i].set_title(f'{col} Distribution')
        axes[i].set_xlabel(col)
        axes[i].set_ylabel('Frequency')
    
    plt.tight_layout()
    
    artifact_paths = []
    if fig_dir:
        fig_path = fig_dir / "histograms.png"
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        artifact_paths.append(str(fig_path))
        plt.close()
    else:
        plt.show()
    
    return {
        "text": f"Histograms created for: {', '.join(numeric_cols)}",
        "artifact_paths": artifact_paths
    }


def plot_corr_heatmap(df: pd.DataFrame, fig_dir: Path = None, **kwargs) -> dict[str, Any]:
    """Create correlation heatmap for numeric columns.
    
    Args:
        df: Input dataframe
        fig_dir: Directory to save figures
        
    Returns:
        Dict with heatmap info
    """
    numeric_df = df.select_dtypes(include=[np.number])
    corr_matrix = numeric_df.corr()
    
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, 
                square=True, ax=ax, fmt='.2f')
    ax.set_title('Correlation Heatmap')
    
    artifact_paths = []
    if fig_dir:
        fig_path = fig_dir / "correlation_heatmap.png"
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        artifact_paths.append(str(fig_path))
        plt.close()
    else:
        plt.show()
    
    return {
        "text": "Correlation heatmap created for numeric variables",
        "artifact_paths": artifact_paths
    }


def ttest_by_group(df: pd.DataFrame, numeric_col: str, group_col: str, **kwargs) -> dict[str, Any]:
    """Perform t-test comparing numeric variable between two groups.
    
    Args:
        df: Input dataframe
        numeric_col: Numeric column to test
        group_col: Binary grouping column
        
    Returns:
        Dict with t-test results
    """
    groups = df[group_col].unique()
    if len(groups) != 2:
        return {
            "text": f"Error: {group_col} must have exactly 2 groups, found {len(groups)}"
        }
    
    group1 = df[df[group_col] == groups[0]][numeric_col].dropna()
    group2 = df[df[group_col] == groups[1]][numeric_col].dropna()
    
    t_stat, p_value = stats.ttest_ind(group1, group2)
    
    text = f"""=== T-Test: {numeric_col} by {group_col} ===
Group 1 ({groups[0]}): n={len(group1)}, mean={group1.mean():.4f}, std={group1.std():.4f}
Group 2 ({groups[1]}): n={len(group2)}, mean={group2.mean():.4f}, std={group2.std():.4f}
T-statistic: {t_stat:.4f}
P-value: {p_value:.4f}
Significance: {'Significant' if p_value < 0.05 else 'Not significant'} at α=0.05
"""
    
    return {
        "text": text,
        "t_statistic": t_stat,
        "p_value": p_value
    }


# Tool registry - used by router
TOOLS = {
    "summarize_numeric": summarize_numeric,
    "summarize_categorical": summarize_categorical,
    "missingness_table": missingness_table,
    "pearson_correlation": pearson_correlation,
    "plot_histograms": plot_histograms,
    "plot_corr_heatmap": plot_corr_heatmap,
    "ttest_by_group": ttest_by_group,
}

# Tool descriptions for router
TOOL_DESCRIPTIONS = {
    "summarize_numeric": "Summary statistics (mean, std, min, max, quartiles) for numeric columns",
    "summarize_categorical": "Frequency tables for categorical columns",
    "missingness_table": "Count and percentage of missing values per column",
    "pearson_correlation": "Pearson correlation coefficient between two numeric variables",
    "plot_histograms": "Histogram visualizations for numeric variables",
    "plot_corr_heatmap": "Heatmap visualization of correlations between numeric variables",
    "ttest_by_group": "T-test comparing a numeric variable between two groups",
}
