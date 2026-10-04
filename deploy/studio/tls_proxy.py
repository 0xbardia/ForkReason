"""Process-scoped CONNECT proxy that redirects api.openai.com to the model stub.

GLSim hardcodes `https://api.openai.com/v1/chat/completions` with no base-URL
override. Two alternatives were rejected:

  * editing /etc/hosts — that redirect is machine-global and would break other
    services on the box that legitimately call OpenAI (orbi_bot does);
  * requiring a paid third-party key — Studio Mode must certify consensus
    mechanics without depending on external billing.

Instead GLSim is started with HTTPS_PROXY pointing at this proxy, so only
GLSim's own traffic is intercepted and nothing else on the host is affected.
CONNECT is answered locally and TLS is terminated with a test certificate
whose CA is injected into GLSim alone via REQUESTS_CA_BUNDLE.
"""

import http.server
import select
import socket
import ssl
import sys
import threading

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
STUB_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8089

# Only this host is redirected. GLSim reaches its own RPC endpoint and the
# model stub through the same proxy, so a blanket redirect would send both to
# the wrong place.
INTERCEPT_HOSTS = {"api.openai.com"}

CERT = "/root/ForkReason/deploy/studio/certs/cert.pem"
KEY = "/root/ForkReason/deploy/studio/certs/key.pem"


def pump(src: socket.socket, dst: socket.socket) -> None:
    """Copy one direction until EOF, then shutdown (not close) the write side."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def relay(a: socket.socket, b: socket.socket) -> None:
    """Relay both directions concurrently, then close both sockets once."""
    threads = [
        threading.Thread(target=pump, args=(a, b), daemon=True),
        threading.Thread(target=pump, args=(b, a), daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for s in (a, b):
        try:
            s.close()
        except OSError:
            pass


class ConnectProxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_CONNECT(self):
        """Accept the tunnel, terminate TLS, forward to the local stub."""
        # GLSim's own JSON-RPC traffic to 127.0.0.1:4000 also goes through this
        # proxy when HTTPS_PROXY is set globally. Only api.openai.com is
        # intercepted; anything else is refused rather than misrouted to the
        # model stub, which would corrupt the chain's RPC responses.
        host = self.path.split(":")[0].strip().lower()
        if host not in INTERCEPT_HOSTS:
            self.send_response(502, "Not Intercepted")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(200, "Connection Established")
        self.end_headers()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT, KEY)
        try:
            tls = ctx.wrap_socket(self.connection, server_side=True)
        except (ssl.SSLError, OSError):
            return

        try:
            upstream = socket.create_connection(("127.0.0.1", STUB_PORT), timeout=30)
        except OSError:
            tls.close()
            return

        relay(tls, upstream)

    def _plain_forward(self) -> None:
        if (self.headers.get("Host") or "").split(":")[0].lower() not in INTERCEPT_HOSTS:
            self.send_response(502, "Not Intercepted")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        try:
            upstream = socket.create_connection(("127.0.0.1", STUB_PORT), timeout=30)
            head = f"{self.command} {self.path} HTTP/1.1\r\nHost: api.openai.com\r\n"
            for header in ("Content-Type", "Accept", "Authorization"):
                if header in self.headers:
                    head += f"{header}: {self.headers[header]}\r\n"
            head += f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            upstream.sendall(head.encode() + body)

            chunks = []
            while True:
                data = upstream.recv(65536)
                if not data:
                    break
                chunks.append(data)
            upstream.close()

            _, _, body_bytes = b"".join(chunks).partition(b"\r\n\r\n")
            status = 200
        except OSError as exc:
            body_bytes = f'{{"error": {{"message": "{exc}"}}}}'.encode()
            status = 502

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_POST(self):
        self._plain_forward()

    def do_GET(self):
        self._plain_forward()


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), ConnectProxy)
    server.daemon_threads = True
    print(f"proxy 127.0.0.1:{LISTEN_PORT} -> stub 127.0.0.1:{STUB_PORT}", flush=True)
    server.serve_forever()