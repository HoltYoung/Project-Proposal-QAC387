# AGENTS.md - HypothesisLoop Project Guidelines

## Project Overview
HypothesisLoop is an LLM-powered iterative hypothesis-testing agent for data analysis. Built with Python, using Anthropic Claude, Langfuse for tracing, and standard data science libraries (pandas, scipy, sklearn).

## Build/Lint/Test Commands

### Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Unix/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running Tests
```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_analysis.py

# Run a single test function
pytest tests/test_analysis.py::test_hypothesis_generation

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run tests matching a pattern
pytest -k "test_hypothesis"
```

### Linting and Formatting
```bash
# Format code with black
black src/ tests/

# Check formatting without changes
black --check src/ tests/

# Sort imports
isort src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type checking
mypy src/

# Run all checks
black --check src/ tests/ && isort --check-only src/ tests/ && ruff check src/ tests/ && mypy src/
```

## Code Style Guidelines

### Imports
- Group imports: stdlib → third-party → local
- Use absolute imports within the project
- Sort alphabetically within groups
- Avoid wildcard imports (`from module import *`)

```python
# Standard library
import json
import os
from typing import Any, Optional

# Third-party
import pandas as pd
from anthropic import Anthropic

# Local modules
from hypothesis_loop.memory import TraceStore
from hypothesis_loop.utils import sanitize_code
```

### Formatting
- Line length: 100 characters max
- Use double quotes for strings
- Use trailing commas in multi-line structures
- 4 spaces for indentation

### Type Hints
- Use type hints for all function parameters and return values
- Use `Optional[X]` instead of `X | None` (Python < 3.10 compatibility)
- Use explicit `None` return type for procedures
- Import types from `typing` module

```python
def generate_hypothesis(
    dataset: pd.DataFrame,
    previous_results: list[dict[str, Any]],
    max_iterations: int = 5,
) -> Optional[dict[str, Any]]:
    ...
```

### Naming Conventions
- `snake_case` for functions, variables, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Private methods/attributes prefix with underscore: `_internal_method`
- Descriptive names over abbreviations

### Error Handling
- Use specific exceptions, not bare `except:`
- Log exceptions with context before re-raising
- Use custom exceptions for domain-specific errors
- Always clean up resources (use context managers)

```python
class HypothesisError(Exception):
    """Raised when hypothesis generation fails."""
    pass

class CodeExecutionError(Exception):
    """Raised when generated code fails to execute."""
    pass
```

### Documentation
- Docstrings for all public functions, classes, modules
- Use Google-style docstrings
- Include type information in docstrings if not using type hints

```python
def analyze_data(data: pd.DataFrame, target: str) -> dict[str, Any]:
    """Analyze dataset to find relationships with target variable.

    Args:
        data: Input dataset with features and target.
        target: Name of the target column to predict.

    Returns:
        Dictionary containing correlation scores and significance tests.

    Raises:
        ValueError: If target column not found in data.
    """
```

### LLM Integration Patterns
- Always sanitize generated code before execution
- Use structured JSON output for hypothesis generation
- Implement retry logic with exponential backoff
- Log all LLM interactions via Langfuse
- Cap iteration limits to prevent infinite loops

### Testing Guidelines
- Use `pytest` with fixtures for shared setup
- Mock external APIs (Anthropic, Langfuse) in unit tests
- Test edge cases: empty data, malformed hypotheses, code errors
- Use `tmp_path` fixture for file operations
- Keep tests fast and independent

### Logging Requirements
- **All operations must write to a log** - every function, class, and significant operation must have logging
- Use Python's `logging` module with appropriate log levels:
  - `DEBUG`: Detailed information for debugging
  - `INFO`: General execution flow (entry/exit points, key decisions)
  - `WARNING`: Unexpected but non-fatal issues
  - `ERROR`: Errors that affect functionality
  - `CRITICAL`: System-level failures
- Include contextual data: timestamps, function names, parameters (sanitized), and results
- Logs should be written to both console and file (`logs/app.log`)
- Example:
```python
import logging

logger = logging.getLogger(__name__)

def analyze_data(data: pd.DataFrame) -> dict[str, Any]:
    logger.info(f"Starting analysis on {len(data)} rows")
    try:
        result = _process_data(data)
        logger.info(f"Analysis complete: {len(result)} findings")
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise
```

### Security
- Sandboxed code execution only
- Restricted imports whitelist for generated code
- No hardcoded API keys in source
- Use environment variables for secrets
- Validate all user inputs
- Log all security-relevant events (authentication, authorization, data access)

### Project Structure
```
.
├── src/
│   └── hypothesis_loop/
│       ├── __init__.py
│       ├── agent.py          # Core analysis loop
│       ├── hypothesis.py     # Hypothesis generation
│       ├── executor.py       # Code sandboxing
│       ├── memory.py         # Trace storage
│       └── utils.py
├── tests/
│   ├── conftest.py
│   ├── test_agent.py
│   └── test_executor.py
├── data/                     # Sample datasets (gitignored)
├── notebooks/                # Exploration only
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Pre-commit Checklist
- [ ] All tests pass (`pytest`)
- [ ] Code formatted (`black`)
- [ ] Imports sorted (`isort`)
- [ ] No lint errors (`ruff`)
- [ ] Type checks pass (`mypy`)
- [ ] Docstrings complete
- [ ] No secrets committed

## Pre-merge Requirements (Before Pushing to Main)
- **Holistic Testing**: All components must be tested together in an integration test
- **Audit**: Review logs to ensure proper execution flow and no unexpected behavior
- **Manual Review**: Code reviewed by another team member
- **Integration Tests**: Run `pytest tests/integration/` to verify full workflow
- **Langfuse Traces**: Verify traces show expected hypothesis → experiment → evaluate → learn loop
- **Security Audit**: Check no secrets, proper input validation, sandboxed execution verified
