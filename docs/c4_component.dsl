workspace {

    model {
        # --- Users ---
        developer = person "Developer" "Creates tickets, reviews plans/docs/MRs via emoji reactions (✅/🔄)"

        # --- External Systems ---
        jiraCloud = softwareSystem "Jira Cloud" "Issue tracker — tickets, comments, emoji reactions, labels" "External"
        confluence = softwareSystem "Confluence" "Architecture design docs with inline comments" "External"
        gitlab = softwareSystem "GitLab" "Source control — repos, merge requests, pipelines" "External"
        claudeAPI = softwareSystem "Claude API" "Anthropic LLM via Agent SDK" "External"
        aiopsPlugin = softwareSystem "AIOps Plugin" "Skill prompts and reference docs — loaded via installed Claude Code plugin or local path" "External"

        # --- Monitoring Dashboard (separate system so it shows in context view) ---
        monitoringUI = softwareSystem "Monitoring Dashboard" "Real-time web UI — ticket states, agent logs, tool calls, cost tracking" "Dashboard"

        # --- Task Summoner ---
        boardDispatcher = softwareSystem "Task Summoner" "Autonomous SDLC orchestrator — polls Jira, spawns Claude agents through a deterministic state machine" {

            orchestrator = container "Orchestrator" "Polling loop — discovers tickets, dispatches state handlers, manages agent task lifecycle" "Python, asyncio"

            stateMachine = container "State Machine" "Deterministic transition table (13 states, 22 transitions) — LLM never decides flow" "Python" {
                transitionTable = component "Transition Table" "(state, trigger) → next_state" "Enum + dict"
                stateRegistry = component "State Registry" "TicketState → handler class" "dict"
                baseState = component "BaseState" "ABC — loads skills/docs, manages artifacts" "ABC"
                baseApproval = component "BaseApprovalState" "Reusable ✅/🔄 pattern" "ABC"
            }

            stateHandlers = container "State Handlers" "12 handler classes — one per lifecycle state" "Python" {
                queued = component "QueuedState" "Worktree + claim ticket" "Python"
                checkingDoc = component "CheckingDocState" "Checks if design doc exists/needed" "Python"
                creatingDoc = component "CreatingDocState" "/create-design skill" "Python"
                waitDocReview = component "WaitingDocReviewState" "✅/🔄 on doc" "BaseApprovalState"
                improvingDoc = component "ImprovingDocState" "Reads inline comments, fixes doc" "Python"
                planning = component "PlanningState" "/ticket-plan skill" "Python"
                waitPlanReview = component "WaitingPlanReviewState" "✅/🔄 on plan" "BaseApprovalState"
                implementing = component "ImplementingState" "/ticket-implement skill" "Python"
                waitMrReview = component "WaitingMrReviewState" "✅/🔄 on MR" "BaseApprovalState"
                fixingMr = component "FixingMrState" "Reads MR threads, fixes code" "Python"
                doneState = component "DoneState" "Moves ticket to Done" "Python"
                failedState = component "FailedState" "Terminal error" "Python"
            }

            agentLayer = container "Agent Provider Layer" "AgentProvider protocol + concrete adapters" "Python" {
                agentProtocol = component "AgentProvider" "Protocol: run(prompt, profile, working_dir) -> AgentResult" "Python"
                claudeCodeAdapter = component "ClaudeCodeAdapter" "Claude Agent SDK wrapper: options, env, plugins, event streaming" "async"
                pluginResolver = component "PluginResolver" "Strategy: installed (user settings) or local (explicit path)" "Python"
                codexAdapter = component "CodexAdapter" "Stub — coming soon" "Python"
            }

            trackerPkg = container "Jira Tracker" "acli CLI wrapper + reaction checker" "Python" {
                jiraClient = component "BoardProvider" "search, view, comment, transition, label" "asyncio"
                reactionChecker = component "ReactionChecker" "Polls emoji reactions via REST" "Python"
                adfHelper = component "ADF Helper" "ADF → plain text converter" "Python"
            }

            workspacePkg = container "Workspace Manager" "Git worktree lifecycle — one workspace per ticket" "Python, git"

            eventSystem = container "Event System" "Async pub/sub — EventBus + Pydantic event models" "Python, asyncio"

            apiServer = container "API Server" "FastAPI + SSE — feeds the Monitoring Dashboard" "FastAPI"

            corePkg = container "Core" "Domain models (Pydantic v2), config (YAML + .env), state persistence (JSON)" "Python, Pydantic"
        }

        # --- System Context relationships ---
        developer -> jiraCloud "Tags tickets 'task-summoner', reacts ✅/🔄"
        developer -> confluence "Reviews docs, inline comments"
        developer -> gitlab "Reviews MRs, thread comments"
        developer -> monitoringUI "Monitors agent progress" "HTTPS"

        boardDispatcher -> jiraCloud "Polls tickets, posts comments, reads reactions" "acli + REST"
        boardDispatcher -> confluence "Creates/updates design docs" "MCP Atlassian"
        boardDispatcher -> gitlab "Creates worktrees, pushes code, opens MRs" "git + glab"
        boardDispatcher -> claudeAPI "Spawns planning/implementation/review agents" "Agent SDK"
        boardDispatcher -> aiopsPlugin "Loads skill prompts — via installed plugin or local path (PluginResolver)" "Filesystem / User Settings"
        boardDispatcher -> monitoringUI "Streams real-time events" "SSE"

        # --- Container-level relationships ---
        orchestrator -> stateMachine "Resolves handler for state"
        orchestrator -> stateHandlers "Dispatches handle()"
        orchestrator -> agentLayer "Spawns agent tasks"
        orchestrator -> eventSystem "Emits lifecycle events"
        orchestrator -> corePkg "State persistence"
        orchestrator -> trackerPkg "State labels"

        stateHandlers -> agentLayer "Runs agents with skill prompts"
        stateHandlers -> trackerPkg "Comments, reactions"
        stateHandlers -> workspacePkg "Worktrees"
        stateHandlers -> corePkg "Artifacts"

        agentLayer -> claudeAPI "query() stream"
        agentLayer -> aiopsPlugin "Resolves plugin (installed or local)"
        agentLayer -> eventSystem "Agent events"

        trackerPkg -> jiraCloud "acli + REST"
        workspacePkg -> gitlab "git operations"

        eventSystem -> apiServer "Publishes events"
        apiServer -> monitoringUI "SSE stream"
        apiServer -> corePkg "Reads ticket state"
    }

    views {
        systemContext boardDispatcher "SystemContext" "Task Summoner and its external dependencies" {
            include *
            autoLayout tb
        }

        container boardDispatcher "Containers" "Internal architecture of Task Summoner" {
            include *
            autoLayout tb
        }

        component stateHandlers "StateHandlers" "All 12 lifecycle state handlers" {
            include *
            autoLayout lr
        }

        component agentLayer "AgentLayer" "Agent SDK integration layer" {
            include *
            autoLayout lr
        }

        component trackerPkg "Tracker" "Jira tracker internals" {
            include *
            autoLayout lr
        }

        styles {
            element "External" {
                background #6B7280
                color #ffffff
                shape RoundedBox
            }
            element "Dashboard" {
                background #10B981
                color #ffffff
                shape WebBrowser
            }
            element "Software System" {
                background #6B7280
                color #ffffff
            }
            element "Container" {
                background #2563EB
                color #ffffff
                shape RoundedBox
            }
            element "Component" {
                background #60A5FA
                color #000000
                shape RoundedBox
            }
            element "Person" {
                shape Person
                background #1E40AF
                color #ffffff
            }
        }
    }
}
