# Releasing AI Session Search

Maintainer guide for cutting a release and (optionally) signing + notarizing the
macOS build. Everything here is repo-internal; end users never need it.

The `release` workflow (`.github/workflows/release.yml`) builds double-click
bundles for macOS, Windows, and Linux on a pushed `v*` tag and attaches them to
the GitHub Release:

| OS      | Asset                                   | Built with            |
|---------|-----------------------------------------|-----------------------|
| macOS   | `ai-session-search-macos-arm64.dmg` / `…-x86_64.dmg` | PyInstaller `.app` → `.dmg` (signed + notarized if secrets set) |
| Windows | `ai-session-search-windows-x64.exe`     | PyInstaller `--onefile` (bare `.exe`, unsigned) |
| Linux   | `ai-session-search-linux-x86_64.tar.gz` | PyInstaller `--onefile` binary |

---

## 1. Cut a release

1. **Bump the version.** Edit `__version__` in `src/ai_session_search/app.py`
   (this single value feeds the CLI banner, the MCP `serverInfo`, and the macOS
   bundle version in `scripts/make-macos-app.sh`).
2. **Update `CHANGELOG.md`** — add a section for the new version describing what
   changed. The release notes on GitHub point people here.
3. **Commit** those two files.
4. **Tag and push:**

   ```bash
   git tag v3.1.0
   git push --tags
   ```

   Use the exact `vX.Y.Z` form — the workflow triggers on `tags: ["v*"]`.
5. The `release` workflow runs automatically: it creates the GitHub Release (if
   missing) with user-facing notes, builds each OS bundle, and uploads the
   `.dmg` / `.exe` / `.tar.gz` assets. To (re)build for an existing tag without
   re-tagging, use **Actions → release → Run workflow** and pass the tag.

Without the macOS signing secrets (section 3), the mac build still succeeds — it
is **ad-hoc signed**, so it runs on the build machine but other Macs show the
"unidentified developer" Gatekeeper prompt (users right-click → Open once).

---

## 2. One-time: create the Developer ID Application certificate

Distribution **outside** the App Store requires a **Developer ID Application**
certificate — *not* "Apple Development", "Apple Distribution", or "Mac Developer".
Signing with any of those is the #1 cause of the `not signed with a valid
Developer ID certificate` notarization rejection.

- Only the **Account Holder** or an **Admin** can create it. (An individual
  enrollee *is* the Account Holder.) Limit: 5 Developer ID Application certs per
  account.

**Create it via Keychain Access (recommended):**

1. **Keychain Access → Certificate Assistant → Request a Certificate from a
   Certificate Authority.**
2. Fill in **User Email Address** and **Common Name**; leave **CA Email Address
   blank**; choose **Saved to disk** → Continue. This writes a
   `.certSigningRequest` file and generates the key pair in your login keychain.
3. Go to **developer.apple.com/account → Certificates → +** → **Developer ID
   Application** → upload the `.certSigningRequest`. If asked for a profile type
   / intermediate, take the default ("G2 Sub-CA").
4. **Download** the resulting `.cer` and **double-click** it to install into your
   **login** keychain. In **Keychain Access → My Certificates** it must appear
   with a disclosure triangle revealing the **private key** — if you can't see
   that key, the export in the next step won't include it and signing will fail.

(Alternative: Xcode → Settings → Accounts → your team → Manage Certificates →
**+ → Developer ID Application**.)

**Export to `.p12`:** Keychain Access → **My Certificates** → right-click the
`Developer ID Application: …` entry (the one *with the private key under it*) →
**Export → Personal Information Exchange (.p12)** → set a strong password. You'll
hand both the file and this password to the setup script below.

**App-specific password (for notarytool):** at
[appleid.apple.com](https://appleid.apple.com) → **Sign-In and Security →
App-Specific Passwords → +**. Your normal Apple ID login password will **not**
work with `notarytool`.

You'll also need your **Team ID** (10 characters), from
developer.apple.com/account → **Membership**.

---

## 3. Configure the GitHub secrets (`scripts/setup-notarization.sh`)

Once the certificate exists in your login keychain and you have the `.p12`, run
the helper locally on your Mac:

```bash
./scripts/setup-notarization.sh
```

It auto-detects your `Developer ID Application` identity
(`security find-identity -v -p codesigning`), prompts for the `.p12` path +
password, your Apple ID, Team ID, and app-specific password, then sets all six
GitHub Actions secrets with `gh secret set`. It never echoes secret values and
is safe to re-run (idempotent — `gh secret set` overwrites).

The six secrets it manages (the workflow reads exactly these names):

| Secret | What it is |
|--------|------------|
| `MACOS_CERTIFICATE_BASE64`     | base64 of your exported `.p12` |
| `MACOS_CERTIFICATE_PWD`        | the password you set when exporting the `.p12` |
| `MACOS_SIGN_IDENTITY`          | e.g. `Developer ID Application: Jane Dev (AB12CD34EF)` |
| `APPLE_ID`                     | your Apple ID email |
| `APPLE_TEAM_ID`                | your 10-char Team ID |
| `APPLE_APP_SPECIFIC_PASSWORD`  | the app-specific password (not your login password) |

Once set, every tagged release is signed inside-out with the hardened runtime
(`--options runtime --timestamp --entitlements packaging/entitlements.plist`, no
`--deep`), then the `.app` and the `.dmg` are each notarized and stapled.

> **Why not `--deep`?** `codesign --deep` re-signs every nested item in one pass
> and mis-signs some inner Mach-O binaries, which Apple rejects as "hardened
> runtime not enabled" / "signature invalid". The workflow signs each nested
> `.dylib`/`.so`/executable first, then the bundle last.

---

## 4. Windows: the unsigned-exe reality

The Windows asset is a **bare, unsigned `.exe`**. On download-and-double-click,
Windows shows the blue **"Windows protected your PC"** SmartScreen dialog; the
user clicks **More info → Run anyway** (the release notes and README spell this
out). This is expected and safe — it is not something the build is doing wrong.

Notes for later, if we decide to sign Windows too:

- **Neither OV nor EV certificates give instant SmartScreen trust anymore**
  (Microsoft removed EV's automatic reputation around March 2024). Reputation now
  builds per-certificate as users run clean downloads — but it attaches to the
  certificate/identity, so it survives every rebuild.
- **Cheapest modern path: Azure Trusted Signing** (~$9.99/mo, cloud signing, no
  USB token). **But individual sign-up is US & Canada only** — verify the
  maintainer's country before committing. This repo's maintainer locale is likely
  outside that gate, in which case the international fallback for individuals is
  **Certum** (offers open-source discounts). OV certs (~$65–200/yr) now require
  the key to live on FIPS hardware; EV (~$250–400+/yr) is overkill here.
- **Smart App Control** (some clean Windows 11 installs) *silently* blocks
  unsigned apps with no "Run anyway" — only signing (or shipping via
  winget/Microsoft Store) reliably beats it.
- If AV false-positives on the `--onefile` exe become a problem, prefer
  `--onedir` shipped as a zip, keep PyInstaller updated, don't UPX-compress, and
  submit false positives to Microsoft's Security Intelligence portal.

No code changes are needed to add signing later — it's an extra step in the
Windows job plus a signing credential.

---

## 5. Verify a notarized `.dmg` locally

After a signed release, download the `.dmg` and confirm the ticket is stapled and
Gatekeeper accepts it:

```bash
# The notarization ticket is stapled to the dmg (validates offline):
xcrun stapler validate ai-session-search-macos-arm64.dmg

# Gatekeeper assessment for a disk image:
spctl -a -t open --context context:primary-signature -v ai-session-search-macos-arm64.dmg
#   expect: "accepted" and "source=Notarized Developer ID"

# And the app inside, once mounted / copied out:
codesign --verify --deep --strict --verbose=2 "/Volumes/AI Session Search/AI Session Search.app"
spctl -a -vvv -t exec "/Volumes/AI Session Search/AI Session Search.app"
#   expect: "accepted, source=... Developer ID"
```

If notarization ever fails, pull the log for the exact reason:

```bash
xcrun notarytool log <submission-id> \
  --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD"
```

Common causes: signed with the wrong certificate type (must be *Developer ID
Application*), missing `--timestamp`, a nested binary lacking `--options runtime`
(the classic `--deep` failure), or a binary modified after signing.

## PyPI publishing (optional, trusted publishing — no token)

`pip install ai-session-search` works once the package is on PyPI. Publishing is wired into
`release.yml` as an **opt-in** job (`pypi`) using PyPI **Trusted Publishing** (OIDC — no API
token stored anywhere). One-time setup:

1. On <https://pypi.org> → your account → **Publishing** → **Add a pending publisher**
   (works before the project exists):
   - PyPI project name: `ai-session-search`
   - Owner: `kim-dongryeong`  ·  Repository: `ai-session-search`
   - Workflow name: `release.yml`  ·  Environment: *(leave blank)*
2. In the GitHub repo → **Settings → Secrets and variables → Actions → Variables** →
   add variable `PUBLISH_PYPI` = `true`.
3. Push a version tag (or re-run the release workflow). The `pypi` job builds the sdist+wheel
   and publishes. The uploaded version comes from `__version__`, so it must match the tag.

Until both are done the `pypi` job is skipped cleanly (no failure). Before the first PyPI
release, users can still install from source:
`pipx install git+https://github.com/kim-dongryeong/ai-session-search.git`.
