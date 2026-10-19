"""Demo plugin showing the per-plugin settings feature.

Load it from the Plugins window, then right-click it and pick "Config" to get
a form built from ``config_schema()`` below. Saving writes
``data/Plugin_DemoConfig/config.json`` next to this file and reloads the
plugin, so ``on_load`` prints the new values again.

Everything it does is write the settings to the Logs window, so it is safe to
leave enabled.
"""

__doc_format__ = "mitmgui-plugin"

CONFIG_FILE_HINT = "data/Plugin_DemoConfig/config.json"


def info():
    return {
        "author": "MitmGUI",
        "version": "1.0",
        "description": "Demo of per-plugin settings (right-click -> Config)",
    }


def config_schema():
    """The settings shown in the Config window.

    One field per supported type:
      number   - spin box (int, or float when the default is a float)
      string   - single line text
      text     - multi-line text
      bool     - check box
      combo    - drop-down, pick one
      radio    - radio buttons, pick one
      checkbox - check boxes; "multi": True allows several, otherwise one
    """
    return [
        {
            "key": "retries",
            "label": "Retries",
            "type": "number",
            "default": 3,
            "min": 0,
            "max": 10,
            "step": 1,
            "description": "How many times to retry (0-10).",
        },
        {
            "key": "ratio",
            "label": "Ratio",
            "type": "number",
            "default": 1.5,
            "min": 0.0,
            "max": 100.0,
            "step": 0.1,
            "description": "A fractional number - the default being a float "
                           "is what selects the decimal spin box.",
        },
        {
            "key": "host",
            "label": "Host",
            "type": "string",
            "default": "example.com",
            "description": "A single-line string.",
        },
        {
            "key": "headers",
            "label": "Extra headers",
            "type": "text",
            "default": "X-Demo: 1\nX-Another: two",
            "description": "A multi-line string, one header per line.",
        },
        {
            "key": "verbose",
            "label": "Verbose",
            "type": "bool",
            "default": True,
            "description": "A simple on/off switch.",
        },
        {
            "key": "mode",
            "label": "Mode",
            "type": "combo",
            "choices": ["passive", "active", "off"],
            "default": "passive",
            "description": "Pick one from a drop-down.",
        },
        {
            "key": "scope",
            "label": "Scope",
            "type": "radio",
            "choices": ["all", "in-scope only", "custom"],
            "default": "in-scope only",
            "description": "Pick exactly one (radio buttons).",
        },
        {
            "key": "methods",
            "label": "Methods",
            "type": "checkbox",
            "choices": ["GET", "POST", "PUT", "DELETE"],
            "default": ["GET", "POST"],
            "multi": True,
            "description": "Pick any number - the value is a list.",
        },
        {
            "key": "fallback",
            "label": "Fallback method",
            "type": "checkbox",
            "choices": ["GET", "POST", "HEAD"],
            "default": "GET",
            "multi": False,
            "description": "Pick one - the value is a single string.",
        },
    ]


def _describe(config) -> str:
    """One readable line per setting, for the Logs window."""
    lines = [f"{key} = {value!r}" for key, value in config.items()]
    return " | ".join(lines)


def on_load(api):
    """Called on load, on enable, and again after the settings are saved."""
    config = load_config()
    api.logs.add(f"DemoConfig loaded from {CONFIG_FILE_HINT}")
    api.logs.add(f"DemoConfig values: {_describe(config)}")
    # The same dict is available through the api object.
    assert api.load_config() == config


def on_unload(api):
    api.logs.add("DemoConfig unloaded")


def request(flow, api):
    """Uses one of the settings, so a change is visible on the next request."""
    config = load_config()
    if not config.get("verbose"):
        return
    api.logs.debug(
        f"DemoConfig: {flow.request.method} {flow.request.pretty_url} "
        f"(mode={config.get('mode')}, retries={config.get('retries')})"
    )
