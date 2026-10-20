"""Plugin management for MitmGUI.

Plugins are standalone Python files loaded at runtime. Each plugin may
define hook functions (or a ``Plugin`` class with the same methods):

    def http_connect(flow, api): ...   # CONNECT, before the tunnel is opened
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
    api.load_config()                  # this plugin's settings (see below)

Plugin settings
---------------
A plugin may declare its own settings by defining ``config_schema()`` (a
module-level function, or a ``Plugin`` method) returning a list of fields:

    def config_schema():
        return [
            {"key": "count", "type": "number", "default": 3, "min": 0, "max": 99},
            {"key": "note", "type": "string", "default": "hi"},
            {"key": "mode", "type": "combo", "choices": ["a", "b"], "default": "a"},
        ]

Field keys: ``key`` (required), ``label`` (defaults to the key), ``type``,
``default``, ``description``, ``choices``, ``min``/``max``/``step`` (numbers)
and ``multi`` (checkbox fields). Supported types are ``number``, ``string``,
``text`` (multi-line), ``bool``, ``combo``, ``radio`` (pick one) and
``checkbox`` (``multi: true`` gives a list, otherwise a single choice).

The Plugins dialog's right-click "Config" entry builds a form from that
schema. Values are stored in ``data/<plugin name>/config.json`` next to the
plugin file, and saving them reloads the plugin. Inside the plugin, call
``load_config()`` (injected into the module namespace, also available as
``api.load_config``) to read the current values; missing keys fall back to
the schema defaults.

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


#: Field types a plugin may use in ``config_schema()``.
CONFIG_TYPES = ("number", "string", "text", "bool", "combo", "radio", "checkbox")


def plugin_data_dir(path: str, name: str) -> str:
    """The ``data/<plugin name>`` directory that belongs to a plugin file.

    Resolved next to the plugin itself, so a plugin folder can be moved (or
    copied to another machine) with its settings.
    """
    return os.path.join(os.path.dirname(os.path.abspath(path)), "data", name)


def _extract_config_schema(module) -> list[dict]:
    """The plugin's declared settings, normalised, or [] when it has none."""
    fn = getattr(module, "config_schema", None)
    if not callable(fn):
        return []
    try:
        raw = fn()
    except Exception:  # noqa: BLE001 - a broken schema must not break loading
        return []
    if not isinstance(raw, (list, tuple)):
        return []

    fields: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key or key in seen:
            continue
        field_type = item.get("type", "string")
        if field_type not in CONFIG_TYPES:
            field_type = "string"
        field = {
            "key": key,
            "label": str(item.get("label") or key),
            "type": field_type,
            "default": item.get("default"),
            "description": str(item.get("description") or ""),
        }
        if field_type in ("combo", "radio", "checkbox"):
            choices = item.get("choices")
            field["choices"] = [str(c) for c in choices] if isinstance(choices, (list, tuple)) else []
        if field_type == "checkbox":
            field["multi"] = bool(item.get("multi", False))
        if field_type == "number":
            for bound in ("min", "max", "step"):
                if isinstance(item.get(bound), (int, float)):
                    field[bound] = item[bound]
        if field["default"] is None:
            field["default"] = _default_for(field)
        seen.add(key)
        fields.append(field)
    return fields


def _default_for(field: dict):
    """A sensible default when the schema does not give one."""
    field_type = field["type"]
    if field_type == "number":
        return 0
    if field_type == "bool":
        return False
    if field_type in ("combo", "radio"):
        choices = field.get("choices") or []
        return choices[0] if choices else ""
    if field_type == "checkbox":
        return [] if field.get("multi") else ""
    return ""


def _coerce(value, field: dict):
    """Fit a stored value to its field, falling back to the default."""
    field_type = field["type"]
    default = field["default"]
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return value
    if field_type == "bool":
        return bool(value) if isinstance(value, bool) else default
    if field_type == "checkbox":
        choices = field.get("choices") or []
        if field.get("multi"):
            if not isinstance(value, list):
                return default
            return [v for v in value if v in choices]
        return value if isinstance(value, str) and value in choices else default
    if field_type in ("combo", "radio"):
        choices = field.get("choices") or []
        return value if isinstance(value, str) and value in choices else default
    if isinstance(value, str):
        return value
    return default


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

    def load_config(self) -> dict:
        """This plugin's settings, with the schema defaults filled in."""
        return self._addon.load_config(self._name)

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
        # The settings file lives next to the plugin, so it must be reachable
        # before on_load runs (plugins often read their settings there).
        self.plugins.append(entry)
        self._inject_load_config(entry)
        if enabled:
            self._fire(entry, "on_load")
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

    def reload_plugin(self, name: str) -> None:
        """Re-import a plugin in place, keeping its position and enabled state.

        There is no importlib.reload here on purpose: the file is executed
        afresh into a new module object, so top-level state is rebuilt the way
        it is on a first load (which is what a settings change needs).
        """
        entry = self.get(name)
        if entry is None:
            return
        idx = self.plugins.index(entry)
        path, enabled = entry.path, entry.enabled
        self.unload_plugin(name, save=False)
        new_entry = self.load_plugin(path, enabled=enabled, save=False)
        self.plugins.remove(new_entry)
        self.plugins.insert(idx, new_entry)

    # ── plugin settings ──

    def config_schema(self, name: str) -> list[dict]:
        """The settings a plugin declares, or [] when it declares none."""
        entry = self.get(name)
        if entry is None or entry.module is None:
            return []
        return _extract_config_schema(entry.module)

    def config_path(self, name: str) -> str:
        entry = self.get(name)
        if entry is None:
            return ""
        return os.path.join(plugin_data_dir(entry.path, entry.name), "config.json")

    def load_config(self, name: str) -> dict:
        """A plugin's settings: what is stored, with defaults filled in."""
        entry = self.get(name)
        if entry is None:
            return {}
        schema = self.config_schema(name)
        stored = {}
        path = self.config_path(name)
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    stored = data
            except (OSError, json.JSONDecodeError):
                stored = {}
        return {f["key"]: _coerce(stored.get(f["key"], f["default"]), f) for f in schema}

    def save_config(self, name: str, values: dict) -> None:
        """Store a plugin's settings and reload it so they take effect."""
        entry = self.get(name)
        if entry is None:
            return
        schema = self.config_schema(name)
        payload = {f["key"]: _coerce(values.get(f["key"], f["default"]), f) for f in schema}
        path = self.config_path(name)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self._log("Error", f"Failed to save settings for {name}: {e}")
            return
        self.reload_plugin(name)

    def _inject_load_config(self, entry: PluginEntry) -> None:
        """Give the plugin a module-level ``load_config()`` reading its file.

        A plugin that defines its own ``load_config`` keeps it.
        """
        module = entry.module
        if module is None or callable(getattr(module, "load_config", None)):
            return

        def load_config() -> dict:
            return self.load_config(entry.name)

        load_config.__doc__ = "Return this plugin's settings (see config_schema)."
        module.load_config = load_config

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

    def http_connect(self, flow) -> None:
        """CONNECT requests, before the tunnel is opened.

        Plugins get this before mitmproxy decides where to connect, so they can
        redirect the tunnel itself - which is the only way to reach a different
        server when the original one is unreachable.
        """
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        self._dispatch("http_connect", flow)

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
