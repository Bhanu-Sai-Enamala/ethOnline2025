ethOnline2025/
├── README.md
├── requirements.txt              # root-level aggregator (pulls both subprojects)
├── run.sh                        # one-command setup + run script
├── .gitignore
│
├── scripts/
│   ├── bootstrap.sh              # creates venv + installs all deps
│   ├── run_local.sh              # runs reasoner + backend together
│   └── test_curl.sh              # optional quick test for rebalance API
│
├── agents/
│   └── sentiment_reasoner/
│       ├── .env.example
│       ├── .env                  # (ignored)
│       ├── requirements.txt
│       ├── run.py
│       ├── agent.py
│       ├── models.py
│       ├── rules/
│       │   └── rebalance_rules.metta
│       ├── knowledge/            # optional if dynamic RAG modules exist
│       │   ├── __init__.py
│       │   └── knowledge.py
│       └── venv/                 # ❌ ignored — judges use root venv
│
├── backend/
│   └── rebalance_api/
│       ├── .env.example
│       ├── .env                  # (ignored)
│       ├── requirements.txt
│       ├── run.py
│       ├── port_agent.py
│       ├── rebalance_models.py
│       └── app/
│           ├── __init__.py
│           ├── data/
│           │   └── rebalance_latest.json
│           └── __pycache__/      # ❌ ignored
│
└── venv/                         # root virtual environment (auto-created)