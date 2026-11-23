import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
principal = importlib.import_module("scripts.freios.principal")

if __name__ == "__main__":
    sys.exit(principal.main())
