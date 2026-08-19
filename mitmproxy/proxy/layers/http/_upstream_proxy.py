import time
from logging import DEBUG

from h11._receivebuffer import ReceiveBuffer

from mitmproxy import connection
from mitmproxy import http
from mitmproxy.net.http import http1
from mitmproxy.proxy import commands
from mitmproxy.proxy import context
from mitmproxy.proxy import layer
from mitmproxy.proxy import tunnel
from mitmproxy.proxy.layers import tls
from mitmproxy.proxy.layers.http._hooks import HttpConnectUpstreamHook
from mitmproxy.utils import human


class Socks5UpstreamProxy(tunnel.TunnelLayer):
    def __init__(
        self,
        ctx: context.Context,
        tunnel_conn: connection.Server,
        auth: tuple[str, str] | None,
    ):
        super().__init__(ctx, tunnel_connection=tunnel_conn, conn=ctx.server)
        self.buf = bytearray()
        self.auth = auth
        self.stage = "greeting"

    def start_handshake(self) -> layer.CommandGenerator[None]:
        methods = b"\x00\x02" if self.auth else b"\x00"
        yield commands.SendData(
            self.tunnel_connection, b"\x05" + bytes([len(methods)]) + methods
        )

    def receive_handshake_data(
        self, data: bytes
    ) -> layer.CommandGenerator[tuple[bool, str | None]]:
        self.buf.extend(data)
        if self.stage == "greeting":
            if len(self.buf) < 2:
                return False, None
            if self.buf[0] != 5:
                return False, "SOCKS5 upstream proxy returned an invalid version"
            method = self.buf[1]
            del self.buf[:2]
            if method == 0 and self.auth is None:
                yield from self._send_connect_request()
            elif method == 2 and self.auth is not None:
                username = self.auth[0].encode("utf-8")
                password = self.auth[1].encode("utf-8")
                if len(username) > 255 or len(password) > 255:
                    return False, "SOCKS5 username or password is too long"
                self.stage = "auth"
                yield commands.SendData(
                    self.tunnel_connection,
                    b"\x01"
                    + bytes([len(username)])
                    + username
                    + bytes([len(password)])
                    + password,
                )
            else:
                return False, "SOCKS5 upstream proxy authentication failed"

        if self.stage == "auth":
            if len(self.buf) < 2:
                return False, None
            version, status = self.buf[:2]
            del self.buf[:2]
            if version != 1 or status != 0:
                return False, "SOCKS5 upstream proxy authentication failed"
            yield from self._send_connect_request()

        if self.stage == "connect":
            if len(self.buf) < 4:
                return False, None
            if self.buf[0] != 5:
                return False, "SOCKS5 upstream proxy returned an invalid version"
            address_type = self.buf[3]
            if address_type == 3 and len(self.buf) < 5:
                return False, None
            address_length = {1: 4, 3: 1 + self.buf[4], 4: 16}.get(address_type)
            if address_length is None:
                return False, "SOCKS5 upstream proxy returned an invalid address type"
            response_length = 4 + address_length + 2
            if len(self.buf) < response_length:
                return False, None
            reply = self.buf[1]
            del self.buf[:response_length]
            if reply != 0:
                return False, f"SOCKS5 upstream proxy refused connection ({reply})"
            if self.buf:
                yield from self.receive_data(bytes(self.buf))
                self.buf.clear()
            return True, None
        return False, None

    def _send_connect_request(self) -> layer.CommandGenerator[None]:
        host = self.conn.address[0].encode("idna")
        if len(host) > 255:
            raise ValueError("Target hostname is too long for SOCKS5")
        request = b"\x05\x01\x00\x03" + bytes([len(host)]) + host
        request += self.conn.address[1].to_bytes(2, "big")
        self.stage = "connect"
        yield commands.SendData(self.tunnel_connection, request)


class HttpUpstreamProxy(tunnel.TunnelLayer):
    buf: ReceiveBuffer
    send_connect: bool
    conn: connection.Server
    tunnel_connection: connection.Server

    def __init__(
        self, ctx: context.Context, tunnel_conn: connection.Server, send_connect: bool
    ):
        super().__init__(ctx, tunnel_connection=tunnel_conn, conn=ctx.server)
        self.buf = ReceiveBuffer()
        self.send_connect = send_connect

    @classmethod
    def make(cls, ctx: context.Context, send_connect: bool) -> tunnel.LayerStack:
        assert ctx.server.via
        scheme, address = ctx.server.via
        assert scheme in ("http", "https", "socks5")

        upstream_proxy = connection.Server(address=address)

        stack = tunnel.LayerStack()
        if scheme == "socks5":
            stack /= Socks5UpstreamProxy(ctx, upstream_proxy, ctx.server.via_auth)
        else:
            if scheme == "https":
                upstream_proxy.alpn_offers = tls.HTTP1_ALPNS
                upstream_proxy.sni = address[0]
                stack /= tls.ServerTLSLayer(ctx, upstream_proxy)
            stack /= cls(ctx, upstream_proxy, send_connect)

        return stack

    def start_handshake(self) -> layer.CommandGenerator[None]:
        if not self.send_connect:
            return (yield from super().start_handshake())
        assert self.conn.address
        flow = http.HTTPFlow(self.context.client, self.tunnel_connection)
        authority = (
            self.conn.address[0].encode("idna") + f":{self.conn.address[1]}".encode()
        )
        headers = http.Headers()
        if self.context.options.http_connect_send_host_header:
            headers.insert(0, b"Host", authority)
        flow.request = http.Request(
            host=self.conn.address[0],
            port=self.conn.address[1],
            method=b"CONNECT",
            scheme=b"",
            authority=authority,
            path=b"",
            http_version=b"HTTP/1.1",
            headers=headers,
            content=b"",
            trailers=None,
            timestamp_start=time.time(),
            timestamp_end=time.time(),
        )
        yield HttpConnectUpstreamHook(flow)
        raw = http1.assemble_request(flow.request)
        yield commands.SendData(self.tunnel_connection, raw)

    def receive_handshake_data(
        self, data: bytes
    ) -> layer.CommandGenerator[tuple[bool, str | None]]:
        if not self.send_connect:
            return (yield from super().receive_handshake_data(data))
        self.buf += data
        response_head = self.buf.maybe_extract_lines()
        if response_head:
            try:
                response = http1.read_response_head([bytes(x) for x in response_head])
            except ValueError as e:
                proxyaddr = human.format_address(self.tunnel_connection.address)
                yield commands.Log(f"{proxyaddr}: {e}")
                return False, f"Error connecting to {proxyaddr}: {e}"
            if 200 <= response.status_code < 300:
                if self.buf:
                    yield from self.receive_data(bytes(self.buf))
                    del self.buf
                return True, None
            else:
                proxyaddr = human.format_address(self.tunnel_connection.address)
                raw_resp = b"\n".join(response_head)
                yield commands.Log(f"{proxyaddr}: {raw_resp!r}", DEBUG)
                return (
                    False,
                    f"Upstream proxy {proxyaddr} refused HTTP CONNECT request: {response.status_code} {response.reason}",
                )
        else:
            return False, None
