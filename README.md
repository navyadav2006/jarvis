# Jarvis

A local-first, plugin-based AI desktop assistant. Everything Jarvis
does — voice interaction, browser automation, desktop control, note
storage, memory/search — is a plugin loaded at startup on top of a
small, fixed core (config, logging, a service container, and an event
bus).

**Status:**
- **Phase 1** — architecture and scaffolding (config, logging, DI
  container, event bus, plugin loader). No feature plugins yet.
- **Phase 2** — the central orchestrator: request handling, intent
  routing, session state, and dependency-injected `Memory`/`Automation`
  ports (currently backed by Null Object defaults — no real memory or
  automation backend exists yet).
- **Phase 3** — the global configuration system: five typed, validated
  YAML config domains (`settings`/`permissions`/`voice`/`memory`/`plugins`)
  with defaults, environment-variable overrides (settings only), and
  live reload via `ConfigManager`.
- **Phase 4** — the filesystem module: a real, working
  copy/move/rename/delete/search/read/write implementation, gated by
  an allowlist/blacklist (`filesystem.yaml`, the sixth config domain)
  and a hardcoded, non-configurable protection floor over
  Windows/Program Files/System32/the registry, with every operation
  logged and destructive ones requiring explicit confirmation.
- **Phase 5** — voice support, **interfaces only**: `Protocol`s for
  Microphone/VoiceActivityDetector/SpeechToText/TextToSpeech/AudioPlayer,
  an abstract `VoicePipeline` contract for continuous listening,
  push-to-talk, conversation mode, background listening, and voice
  interruption, and a `listening` section in `voice.yaml`. No wake
  word, no real audio/Whisper.cpp/Piper backend, not wired into
  `main.py` or the orchestrator yet — see below.
- **Phase 6** — Whisper.cpp integration: a real, reusable speech module
  (`core/speech/`) — `WhisperCppSpeechToText` (pywhispercpp bindings,
  automatic language detection), `WebRtcVoiceActivityDetector` (noise
  filtering + speaker-pause detection), and `StreamingTranscriber`
  (real-time buffering, low-latency partial results, no-speech/
  inference timeout handling). Every optional dependency is lazily
  imported — the module works, and is fully unit-tested, with none of
  them installed. Still not wired into `main.py`/the orchestrator.
- **Phase 7** — Piper integration: `PiperTextToSpeech` (piper-tts
  bindings, speaking rate via `speed`) and `SpeechQueue` — the reusable
  engine for queueing multiple responses, three distinct ways to
  interrupt them (`skip`/`clear`/`interrupt`), and live volume control
  via pure-stdlib PCM gain scaling (no numpy needed for this part).
  Same scoping as Phase 6: real synthesis, no real speaker output yet,
  not wired into `main.py`/the orchestrator.
- **Phase 8** — wake word support: `OpenWakeWordDetector`
  (`core/speech/wake_word.py`), a real `WakeWordPort` backed by
  openWakeWord, supporting multiple simultaneous wake words (built-in
  or custom-trained), audio-duration-based cooldown, and
  enable/disable via `voice.yaml`. Unlike Phases 6-7, this phase also
  extends `VoicePipeline`'s own contract: a new `WAITING_FOR_WAKE_WORD`
  state gates the expensive VAD/STT stages behind the cheap wake-word
  model, and the ABC now specifies that a conversation ending returns
  to waiting-for-wake-word rather than fully idle. Still no real
  microphone backend and not wired into `main.py`/the orchestrator.
- **Phase 9** — the Cowork integration layer: Jarvis is now a
  system-wide AI operating layer, not a single-agent assistant. When no
  local capability matches a request, `Orchestrator` offers it to
  Claude Cowork (`core/cowork/`) for planning via `CoworkClient`
  (timeout handling, exponential-backoff retries, response parsing,
  diagnostics, all typed pydantic models), then **executes the returned
  plan itself** via the existing `AutomationPort` — Cowork's response
  is inert data with no method that could touch the filesystem,
  desktop, browser, or terminal. Disabled by default
  (`cowork.yaml`'s `enabled: false`); `main.bootstrap()` wires in
  `NullCoworkClientPort` unless a deployment opts in.
- **Phase 10** — the internal Cowork workspace: eight specialist
  collaborator roles (Architect, Planner, Coder, Researcher, Memory
  Manager, Automation Engineer, Documentation Engineer, QA Engineer),
  each with defined responsibilities, boundaries, and a reusable prompt
  template (`core/cowork/collaborators.py`). `CoworkWorkspace`
  (`core/cowork/workspace.py`) picks a role and renders its prompt,
  then delegates to the same Phase 9 `CoworkClientPort` — it
  implements that same port itself, so `Orchestrator` is unchanged.
  Every collaborator's output is still the inert `CoworkPlanStep` shape
  from Phase 9: no collaborator can touch the OS, and every action
  still flows back through `Orchestrator._try_cowork()`.
- **Phase 11** — the full voice pipeline, wired together:
  `JarvisVoicePipeline` (`core/speech/jarvis_pipeline.py`) is the first
  concrete `VoicePipeline`, connecting every piece built since Phase 5
  (wake word → whisper.cpp → `Orchestrator`, which already handles
  intent parsing and Cowork routing → Piper) into one running state
  machine, with conversation interruption (barge-in), automatic
  conversation follow-ups, and per-turn latency events. See
  `scripts/benchmark_voice_latency.py` /
  `docs/benchmarks/voice_latency.md` for latency benchmarks. Still no
  real microphone/speaker backend and not wired into `main.py`.
- **Phase 12** — the Memory Manager collaborator: `core/memory/`'s
  `SqliteMemoryManager` (stdlib `sqlite3`, no embeddings) gives Jarvis
  a real, working long-term memory called via a structured API —
  remember turns, store explicit knowledge, recall ranked by
  importance/recency/keyword-overlap, summarize a session, and forget
  temporary information while durable facts survive.
  `orchestrator/memory_adapter.py` bridges it to `Orchestrator`'s
  existing `MemoryPort`. `EmbeddingIndexPort` is prepared, unimplemented
  interface for future semantic memory. Wired into `main.bootstrap()`
  behind `memory.yaml`'s `long_term.enabled` (default off).
- **Phase 13** — the Obsidian vault connection: `core/vault/`'s
  `VaultService` (real, over `FilesystemPort`, no new dependency) turns
  a vault into Jarvis's permanent knowledge base — notes with YAML
  frontmatter, daily journals, project notes, conversation summaries,
  dev logs, automatic `[[wikilink]]` backlinks, and folder
  organization. Every overwrite is versioned first (`.jarvis/versions/`
  inside the vault) and `rollback_note()` restores any prior version.
  Wired into `main.bootstrap()` behind `vault.yaml`'s `enabled`
  (default off); not yet called by `Orchestrator` or a plugin.
- **Phase 14** — semantic memory: `core/memory/`'s `SemanticIndex`
  (the first real `EmbeddingIndexPort`, JSON-persisted, content-hash
  embedding cache) and `HashingEmbeddingProvider` (a dependency-free
  feature-hashing embedding — no real ML model). `VaultIndexer` indexes
  the vault incrementally; `HybridMemorySearch` combines keyword and
  semantic search into ranked, cited results.
  `CoworkWorkspace` gained an optional `context_provider` that injects
  those results into every Cowork request's context before the
  collaborator prompt is rendered — "give Cowork only the relevant
  memories instead of the entire vault." Wired into `main.bootstrap()`
  behind `memory.yaml`'s `semantic.enabled` (needs long-term memory and
  the vault both enabled too; default off).
- **Phase 15** — the Desktop Execution Engine: `core/execution/`'s
  `ExecutionEngine` is the first real `AutomationPort`, giving Claude
  Cowork's plan steps (Phase 9) somewhere real to execute — filesystem
  (reuses `FilesystemPort`), terminal (`subprocess`, allowlisted
  executables), application launch/close, and desktop
  automation/clipboard/screenshot/window (lazy-imported, the new
  'desktop' extra). Every action is checked against `permissions.yaml`
  (Phase 3's `PermissionsConfig`, unenforced until now) before running,
  and every attempt — allowed or not — is written to a JSON-Lines audit
  trail. Wired into `main.bootstrap()` behind `execution.yaml`'s
  `enabled` (default off); desktop/clipboard/screenshot/window stay
  Null even when enabled, since they need real hardware/the optional
  extra.
- **Phase 16** — the Browser Agent: `core/browser/`'s `PlaywrightBrowser`
  is `ExecutionEngine`'s eighth category (search the web, navigate,
  fill forms, authenticate, download files, screenshot, and summarize
  pages), lazy-imported behind a new 'browser' extra (Playwright also
  needs a separate `playwright install <engine>` binary download).
  `actions.py` composes the seven primitives into reusable, named
  actions (`login()`, `search_and_summarize_top_result()`, ...).
  `BrowserConfig.engine` picks chromium/firefox/webkit, supporting
  future multi-browser operation without any caller needing to know
  which. Cowork requests browser tasks the same way it requests any
  other action — through `Orchestrator` -> `AutomationPort` ->
  `ExecutionEngine`, no new plumbing needed. Wired in behind
  `execution.yaml`'s `browser.enabled` (its own flag, independent of
  the rest of the execution engine; default off).
- **Phase 17** — the Planning Engine: `core/planning/`'s
  `PlanningEngine` is pure local logic (no backend, always real) that
  breaks a request into tasks (`decompose_request()`), estimates
  dependencies and detects parallel work (`topological_waves()` — a
  real Kahn's-algorithm leveling), assigns a collaborator to each task
  (reusing Phase 10's `select_role()`), tracks progress through six
  statuses, retries failed tasks (and correctly reopens anything that
  was skipped because of them), and renders a human-readable plan.
  `should_preview()` decides when Jarvis should show the plan before
  running it. Deliberately not tied to Cowork specifically —
  `plan_from_cowork_response()` is one integration point among
  possible future ones, not a requirement to use it. Always registered
  in `main.bootstrap()`'s container; not yet wired into `Orchestrator`.
- **Phase 18** — the plugin framework: `PluginBase` gains
  `dependencies`, `required_permissions`, `description`, and a
  `configure()` hook; `PluginLoader` gains dependency-ordered loading
  (version-constraint-aware, e.g. `"docker>=1.0.0"`), permission
  enforcement (`permissions.yaml`'s second real caller, after Phase
  15), `install_plugin()`, and `plugin_catalog()` — included in every
  Cowork request's metadata so Cowork can see what Jarvis's plugins can
  do without ever being able to call one directly. Six real, working
  reference plugins ship in `src/jarvis/plugins/examples/` (GitHub,
  Docker, PostgreSQL, Obsidian, Calendar, Email) — none need a new hard
  dependency, and none auto-load by default (verified, not assumed).
- **Phase 19** — the Jarvis Security Manager: `core/security/`'s
  `SecurityManager` — six risk levels (Read/Write/Execute/
  Administrator/Dangerous/Blocked), confirmation dialogs for the risky
  ones, filesystem allow/deny (reusing Phase 4's `PathGuard`), rate
  limiting, a durable JSONL audit log, in-memory per-requester session
  history, and an emergency shutdown that denies everything until
  lifted. Always constructed (no `enabled` flag — pure local logic, the
  same "always real" choice Phase 17's `PlanningEngine` made) and wired
  in front of `ExecutionEngineAdapter`, which now calls
  `SecurityManager.authorize()` before `ExecutionEngine.execute()` is
  ever reached — the concrete answer to "Claude Cowork must never
  bypass the security layer."
- **Phase 20** — autonomous workflows: `core/workflow/`'s
  `WorkflowEngine` — saved, reusable, multi-step `Workflow`s with
  wave-by-wave dependency execution, conditional execution
  (`ALWAYS`/`ON_SUCCESS`/`ON_FAILURE`/`OUTPUT_EQUALS`/
  `OUTPUT_CONTAINS`), background execution (`WorkflowRunner`, a bounded
  worker pool), scheduling (`WorkflowScheduler`, interval or
  hand-rolled dependency-free cron — recurring maintenance is just a
  scheduled workflow, no separate mechanism), durable run history and
  full CRUD editing (`SqliteWorkflowStore`), and Mermaid
  visualisations. `WorkflowEngine.workflow_from_cowork_response()`
  turns a Cowork plan into a saved workflow; steps execute via
  `AutomationWorkflowActionPort`, which just delegates to the same
  `AutomationPort` every other action already goes through — so a
  workflow step passes through the exact same Phase 19 SecurityManager
  gate as anything else, with no second path.
- **Phase 21** — architectural review & production readiness: a full
  review (test coverage, startup latency, memory footprint, layering
  discipline) ran before any code changed, findings were presented to
  the user, and four concrete workstreams were picked from the
  results — an open-ended "refactor everything" pass was offered and
  not selected. Delivered: a startup-latency fix (`uvicorn` is now a
  lazy import inside `main()`, saving ~1s for every `bootstrap()`-only
  caller — tests, scripts, `create_app()`), 13 new targeted tests plus
  a real bug fix (`/config` had silently drifted to returning only 7
  of 12 config domains for 5 phases), `docs/diagrams.md` (Mermaid
  system component + class diagrams), richer `/health`/`/config`/
  `/message` OpenAPI docs plus `scripts/export_openapi.py`, and
  deployment instructions (`Dockerfile`, `docker-compose.yml`,
  `docs/deployment.md`) that are explicit about what does and doesn't
  run the same way in a container (desktop automation and voice both
  need real hardware a container doesn't have).
- **Phase 22** — the Prompt Registry: suggested by the user in
  response to Phase 10's collaborator prompts being hardcoded Python
  strings. New `prompts/` directory (`system.md` + one file per
  collaborator role) and `core/cowork/prompts.py`'s `PromptRegistry`,
  which reads the relevant file fresh on every Cowork request — no
  restart needed to refine a collaborator's behavior. Fully optional
  and backward compatible: with no registry wired in (or a missing
  file), `CollaboratorSpec.render_prompt()` behaves exactly as it did
  in Phase 10, falling back to the hardcoded `prompt_template`.

See `docs/architecture.md` for the full design rationale, including a
Phase-2-specific section on why every orchestrator dependency is
injected rather than imported, a Phase-3-specific section on the
config system's fail-fast-at-startup / fail-safe-at-reload split, a
Phase-4-specific section on why the system-path protection is
hardcoded rather than just a well-chosen default blacklist entry, a
Phase-5-specific section on why `VoicePipeline` is an ABC (like
`PluginBase`) while every other port this project has added is a
`Protocol`, a Phase-6-specific section on why timeouts are
audio-duration-based rather than wall-clock (and the one that isn't),
a Phase-7-specific section on why volume is a live playback-time
concern while speed is a fixed synthesis-time one, and a
Phase-8-specific section on why wake word support — unlike Phases 6-7
— required changing `VoicePipeline`'s own contract instead of just
adding a new port implementation, and a Phase-9-specific section on why
the "Cowork must never touch the OS" boundary is structural (no
method exists to touch it) rather than a runtime permission check,
a Phase-19-specific section on why `SecurityManager` sits in
front of `ExecutionEngine` as a second gate rather than growing that
class further, including the scope-string sharing bug this phase's
live testing caught between the two, a Phase-20-specific section
on why conditional execution needed its own rule beyond dependency
status, why cron is hand-rolled instead of a new dependency, and why
workflow steps can't bypass SecurityManager, a Phase-21-specific
section with the full architectural review's findings, and a
Phase-22-specific section on the scoping decisions behind the Prompt
Registry (why `automation_engineer` wasn't split into browser/desktop,
and why there's no `orchestrator.md`/`security.md`). See
`docs/diagrams.md` for UML/component diagrams and `docs/deployment.md`
for deployment instructions.

## Quick start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements-dev.txt
pip install -e .
# Optional, only for the real speech backends (core/speech/):
# pip install -r requirements-voice.txt
# Optional, only for the real Cowork HTTP backend (core/cowork/):
# pip install -r requirements-cowork.txt

# 3. Configure
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux

# 4. Run
python -m jarvis.main

# 5. Verify
curl http://127.0.0.1:8756/health
curl http://127.0.0.1:8756/config       # current value of all 6 config domains
curl -X POST http://127.0.0.1:8756/message \
  -H "Content-Type: application/json" \
  -d '{"text": "hello", "session_id": "demo"}'
# -> {"session_id":"demo","intent":"unknown","handled":false,"text":null,"data":{}}
# ("unknown" is expected: no plugin has registered a capability yet)

# 6. Try live reload: with Jarvis still running, edit config/settings.yaml
# (e.g. change app.name) and save. Within poll_interval_seconds (2s by
# default), `curl http://127.0.0.1:8756/health` reflects the new value —
# no restart needed.
```

## Running tests

```bash
pytest
```

## Project layout

```
Jarvis/
├── config/
│   ├── settings.yaml        # app/logging/paths/api/live-reload settings
│   ├── permissions.yaml     # per-plugin capability allow/deny rules
│   ├── voice.yaml           # wake word / STT / TTS / listening-mode settings
│   ├── memory.yaml          # short-term + long-term memory settings
│   ├── plugins.yaml         # which plugins load, per-plugin config
│   ├── filesystem.yaml      # allowlist/blacklist + confirmation policy
│   ├── cowork.yaml          # Claude Cowork client/routing/retry settings
│   └── examples/            # heavily-commented populated examples of all 7
├── data/                   # local-first app data (SQLite DB, FAISS index) — git-ignored
├── docs/
│   └── architecture.md     # full architectural rationale + diagrams
├── logs/                   # rotating log files — git-ignored
├── plugins/                # external/user-installed plugins — git-ignored
├── src/jarvis/
│   ├── api/                 # FastAPI app factory + routes
│   ├── core/                 # config, logging, DI container, event bus, plugin loader
│   │   ├── config/              # the global configuration system (Phase 3)
│   │   ├── filesystem/          # the filesystem module (Phase 4)
│   │   ├── voice/                # voice pipeline interfaces only (Phase 5)
│   │   ├── speech/               # real openWakeWord/whisper.cpp/Piper speech module (Phase 6-8)
│   │   └── cowork/               # Claude Cowork integration layer (Phase 9)
│   ├── orchestrator/          # central request-handling pipeline (Phase 2)
│   ├── plugins/               # built-in plugins (namespace package, empty in Phase 1)
│   └── main.py                 # startup sequence
├── tests/                  # mirrors src/jarvis structure
├── vault/                  # Obsidian vault root — git-ignored
├── .env.example
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── requirements-voice.txt    # optional: real speech backends (openwakeword, pywhispercpp, webrtcvad, piper-tts, numpy)
└── requirements-cowork.txt   # optional: real Cowork HTTP backend (httpx)
```

Every folder's purpose is explained in detail in
[`docs/architecture.md`](docs/architecture.md).

## Configuration

Seven YAML files under `config/`, one typed & validated pydantic model
per file:

| File | Model | Covers |
|---|---|---|
| `settings.yaml` | `Settings` | app identity, logging, paths, API bind address, live-reload |
| `permissions.yaml` | `PermissionsConfig` | per-plugin capability allow/deny rules |
| `voice.yaml` | `VoiceConfig` | wake word / speech-to-text / text-to-speech |
| `memory.yaml` | `MemoryConfig` | short-term (session) + long-term (SQLite/FAISS) memory |
| `plugins.yaml` | `PluginsConfig` | which plugins load, per-plugin config blobs |
| `filesystem.yaml` | `FilesystemConfig` | allowlist/blacklist dirs, which operations require confirmation |
| `cowork.yaml` | `CoworkConfig` | Cowork enable/disable, endpoint, timeout/retry tuning, routing threshold |

A missing file just means "use defaults" (every field has one); an
invalid one raises `ConfigurationError` — at startup this stops the
process, at reload it's logged and the last good config is kept
instead (see `docs/architecture.md`'s Phase 3 section for why those
two cases behave differently). Only `settings.yaml` supports
environment-variable overrides (`APP__NAME=...`, `.env`); the other
six are meant to be edited directly (`cowork.yaml`'s API key is the one
exception — it's read from the environment variable named by
`api_key_env_var`, never stored in YAML).

`ConfigManager` (`container.resolve(ConfigManager)`) is the reload-aware
entry point — `.settings`, `.permissions`, `.voice`, `.memory`,
`.plugins`, `.filesystem`, `.cowork` always return the current value,
and its background watcher thread (on by default, `settings.yaml`'s
`config.live_reload`) polls for file changes and reloads automatically.
Populated example files for all seven domains live in `config/examples/`.

## The filesystem module

`container.resolve(FilesystemPort)` (or `context.filesystem` inside a
capability handler) gives `read`/`write`/`copy`/`move`/`rename`/
`delete`/`search`, all enforced by `filesystem.yaml`:

```python
from jarvis.core.exceptions import ConfirmationRequiredError

fs = container.resolve(FilesystemPort)

fs.write("data/notes/todo.txt", "buy milk")          # inside allowed_dirs -> OK
fs.read("data/notes/todo.txt")                          # "buy milk"

try:
    fs.delete("data/notes/todo.txt")                     # delete needs confirmation
except ConfirmationRequiredError:
    fs.delete("data/notes/todo.txt", confirmed=True)      # explicit opt-in required

fs.read(r"C:\Windows\System32\drivers\etc\hosts")        # always raises FilesystemAccessError
```

Every path — including copy/move destinations and a rename's computed
new name — is checked in a fixed order: hardcoded protected system
paths (Windows/Program Files/System32/the registry — never
configurable) first, then `filesystem.yaml`'s `blacklisted_dirs`, then
its `allowed_dirs`. Every operation is logged and published as an
`EventBus` event (`filesystem.operation_succeeded`, `.denied`,
`.confirmation_required`, `.operation_failed`) regardless of outcome.
See `docs/architecture.md`'s Phase 4 section for the full rationale.

## Voice support (interfaces only)

`src/jarvis/core/voice/` defines the shape of a Microphone -> Speech-
to-Text -> Assistant -> Text-to-Speech pipeline, but **there is no
concrete implementation yet** — no real microphone, Whisper.cpp, or
Piper integration, and nothing in `main.py` or the orchestrator
references this package:

- **`ports.py`** — `MicrophonePort`, `VoiceActivityDetector`,
  `SpeechToTextPort`, `TextToSpeechPort`, `AudioPlayerPort` (`Protocol`s
  with Null Object defaults, same pattern as `MemoryPort`/`AutomationPort`),
  and `AssistantHandler` (a callable Protocol standing in for
  `Orchestrator`, so `core/voice/` never depends on `orchestrator/`).
- **`pipeline.py`** — `VoicePipeline`, an `ABC` (like `PluginBase`, not
  a `Protocol` like the ports above) defining `start()`, `stop()`,
  `push_to_talk_press()`/`push_to_talk_release()`, and `interrupt()`.
  Continuous listening, push-to-talk, conversation mode, and
  background listening are `voice.yaml`'s `listening` section —
  config-driven modifiers of `start()`'s behavior; voice interruption
  (barge-in) is its own method, since it's an action that can happen
  *during* playback rather than a variant of how listening starts.
- **No wake word** — `voice.yaml`'s `wake_word` section (from Phase 3)
  stays reserved; `ListeningMode` has exactly two members
  (`push_to_talk`, `continuous`), deliberately no third.

```python
from jarvis.core.voice import VoicePipeline, VoiceState

class MyVoicePipeline(VoicePipeline):
    def start(self) -> None: ...       # must implement all five
    def stop(self) -> None: ...        # abstract methods to be
    def push_to_talk_press(self) -> None: ...   # instantiable —
    def push_to_talk_release(self) -> None: ... # this is the whole
    def interrupt(self) -> None: ...             # point of the ABC
```

See `docs/architecture.md`'s Phase 5 section for the state machine
diagram and the full rationale (including why interruption gets its
own abstract method while the other four requirements don't).

## The speech module: speech-to-text (Whisper.cpp)

`src/jarvis/core/speech/` is a real, reusable implementation of Phase
5's `SpeechToTextPort`/`VoiceActivityDetector` interfaces, plus a
real-time streaming layer on top. It's still not wired into
`main.py`/the orchestrator — this is a module other code can use, not
yet an activated feature:

- **`WhisperCppSpeechToText`** — backed by
  [pywhispercpp](https://github.com/absadiki/pywhispercpp); the model
  loads once (lazily, on first `transcribe()` call) and stays resident
  in memory. `voice.yaml`'s `stt.language: "auto"` enables whisper.cpp's
  own automatic language detection.
- **`WebRtcVoiceActivityDetector`** — backed by `webrtcvad`; doubles as
  both noise filtering (it classifies speech vs. background noise, not
  just "loud vs. quiet") and the speaker-pause signal
  `StreamingTranscriber` finalizes utterances on.
- **`StreamingTranscriber`** — the real-time engine: buffers fed audio,
  emits low-latency partial transcriptions as speech continues,
  finalizes on a detected pause or a max-duration timeout, and raises
  if no speech is heard at all within a configurable window. Has **zero
  required dependencies** — it's pure buffering logic over whatever
  `SpeechToTextPort`/`VoiceActivityDetector` it's given, which is what
  makes its entire test suite runnable without `pywhispercpp`/`webrtcvad`
  installed.

```python
from jarvis.core.config.voice_config import StreamingConfig
from jarvis.core.speech import StreamingTranscriber, WebRtcVoiceActivityDetector, WhisperCppSpeechToText

transcriber = StreamingTranscriber(
    stt=WhisperCppSpeechToText(voice_config.stt),
    vad=WebRtcVoiceActivityDetector(aggressiveness=voice_config.streaming.vad_aggressiveness),
    config=voice_config.streaming,
    on_partial=lambda result: print("partial:", result.text),
)

for chunk in audio_chunks:            # from any AudioChunk source
    final = transcriber.feed(chunk)
    if final is not None:
        print("utterance:", final.text, final.language)
        break
```

`pywhispercpp`/`webrtcvad`/`numpy` are all imported lazily — only the
first real call to `transcribe()`/`is_speech()` needs them installed
(`pip install -r requirements-voice.txt`); everything else, including
`StreamingTranscriber`'s own logic, works and is tested without them.
See `docs/architecture.md`'s Phase 6 section for the integration
approach considered and rejected (a `whisper-server` subprocess, a
CLI-per-utterance subprocess) and why most of `StreamingTranscriber`'s
timeouts are computed from the audio's own duration rather than
wall-clock time.

## The speech module: text-to-speech (Piper)

`PiperTextToSpeech` and `SpeechQueue` are Phase 7's mirror image of
the above: a real `TextToSpeechPort` and the reusable engine that
turns single-shot synthesis into queueable, interruptible,
volume-controlled playback. Also not wired into `main.py`/the
orchestrator yet.

- **`PiperTextToSpeech`** — backed by
  [piper-tts](https://github.com/OHF-Voice/piper1-gpl); the voice model
  loads once (lazily, on first `synthesize()` call). `voice.yaml`'s
  `tts.speed` (1.0 = normal, 2.0 = twice as fast, 0.5 = half speed) maps
  to Piper's `length_scale` at synthesis time.
- **`SpeechQueue`** — the real-time playback engine: a background
  worker drains a text queue, synthesizes each item, applies the
  current volume, and plays it, polling `AudioPlayerPort.is_playing` to
  know when to advance. Three distinct ways to stop it —
  `skip()` (stop current, keep the rest), `clear()` (drop the rest, let
  current finish), `interrupt()` (both — what a future
  `VoicePipeline.interrupt()`/barge-in would call) — plus
  `set_volume()`, which applies live via pure-stdlib PCM gain scaling
  (`speech.audio.apply_gain`, no numpy needed), affecting every future
  dequeue with no resynthesis required. Has **zero required
  dependencies**, same property as `StreamingTranscriber`.

```python
from jarvis.core.config.voice_config import SpeechQueueConfig
from jarvis.core.speech import PiperTextToSpeech, SpeechQueue

speech_queue = SpeechQueue(
    tts=PiperTextToSpeech(voice_config.tts),
    player=my_audio_player,          # any AudioPlayerPort, real or fake
    config=voice_config.queue,
    initial_volume=voice_config.tts.volume,
)
speech_queue.start()

speech_queue.enqueue("Hello, how can I help?")
speech_queue.enqueue("The weather is sunny today.")
# ... user starts talking over the assistant ...
speech_queue.interrupt()             # stop now, drop "The weather..." entirely

speech_queue.set_volume(0.5)         # takes effect on the next item spoken
speech_queue.close()
```

## The speech module: wake word detection (openWakeWord)

`OpenWakeWordDetector` is Phase 8's real implementation of the new
`WakeWordPort` interface, plus — unlike Phases 6-7 — a change to
`VoicePipeline` itself: it now takes a required `wake_word: WakeWordPort`
dependency, gains a `WAITING_FOR_WAKE_WORD` state, and its contract
specifies that a concrete implementation feeds audio through
`wake_word.process()` (not `vad`/`stt`) while idle, only escalating to
full listening once a word fires — and returns to
`WAITING_FOR_WAKE_WORD` (not `IDLE`) once a conversation ends, so no
manual restart is needed. Still not wired into `main.py`/the
orchestrator.

- **`OpenWakeWordDetector`** — backed by
  [openWakeWord](https://github.com/dscripka/openWakeWord); the
  model(s) load once (lazily, on first `process()` call).
  `voice.yaml`'s `wake_word.models` is a list — built-in names (e.g.
  `hey_jarvis`) and/or paths to custom-trained `.onnx`/`.tflite`
  models, scored simultaneously, which is how multiple/custom wake
  words are supported. A per-model cooldown
  (`wake_word.cooldown_seconds`, tracked in fed-audio seconds, not
  wall-clock) suppresses immediate re-triggering from a sustained
  utterance or speaker echo.

```python
from jarvis.core.config.voice_config import WakeWordConfig
from jarvis.core.speech import OpenWakeWordDetector

detector = OpenWakeWordDetector(voice_config.wake_word)

for chunk in audio_chunks:            # 16kHz mono 16-bit PCM, any AudioChunk source
    name = detector.process(chunk)
    if name is not None:
        print("wake word detected:", name)
        detector.reset()              # clear buffering/cooldown before waiting again
```

`openwakeword`/`numpy` are imported lazily — only the first real call
to `process()` needs them installed (`pip install -r
requirements-voice.txt`). See `docs/architecture.md`'s Phase 8 section
for why this phase — unlike Phases 6-7 — required extending
`VoicePipeline`'s own contract rather than only adding a new port
implementation.

`piper-tts` is imported lazily — only the first real `synthesize()`
call needs it installed (`pip install -r requirements-voice.txt`);
`SpeechQueue`'s own queueing/interruption/volume logic works and is
tested (against a timer-based fake player) without it. See
`docs/architecture.md`'s Phase 7 section for why volume is a live
playback-time concern while speed is a fixed synthesis-time one, and
why `SpeechQueue` polls rather than requiring `AudioPlayerPort` to
support a completion callback.

## How the orchestrator routes a request

1. `POST /message {"text": ..., "session_id": ...}` calls
   `Orchestrator.handle()` — the one request-handling pipeline used by
   the API today and any future CLI/voice loop.
2. `PatternIntentRecognizer` matches the text against patterns
   registered by plugins in the `CapabilityRegistry`.
3. If a capability matches, its handler runs with a `CapabilityContext`
   giving it the request, session, recalled memory, and the
   `MemoryPort`/`AutomationPort`/`FilesystemPort` interfaces — never a
   concrete plugin, memory, automation, or filesystem implementation.
4. If nothing matches, the response comes back `handled: false` — a
   normal outcome, not an error.

See `docs/architecture.md`'s Phase 2 section for the full pipeline
diagram and the reasoning behind each design choice (DI, `Protocol`
ports, Null Object defaults, the capability registry).

## Adding a plugin

A plugin subclasses `jarvis.plugins.base.PluginBase` and, in
`on_load(container, events)`, resolves the `CapabilityRegistry` from
the container and registers whatever it wants the orchestrator to be
able to route to:

```python
from jarvis.orchestrator.capability_registry import CapabilityRegistry

class GreeterPlugin(PluginBase):
    name = "greeter"

    def on_load(self, container, events) -> None:
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "greet",
            self._handle_greet,
            patterns=[r"\bhello\b", r"\bhi\b"],
            plugin=self.name,
        )

    def on_unload(self, container, events) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _handle_greet(self, context):
        return CapabilityResult(text=f"Hello! You said: {context.request.text}")
```

See `tests/test_plugin_orchestrator_integration.py` for a complete,
runnable version of this example, and `plugins/README.md` for where to
put external (user-installed) plugins.

## The Cowork integration layer

`core/cowork/` (Phase 9) is what makes Jarvis a system-wide AI
operating layer rather than a single-agent assistant: when no local
capability matches, `Orchestrator` offers the request to Claude
Cowork for planning, then executes the returned plan itself. Cowork's
response is inert typed data — it cannot execute anything.

```python
from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.cowork import CoworkClient, HttpCoworkTransport, CoworkTaskRequest

config = CoworkConfig(enabled=True)
client = CoworkClient(transport=HttpCoworkTransport(config), config=config)

response = client.submit(
    CoworkTaskRequest(session_id="s1", instruction="organize my downloads folder")
)
for step in response.steps:
    print(step.action_type, step.description)  # Jarvis, not Cowork, executes these
```

Disabled by default (`cowork.yaml`'s `enabled: false`); `main.bootstrap()`
wires in `NullCoworkClientPort` — an empty-plan stand-in — until a
deployment opts in and sets the `COWORK_API_KEY` environment variable.
See `docs/architecture.md`'s Phase 9 section for the full rationale,
including why the OS-access boundary is structural rather than a
runtime permission check.

## The Prompt Registry

Each Cowork collaborator's prompt (Phase 10's `CollaboratorRole`s —
Architect, Planner, Coder, Researcher, Memory Manager, Automation
Engineer, Documentation Engineer, QA Engineer) is sourced from a
Markdown file under `prompts/`, not hardcoded in Python:

```python
from pathlib import Path
from jarvis.core.cowork import PromptRegistry, CoworkWorkspace

registry = PromptRegistry(Path("prompts"))
workspace = CoworkWorkspace(inner=cowork_client, prompt_registry=registry)
```

Edit `prompts/coder.md` and the next Cowork request routed to the
Coder role uses the new text — no restart, no code change.
`prompts/system.md` is prepended to every collaborator's rendered
prompt as a shared preamble. Falls back to the hardcoded template in
`COLLABORATOR_SPECS` (`core/cowork/collaborators.py`) if a file — or
the whole `prompts/` directory — is missing, so this is fully optional:
omit `prompt_registry` entirely and behavior is unchanged from Phase
10. Always constructed in `main.bootstrap()` (`settings.yaml`'s
`paths.prompts_dir`, default `prompts/`), the same "always real,
built-in fallback" pattern `WorkflowEngine` uses. See `prompts/README.md`
for the full file-to-role mapping and `docs/architecture.md`'s Phase 22
section for the scoping decisions behind it.

## The Security Manager

`container.resolve(SecurityManager)` is the one gate every action —
Cowork-originated or otherwise — passes through before it reaches
`ExecutionEngine`:

```python
from jarvis.core.security import SecurityManager, SecurityRequest

security = container.resolve(SecurityManager)

decision = security.authorize(
    SecurityRequest(category="filesystem", action="delete", requested_by="cowork")
)
if not decision.allowed:
    print(decision.reason)  # e.g. "confirmation was declined"

# Emergency shutdown: denies every request immediately until resumed.
security.trigger_emergency_shutdown("suspicious activity detected")
security.resume("resolved")

# Session history + durable audit log, per requester.
security.session_history_for("cowork")
security.audit_log()
```

Always constructed in `main.bootstrap()` (no `enabled` flag — pure
local logic with no external backend) and wired into
`ExecutionEngineAdapter`, which calls `authorize()` before
`ExecutionEngine.execute()` — a denial means the engine is never
invoked. No confirmation UI exists yet, so `AutoDenyConfirmation` is
the default (fails closed); pass a `CallbackConfirmation` to wire in a
real yes/no surface. See `docs/architecture.md`'s Phase 19 section for
the full check order and the scope-string sharing bug live testing
caught between `SecurityManager` and `ExecutionEngine`.

## The Autonomous Workflow engine

`container.resolve(WorkflowEngine)` creates, edits, runs, and tracks
history for multi-step, optionally-scheduled `Workflow`s:

```python
from jarvis.core.workflow import WorkflowEngine, WorkflowRunner, WorkflowStep
from jarvis.core.workflow import WorkflowSchedule, WorkflowCondition, ConditionType

engine = container.resolve(WorkflowEngine)

workflow = engine.create_workflow(
    "nightly cleanup",
    steps=[
        WorkflowStep(id="scan", name="scan temp dir", action="filesystem.search"),
        WorkflowStep(
            id="delete", name="delete old files", action="filesystem.delete",
            depends_on=("scan",),
        ),
        WorkflowStep(  # runs even if the steps above failed
            id="notify", name="notify on failure", action="filesystem.write",
            depends_on=("delete",),
            condition=WorkflowCondition(type=ConditionType.ON_FAILURE, step_id="delete"),
        ),
    ],
    schedule=WorkflowSchedule(cron="0 2 * * *"),  # daily at 02:00
)

run = engine.run_workflow(workflow.id)  # synchronous
print(run.status, {sid: r.status for sid, r in run.step_results.items()})

# Background execution instead:
runner = container.resolve(WorkflowRunner)
runner.submit(workflow.id)

# History and visualization:
engine.list_runs(workflow.id)
print(engine.render_mermaid(workflow.id, run=run))
```

`WorkflowScheduler` (also always running, `container.resolve(...)`)
polls every scheduled, enabled workflow and submits due ones to
`WorkflowRunner` automatically — nothing above needs to call
`run_workflow()` for a scheduled workflow. Claude Cowork generates
plans, Jarvis owns and executes them:
`engine.workflow_from_cowork_response(response)` turns a
`CoworkTaskResponse` into a saved, runnable workflow.

Always constructed in `main.bootstrap()` (no `enabled` flag, like
`PlanningEngine`/`SecurityManager`). Steps execute via
`AutomationWorkflowActionPort`, which delegates to the same
`AutomationPort` every other action already goes through — a workflow
step passes through the exact same Phase 19 `SecurityManager` gate,
with no second path. See `docs/architecture.md`'s Phase 20 section for
the full design rationale, including why conditional execution needed
its own rule and why cron is hand-rolled.
