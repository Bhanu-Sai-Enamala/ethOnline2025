# run.py
import os
from dotenv import load_dotenv

# Load environment early so seed and mailbox are in place
load_dotenv()

from agent import agent  # noqa: E402

if __name__ == "__main__":
    print(f"[sentiment-reasoner] Address: {agent.address}")
    agent.run()