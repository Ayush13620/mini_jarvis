"""Compatibility wrapper for the root Mini Jarvis server.

The canonical implementation lives at ../assistant_server.py.  Keeping this
thin wrapper avoids duplicate server code while preserving older launch paths.
"""

from pathlib import Path
import runpy


ROOT_SERVER = Path(__file__).resolve().parents[1] / "assistant_server.py"


if __name__ == "__main__":
    runpy.run_path(str(ROOT_SERVER), run_name="__main__")
