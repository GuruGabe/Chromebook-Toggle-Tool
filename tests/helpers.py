# tests/helpers.py
# ASCII only. Shared test scaffolding (this file contains no tests itself):
# a tiny web server on THIS PC that plays the part of GitHub, so the updater's
# real network code can be exercised without touching the internet.
import http.server
import socketserver
import threading


class FakeGitHub(http.server.BaseHTTPRequestHandler):
    # routes: path -> (status, extra_headers dict, body bytes). Replace the
    # dictionary in each test's setUp.
    routes = {}

    def do_GET(self):
        status, headers, body = self.routes.get(self.path, (404, {}, b"not found"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Keep the test output quiet.
        pass


class LocalServer(http.server.ThreadingHTTPServer):
    # http.server's normal bind does a reverse-DNS lookup (socket.getfqdn) of
    # the address it binds to. That can take seconds on a managed network and
    # this server only ever runs on 127.0.0.1, so skip the lookup.
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def start_server():
    # Starts the fake GitHub on a free port. Returns (server, base_url).
    FakeGitHub.routes = {}
    server = LocalServer(("127.0.0.1", 0), FakeGitHub)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]


def stop_server(server):
    server.shutdown()
    server.server_close()
