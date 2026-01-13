import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stock_reporter import run  # noqa: E402


if __name__ == "__main__":
    config_path = ROOT / "config" / "subscriptions.json"
    run("tw", str(config_path))
