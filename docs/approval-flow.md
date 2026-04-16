# Board Dispatcher — Approval Flow (simplified)

High-level view of the three-phase lifecycle with approval gates.

```mermaid
flowchart LR
    START(["Label 'claudio'"]) --> ARCH

    subgraph ARCH["ARCHITECTURE"]
        direction TB
        A1{"Needs doc?"}
        A1 -->|"Needed"| A2["Write design doc"]
        A1 -->|"Exists / Not needed"| AG1
        A2 --> AG1
        AG1{{"Developer reviews"}}
        AG1 -.->|"retry"| A3["Improve doc"] -.-> AG1
    end

    ARCH -->|"lgtm"| PLAN

    subgraph PLAN["PLAN"]
        direction TB
        P1["Create implementation plan"] --> PG1{{"Developer reviews"}}
        PG1 -.->|"retry"| P2["Revise plan"] -.-> PG1
    end

    PLAN -->|"lgtm"| CODE

    subgraph CODE["CODE"]
        direction TB
        C1["Write code + open MR"] --> CG1{{"Developer reviews"}}
        CG1 -.->|"retry"| C2["Fix review feedback"] -.-> CG1
    end

    CODE -->|"lgtm"| DONE(["Done"])

    classDef agent fill:#0ea5e9,stroke:#0284c7,color:#fff
    classDef gate fill:#f59e0b,stroke:#d97706,color:#fff
    classDef start fill:#1e3a5f,stroke:#1e3a5f,color:#fff
    classDef done fill:#10b981,stroke:#059669,color:#fff
    classDef decision fill:#0d9488,stroke:#0f766e,color:#fff

    class A2,A3,P1,P2,C1,C2 agent
    class AG1,PG1,CG1 gate
    class START start
    class DONE done
    class A1 decision
```

**Legend:**
- Blue = AI agent executes
- Amber = Developer reviews (approval gate)
- Dotted arrows = retry loop (developer requests changes)

Human in the loop at every gate. System handles everything in between.
