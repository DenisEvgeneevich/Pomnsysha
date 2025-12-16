import os
import sys
import threading
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.telegram_bot import run_bot

if __name__ == "__main__":
    run_bot()
