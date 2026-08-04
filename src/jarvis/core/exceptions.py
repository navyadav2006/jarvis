"""Root exception hierarchy for Jarvis.

Every error raised by Jarvis's own code (as opposed to a third-party
library) should subclass :class:`JarvisError`. This lets callers catch
"anything Jarvis-specific went wrong" without accidentally swallowing
unrelated exceptions (e.g. a bare ``except Exception``).
"""

from __future__ import annotations


class JarvisError(Exception):
    """Base class for all Jarvis-raised exceptions."""


class ConfigurationError(JarvisError):
    """Settings failed to load or failed validation."""


class PluginError(JarvisError):
    """Base class for plugin-related failures."""


class PluginLoadError(PluginError):
    """A plugin module could not be imported or instantiated."""


class PluginContractError(PluginError):
    """A plugin was loaded but does not satisfy the PluginBase contract."""


class PluginPermissionError(PluginError):
    """A plugin declares a `required_permissions` scope that
    permissions.yaml does not grant it.
    """


class PluginDependencyError(PluginError):
    """A plugin's declared `dependencies` are missing, unsatisfied by
    version, or form a cycle with other plugins' dependencies.
    """


class SecurityError(JarvisError):
    """Base class for all Jarvis Security Manager failures."""


class EmergencyShutdownActiveError(SecurityError):
    """SecurityManager.authorize() was called while an emergency
    shutdown is in effect. Every request is denied during a shutdown;
    this exists for callers that prefer an exception over inspecting
    the returned SecurityDecision.
    """


class ServiceNotRegisteredError(JarvisError):
    """The service container was asked to resolve a key it has no provider for."""


class FilesystemError(JarvisError):
    """Base class for all filesystem-module failures."""


class FilesystemAccessError(FilesystemError):
    """A path was denied by PathGuard: inside a protected system path,
    inside a blacklisted directory, or outside every allowed directory.
    """


class ConfirmationRequiredError(FilesystemError):
    """A destructive operation was attempted without confirmed=True."""


class FilesystemOperationError(FilesystemError):
    """The underlying OS operation failed, or an operation's own input
    validation (e.g. rename's new_name) rejected the request.
    """


class SpeechError(JarvisError):
    """Base class for all speech-module (wake word/STT/VAD/TTS) failures."""


class SpeechBackendUnavailableError(SpeechError):
    """A required optional dependency (openwakeword, pywhispercpp,
    webrtcvad, piper-tts, numpy) is not installed, or a required model
    file is missing. Raised lazily, on first real use — never at import
    time — so the rest of Jarvis works with the voice extra uninstalled.
    """


class TranscriptionTimeoutError(SpeechError):
    """A transcription call did not complete within inference_timeout_seconds."""


class NoSpeechTimeoutError(SpeechError):
    """No speech was detected within no_speech_timeout_seconds of fed audio."""


class SpeechQueueFullError(SpeechError):
    """SpeechQueue.enqueue() was called with `max_queue_size` pending
    items already queued.
    """


class CoworkError(JarvisError):
    """Base class for all Claude Cowork integration failures."""


class CoworkTimeoutError(CoworkError):
    """A Cowork request did not complete within timeout_seconds, across
    every retry attempt.
    """


class CoworkUnavailableError(CoworkError):
    """The Cowork transport is unreachable/misconfigured (e.g. missing
    API key, missing httpx, connection refused) and retries are
    exhausted.
    """


class CoworkResponseError(CoworkError):
    """Cowork returned a response that could not be parsed into a
    CoworkTaskResponse (missing/malformed fields).
    """


class VaultError(JarvisError):
    """Base class for all Obsidian vault module failures."""


class NoteNotFoundError(VaultError):
    """update_note()/read_note() was called on a path with no existing note."""


class VersionNotFoundError(VaultError):
    """rollback_note() was asked for a version_id that doesn't exist."""


class ExecutionError(JarvisError):
    """Base class for all Desktop Execution Engine failures."""


class ExecutionBackendUnavailableError(ExecutionError):
    """A required optional dependency (pyautogui, pyperclip, Pillow,
    pygetwindow) is not installed, or the requested command isn't on
    the terminal's allowlist. Raised lazily, on first real use.
    """


class UnknownActionError(ExecutionError):
    """The requested action's category or action name isn't recognized."""


class PlanningError(JarvisError):
    """Base class for all Planning Engine failures."""


class CyclicDependencyError(PlanningError):
    """A plan's task dependencies contain a cycle, so no valid
    topological ordering (and therefore no parallel-work grouping)
    exists for it.
    """


class UnknownTaskError(PlanningError):
    """A plan operation referenced a task id that isn't in the plan."""


class WorkflowError(JarvisError):
    """Base class for all Autonomous Workflow failures."""


class WorkflowNotFoundError(WorkflowError):
    """A workflow operation referenced a workflow id that doesn't exist."""


class CyclicWorkflowError(WorkflowError):
    """A workflow's step dependencies contain a cycle, so no valid
    execution order exists for it.
    """


class InvalidWorkflowScheduleError(WorkflowError):
    """A WorkflowSchedule is malformed: neither or both of
    interval_seconds/cron are set.
    """


class InvalidCronExpressionError(WorkflowError):
    """A cron expression isn't a valid 5-field expression, or never
    matches any time within the search horizon.
    """


class InvalidWorkflowConditionError(WorkflowError):
    """A WorkflowStep's condition references a step_id that isn't listed
    in its own depends_on — wave-based execution can only guarantee a
    referenced step has already finished if it's a real dependency.
    """
