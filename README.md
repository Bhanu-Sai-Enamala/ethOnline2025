flowchart LR
  subgraph Client["Frontend (dApp / Web UI)"]
    UI[Wallet UI\n+ Vacation Toggle + Balances Display]
  end

  subgraph Backend["Render.com Web Service"]
    direction TB
    REST[Rebalance Port Agent (REST)\n(uAgents @ PORT=8011)]
    Data[Local JSON Storage:\nvacation_users.json\nrebalance_latest.json\nrebalance_preview.json]
    Env[.env Config:\nBALANCER_AGENT_ADDRESS\nPORT=8011\nUSE_MAILBOX=true]
    Mailbox[(uAgents Mailbox)]
  end

  subgraph Agents["Agent Network"]
    direction TB
    Balancer[Balancer / Planner Agent\nHandles allocation + swaps]
    Reasoner[Sentiment Reasoner Agent\n10-coin risk + regime engine]
  end

  UI -- "REST API calls" --> REST
  REST --> Data
  REST --> Mailbox
  Mailbox --> Balancer
  Balancer --> Reasoner
  Reasoner --> Balancer
  Balancer --> REST

  classDef box fill:#0b5,stroke:#0a4,stroke-width:1,color:#fff;
  class REST,Balancer,Reasoner box;