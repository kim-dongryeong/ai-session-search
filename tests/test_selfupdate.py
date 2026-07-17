"""Unit tests for the in-app self-updater (macOS). These stay hermetic: no network,
no real .app, no privileged commands — the OS-touching parts (codesign/spctl/hdiutil)
are exercised manually against real bundles during release, not here."""
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


class ArchAndQuoting(unittest.TestCase):
    def test_dmg_asset_name_by_arch(self):
        for machine, want in [("arm64", "ai-session-search-macos-arm64.dmg"),
                              ("aarch64", "ai-session-search-macos-arm64.dmg"),
                              ("x86_64", "ai-session-search-macos-x86_64.dmg"),
                              ("amd64", "ai-session-search-macos-x86_64.dmg"),
                              ("mips", None)]:
            with mock.patch("platform.machine", return_value=machine):
                self.assertEqual(app._dmg_asset_name(), want)

    def test_shq_survives_bash(self):
        for s in ["/Applications/AI Session Search.app", "a'b c", 'x"y', "$(whoami)", "back`tick`"]:
            out = subprocess.run(["/bin/bash", "-c", f"printf %s {app._shq(s)}"],
                                 capture_output=True, text=True)
            self.assertEqual(out.stdout, s)


class Capability(unittest.TestCase):
    def test_not_supported_when_not_frozen(self):
        self.assertFalse(app.self_update_supported())   # running from source in tests

    def test_frozen_bundle_none_when_not_frozen(self):
        self.assertIsNone(app._frozen_app_bundle())

    def test_check_update_reports_capability(self):
        os.environ["AISS_NO_UPDATE_CHECK"] = "1"
        try:
            info = app.check_update()
        finally:
            del os.environ["AISS_NO_UPDATE_CHECK"]
        self.assertIn("can_self_update", info)
        self.assertFalse(info["can_self_update"])       # not frozen


class Worker(unittest.TestCase):
    def setUp(self):
        app._set_update("idle", "", 0, target=None)

    def test_worker_errors_when_not_frozen(self):
        app.run_self_update()
        self.assertEqual(app._UPDATE["state"], "error")

    def test_worker_errors_when_no_asset(self):
        with mock.patch.object(app, "_frozen_app_bundle", return_value="/tmp/Fake.app"), \
             mock.patch.object(app, "_latest_release_asset", return_value=(None, None)):
            app.run_self_update()
        self.assertEqual(app._UPDATE["state"], "error")

    def test_worker_uptodate_when_not_newer(self):
        with mock.patch.object(app, "_frozen_app_bundle", return_value="/tmp/Fake.app"), \
             mock.patch.object(app, "_latest_release_asset",
                               return_value=(app.__version__, "https://example/x.dmg")):
            app.run_self_update()
        self.assertEqual(app._UPDATE["state"], "uptodate")

    def test_install_helper_script_is_safe_and_relaunches(self):
        captured = {}
        real_popen = subprocess.Popen

        def fake_popen(argv, **kw):
            captured["script"] = argv[1]          # ["/bin/bash", <script>]
            with open(argv[1]) as f:
                captured["body"] = f.read()
            # don't actually run it — return a harmless process
            return real_popen(["/usr/bin/true"], **{k: v for k, v in kw.items() if k != "start_new_session"})

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            app._install_helper("/Volumes/upd/AI Session Search.app",
                                "/Applications/AI Session Search.app", "/Volumes/upd")
        body = captured["body"]
        self.assertIn("ditto", body)
        self.assertIn("open ", body)
        self.assertIn("com.apple.quarantine", body)
        # the mount app path is single-quoted (spaces handled)
        self.assertIn("'/Volumes/upd/AI Session Search.app'", body)
        os.unlink(captured["script"])


class EndpointGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "src", "ai_session_search", "demo")
        app.configure(root)
        app.ROOTS[:] = [root]; app.ROOT = root
        app.DEFAULT_ROOTS = [root]; app.SAVED_ROOTS = []
        app._SHUTDOWN_TOKEN = "unit-token"
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _post(self, token):
        headers = {"X-Shutdown-Token": token} if token else {}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/self_update",
                                     data=b"", method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_post_requires_token(self):
        self.assertEqual(self._post(None), 403)
        self.assertEqual(self._post("wrong"), 403)

    def test_post_400_when_unsupported(self):
        # correct token, but not a frozen macOS app → nothing to update
        self.assertEqual(self._post("unit-token"), 400)

    def test_get_returns_progress_state(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/self_update", timeout=5) as r:
            import json
            d = json.loads(r.read().decode())
        self.assertEqual(set(d), {"state", "detail", "pct", "target"})


if __name__ == "__main__":
    unittest.main()
