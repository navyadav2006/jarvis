"""Startup sequence.

This is the one place that wires everything together, in a fixed order:

    1. Load environment variables from .env (python-dotenv) — before
       anything reads os.environ for config overrides.
    2. Build the ConfigManager, which loads and validates all twelve
       config domains (settings/permissions/voice/memory/plugins/
       filesystem/cowork/vault/execution/planning/security/workflow)
       from config/*.yaml. A validation failure here is fatal — the
       process must not start with broken config.
    3. Configure logging from the loaded settings.
    4. Create the ServiceContainer and register core services into it
       (ConfigManager, Settings, EventBus). ConfigManager is attached
       to the EventBus once it exists, so config.reloaded /
       config.reload_failed become visible the same way any other
       event is.
    5. Create and register the orchestrator's collaborators — the
       CapabilityRegistry, SessionStore, IntentRecognizer, a MemoryPort
       (a real MemoryManagerAdapter/SqliteMemoryManager if memory.yaml's
       `long_term.enabled` is true, otherwise NullMemoryPort), the real
       LocalFilesystemService (built from filesystem.yaml), an
       AutomationPort (a real ExecutionEngineAdapter/ExecutionEngine —
       the Desktop Execution Engine, Phase 15, including the Phase 16
       Browser Agent behind its own `execution.yaml`'s
       `browser.enabled` flag — if execution.yaml's `enabled` is true,
       otherwise NullAutomationPort, and always checked by a
       SecurityManager first — Phase 19, also always real — before any
       action reaches it), a WorkflowEngine/WorkflowRunner/
       WorkflowScheduler (Phase 20, always real — steps execute via
       AutomationWorkflowActionPort, wrapping the same AutomationPort
       above so a workflow step passes through the same SecurityManager
       gate as anything else), a PlanningEngine (Phase 17,
       always real — pure local logic, no backend to gate), a
       VaultPort (a real VaultService if vault.yaml's `enabled` is
       true, otherwise NullVaultPort), and a CoworkClientPort (a real
       CoworkClient/HttpCoworkTransport if cowork.yaml's `enabled` is
       true, otherwise NullCoworkClientPort, wrapped either way in a
       CoworkWorkspace that picks which of Phase 10's eight specialist
       roles handles the task) — *before* plugins load, so a plugin's
       on_load() can resolve the CapabilityRegistry and register its
       capabilities.
    6. Construct the Orchestrator itself from those collaborators and
       register it, so the API layer (or a future CLI/voice loop) can
       resolve it without knowing how it was assembled.
    7. If voice.yaml's `enabled` is true, construct a real
       JarvisVoicePipeline (Phase 11's implementation, unwired until
       now) from real backends — SoundDeviceMicrophone/
       SoundDeviceAudioPlayer for mic/speaker I/O, OpenWakeWordDetector
       (or NullWakeWordPort if wake_word.enabled is false),
       WebRtcVoiceActivityDetector, WhisperCppSpeechToText,
       PiperTextToSpeech — and start it as a background thread.
       Its AssistantHandler is a lambda over the Orchestrator built in
       step 6, the exact shape core/voice/ports.py has documented
       since Phase 5. Unlike every other collaborator above, there is
       no Null Object default here: nothing else in the app depends on
       a VoicePipeline, so a disabled/unconfigured deployment simply
       has none registered rather than a real port standing in for
       "no backend." Voice's optional dependencies (the 'voice'
       extra) and downloaded model files (whisper.cpp/Piper/
       openWakeWord) are still required for this to actually produce
       audio — see docs/architecture.md's voice-wiring section.
    8. Create and run the PluginLoader, activating discovered plugins,
       using plugins.yaml's autoload/enabled/disabled.
    9. Start ConfigManager's background file watcher if settings.yaml's
       config.live_reload is true.
    10. Build the FastAPI app from the now-populated container.
    11. Serve it with uvicorn.

Every other module in the app should be reachable *from* this sequence
(directly or via a plugin loaded in step 8) — nothing should be doing
its own ad hoc "read settings / configure logging" on import, because
that would make startup order implicit instead of explicit. This is
also the only module that is allowed to know every concrete type in
the system (Settings, EventBus, PatternIntentRecognizer, NullMemoryPort,
LocalFilesystemService, ...) — everything downstream of it depends on
interfaces, not on each other.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from jarvis.api.app import create_app
from jarvis.core.browser import BrowserPort, NullBrowserPort, PlaywrightBrowser
from jarvis.core.config import DEFAULT_CONFIG_DIR, ConfigManager, Settings
from jarvis.core.container import ServiceContainer
from jarvis.core.cowork.client import CoworkClient
from jarvis.core.cowork.http_transport import HttpCoworkTransport
from jarvis.core.cowork.ports import CoworkClientPort, CoworkContextProvider, NullCoworkClientPort
from jarvis.core.cowork.prompts import PromptRegistry
from jarvis.core.cowork.workspace import CoworkWorkspace
from jarvis.core.events import EventBus
from jarvis.core.execution import (
    ExecutionEngine,
    PillowScreenshotter,
    ProcessApplicationManager,
    PyAutoGuiDesktopAutomation,
    PyGetWindowManager,
    PyperclipClipboard,
    SubprocessTerminal,
)
from jarvis.core.filesystem import FilesystemPort, LocalFilesystemService
from jarvis.core.logging_setup import configure_logging, set_level
from jarvis.core.memory import (
    HashingEmbeddingProvider,
    HybridMemorySearch,
    SemanticIndex,
    SqliteMemoryManager,
    VaultIndexer,
)
from jarvis.core.planning import PlanningEngine
from jarvis.core.plugin_loader import PluginLoader
from jarvis.core.security import AutoDenyConfirmation, SecurityManager
from jarvis.core.speech import (
    JarvisVoicePipeline,
    OpenWakeWordDetector,
    PiperTextToSpeech,
    SoundDeviceAudioPlayer,
    SoundDeviceMicrophone,
    WebRtcVoiceActivityDetector,
    WhisperCppSpeechToText,
)
from jarvis.core.vault import NullVaultPort, VaultPort, VaultService
from jarvis.core.voice.ports import NullWakeWordPort, WakeWordPort
from jarvis.core.workflow import (
    SqliteWorkflowStore,
    WorkflowEngine,
    WorkflowRunner,
    WorkflowScheduler,
)
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.execution_adapter import ExecutionEngineAdapter
from jarvis.orchestrator.intent_recognizer import PatternIntentRecognizer
from jarvis.orchestrator.memory_adapter import MemoryManagerAdapter
from jarvis.orchestrator.models import Request as OrchestratorRequest
from jarvis.orchestrator.orchestrator import Orchestrator
from jarvis.orchestrator.ports import (
    AutomationPort,
    IntentRecognizer,
    MemoryPort,
    NullAutomationPort,
    NullMemoryPort,
)
from jarvis.orchestrator.session_store import SessionStore
from jarvis.orchestrator.workflow_adapter import AutomationWorkflowActionPort

logger = logging.getLogger(__name__)


def bootstrap() -> ServiceContainer:
    """Run steps 1-8 of the startup sequence and return the populated container.

    Split out from main() so tests (and the FastAPI app factory) can
    build a fully-wired container without also starting a uvicorn server.
    """
    load_dotenv()

    config_manager = ConfigManager(config_dir=DEFAULT_CONFIG_DIR)
    settings = config_manager.settings
    configure_logging(settings.logging)
    logger.info("Starting %s (env=%s)", settings.app.name, settings.app.env)

    container = ServiceContainer()
    container.register_instance(ConfigManager, config_manager)
    container.register_instance(Settings, settings)

    events = EventBus()
    container.register_instance(EventBus, events)
    config_manager.attach_events(events)
    events.subscribe(
        "config.reloaded", lambda _event: set_level(config_manager.settings.logging.level)
    )

    capability_registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, capability_registry)

    session_store = SessionStore()
    container.register_instance(SessionStore, session_store)

    intent_recognizer: IntentRecognizer = PatternIntentRecognizer(capability_registry)
    container.register_instance(IntentRecognizer, intent_recognizer)

    # Memory stays a Null Object unless explicitly enabled in
    # memory.yaml — see docs/architecture.md's Phase 12 section. Kept as
    # a raw MemoryManagerPort (not yet adapted to orchestrator's
    # MemoryPort) so Phase 14's vault indexer/hybrid search below can
    # use it directly, alongside the adapted version Orchestrator gets.
    long_term_config = config_manager.memory.long_term
    memory_manager = SqliteMemoryManager(long_term_config) if long_term_config.enabled else None
    memory: MemoryPort = (
        MemoryManagerAdapter(memory_manager) if memory_manager is not None else NullMemoryPort()
    )
    container.register_instance(MemoryPort, memory)

    filesystem: FilesystemPort = LocalFilesystemService(
        config_manager.filesystem, events=events
    )
    container.register_instance(FilesystemPort, filesystem)

    # Automation stays a Null Object unless explicitly enabled in
    # execution.yaml — see docs/architecture.md's Phase 15 section.
    # Desktop/clipboard/screenshot/window handlers are real
    # (PyAutoGuiDesktopAutomation/PyperclipClipboard/
    # PillowScreenshotter/PyGetWindowManager) whenever the engine
    # itself is enabled — each lazy-imports its optional dependency
    # (the 'desktop' extra) on first real call, so construction here
    # never requires it installed; a deployment without the extra just
    # gets a clear ExecutionBackendUnavailableError the first time one
    # is actually used, same as every other lazy-import backend in
    # this project. The browser category (Phase 16) has its own
    # independent enable flag, execution.yaml's `browser.enabled`,
    # since it needs the separate 'browser' extra plus a `playwright
    # install` binary download.
    execution_config = config_manager.execution

    # SecurityManager (Phase 19) is pure local logic — always real, no
    # enabled flag — the one gate every AutomationAction passes through
    # regardless of who's asking. No confirmation UI exists yet, so it
    # fails closed (AutoDenyConfirmation denies DANGEROUS/ADMINISTRATOR
    # actions) until a real surface is wired in.
    security_manager = SecurityManager(
        config_manager.security,
        filesystem_config=config_manager.filesystem,
        permissions=config_manager.permissions,
        confirmation=AutoDenyConfirmation(),
        events=events,
    )
    container.register_instance(SecurityManager, security_manager)

    automation: AutomationPort
    if execution_config.enabled:
        browser: BrowserPort = (
            PlaywrightBrowser(execution_config.browser)
            if execution_config.browser.enabled
            else NullBrowserPort()
        )
        engine = ExecutionEngine(
            filesystem=filesystem,
            terminal=SubprocessTerminal(execution_config.terminal),
            desktop=PyAutoGuiDesktopAutomation(),
            application=ProcessApplicationManager(),
            clipboard=PyperclipClipboard(),
            screenshot=PillowScreenshotter(),
            window=PyGetWindowManager(),
            browser=browser,
            permissions=config_manager.permissions,
            audit_log_path=execution_config.audit_log_path,
            events=events,
        )
        automation = ExecutionEngineAdapter(
            engine,
            requested_by=execution_config.default_requester,
            security=security_manager,
        )
    else:
        automation = NullAutomationPort()
    container.register_instance(AutomationPort, automation)

    # WorkflowEngine/WorkflowRunner/WorkflowScheduler (Phase 20) are
    # always real, like SecurityManager/PlanningEngine — an empty
    # workflow store with an idle scheduler is harmless. Steps execute
    # via AutomationWorkflowActionPort, which just delegates to the
    # `automation` port built above — so a workflow step is checked by
    # the exact same SecurityManager gate as any other automation
    # action, not a second, unguarded path.
    workflow_config = config_manager.workflow
    workflow_store = SqliteWorkflowStore(workflow_config.database_path)
    workflow_engine = WorkflowEngine(
        workflow_store, AutomationWorkflowActionPort(automation), events=events
    )
    container.register_instance(WorkflowEngine, workflow_engine)

    workflow_runner = WorkflowRunner(
        workflow_engine, max_workers=workflow_config.max_concurrent_runs
    )
    workflow_runner.start()
    container.register_instance(WorkflowRunner, workflow_runner)

    workflow_scheduler = WorkflowScheduler(
        workflow_engine,
        workflow_runner,
        poll_interval_seconds=workflow_config.scheduler_poll_interval_seconds,
    )
    workflow_scheduler.start()
    container.register_instance(WorkflowScheduler, workflow_scheduler)

    # PlanningEngine (Phase 17) is pure local logic with no external
    # backend — always real, no enabled flag/Null default needed,
    # unlike everything else registered so far.
    planning_engine = PlanningEngine(config_manager.planning, events=events)
    container.register_instance(PlanningEngine, planning_engine)

    # Vault stays a Null Object unless explicitly enabled in vault.yaml
    # — see docs/architecture.md's Phase 13 section.
    vault_config = config_manager.vault
    vault: VaultPort = (
        VaultService(filesystem, vault_config) if vault_config.enabled else NullVaultPort()
    )
    container.register_instance(VaultPort, vault)

    # Semantic memory (Phase 14) only stands up if memory, vault, AND
    # memory.yaml's `semantic.enabled` are all true — it indexes the
    # vault into long-term memory, so both of those need a real backend
    # first. Indexing runs once, synchronously, at startup (incremental:
    # an unchanged vault re-indexes almost instantly — see
    # VaultIndexer's module docstring).
    semantic_config = config_manager.memory.semantic
    context_provider: CoworkContextProvider | None = None
    if semantic_config.enabled and memory_manager is not None and vault_config.enabled:
        embedding_provider = HashingEmbeddingProvider(dim=semantic_config.embedding_dim)
        semantic_index = SemanticIndex(
            embedding_provider,
            cache_path=semantic_config.cache_path,
            index_path=semantic_config.index_path,
        )
        indexer = VaultIndexer(
            vault=vault,
            memory=memory_manager,
            semantic_index=semantic_index,
            state_path=semantic_config.cache_path.parent / "vault_index_state.json",
        )
        report = indexer.index_vault()
        logger.info(
            "Vault semantic index: %d indexed, %d skipped, %d failed",
            report.indexed,
            report.skipped,
            report.failed,
        )
        context_provider = HybridMemorySearch(
            memory=memory_manager,
            semantic_index=semantic_index,
            provider=embedding_provider,
            semantic_weight=semantic_config.semantic_weight,
        )

    # Cowork stays a Null Object unless explicitly enabled in
    # cowork.yaml — an unconfigured deployment must never attempt a
    # real network call. See docs/architecture.md's Phase 9 section.
    cowork_config = config_manager.cowork
    cowork: CoworkClientPort = (
        CoworkClient(
            transport=HttpCoworkTransport(cowork_config),
            config=cowork_config,
            events=events,
        )
        if cowork_config.enabled
        else NullCoworkClientPort()
    )
    # PromptRegistry (Phase 22) is always real, like PlanningEngine/
    # SecurityManager — it's pure local file-reading logic with a
    # built-in fallback (CollaboratorSpec.prompt_template) for any role
    # whose prompts/*.md file doesn't exist yet, so there's no
    # meaningful disabled state to gate behind a flag.
    prompt_registry = PromptRegistry(settings.paths.resolved().prompts_dir)
    container.register_instance(PromptRegistry, prompt_registry)

    # CoworkWorkspace (Phase 10) wraps whichever backend was just built,
    # adding collaborator-role selection/prompt rendering ahead of it,
    # plus Phase 14's memory-context injection if semantic memory stood
    # up above and Phase 22's file-sourced prompt templates. It
    # implements CoworkClientPort itself, so Orchestrator's dependency
    # doesn't change shape.
    cowork = CoworkWorkspace(
        inner=cowork,
        context_provider=context_provider,
        context_limit=semantic_config.context_injection_limit,
        prompt_registry=prompt_registry,
    )
    container.register_instance(CoworkClientPort, cowork)

    # Built (but not yet loaded — see load_all() below) before
    # Orchestrator so plugin_catalog() (Phase 18: "expose plugin APIs
    # to Claude Cowork") can be handed to it now. The bound method is
    # only ever *called* per-request, by which point plugins have
    # already loaded, so construction order here doesn't need to match
    # load order.
    plugins_config = config_manager.plugins
    plugin_loader = PluginLoader(
        container,
        events,
        enabled=plugins_config.enabled,
        disabled=plugins_config.disabled,
        external_dir=settings.paths.resolved().plugins_dir,
        permissions=config_manager.permissions,
        plugin_configs=plugins_config.plugins,
        capability_registry=capability_registry,
    )
    container.register_instance(PluginLoader, plugin_loader)

    orchestrator = Orchestrator(
        events=events,
        capability_registry=capability_registry,
        intent_recognizer=intent_recognizer,
        session_store=session_store,
        memory=memory,
        automation=automation,
        filesystem=filesystem,
        cowork=cowork,
        plugin_catalog=plugin_loader.plugin_catalog,
    )
    container.register_instance(Orchestrator, orchestrator)

    # Voice pipeline (Phase 11's JarvisVoicePipeline, unwired until this
    # phase) — see the docstring's step 7. No Null Object default: an
    # unconfigured/disabled deployment simply has no VoicePipeline
    # registered, since nothing else in the app calls into one.
    voice_config = config_manager.voice
    if voice_config.enabled:
        wake_word: WakeWordPort = (
            OpenWakeWordDetector(voice_config.wake_word)
            if voice_config.wake_word.enabled
            else NullWakeWordPort()
        )

        def _voice_assistant(text: str, session_id: str) -> str:
            response = orchestrator.handle(
                OrchestratorRequest(text=text, session_id=session_id, source="voice")
            )
            return response.text or ""

        voice_pipeline = JarvisVoicePipeline(
            microphone=SoundDeviceMicrophone(voice_config.mic),
            wake_word=wake_word,
            vad=WebRtcVoiceActivityDetector(
                aggressiveness=voice_config.streaming.vad_aggressiveness
            ),
            stt=WhisperCppSpeechToText(voice_config.stt),
            assistant=_voice_assistant,
            tts=PiperTextToSpeech(voice_config.tts),
            player=SoundDeviceAudioPlayer(voice_config.player),
            config=voice_config,
            events=events,
        )
        container.register_instance(JarvisVoicePipeline, voice_pipeline)
        voice_pipeline.start()
        logger.info("Voice pipeline started (mode=%s)", voice_config.listening.mode)
    else:
        logger.info("Voice disabled (voice.yaml enabled=false); no voice pipeline started")

    if plugins_config.autoload:
        plugin_loader.load_all()
    else:
        logger.info("Plugin autoload disabled; skipping plugin activation")

    if settings.config.live_reload:
        config_manager.start_watching(settings.config.poll_interval_seconds)

    logger.info("Startup sequence complete")
    return container


def main() -> None:
    # Imported here, not at module level: uvicorn (and the watchfiles/
    # click/anyio it pulls in) costs ~0.4s to import, and only this
    # function ever calls uvicorn.run(). bootstrap() is also used by
    # every test, script, and create_app() itself — none of which
    # start a server — so keeping this import out of the module's
    # top-level import graph is a real, measured startup-latency win
    # for every one of those callers (Phase 21).
    import uvicorn

    container = bootstrap()
    settings = container.resolve(Settings)
    config_manager = container.resolve(ConfigManager)
    workflow_runner = container.resolve(WorkflowRunner)
    workflow_scheduler = container.resolve(WorkflowScheduler)
    app = create_app(container)

    try:
        uvicorn.run(app, host=settings.api.host, port=settings.api.port, log_config=None)
    finally:
        config_manager.stop_watching()
        workflow_scheduler.stop()
        workflow_runner.stop()
        if container.has(JarvisVoicePipeline):
            container.resolve(JarvisVoicePipeline).stop()


if __name__ == "__main__":
    main()
