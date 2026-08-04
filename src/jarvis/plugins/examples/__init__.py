"""Reference example plugins (Phase 18): GitHub, Docker, PostgreSQL,
Obsidian, Calendar, Email — one file each, demonstrating the plugin
framework's manifest fields (dependencies/required_permissions/
description), the configure() hook, and capability registration.

Deliberately NOT imported/re-exported here: `PluginLoader._iter_builtin_modules()`
only finds `PluginBase` subclasses defined in a module's *own*
namespace (see plugin_loader.py's `_plugin_classes_in`), and this
`__init__.py` doesn't define or import any. That means these examples
are discovered as a subpackage but contribute zero plugin classes to
auto-loading — deliberately, since several of them would otherwise run
subprocess/network code on every `bootstrap()` by default. To activate
one: copy its file into your external `plugins/` directory (see
`paths.plugins_dir`), or add its module under a package on that path.
"""

from __future__ import annotations
