"""Built-in plugin namespace.

Plugins that ship as part of Jarvis itself live here as submodules,
one package per plugin (e.g. ``jarvis.plugins.voice``, added in a
later phase). Nothing is defined here yet in Phase 1 — this package
only exists so the plugin loader has a namespace to scan.

User-installed / third-party plugins do NOT go here; they live in the
external directory configured by ``paths.plugins_dir`` (default:
``<project_root>/plugins/``) and are discovered separately, by path,
so they can be added or removed without touching this package at all.
"""
