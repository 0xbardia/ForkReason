import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT / "apps" / "api"))
