"""plugin_BurpFinger.py

基于 burp-finger 规则库的被动指纹识别插件。

- 仅使用 burp-finger 的被动检测逻辑（MatchingEngine）：在 request / response
  阶段对请求头、响应头、响应体、favicon hash 做指纹匹配，不进行主动探测。
- 命中结果写入会话列表新增的 Info 列：
    * CMS / API                    -> 红色
    * Editor                       -> 蓝色
    * Language / Middleware 等其它类型 -> 浅灰色
- 规则库：data/plugin_BurpFinger/fingerprints.json（与 burp-finger 相同，
  rules.index 仅用于说明规则来源）。

性能优化（参考源项目 MatchingEngine/PassiveScanner 并针对 Python 版改进）：
  1. 规则加载时预编译正则、按匹配位置（header / body / hash）分组索引；
  2. hash 规则（517 条 favicon 指纹）仅在响应为图标类内容时才计算 hash；
  3. 非图标的二进制数据文件（image/*、video/*、application/octet-stream 等）
     跳过 body 与 hash 检测；
  4. 超过 512KB 的非图标 body 跳过 body 匹配；
  5. 同一 URL 只做一次被动检测（URL 级去重），同一 flow 的 request 只扫一次；
  6. 同一指纹任一规则命中后，跳过该指纹其余规则（规则间为 OR）。
"""

import base64
import hashlib
import json
import os
import re
import threading

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PLUGIN_DIR, "data", "plugin_BurpFinger")
_RULES_FILE = os.path.join(_DATA_DIR, "fingerprints.json")

# 超过该大小的非图标 body 跳过匹配（图标类内容很小，不受此限制）。
_MAX_BODY_SCAN = 512 * 1024
# 图标 hash 计算的上限，避免个别异常巨大的图标拖慢代理。
_MAX_ICON_SCAN = 2 * 1024 * 1024

_ICON_CONTENT_TYPES = frozenset(
    {"image/x-icon", "image/vnd.microsoft.icon", "image/ico"}
)
# 命中这些 content-type 前缀/值的响应视为二进制，跳过 body 与 hash 匹配。
_BINARY_HINTS = (
    "video/", "audio/", "font/",
    "application/octet-stream", "application/zip", "application/gzip",
    "application/x-gzip", "application/pdf", "application/x-tar",
    "application/x-rar-compressed", "application/x-7z-compressed",
    "application/vnd", "application/msword", "application/java-archive",
    "application/x-msdownload", "application/x-dosexec",
)
# 含这些字符的 match 模式视为正则，否则按字面量（大小写不敏感）快速匹配。
_REGEX_CHARS = set(r".^$*+?{}[]\|()")

_lock = threading.Lock()


def info():
    return {
        "author": "burp-finger",
        "version": "1.0",
        "description": "被动指纹识别（基于 burp-finger 规则库）",
    }


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _compile_match(pattern: str):
    """将单个 match 模式编译为 (kind, needle)。

    kind == "lit" 时使用大小写不敏感的子串匹配（更快）；
    kind == "re"  时为预编译正则（IGNORECASE | DOTALL，与 Java 一致）。
    正则编译失败时回退为字面量匹配。
    """
    if any(c in _REGEX_CHARS for c in pattern):
        try:
            return ("re", re.compile(pattern, re.IGNORECASE | re.DOTALL))
        except re.error:
            return ("lit", pattern.lower())
    return ("lit", pattern.lower())


def _match_patterns(pats, candidates) -> bool:
    """AND 语义：每个 pattern 都必须在候选值中至少命中一次。"""
    if not pats:
        return False
    for kind, needle in pats:
        if kind == "lit":
            if not any(needle in v.lower() for v in candidates):
                return False
        else:
            if not any(needle.search(v) for v in candidates):
                return False
    return True


def _match_text(pats, text: str) -> bool:
    """对 body 文本做 AND 语义匹配。"""
    if not pats:
        return False
    for kind, needle in pats:
        if kind == "lit":
            if needle not in text.lower():
                return False
        else:
            if needle.search(text) is None:
                return False
    return True


def _norm_path(p: str) -> str:
    """规范化路径用于比对：去查询串、确保以 / 开头、去末尾 /、转小写。"""
    if not p:
        return ""
    if "?" in p:
        p = p.split("?", 1)[0]
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p.lower()


def _decode_body(raw: bytes, content_type: str) -> str:
    """按 Content-Type 中的 charset 解码 body；未知则用 utf-8 + replace。"""
    m = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.I)
    charset = m.group(1) if m else None
    if charset:
        try:
            return raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            pass
    return raw.decode("utf-8", "replace")


def _is_binary_ct(content_type: str) -> bool:
    """判断 content-type 是否为非图标的二进制内容。"""
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        # 图标由调用方先判断（_looks_like_icon），这里剩下的 image/* 视为二进制。
        return True
    if ct.startswith(_BINARY_HINTS):
        return True
    return False


def _looks_like_icon(path: str, content_type: str) -> bool:
    """响应是否为图标类内容（favicon），只有这类内容才值得算 hash。"""
    p = (path or "").lower()
    if p.endswith(".ico") or "favicon" in p:
        return True
    ct = (content_type or "").lower().split(";", 1)[0].strip()
    return ct in _ICON_CONTENT_TYPES


def _murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86 32-bit（seed 默认 0），返回有符号 32 位整数。

    与 Guava 的 murmur3_32_fixed().asInt() 输出一致。
    """
    c1 = 0xCC9E2D51
    c2 = 0x1B873593
    h1 = seed & 0xFFFFFFFF
    nblocks = len(data) // 4
    for i in range(nblocks):
        k1 = int.from_bytes(data[i * 4:i * 4 + 4], "little")
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h1 ^= k1
        h1 = ((h1 << 13) | (h1 >> 19)) & 0xFFFFFFFF
        h1 = (h1 * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[nblocks * 4:]
    k1 = 0
    if len(tail) >= 3:
        k1 ^= tail[2] << 16
    if len(tail) >= 2:
        k1 ^= tail[1] << 8
    if len(tail) >= 1:
        k1 ^= tail[0]
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h1 ^= k1
    h1 ^= len(data)
    h1 ^= h1 >> 16
    h1 = (h1 * 0x85EBCA6B) & 0xFFFFFFFF
    h1 ^= h1 >> 13
    h1 = (h1 * 0xC2B2AE35) & 0xFFFFFFFF
    h1 ^= h1 >> 16
    return h1 - 0x100000000 if h1 >= 0x80000000 else h1


def _favicon_hash(data: bytes) -> str:
    """Shodan 风格 favicon hash：base64 每 76 字符换行 + 末尾换行，再算 murmur3。

    与 burp-finger HashUtils.calculateFaviconHash 完全一致。
    """
    b64 = base64.b64encode(data).decode("ascii")
    sb = []
    for i, ch in enumerate(b64):
        sb.append(ch)
        if (i + 1) % 76 == 0:
            sb.append("\n")
    sb.append("\n")
    return str(_murmur3_32("".join(sb).encode("utf-8"), 0))


# ── 插件主体 ────────────────────────────────────────────────────────────────

class Plugin:
    """被动指纹识别插件。"""

    def __init__(self):
        self._loaded = False
        self._header_rules = []  # [(fp, rule)]，location == "header"
        self._body_rules = []    # [(fp, rule)]，location == "body"
        self._hash_rules = []    # [(fp, rule)]，location == "hash"
        self._status_rules = []  # [(fp, rule)]，location == "status"
        self._scanned = set()    # "req:{flow_id}" 与响应 URL 去重

    # ── 生命周期 ──

    def on_load(self, api) -> None:
        self._load_rules(api)

    def on_unload(self, api) -> None:
        with _lock:
            self._scanned.clear()

    def _load_rules(self, api) -> None:
        try:
            with open(_RULES_FILE, "r", encoding="utf-8") as f:
                fingerprints = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            api.logs.error(f"加载规则失败: {_RULES_FILE} ({e})")
            return
        self._header_rules = []
        self._body_rules = []
        self._hash_rules = []
        self._status_rules = []
        for fp in fingerprints or []:
            for rule in fp.get("rules") or []:
                rule = dict(rule)
                if rule.get("match"):
                    rule["pats"] = [_compile_match(m) for m in rule["match"]]
                loc = (rule.get("location") or "").lower()
                bucket = {
                    "header": self._header_rules,
                    "body": self._body_rules,
                    "hash": self._hash_rules,
                    "status": self._status_rules,
                }.get(loc)
                if bucket is not None:
                    bucket.append((fp, rule))
        self._loaded = True
        api.logs.info(
            f"规则已加载: {len(self._header_rules)} header / "
            f"{len(self._body_rules)} body / {len(self._hash_rules)} hash / "
            f"{len(self._status_rules)} status"
        )

    # ── 流量钩子 ──

    def request(self, flow, api) -> None:
        req = getattr(flow, "request", None)
        if req is None:
            return
        with _lock:
            key = f"req:{flow.id}"
            if key in self._scanned:
                return
            self._scanned.add(key)
        try:
            info = self._scan_headers_body(
                req.headers,
                req.get_content(strict=False),
                req.headers.get("content-type", ""),
                0,
                req.path,
            )
        except Exception:  # 插件错误不得影响代理
            return
        if info:
            self._apply_info(flow, info, api)

    def response(self, flow, api) -> None:
        req = getattr(flow, "request", None)
        resp = getattr(flow, "response", None)
        if req is None or resp is None:
            return
        url = req.pretty_url
        with _lock:
            if url in self._scanned:
                return
            self._scanned.add(url)
        content_type = resp.headers.get("content-type", "")
        path = req.path
        try:
            raw = resp.get_content(strict=False)
        except Exception:
            raw = None
        info = self._scan_headers_body(
            resp.headers, raw, content_type, resp.status_code, path
        )
        # hash 类规则（favicon 指纹）只在图标响应时执行；favicon hash / md5
        # 各计算一次后与 517 条规则的期望值比对，避免重复计算。
        if (
            raw is not None
            and self._hash_rules
            and _looks_like_icon(path, content_type)
            and len(raw) <= _MAX_ICON_SCAN
        ):
            fav_hash = _favicon_hash(raw)
            md5_hash = hashlib.md5(raw).hexdigest().lower()
            path_norm = _norm_path(path) if path else ""
            matched_names = {x["name"] for x in info}
            for fp, rule in self._hash_rules:
                name = fp.get("name")
                if name in matched_names or not self._rule_allowed(rule, path_norm, resp.status_code):
                    continue
                expected = rule.get("hash")
                if expected and (expected == fav_hash or expected.lower() == md5_hash):
                    info.append({"name": name, "type": fp.get("type", "")})
                    matched_names.add(name)
        if info:
            self._apply_info(flow, info, api)

    # ── 匹配 ──

    def _scan_headers_body(self, headers, raw, content_type, status_code, path):
        """匹配 header / body / status 类规则，返回 [{"name", "type"}, ...]。"""
        if not self._loaded:
            return []
        try:
            fields = [(n.decode("latin-1", "replace"), v.decode("latin-1", "replace"))
                      for n, v in headers.fields]
        except Exception:
            fields = []
        block = "\r\n".join(f"{n}: {v}" for n, v in fields)

        body_text = None
        if raw is not None and len(raw) <= _MAX_BODY_SCAN and not _is_binary_ct(content_type):
            body_text = _decode_body(raw, content_type)

        path_norm = _norm_path(path) if path else ""
        hits = {}
        matched = set()

        for fp, rule in self._header_rules:
            name = fp.get("name")
            if name in matched or not self._rule_allowed(rule, path_norm, status_code):
                continue
            if self._match_header(rule, fields, block):
                hits[name] = {"name": name, "type": fp.get("type", "")}
                matched.add(name)

        if body_text is not None:
            for fp, rule in self._body_rules:
                name = fp.get("name")
                if name in matched or not self._rule_allowed(rule, path_norm, status_code):
                    continue
                if _match_text(rule.get("pats", []), body_text):
                    hits[name] = {"name": name, "type": fp.get("type", "")}
                    matched.add(name)

        if status_code:
            for fp, rule in self._status_rules:
                name = fp.get("name")
                if name in matched or not self._rule_allowed(rule, path_norm, status_code):
                    continue
                if rule.get("status") == status_code:
                    hits[name] = {"name": name, "type": fp.get("type", "")}
                    matched.add(name)

        return list(hits.values())

    @staticmethod
    def _rule_allowed(rule, path_norm: str, status_code: int) -> bool:
        """path / status 前置检查（与 Java MatchingEngine.matchRule 一致）。

        规则定义了 path 时，当前请求路径必须与之精确匹配（归一化、忽略大小写）；
        规则定义了 status 时，响应状态码必须一致。
        """
        rp = rule.get("path")
        if rp and path_norm != _norm_path(rp):
            return False
        st = rule.get("status")
        if st is not None and status_code and status_code != st:
            return False
        return True

    @staticmethod
    def _match_header(rule, fields, block) -> bool:
        pats = rule.get("pats", [])
        if not pats:
            return False
        fld = rule.get("field")
        if fld:
            fld_l = fld.lower()
            candidates = [v for n, v in fields if n.lower() == fld_l]
            if not candidates:
                return False
            return _match_patterns(pats, candidates)
        return _match_patterns(pats, [block])

    # ── 输出 ──

    def _apply_info(self, flow, info, api) -> None:
        """将匹配结果写入 flow.metadata 并通知 GUI。

        - 会话列表 Info 列：``_plugin_info``（含类型，用于着色）；
        - 会话 Properties：``Finger``（匹配的 name 列表）；
        - Logs - Plugin：Type=Info，Message=匹配的 name 列表，Comment 为空。
        """
        try:
            if not getattr(flow, "metadata", None):
                flow.metadata = {}
            existing = flow.metadata.get("_plugin_info") or []
            by_name = {item["name"]: item for item in existing if isinstance(item, dict)}
            for item in info:
                by_name.setdefault(item["name"], item)
            merged = list(by_name.values())
            flow.metadata["_plugin_info"] = merged
            flow.metadata["Finger"] = [item["name"] for item in merged]
            api.view.set_info(flow, merged)
            api.logs.add(", ".join(flow.metadata["Finger"]), log_type="Info")
        except Exception:
            pass
