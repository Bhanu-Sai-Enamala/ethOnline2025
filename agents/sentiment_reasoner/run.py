# run.py
import os
from dotenv import load_dotenv, find_dotenv

# Always try to load the *root* .env by searching upward from CWD
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)

from agent import agent  # noqa: E402

if __name__ == "__main__":
    print(f"[sentiment-reasoner] Address: {agent.address}")
    agent.run()