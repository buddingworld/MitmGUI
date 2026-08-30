"""Plugin management for MitmGUI.

Plugins are standalone Python files loaded at runtime. Each plugin may
define hook functions (or a ``Plugin`` class with the same methods):

    def request(flow, api): ...
    def response(flow, api): ...
    def websocket_message(flow, message, api): ...
    def on_load(api): ...      # called when the plugin is loaded / enabled
    def on_unload(api): ...    # called when it is disabled / unloaded

``info()`` (module-level function, optional) returns plugin metadata shown
in the Plugins dialog; it may return a plain string or a dict such as
{"author": ..., "version": ..., "description": ...}.

``api`` is a :class:`PluginAPI` instance exposing:

    api.view              session list read/write (all / find / add / remove / edit)
    api.logs.add(msg, log_type="Info", log_comment=None)   # Logs Plugin tab
    api.logs.info/error/debug(msg)
    api.session.new_session()          # open the New Session dialog

The plugin hooks run *after* the Auto Rules / rules.py handlers because
the ``_PluginsAddon`` is registered last.
"""

import importlib.util
import json
import os
import sys
import threading

PLUGINS_FILE = os.path.join(os.getcwd(), "plugins.json")

HOOKS = ("request", "response", "websocket_message", "on_load", "on_unload")


class PluginEntry:
    """A single loaded plugin."""

    def __init__(self, name: str, path: str, enabled: bool = True):
        self.name = name
        self.path = path
        self.enabled = bool(enabled)
        self.module = None
        self.instance = None  # Plugin class instance, or the module (functional style)
        self.api = None
        self.info = ""


def _load_plugin_module(path: str):
    """Import a plugin file. Returns (name, module, instance)."""
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot create a module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    cls = getattr(module, "Plugin", None)
    instance = cls() if isinstance(cls, type) else module
    return name, module, instance


def _extract_info(module) -> str:
    fn = getattr(module, "info", None)
    if not callable(fn):
        return ""
    try:
        value = fn()
    except Exception as e:  # noqa: BLE001 - plugin error must not break loading
        return f"(info error: {e})"
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


class PluginViewAPI:
    """Read/write access to the session list (delegates to master.view)."""

    def __init__(self, master, addon):
        self._master = master
        self._addon = addon

    def all(self) -> list:
        return list(self._master.view)

    def find(self, predicate) -> list:
        return [f for f in self._master.view if predicate(f)]

    def add(self, flow) -> None:
        self._master.view.add([flow])

    def remove(self, flow_id) -> None:
        flow = self._master.view.get_by_id(flow_id)
        if flow is not None:
            self._master.view.remove([flow])

    def edit(self, flow_id, *, request=None, response=None) -> None:
        flow = self._master.view.get_by_id(flow_id)
        if flow is None:
            return
        if request is not None:
            flow.request = request
        if response is not None:
            flow.response = response
        self._master.view.update([flow])

    def set_bgcolor(self, flow, color) -> None:
        """Set the session-list background color for a flow (e.g. "#ffc2fd").

        The color is stashed in the flow metadata so it also survives flows that
        are added to the session list after this call, and pushed to the GUI
        via the cross-thread bridge.
        """
        flow.metadata["_plugin_color"] = str(color)
        fid = getattr(flow, "id", None)
        if fid is None or self._addon.bridge is None:
            return
        self._addon.bridge.set_flow_color.emit(fid, str(color))

    def set_info(self, flow, info) -> None:
        """Set the session-list Info column value for a flow.

        ``info`` may be a plain string or a list of ``{"name", "type"}`` dicts.
        A list is rendered with color priority CMS/API (red) > Editor (blue) >
        anything else (light gray). Stashed in flow metadata so it survives
        flows added to the list after this call.
        """
        if not getattr(flow, "metadata", None):
            flow.metadata = {}
        flow.metadata["_plugin_info"] = info
        fid = getattr(flow, "id", None)
        if fid is None or self._addon.bridge is None:
            return
        self._addon.bridge.set_flow_info.emit(str(fid))


class PluginLogAPI:
    """Write to the Logs window (Plugin tab). Thread-safe via the GUI bridge."""

    def __init__(self, plugin_name: str, addon):
        self._name = plugin_name
        self._addon = addon

    def add(self, message, log_type: str = "Info", log_comment=None) -> None:
        if self._addon.bridge is not None:
            self._addon.bridge.log.emit(self._name, log_type, str(message), log_comment)

    def info(self, message) -> None:
        self.add(message, "Info")

    def error(self, message) -> None:
        self.add(message, "Error")

    def debug(self, message) -> None:
        self.add(message, "Debug")

    def plugin(self, message) -> None:
        self.add(message, "Plugin")


class PluginSessionAPI:
    """Trigger the New Session dialog on the GUI thread."""

    def __init__(self, addon):
        self._addon = addon

    def new_session(self) -> None:
        if self._addon.bridge is not None:
            self._addon.bridge.new_session.emit()


class PluginAPI:
    """Per-plugin API object passed to every hook call."""

    def __init__(self, plugin_name: str, addon):
        self._name = plugin_name
        self._addon = addon
        master = getattr(addon, "master", None)
        self.view = PluginViewAPI(master, addon) if master is not None else None
        self.logs = PluginLogAPI(plugin_name, addon)
        self.session = PluginSessionAPI(addon)

    @property
    def name(self) -> str:
        return self._name


class _PluginsAddon:
    """Loads/unloads plugins and dispatches traffic hooks to them.

    Registered after the Auto Rules addon so plugin hooks run last.
    """

    def __init__(self):
        self.plugins: list[PluginEntry] = []
        self._lock = threading.Lock()
        self.bridge = None  # set by the GUI (_PluginBridge) for Logs / New Session

    # ── registry helpers ──

    def names(self) -> list[str]:
        return [p.name for p in self.plugins]

    def get(self, name: str):
        return next((p for p in self.plugins if p.name == name), None)

    def save(self) -> None:
        data = [
            {"name": p.name, "path": p.path, "enabled": bool(p.enabled)}
            for p in self.plugins
        ]
        try:
            with open(PLUGINS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self._log("Error", f"Failed to save plugins.json: {e}")

    def load_from_file(self) -> None:
        """Load the plugins recorded in plugins.json (called at startup)."""
        try:
            with open(PLUGINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for item in data:
            path = item.get("path", "")
            if not path or not os.path.isfile(path):
                continue
            try:
                self.load_plugin(path, enabled=item.get("enabled", True), save=False)
            except Exception as e:  # noqa: BLE001
                self._log("Error", f"Failed to load plugin {path}: {e}")

    def reload_from_disk(self) -> None:
        """Discard in-memory changes and rebuild from plugins.json.

        Used by the Plugins dialog when the user clicks Cancel.
        """
        for entry in list(self.plugins):
            self.unload_plugin(entry.name, save=False)
        self.load_from_file()

    def load_plugin(self, path: str, enabled: bool = True, save: bool = False) -> PluginEntry:
        name, module, instance = _load_plugin_module(path)
        if self.get(name) is not None:
            raise ValueError(f"A plugin named '{name}' is already loaded")
        entry = PluginEntry(name, path, enabled)
        entry.module = module
        entry.instance = instance
        entry.api = PluginAPI(name, self)
        entry.info = _extract_info(module)
        if enabled:
            self._fire(entry, "on_load")
        self.plugins.append(entry)
        if save:
            self.save()
        return entry

    def unload_plugin(self, name: str, save: bool = False) -> None:
        entry = self.get(name)
        if entry is None:
            return
        self._fire(entry, "on_unload")
        self.plugins.remove(entry)
        if entry.module is not None:
            sys.modules.pop(entry.module.__name__, None)
        if save:
            self.save()

    def set_enabled(self, name: str, enabled: bool, save: bool = False) -> None:
        entry = self.get(name)
        if entry is None:
            return
        entry.enabled = bool(enabled)
        if entry.enabled:
            self._fire(entry, "on_load")
        else:
            self._fire(entry, "on_unload")
        if save:
            self.save()

    def move(self, name: str, delta: int, save: bool = False) -> None:
        idx = next((i for i, p in enumerate(self.plugins) if p.name == name), None)
        if idx is None:
            return
        new_idx = idx + delta
        if not (0 <= new_idx < len(self.plugins)):
            return
        self.plugins.insert(new_idx, self.plugins.pop(idx))
        if save:
            self.save()

    # ── hook dispatch ──

    def _fire(self, entry: PluginEntry, hook: str, *args) -> None:
        """Call one hook on one plugin (on_load / on_unload)."""
        fn = getattr(entry.instance, hook, None)
        if not callable(fn):
            return
        try:
            fn(*args, entry.api)
        except Exception as e:  # noqa: BLE001 - isolate plugin errors
            self._log("Error", f"Plugin {entry.name}.{hook}: {e}")

    def _dispatch(self, hook: str, *args) -> None:
        """Call one traffic hook on every enabled plugin, in registration order."""
        for p in self.plugins:
            if not p.enabled:
                continue
            fn = getattr(p.instance, hook, None)
            if not callable(fn):
                continue
            try:
                fn(*args, p.api)
            except Exception as e:  # noqa: BLE001 - isolate plugin errors
                self._log("Error", f"Plugin {p.name}.{hook}: {e}")

    # ── traffic hooks (registered via master.addons) ──

    def request(self, flow) -> None:
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        self._dispatch("request", flow)

    def response(self, flow) -> None:
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        self._dispatch("response", flow)

    def websocket_message(self, flow, message) -> None:
        self._dispatch("websocket_message", flow, message)

    # ── logging ──

    def _log(self, log_type: str, message: str) -> None:
        if self.bridge is not None:
            self.bridge.log.emit("Manager", log_type, message, None)
