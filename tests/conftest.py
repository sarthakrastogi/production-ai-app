import sys
import os
from pathlib import Path

repo_root = Path(__file__).parent.parent

# Make `from app.X import Y` work by creating a symlink or using path tricks.
# The repo root contains config.py, graph/, etc. — it IS the app package.
# We add repo_root.parent to sys.path so Python finds `production-ai-app` as a dir,
# but since it's not named `app`, we also create a namespace mapping.
sys.path.insert(0, str(repo_root))

# Patch: make `app` resolve to the repo root package
import importlib
import types

if "app" not in sys.modules:
    app_module = types.ModuleType("app")
    app_module.__path__ = [str(repo_root)]
    app_module.__file__ = str(repo_root / "__init__.py")
    sys.modules["app"] = app_module
