# External plugins

Drop third-party or user-authored plugins here — either as a single
`.py` file or a package directory containing `__init__.py`. Each must
define at least one subclass of `jarvis.plugins.base.PluginBase`.

This directory is scanned by `PluginLoader` at every startup
(`paths.plugins_dir` in config). It is **not** part of the Jarvis
package itself (see `src/jarvis/plugins/` for built-in plugins), so
plugins here can be added, removed, or swapped without touching
Jarvis's source tree or requiring a reinstall.

Nothing is loaded from this directory until a plugin is actually
placed here — it is intentionally empty in Phase 1.
