"""Shared pytest configuration for the TCD test suite."""

import sys
from pathlib import Path

# Add the project root to sys.path so top-level packages such as benchmark/
# are importable in tests. The project root is the parent of this tests/ dir.
sys.path.insert(0, str(Path(__file__).parent.parent))