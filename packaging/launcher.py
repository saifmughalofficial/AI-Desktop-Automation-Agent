"""PyInstaller entry point: runs the bundled Streamlit app on the local port."""
import os
import sys
from pathlib import Path

base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
os.chdir(base)
sys.path.insert(0, str(base))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
