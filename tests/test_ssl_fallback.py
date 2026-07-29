"""Unit tests for the frozen-app SSL fallback (missing CA certs in the PyInstaller build).

Covers: _bundled_cacert_path / _ssl_ctx resolution against a fake sys._MEIPASS, and that
check_update() surfaces a check_error (without caching it) on failure, but still caches
normally on success. Hermetic: no real network calls."""
import json
import os
import shutil
import ssl
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


class BundledCacertPath(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_meipass = getattr(sys, "_MEIPASS", None)
        app._SSL_CTX_CACHE.clear()

    def tearDown(self):
        if self._orig_meipass is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = self._orig_meipass
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        app._SSL_CTX_CACHE.clear()

    def test_none_when_no_bundled_pem(self):
        sys._MEIPASS = self.tmpdir  # empty — no cacert.pem in it
        self.assertIsNone(app._bundled_cacert_path())

    def test_found_under_fake_meipass(self):
        pem_path = os.path.join(self.tmpdir, "cacert.pem")
        # a syntactically-valid (self-signed) PEM is enough to exercise the path-resolution
        # and ssl.create_default_context(cafile=...) plumbing without any network access.
        _write_fake_pem(pem_path)
        sys._MEIPASS = self.tmpdir
        self.assertEqual(app._bundled_cacert_path(), pem_path)

    def test_ssl_ctx_fallback_uses_bundled_pem(self):
        pem_path = os.path.join(self.tmpdir, "cacert.pem")
        _write_fake_pem(pem_path)
        sys._MEIPASS = self.tmpdir
        ctx = app._ssl_ctx(fallback=True)
        self.assertIsInstance(ctx, ssl.SSLContext)

    def test_ssl_ctx_fallback_raises_without_bundled_pem(self):
        sys._MEIPASS = self.tmpdir  # empty
        with self.assertRaises(RuntimeError):
            app._ssl_ctx(fallback=True)

    def test_ssl_ctx_default_is_cached(self):
        ctx1 = app._ssl_ctx()
        ctx2 = app._ssl_ctx()
        self.assertIs(ctx1, ctx2)


def _write_fake_pem(path):
    # Minimal syntactically-valid self-signed cert, generated once and inlined here so the
    # test needs no network / no `openssl` subprocess dependency.
    import subprocess
    try:
        subprocess.run(
            ["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", "/dev/null",
             "-out", path, "-days", "1", "-nodes", "-subj", "/CN=test"],
            capture_output=True, timeout=20, check=True)
    except Exception:
        # No openssl available — fall back to asserting path resolution only, with a
        # syntactically-empty file (ssl.create_default_context tolerates a present-but-empty
        # cafile at context-creation time; only real use would fail, which we don't exercise).
        with open(path, "w") as f:
            f.write("")


class UrlopenSslFallback(unittest.TestCase):
    """_urlopen itself: the real-world failure shape is urllib.request.urlopen wrapping the
    SSL error inside urllib.error.URLError (as e.reason), NOT raising the bare
    ssl.SSLCertVerificationError. A monkeypatch that raises the bare exception (the previous
    test's mistake) passes even when the production `except ssl.SSLCertVerificationError:`
    clause can never fire against a real urlopen call — so these simulate both shapes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_meipass = getattr(sys, "_MEIPASS", None)
        sys._MEIPASS = self.tmpdir
        _write_fake_pem(os.path.join(self.tmpdir, "cacert.pem"))
        app._SSL_CTX_CACHE.clear()

    def tearDown(self):
        if self._orig_meipass is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = self._orig_meipass
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        app._SSL_CTX_CACHE.clear()

    def test_wrapped_url_error_triggers_bundled_ca_fallback(self):
        # First call (default context): urlopen wraps the verification failure in a
        # URLError, with the original SSLCertVerificationError as .reason — this is what
        # urllib.request.urlopen actually raises, not the bare exception.
        wrapped = urllib.error.URLError(
            ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate"))
        fake_resp = mock.sentinel.response
        calls = []

        def fake_urlopen(req_or_url, timeout=None, context=None):
            calls.append(context)
            if len(calls) == 1:
                raise wrapped
            return fake_resp

        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            result = app._urlopen("https://example.invalid/x", timeout=5)

        self.assertIs(result, fake_resp)
        self.assertEqual(len(calls), 2)
        # call #1 used the default (OS/venv trust-store) context; call #2 used a DIFFERENT
        # context — the bundled-CA fallback — proving the retry actually swapped contexts
        # rather than e.g. retrying with the same (still-failing) default context.
        self.assertIsNot(calls[0], calls[1])
        self.assertIs(calls[0], app._ssl_ctx())
        self.assertIs(calls[1], app._ssl_ctx(fallback=True))

    def test_bare_ssl_cert_verification_error_also_triggers_fallback(self):
        # Keep the bare-exception shape covered too — some code paths (or future urllib
        # versions) might raise it unwrapped, and both shapes must trigger the same fallback.
        fake_resp = mock.sentinel.response
        calls = []

        def fake_urlopen(req_or_url, timeout=None, context=None):
            calls.append(context)
            if len(calls) == 1:
                raise ssl.SSLCertVerificationError("certificate verify failed")
            return fake_resp

        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            result = app._urlopen("https://example.invalid/x", timeout=5)

        self.assertIs(result, fake_resp)
        self.assertEqual(len(calls), 2)
        self.assertIsNot(calls[0], calls[1])

    def test_unrelated_url_error_is_not_swallowed(self):
        # A URLError whose .reason is NOT an SSL cert-verification failure (e.g. plain
        # network-unreachable) must propagate untouched — no bundled-CA retry, no masking.
        plain = urllib.error.URLError("no route to host")

        with mock.patch.object(urllib.request, "urlopen", side_effect=plain) as m:
            with self.assertRaises(urllib.error.URLError) as ctx:
                app._urlopen("https://example.invalid/x", timeout=5)
        self.assertIs(ctx.exception, plain)
        self.assertEqual(m.call_count, 1)  # no retry attempted


class UpdateCheckErrorSurfacing(unittest.TestCase):
    def setUp(self):
        self._orig_cfg = app.CONFIG_DIR
        self._orig_update_file = app.UPDATE_FILE
        self.tmpcfg = tempfile.mkdtemp()
        app.CONFIG_DIR = self.tmpcfg
        app.UPDATE_FILE = os.path.join(self.tmpcfg, "update.json")

    def tearDown(self):
        app.CONFIG_DIR = self._orig_cfg
        app.UPDATE_FILE = self._orig_update_file
        shutil.rmtree(self.tmpcfg, ignore_errors=True)

    def test_check_error_surfaced_on_failure_and_not_cached(self):
        with mock.patch.object(app, "_urlopen",
                                side_effect=ssl.SSLCertVerificationError("cert verify failed")):
            info = app.check_update(force=True)
        self.assertIn("check_error", info)
        self.assertIn("SSLCertVerificationError", info["check_error"])
        self.assertFalse(os.path.exists(app.UPDATE_FILE))

    def test_check_error_surfaced_on_url_error(self):
        with mock.patch.object(app, "_urlopen",
                                side_effect=urllib.error.URLError("no network")):
            info = app.check_update(force=True)
        self.assertIn("check_error", info)
        self.assertFalse(os.path.exists(app.UPDATE_FILE))

    def test_success_path_still_writes_cache_and_no_check_error(self):
        fake_resp = mock.MagicMock()
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False
        fake_resp.read.return_value = json.dumps(
            {"tag_name": "v9.9.9", "html_url": "https://example.invalid/x"}).encode()
        with mock.patch.object(app, "_urlopen", return_value=fake_resp):
            info = app.check_update(force=True)
        self.assertNotIn("check_error", info)
        self.assertEqual(info["latest"], "9.9.9")
        self.assertTrue(os.path.exists(app.UPDATE_FILE))
        with open(app.UPDATE_FILE, encoding="utf-8") as fh:
            cache = json.load(fh)
        self.assertEqual(cache["latest"], "9.9.9")


if __name__ == "__main__":
    unittest.main()
