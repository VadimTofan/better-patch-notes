from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest


from automation.http_client import (
    BlizzardHttpClient,
    SourceRejected,
    SourceUnavailable,
)


class _SourceHandler(BaseHTTPRequestHandler):
    retry_requests = 0

    def do_GET(self) -> None:
        if self.path == "/redirect-external":
            self.send_response(302)
            self.send_header("Location", "https://example.com/notes")
            self.end_headers()
            return

        if self.path == "/large":
            body = b"x" * 64
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/unsupported-mime":
            body = b"binary"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/retry":
            type(self).retry_requests += 1
            if type(self).retry_requests < 3:
                self.send_response(503)
                self.end_headers()
                return

        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return

        body = b"<html>official notes</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


# Describe: bounded retrieval of untrusted Blizzard responses
class BlizzardHttpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _SourceHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _SourceHandler.retry_requests = 0

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server.server_port}{path}"

    def _client(self, max_response_bytes: int = 1024) -> BlizzardHttpClient:
        return BlizzardHttpClient(
            allowed_hosts={"127.0.0.1"},
            max_response_bytes=max_response_bytes,
            timeout_seconds=1,
            sleep=lambda _: None,
            allow_insecure_localhost=True,
        )

    def test_rejects_a_redirect_outside_the_allowlist(self) -> None:
        # Given
        client = self._client()

        # When / Then
        with self.assertRaisesRegex(SourceRejected, "redirect host"):
            client.get(self._url("/redirect-external"))

    def test_rejects_a_response_larger_than_the_limit(self) -> None:
        # Given
        client = self._client(max_response_bytes=32)

        # When / Then
        with self.assertRaisesRegex(SourceRejected, "response limit"):
            client.get(self._url("/large"))

    def test_rejects_unsupported_mime_types(self) -> None:
        # Given
        client = self._client()

        # When / Then
        with self.assertRaisesRegex(SourceRejected, "MIME type"):
            client.get(self._url("/unsupported-mime"))

    def test_retries_transient_responses_with_bounded_delays(self) -> None:
        # Given
        delays: list[float] = []
        client = BlizzardHttpClient(
            allowed_hosts={"127.0.0.1"},
            max_response_bytes=1024,
            timeout_seconds=1,
            sleep=delays.append,
            allow_insecure_localhost=True,
        )

        # When
        response = client.get(self._url("/retry"))

        # Then
        self.assertEqual(response.body, b"<html>official notes</html>")
        self.assertEqual(delays, [1.0, 2.0])
        self.assertEqual(_SourceHandler.retry_requests, 3)

    def test_does_not_retry_a_permanent_client_error(self) -> None:
        # Given
        client = self._client()

        # When / Then
        with self.assertRaisesRegex(SourceUnavailable, "HTTP 404"):
            client.get(self._url("/missing"))

    def test_rejects_credentials_fragments_and_plain_http(self) -> None:
        # Given
        client = BlizzardHttpClient(
            allowed_hosts={"news.blizzard.com"},
            max_response_bytes=1024,
            timeout_seconds=1,
        )
        urls = (
            "https://user:secret@news.blizzard.com/notes",
            "https://news.blizzard.com/notes#section",
            "http://news.blizzard.com/notes",
        )

        # When / Then
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(SourceRejected):
                    client.get(url)


if __name__ == "__main__":
    unittest.main()
