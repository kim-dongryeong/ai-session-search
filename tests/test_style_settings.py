"""/settings — UI style customization (code font/colors, table borders, highlight colors, body
typography/width), persisted to CONFIG_DIR/settings.json's "style" key. Covers:
  1. an untouched style dict renders CSS equivalent to the pre-feature hardcoded page,
  2. save-time AND render-time validation reject CSS/HTML injection attempts,
  3. a valid, saved setting actually shows up in the rendered CSS,
  4. the /settings page itself renders (preview / presets / advanced sections),
  5. the reset button restores defaults,
  6. an @media print reset block exists once something is customized,
  7. the 3-state [data-theme] token pattern is present.

Never touches the user's real CONFIG_DIR or ~/.claude data — CONFIG_DIR is swapped for a
tempdir, and the server root is a synthetic fixture opened with exclusive=True (no
auto-discovery of the real ~/.claude / ~/.codex projects dirs), same pattern as
tests/test_lazy_settings.py."""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def build_fixture_root():
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-styledemo")
    os.makedirs(proj)
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    lines = [
        {"type": "ai-title", "aiTitle": "style settings demo"},
        {"type": "user", "timestamp": "2026-06-30T01:00:00Z", "cwd": "/Users/x/styledemo",
         "message": {"role": "user", "content": "hello there"}},
        {"type": "assistant", "cwd": "/Users/x/styledemo",
         "message": {"role": "assistant", "model": "claude-opus-4-8",
                     "content": [{"type": "text", "text": "```python\nprint('hi')\n```"}]}},
    ]
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root


class StyleSettingsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        cls.root = build_fixture_root()
        app.configure(cls.root, exclusive=True)   # exclusive=True: never touch real ~/.claude etc.
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg

    def setUp(self):
        app._SETTINGS = {}   # fresh style state before each test

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def get_json(self, path):
        status, body = self.get(path)
        return status, json.loads(body)


class DefaultRenderingUnchanged(StyleSettingsBase):
    """#1 — an untouched style dict must render byte-identical CSS to the pre-feature page."""

    def test_style_css_text_empty_when_untouched(self):
        self.assertEqual(app.style_css_text({}), "")
        self.assertEqual(app.style_css_text(None), "")

    def test_no_style_customization_yet(self):
        self.assertFalse(app._SETTINGS.get("style"))

    def test_shell_pages_have_no_custom_property_overrides_by_default(self):
        # a page that goes through shell() (not /settings, which always embeds a full live
        # preview block) must carry NO --code-bg/--hl0/etc :root override when nothing was ever
        # saved — only the target rules' own var(--x, ORIGINAL) fallbacks should be present.
        status, body = self.get("/favs")
        self.assertEqual(status, 200)
        self.assertNotIn("--code-bg:", body)
        self.assertNotIn("--hl0:", body)
        self.assertNotIn("--tbl-bd:", body)

    def test_target_rule_fallbacks_match_original_hardcoded_values(self):
        # the var() fallback strings must equal exactly what was hardcoded before this feature —
        # this IS the guarantee that an untouched page renders identically.
        status, body = self.get("/favs")
        self.assertIn("var(--code-bg,#fafbfc)", body)
        self.assertIn("var(--code-bd,#e6e9ee)", body)
        self.assertIn("var(--code-font,ui-monospace,Menlo,monospace)", body)
        self.assertIn("var(--code-size,12.5px)", body)
        self.assertIn("var(--tbl-bd,#dfe3e8)", body)
        self.assertIn("var(--tbl-head-bg,#f0f3f7)", body)
        self.assertIn("var(--tbl-zebra,#fafbfc)", body)
        self.assertIn("var(--hl0,#ffe27a)", body)
        self.assertIn("var(--hl5,#cbb2f7)", body)
        self.assertIn("var(--content-w,940px)", body)
        self.assertIn("var(--body-size,14.5px)", body)
        self.assertIn("var(--body-lh,1.65)", body)


class InjectionDefense(StyleSettingsBase):
    """#2 — a malicious value must never reach the rendered <style> block; it is silently
    replaced by the default (both at save time, here via /api/style, and at render time, via
    resolve_style()/style_css_text(), which is exercised separately below by hand-poisoning
    _SETTINGS to simulate a tampered settings.json)."""

    def test_font_injection_rejected_at_save(self):
        import urllib.parse as up
        payload = up.quote("Menlo;}</style><script>alert(1)</script>")
        status, d = self.get_json(f"/api/style?code_font={payload}")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["code_font"], app.STYLE_DEFAULTS["code_font"])
        # and it must not have been written to disk verbatim either
        with open(app._settings_file(), encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertEqual(on_disk["style"]["code_font"], app.STYLE_DEFAULTS["code_font"])

    def test_color_injection_rejected_at_save(self):
        import urllib.parse as up
        payload = up.quote("red;background:url(x)")
        status, d = self.get_json(f"/api/style?code_bg_light={payload}")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["code_bg"]["light"], app.STYLE_DEFAULTS["code_bg"]["light"])

    def test_size_out_of_range_and_garbage_rejected_at_save(self):
        for bad in ("999", "-5", "abc"):
            status, d = self.get_json(f"/api/style?code_size={bad}")
            self.assertEqual(status, 200)
            self.assertEqual(d["style"]["code_size"], app.STYLE_DEFAULTS["code_size"])

    def test_injected_payload_never_reaches_rendered_html(self):
        import urllib.parse as up
        font_payload = up.quote("Menlo;}</style><script>alert(1)</script>")
        color_payload = up.quote("red;background:url(x)")
        self.get(f"/api/style?code_font={font_payload}")
        self.get(f"/api/style?code_bg_light={color_payload}&code_size=999")
        status, body = self.get("/settings")
        self.assertEqual(status, 200)
        self.assertNotIn("alert(1)", body)
        self.assertNotIn("</style><script>", body)
        self.assertNotIn("url(x)", body)
        # the page must still be one coherent document — no stray injected tag count
        self.assertEqual(body.count("<script"), body.count("</script>"))

    def test_render_time_validation_catches_a_hand_tampered_settings_file(self):
        # simulate settings.json having been hand-edited (or written by an older/buggy build)
        # with an out-of-schema value — render-time validation (not just save-time) must still
        # neutralize it, since resolve_style()/style_css_text() re-validate independently.
        app._SETTINGS = {"style": {
            "code_font": "Menlo</style><script>evil()</script>",
            "code_bg": {"light": "javascript:alert(1)", "dark": "#15171c"},
            "code_size": "not-a-number",
            "table_zebra": {"nested": "object"},
        }}
        status, body = self.get("/favs")
        self.assertEqual(status, 200)
        self.assertNotIn("evil()", body)
        self.assertNotIn("javascript:alert", body)
        resolved = app.resolve_style(app._SETTINGS["style"])
        self.assertEqual(resolved["code_font"], app.STYLE_DEFAULTS["code_font"])
        self.assertEqual(resolved["code_bg"]["light"], app.STYLE_DEFAULTS["code_bg"]["light"])
        self.assertEqual(resolved["code_size"], app.STYLE_DEFAULTS["code_size"])
        self.assertEqual(resolved["table_zebra"], app.STYLE_DEFAULTS["table_zebra"])


class ValidSettingsApply(StyleSettingsBase):
    """#3 — a valid, saved setting actually shows up in the rendered CSS."""

    def test_valid_font_color_size_applied_site_wide(self):
        import urllib.parse as up
        font = up.quote("Fira Code, monospace")
        status, d = self.get_json(f"/api/style?code_font={font}&code_bg_light=%23112233&code_size=16")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["code_font"], "Fira Code, monospace")
        self.assertEqual(d["style"]["code_bg"]["light"], "#112233")
        self.assertEqual(d["style"]["code_size"], 16)
        status, body = self.get("/favs")
        self.assertEqual(status, 200)
        self.assertIn("--code-font:Fira Code, monospace", body)
        self.assertIn("--code-bg:#112233", body)
        self.assertIn("--code-size:16px", body)

    def test_valid_highlight_color_applied(self):
        status, d = self.get_json("/api/style?hl2_light=%23abcdef")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["hl"][2]["light"], "#abcdef")
        status, body = self.get("/favs")
        self.assertIn("--hl2:#abcdef", body)

    def test_table_zebra_toggle_off_applied(self):
        status, d = self.get_json("/api/style?table_zebra=0")
        self.assertFalse(d["style"]["table_zebra"])
        status, body = self.get("/favs")
        self.assertIn("--tbl-zebra:transparent", body)


class SettingsPageRenders(StyleSettingsBase):
    """#4 — /settings itself renders its preview, presets, and advanced sections."""

    def test_settings_page_200_with_sections(self):
        status, body = self.get("/settings")
        self.assertEqual(status, 200)
        self.assertIn("id=stylepreview", body)
        self.assertIn("presetrow", body)
        self.assertIn("styleadv", body)
        self.assertIn("GitHub", body)
        self.assertIn("Dracula", body)
        self.assertIn("Solarized", body)

    def test_settings_linked_from_index(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/settings"', body)

    def test_other_settings_listed_read_only(self):
        status, body = self.get("/settings")
        self.assertIn(str(app.get_timeline_lim()), body)


class ResetRestoresDefaults(StyleSettingsBase):
    """#5 — the reset action clears the style dict back to defaults."""

    def test_reset_clears_style(self):
        self.get("/api/style?code_size=20&table_zebra=0")
        self.assertTrue(app._SETTINGS.get("style"))
        status, d = self.get_json("/api/style?reset=1")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["code_size"], app.STYLE_DEFAULTS["code_size"])
        self.assertFalse(app._SETTINGS.get("style"))
        with open(app._settings_file(), encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertFalse(on_disk.get("style"))
        # a page rendered after reset is back to carrying no override at all
        status, body = self.get("/favs")
        self.assertNotIn("--code-size:", body)


class PrintResetBlock(StyleSettingsBase):
    """#6 — @media print forces the themed tokens back to their light values."""

    def test_print_reset_present_once_customized(self):
        self.get("/api/style?table_zebra=0&code_bg_light=%23112233")
        status, body = self.get("/favs")
        self.assertEqual(status, 200)
        self.assertIn("@media print", body)
        self.assertIn(':root{--code-bg:#112233', body.replace(" ", ""))


class ThreeStateThemeTokens(StyleSettingsBase):
    """#7 — the [data-theme] 3/4-state pattern is present in the rendered CSS."""

    def test_tokens_present_on_settings_page_always(self):
        # /settings always embeds a full preview block, even with zero customization, so the
        # 밝게/어둡게 toggle can demonstrate contrast from a fresh install onward.
        status, body = self.get("/settings")
        self.assertEqual(status, 200)
        self.assertIn('[data-theme="dark"]', body)
        self.assertIn(':root:not([data-theme="light"])', body)
        self.assertIn('[data-theme="light"]', body)
        # the preview container itself is also theme-scoped (contrast is the whole point)
        self.assertIn('[data-theme="dark"] .stylepreview', body)

    def test_tokens_present_site_wide_once_customized(self):
        self.get("/api/style?code_bg_light=%23112233")
        status, body = self.get("/favs")
        self.assertIn('[data-theme="dark"]', body)
        self.assertIn(':root:not([data-theme="light"])', body)


if __name__ == "__main__":
    unittest.main()


class AnchorsRejectTrailingNewline(unittest.TestCase):
    """Python's `$` also matches just before a trailing newline, so "#ffffff\\n" / "Menlo\\n"
    would validate and be written verbatim into the <style> block. Harmless in CSS (it's just
    whitespace) but the anchor must mean end-of-string, so both patterns use \\Z."""

    def test_color_with_trailing_newline_is_rejected(self):
        self.assertEqual(app._valid_color("#ffffff\n", "#000000"), "#000000")
        self.assertEqual(app._valid_color("#ffffff", "#000000"), "#ffffff")

    def test_font_with_trailing_newline_is_rejected(self):
        self.assertEqual(app._valid_font("Menlo\n", "monospace"), "monospace")
        self.assertEqual(app._valid_font("Menlo", "monospace"), "Menlo")


class SavedFlashHiddenUntilSaved(unittest.TestCase):
    """`.colorpair span{display:flex}` also matches the "✓ saved" flash inside a colour control,
    and an author `display` beats the UA's [hidden]{display:none} — so without an explicit
    override every colour control claimed "saved" before anything had been saved."""

    def test_hidden_saved_flash_has_a_display_none_override(self):
        html = app.shell("Test", "<p>body</p>")
        self.assertIn(".colorpair span[hidden]{display:none}", html)


class CodeFontAndBorderActuallyApply(unittest.TestCase):
    """Two settings rendered as CSS but had no visible effect (4.1.1):

    - Code font: markdown code blocks put the text in a <code> INSIDE the <pre>. A UA-stylesheet
      rule (`code{font-family:monospace}`) matches that child directly, and a directly-matching
      rule beats an inherited value — so the font set on pre.md-code never reached the text.
    - Code border width/color/radius: only pre.code (the separate "Code only" view) had a border.
      The markdown code block's frame is drawn by its .md-codewrap parent, which still hardcoded
      its border, so the border settings did nothing where code is normally read.
    """

    def test_inner_code_inherits_the_configured_font(self):
        html = app.shell("Test", "<p>body</p>")
        self.assertIn("pre.md-code code{font-family:inherit;font-size:inherit}", html)

    def test_markdown_code_wrapper_uses_the_border_variables(self):
        html = app.shell("Test", "<p>body</p>")
        m = re.search(r"\.md-codewrap\{[^}]*\}", html)
        self.assertIsNotNone(m)
        rule = m.group(0)
        self.assertIn("var(--code-bw,", rule)
        self.assertIn("var(--code-bd,", rule)
        self.assertIn("var(--code-rad,", rule)

    def test_dark_wrapper_border_also_honors_the_variable(self):
        # the dark override must not re-hardcode the color, or a chosen border color would be
        # silently dropped for anyone using dark mode
        html = app.shell("Test", "<p>body</p>")
        self.assertIn(".md-codewrap{border-color:var(--code-bd,", html)


class InlineCodeStyleIsSeparateFromCodeBlockStyle(StyleSettingsBase):
    """Inline code (`.md-ic`) used to share code_size/code_bg/code_radius with code BLOCKS
    (pre.md-code) — bumping the block font size for a big code sample also bumped every inline
    `code` mention mid-sentence, blowing out line-height, and inline code's background/radius
    could not be customized at all (hardcoded). This split gives inline code its own ic_size/
    ic_bg/ic_fg/ic_radius keys, sharing only code_font. Covers items #1-#6 of the task write-up."""

    def test_default_md_ic_rule_has_the_original_values_as_fallbacks(self):
        # #1 — untouched, .md-ic's var() fallbacks must equal exactly what was hardcoded before
        # this feature (background #eef1f4, radius 4px, size .9em) — same guarantee style_css_text
        # gives every other target rule.
        html = app.shell("Test", "<p>body</p>")
        m = re.search(r"\.md-ic\{[^}]*\}", html)
        self.assertIsNotNone(m)
        rule = m.group(0)
        self.assertIn("var(--ic-bg,#eef1f4)", rule)
        self.assertIn("var(--ic-rad,4px)", rule)
        self.assertIn("var(--ic-size,.9em)", rule)
        self.assertIn("var(--code-font,", rule)  # font is still shared with code blocks

    def test_saved_ic_settings_show_up_as_their_own_css_variables(self):
        # #2 — ic_size/ic_bg/ic_fg/ic_radius, once saved, render as --ic-* custom properties.
        status, d = self.get_json(
            "/api/style?ic_size=1.3&ic_bg_light=%23ff0000&ic_fg_light=%230000ff&ic_radius=0")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["ic_size"], 1.3)
        self.assertEqual(d["style"]["ic_bg"]["light"], "#ff0000")
        self.assertEqual(d["style"]["ic_fg"]["light"], "#0000ff")
        self.assertEqual(d["style"]["ic_radius"], 0)
        status, body = self.get("/favs")
        self.assertIn("--ic-size:1.3em", body)
        self.assertIn("--ic-bg:#ff0000", body)
        self.assertIn("--ic-fg:#0000ff", body)
        self.assertIn("--ic-rad:0px", body)

    def test_code_block_size_change_does_not_touch_inline_code_variable(self):
        # #3 — the actual point of this task: changing code_size (code BLOCK size) must never
        # emit or alter --ic-size. This is the regression the whole split guards against.
        status, d = self.get_json("/api/style?code_size=20")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["code_size"], 20)
        status, body = self.get("/favs")
        self.assertIn("--code-size:20px", body)
        self.assertNotIn("--ic-size:", body)

    def test_ic_bg_and_ic_size_injection_defense(self):
        # #4 — a bad ic_bg_light color or an out-of-range/garbage ic_size must fall back to the
        # default, both at save time and (independently) at render time.
        import urllib.parse as up
        payload = up.quote("red;background:url(x)")
        status, d = self.get_json(f"/api/style?ic_bg_light={payload}")
        self.assertEqual(status, 200)
        self.assertEqual(d["style"]["ic_bg"]["light"], app.STYLE_DEFAULTS["ic_bg"]["light"])
        for bad in ("2.0", "0.1", "abc"):
            status, d = self.get_json(f"/api/style?ic_size={bad}")
            self.assertEqual(status, 200)
            self.assertEqual(d["style"]["ic_size"], app.STYLE_DEFAULTS["ic_size"])
        app._SETTINGS = {"style": {"ic_bg": {"light": "javascript:alert(1)", "dark": "#2a2e35"},
                                    "ic_size": "not-a-number"}}
        resolved = app.resolve_style(app._SETTINGS["style"])
        self.assertEqual(resolved["ic_bg"]["light"], app.STYLE_DEFAULTS["ic_bg"]["light"])
        self.assertEqual(resolved["ic_size"], app.STYLE_DEFAULTS["ic_size"])

    def test_dark_media_override_uses_the_css_variable_not_a_hardcoded_color(self):
        # #5 — same reasoning as pre.md-code's 4.1.1 fix: a bare hardcoded dark background would
        # always win over a user-customized --ic-bg (same specificity, declared later).
        html = app.shell("Test", "<p>body</p>")
        m = re.search(r'@media\(prefers-color-scheme:dark\)\{\.md-ic\{[^}]*\}\}', html)
        self.assertIsNotNone(m)
        self.assertIn("var(--ic-bg,", m.group(0))

    def test_preview_renders_an_inline_code_element(self):
        # #6 — the /settings preview must show inline code, not just code blocks/tables/
        # highlights, so the ic_* controls can actually be judged against something.
        status, body = self.get("/settings")
        self.assertEqual(status, 200)
        self.assertIn('class="md-ic"', body)
