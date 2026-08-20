"""Redirecting CONFIG_DIR must redirect every per-machine state file with it.

Regression: these paths used to be module-level constants joined with CONFIG_DIR at IMPORT
time. Reassigning app.CONFIG_DIR afterwards (what every test and the demo mode does to stay
away from the user's real config) moved the directory but not the file paths, so writes still
landed in the real ~/.config/ai-session-search. That silently destroyed a user's saved
settings during in-browser verification of another feature. The paths are resolved at call
time now; this test fails loudly if anyone reintroduces an import-time constant."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402

PATH_FUNCS = ("_roots_file", "_stars_file", "_settings_file", "_update_file", "_favs_file")


class ConfigDirRedirectIsHonored(unittest.TestCase):
    def setUp(self):
        self._orig = app.CONFIG_DIR
        self.tmp = tempfile.mkdtemp(prefix="aiss-iso-")
        app.CONFIG_DIR = self.tmp

    def tearDown(self):
        app.CONFIG_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_state_path_follows_a_reassigned_config_dir(self):
        for name in PATH_FUNCS:
            p = getattr(app, name)()
            self.assertTrue(p.startswith(self.tmp + os.sep),
                            f"{name}() -> {p} escaped the redirected CONFIG_DIR {self.tmp}")

    def test_saving_settings_writes_into_the_redirected_dir_only(self):
        app._SETTINGS = {}
        app.save_settings({"default_lim": 4321})
        written = os.path.join(self.tmp, "settings.json")
        self.assertTrue(os.path.exists(written))
        # and reading it back goes to the same place
        self.assertEqual(app.load_settings().get("default_lim"), 4321)

    def test_saving_favorites_and_stars_write_into_the_redirected_dir_only(self):
        app.save_favs({"sid:1": {"sid": "sid", "gi": 1}})
        app.save_stars({"abc"})
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "favorites.json")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "stars.json")))

    def test_no_import_time_constant_remains(self):
        # the old names must be gone entirely — a leftover constant would be a live landmine
        for old in ("SETTINGS_FILE", "FAVS_FILE", "STARS_FILE", "ROOTS_FILE", "UPDATE_FILE"):
            self.assertFalse(hasattr(app, old),
                             f"app.{old} is back as an import-time constant; use the _*_file() function")


if __name__ == "__main__":
    unittest.main()
