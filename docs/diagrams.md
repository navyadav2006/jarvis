# Jarvis — UML & Component Diagrams

Hand-authored Mermaid diagrams (no UML-generation tooling is installed
— see `docs/architecture.md`'s Phase 21 section for why), covering the
system's static structure. For *behavioral* diagrams (request/response
sequences), see the sequence diagrams already embedded in the relevant
phase sections of `docs/architecture.md` — this file is the static
counterpart: what depends on what, and each package's key classes.

## System component diagram

The layering rule that has held since Phase 2, verified by grep across
every `core/` file before this diagram was drawn (the only
`orchestrator` reference inside `core/` is a `TYPE_CHECKING`-only
annotation in `plugin_loader.py`, never a real runtime dependency):
`core/` never imports `orchestrator/`; `orchestrator/` depends on
`core/`, never the reverse; `main.py` is the only module allowed to
import every concrete type in the system.

```mermaid
graph TD
    subgraph API["src/jarvis/api/"]
        app[app.py]
    end

    subgraph Orchestrator["src/jarvis/orchestrator/"]
        orch[orchestrator.py]
        ports[ports.py]
        adapters["*_adapter.py<br/>(execution, memory, workflow)"]
        registry[capability_registry.py]
    end

    subgraph Plugins["src/jarvis/plugins/"]
        base[base.py]
        examples[examples/*]
    end

    subgraph Core["src/jarvis/core/"]
        config[config/]
        events[events.py]
        container[container.py]
        security[security/]
        execution[execution/]
        workflow[workflow/]
        planning[planning/]
        memory[memory/]
        vault[vault/]
        cowork[cowork/]
        filesystem[filesystem/]
        browser[browser/]
        speech[speech/]
        voice[voice/]
        plugin_loader[plugin_loader.py]
    end

    main[main.py — the one place<br/>allowed to know every<br/>concrete type]

    main --> API
    main --> Orchestrator
    main --> Core
    main --> Plugins

    API --> Orchestrator
    Orchestrator --> Core
    Plugins -.->|structural only,<br/>no import| Orchestrator
    adapters --> execution
    adapters --> memory
    adapters --> workflow
    workflow --> security
    execution --> security

    classDef core fill:#1f6feb,color:#fff
    classDef orch fill:#8957e5,color:#fff
    class config,events,container,security,execution,workflow,planning,memory,vault,cowork,filesystem,browser,speech,voice,plugin_loader core
    class orch,ports,adapters,registry orch
```

## `core/security/` — the Security Manager (Phase 19)

```mermaid
classDiagram
    class PermissionLevel {
        <<enumeration>>
        READ
        WRITE
        EXECUTE
        ADMINISTRATOR
        DANGEROUS
        BLOCKED
        +label str
    }

    class SecurityManager {
        -PathGuard path_guard
        -RateLimiter rate_limiter
        -SecurityAuditTrail audit
        -SessionHistory session_history
        -bool shutdown
        +authorize(SecurityRequest) SecurityDecision
        +trigger_emergency_shutdown(reason)
        +resume(reason)
        +session_history_for(requested_by) list
        +audit_log() list
    }

    class SecurityRequest {
        +str category
        +str action
        +str requested_by
        +str path
        +dict parameters
    }

    class SecurityDecision {
        +bool allowed
        +PermissionLevel level
        +str reason
        +bool required_confirmation
    }

    class RateLimiter {
        -dict limits
        +allow(requested_by, level) bool
        +remaining(requested_by, level) int
    }

    class ConfirmationPort {
        <<interface>>
        +confirm(prompt) bool
    }
    class AutoDenyConfirmation
    class CallbackConfirmation

    class SecurityAuditTrail {
        +record(SecurityAuditEntry)
        +read_all() list
    }

    class SessionHistory {
        +record(requested_by, SecurityDecision)
        +for_requester(requested_by) list
    }

    ConfirmationPort <|.. AutoDenyConfirmation
    ConfirmationPort <|.. CallbackConfirmation
    SecurityManager --> RateLimiter
    SecurityManager --> ConfirmationPort
    SecurityManager --> SecurityAuditTrail
    SecurityManager --> SessionHistory
    SecurityManager ..> SecurityRequest : authorize()
    SecurityManager ..> SecurityDecision : returns
    SecurityDecision --> PermissionLevel
```

## `core/workflow/` — Autonomous Workflows (Phase 20)

```mermaid
classDiagram
    class WorkflowEngine {
        -WorkflowStorePort store
        -WorkflowActionPort action_port
        +create_workflow(name, steps) Workflow
        +update_workflow(id, ...) Workflow
        +delete_workflow(id)
        +run_workflow(id, trigger) WorkflowRun
        +workflow_from_cowork_response(response) Workflow
        +render_mermaid(id, run) str
    }

    class Workflow {
        +str id
        +str name
        +list~WorkflowStep~ steps
        +WorkflowSchedule schedule
        +bool enabled
    }

    class WorkflowStep {
        +str id
        +str action
        +dict parameters
        +tuple depends_on
        +WorkflowCondition condition
    }

    class WorkflowCondition {
        +ConditionType type
        +str step_id
        +object value
    }

    class WorkflowRun {
        +str id
        +WorkflowStatus status
        +dict~str,WorkflowStepResult~ step_results
    }

    class WorkflowRunner {
        -Queue queue
        -list~Thread~ workers
        +submit(workflow_id, trigger)
        +start()
        +stop()
    }

    class WorkflowScheduler {
        -dict next_run_at
        +tick()
        +start()
        +stop()
    }

    class WorkflowActionPort {
        <<interface>>
        +execute(action, parameters) WorkflowActionResult
    }

    class AutomationWorkflowActionPort {
        -AutomationPort automation
    }

    WorkflowEngine --> Workflow : creates/runs
    Workflow "1" *-- "many" WorkflowStep
    WorkflowStep --> WorkflowCondition
    WorkflowEngine ..> WorkflowRun : produces
    WorkflowRunner --> WorkflowEngine : run_workflow()
    WorkflowScheduler --> WorkflowRunner : submit()
    WorkflowScheduler --> WorkflowEngine : list_workflows()
    WorkflowActionPort <|.. AutomationWorkflowActionPort
    WorkflowEngine --> WorkflowActionPort
```

## `orchestrator/` — request handling (Phase 2, extended through Phase 20)

```mermaid
classDiagram
    class Orchestrator {
        -CapabilityRegistry registry
        -IntentRecognizer intent_recognizer
        -SessionStore sessions
        -MemoryPort memory
        -AutomationPort automation
        -FilesystemPort filesystem
        -CoworkClientPort cowork
        +handle(Request) Response
    }

    class MemoryPort {
        <<interface>>
        +recall(session_id, query) list
        +remember(session_id, turn)
    }
    class AutomationPort {
        <<interface>>
        +execute(AutomationAction) AutomationResult
    }
    class NullMemoryPort
    class NullAutomationPort
    class ExecutionEngineAdapter
    class MemoryManagerAdapter
    class AutomationWorkflowActionPort

    class CapabilityRegistry {
        +register(name, handler, patterns, plugin)
        +all() list
    }

    class Session {
        +str session_id
        +list~Turn~ history
        +dict state
    }

    MemoryPort <|.. NullMemoryPort
    MemoryPort <|.. MemoryManagerAdapter
    AutomationPort <|.. NullAutomationPort
    AutomationPort <|.. ExecutionEngineAdapter
    AutomationWorkflowActionPort --> AutomationPort : delegates to
    Orchestrator --> MemoryPort
    Orchestrator --> AutomationPort
    Orchestrator --> CapabilityRegistry
    Orchestrator --> Session : reads/writes via SessionStore
```

## Config domains (Phase 3, grown to 12 domains through Phase 20)

```mermaid
classDiagram
    class ConfigManager {
        -LoadedConfig current
        +settings Settings
        +permissions PermissionsConfig
        +security SecurityConfig
        +workflow WorkflowConfig
        +reload() bool
        +start_watching(interval)
    }

    class LoadedConfig {
        +Settings settings
        +PermissionsConfig permissions
        +VoiceConfig voice
        +MemoryConfig memory
        +PluginsConfig plugins
        +FilesystemConfig filesystem
        +CoworkConfig cowork
        +VaultConfig vault
        +ExecutionConfig execution
        +PlanningConfig planning
        +SecurityConfig security
        +WorkflowConfig workflow
    }

    ConfigManager --> LoadedConfig : atomically swapped on reload()
    note for LoadedConfig "One frozen pydantic model per\nconfig/*.yaml file. See\ncore/config/manager.py's\n_files()/_load_all() — the\nsingle source of truth this\ndiagram is generated from."
```
