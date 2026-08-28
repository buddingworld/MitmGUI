"""Configuration manager for mitmgui.

Reads/writes Config.json in the current working directory.
"""

import json
import os
import sys


class AppConfig:
    """Application-wide configuration persisted to Config.json."""

    # Use current working directory, or exe directory when frozen
    _CONFIG_FILE = os.path.join(
        os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
        else os.getcwd(),
        "Config.json",
    )

    DEFAULTS = {
        "https": {
            "decrypt": False,
            "cert_path": "",
            "cert_passphrase": "",
        },
        "connections": {
            "listen_host": "127.0.0.1",
            "listen_port": 8080,
        },
        "gateway": {
            "mode": "no_proxy",  # "system", "manual", "no_proxy"
            "manual_proxy": "http://127.0.0.1:8888",
        },
        "settings": {
            "auto_adjust_content_length": True,
            "ssl_insecure": True,
            "theme": "default",
            "window_geometry": None,  # [x, y, width, height] or None
            "window_maximized": False,
            "raw_encoding": "utf-8",
            "raw_font_zoom": -2,  # QScintilla zoom level for Raw / New Session
            "raw_word_wrap": True,  # Word Wrap for Raw editors (on by default)
            "session_list_font_size": 15,
        },
        "sendto": [
            {"name": "Fiddler", "address": "http://127.0.0.1:8888"},
        ],
    }

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge with defaults in case new keys were added
            return self._deep_merge(self.DEFAULTS, loaded)
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(self.DEFAULTS)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._CONFIG_FILE), exist_ok=True)
        with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = AppConfig._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    # ── HTTPS ──

    @property
    def decrypt_https(self) -> bool:
        return self._data["https"]["decrypt"]

    @decrypt_https.setter
    def decrypt_https(self, val: bool) -> None:
        self._data["https"]["decrypt"] = val

    @property
    def cert_path(self) -> str:
        return self._data["https"]["cert_path"]

    @cert_path.setter
    def cert_path(self, val: str) -> None:
        self._data["https"]["cert_path"] = val

    @property
    def cert_passphrase(self) -> str:
        return self._data["https"]["cert_passphrase"]

    @cert_passphrase.setter
    def cert_passphrase(self, val: str) -> None:
        self._data["https"]["cert_passphrase"] = val

    # ── Connections ──

    @property
    def listen_host(self) -> str:
        return self._data["connections"]["listen_host"]

    @listen_host.setter
    def listen_host(self, val: str) -> None:
        self._data["connections"]["listen_host"] = val

    @property
    def listen_port(self) -> int:
        return self._data["connections"]["listen_port"]

    @listen_port.setter
    def listen_port(self, val: int) -> None:
        self._data["connections"]["listen_port"] = val

    # ── Gateway ──

    @property
    def gateway_mode(self) -> str:
        return self._data["gateway"]["mode"]

    @gateway_mode.setter
    def gateway_mode(self, val: str) -> None:
        self._data["gateway"]["mode"] = val

    @property
    def manual_proxy(self) -> str:
        return self._data["gateway"]["manual_proxy"]

    @manual_proxy.setter
    def manual_proxy(self, val: str) -> None:
        self._data["gateway"]["manual_proxy"] = val

    # ── Settings ──

    @property
    def auto_adjust_content_length(self) -> bool:
        return self._data["settings"]["auto_adjust_content_length"]

    @auto_adjust_content_length.setter
    def auto_adjust_content_length(self, val: bool) -> None:
        self._data["settings"]["auto_adjust_content_length"] = val

    @property
    def ssl_insecure(self) -> bool:
        return self._data["settings"]["ssl_insecure"]

    @ssl_insecure.setter
    def ssl_insecure(self, val: bool) -> None:
        self._data["settings"]["ssl_insecure"] = val

    @property
    def theme(self) -> str:
        return self._data["settings"]["theme"]

    @theme.setter
    def theme(self, val: str) -> None:
        self._data["settings"]["theme"] = val

    @property
    def window_geometry(self) -> list[int] | None:
        return self._data["settings"].get("window_geometry")

    @window_geometry.setter
    def window_geometry(self, val: list[int] | None) -> None:
        self._data["settings"]["window_geometry"] = val

    @property
    def window_maximized(self) -> bool:
        return bool(self._data["settings"].get("window_maximized"))

    @window_maximized.setter
    def window_maximized(self, val: bool) -> None:
        self._data["settings"]["window_maximized"] = bool(val)

    @property
    def raw_encoding(self) -> str:
        # Keep reading the key used by older mitmgui builds so an existing
        # encoding choice is not lost after upgrading.
        settings = self._data["settings"]
        return settings.get("raw_encoding", settings.get("encoding", "utf-8"))

    @raw_encoding.setter
    def raw_encoding(self, val: str) -> None:
        self._data["settings"]["raw_encoding"] = val
        # Remove the legacy key once the setting is saved under its current
        # name, avoiding two competing defaults in Config.json.
        self._data["settings"].pop("encoding", None)

    @property
    def raw_font_zoom(self) -> int:
        return int(self._data["settings"].get("raw_font_zoom", -2))

    @raw_font_zoom.setter
    def raw_font_zoom(self, val: int) -> None:
        self._data["settings"]["raw_font_zoom"] = int(val)

    @property
    def raw_word_wrap(self) -> bool:
        return bool(self._data["settings"].get("raw_word_wrap", True))

    @raw_word_wrap.setter
    def raw_word_wrap(self, val: bool) -> None:
        self._data["settings"]["raw_word_wrap"] = bool(val)

    @property
    def session_list_font_size(self) -> int:
        return int(self._data["settings"].get("session_list_font_size", 15))

    @session_list_font_size.setter
    def session_list_font_size(self, val: int) -> None:
        self._data["settings"]["session_list_font_size"] = int(val)

    # ── SendTo ──

    @property
    def sendto_entries(self) -> list[dict]:
        return self._data["sendto"]

    @sendto_entries.setter
    def sendto_entries(self, val: list[dict]) -> None:
        self._data["sendto"] = val

    # ── Convenience ──

    def apply_to_opts(self, opts) -> None:
        """Apply connection/gateway/cert settings to mitmproxy Options.

        Only sets options that need to change, exactly mirroring how
        ``mitmdump --certs X --cert-passphrase Y`` behaves at the CLI
        level.  Unset options are left at their mitmproxy defaults.
        """
        updates: dict = {}

        # Connections
        if self.listen_host != opts.listen_host:
            updates["listen_host"] = self.listen_host
        if self.listen_port != opts.listen_port:
            updates["listen_port"] = self.listen_port

        # Gateway / upstream → mode
        if self.gateway_mode == "manual" and self.manual_proxy:
            new_mode = ["upstream:" + self.manual_proxy]
        elif self.gateway_mode == "no_proxy":
            new_mode = ["regular"]
        elif self.gateway_mode == "system":
            new_mode = ["regular"]
        else:
            new_mode = list(opts.mode)
        if new_mode != list(opts.mode):
            updates["mode"] = new_mode

        # HTTPS — only set when user has explicitly opted in.
        # This mirrors ``--certs`` and ``--cert-passphrase`` CLI flags:
        # if the flag is omitted the option stays at its default ([] / None).
        if self.decrypt_https:
            if self.cert_path:
                updates["certs"] = [self.cert_path]
            if self.cert_passphrase:
                updates["cert_passphrase"] = self.cert_passphrase

        if updates:
            opts.update(**updates)

        # ssl_insecure: always apply (not in changes dict since it doesn't require restart)
        if self.ssl_insecure != opts.ssl_insecure:
            opts.update(ssl_insecure=self.ssl_insecure)
