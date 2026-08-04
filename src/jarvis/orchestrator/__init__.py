"""The central assistant orchestrator.

This package is the one place in Jarvis that knows how to take a raw
request ("what did the user say/type/send") and turn it into a
response, by:

  - recognizing what the user wants (an Intent), via a pluggable
    IntentRecognizer;
  - finding which plugin capability handles that intent, via the
    CapabilityRegistry (populated by plugins at load time, never
    hardcoded here);
  - maintaining short-lived conversation state per session, via the
    SessionStore;
  - giving the chosen capability handler access to memory and
    automation *ports* (abstract interfaces), never concrete
    implementations.

Nothing in this package imports a concrete plugin, a concrete memory
backend, or a concrete automation backend. Those are supplied via
dependency injection (see main.bootstrap()), which is what lets the
orchestrator stay correct and testable while every other phase adds
real plugins, a real memory backend, and real automation underneath it.
"""
