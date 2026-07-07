#!/usr/bin/env bash
#
# setup-notarization.sh — one-time LOCAL setup (run on your Mac) of the GitHub
# Actions secrets that let the `release` workflow sign + NOTARIZE the macOS build.
#
# This script does NOT create the Apple certificate. Creating a "Developer ID
# Application" certificate is a manual step in the Apple Developer portal
# (Keychain Access CSR -> developer.apple.com). See docs/RELEASING.md, section
# "One-time: create the Developer ID Application certificate", for how.
#
# What this DOES do, once you have that certificate installed in your login
# keychain and exported to a .p12:
#   1. find your "Developer ID Application" signing identity,
#   2. collect the .p12 export + your Apple credentials,
#   3. push all six secrets to the repo with `gh secret set`.
#
# It is safe to re-run — `gh secret set` overwrites, so this is idempotent.
set -euo pipefail

REPO="kim-dongryeong/ai-session-search"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
info() { printf '  %s\n' "$1"; }
die()  { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

bold "AI Session Search — notarization secret setup"
cat <<'PRE'

Before running this you must ALREADY have:
  * Enrolled in the Apple Developer Program, and
  * Created a "Developer ID Application" certificate and installed it in your
    LOGIN keychain. In Keychain Access -> My Certificates it must appear WITH a
    private key under its disclosure triangle (otherwise the .p12 export is
    useless). How to create it is in docs/RELEASING.md.

This script only uploads the resulting .p12 + your Apple credentials to the
GitHub Actions secrets of the release repo:
PRE
info "repo: $REPO"
echo

# --- 0. Preconditions -------------------------------------------------------
command -v security >/dev/null 2>&1 || die "'security' not found — run this on macOS."
command -v gh       >/dev/null 2>&1 || die "GitHub CLI (gh) is not installed — https://cli.github.com"
command -v base64   >/dev/null 2>&1 || die "'base64' not found."

echo "Checking GitHub CLI authentication..."
gh auth status >/dev/null 2>&1 || die "not logged in to GitHub. Run: gh auth login"
info "ok"
echo

# --- 1. Detect the Developer ID Application identity ------------------------
bold "1) Developer ID Application signing identity"
IDS=()
while IFS= read -r line; do
  [ -n "$line" ] || continue
  name=${line#*\"}       # drop everything up to the first quote
  name=${name%\"*}       # drop the trailing quote
  IDS+=("$name")
done < <(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" || true)

if [ "${#IDS[@]}" -eq 0 ]; then
  die "no 'Developer ID Application' identity found in your keychains.
       Create one first (see docs/RELEASING.md), install it in your login
       keychain, then re-run this script."
elif [ "${#IDS[@]}" -eq 1 ]; then
  SIGN_IDENTITY="${IDS[0]}"
  info "found: $SIGN_IDENTITY"
else
  echo "Multiple Developer ID Application identities found:"
  i=1
  for id in "${IDS[@]}"; do printf "  %d) %s\n" "$i" "$id"; i=$((i + 1)); done
  printf "Which one? [1-%d] " "${#IDS[@]}"
  read -r choice
  case "$choice" in
    ''|*[!0-9]*) die "not a number: $choice" ;;
  esac
  [ "$choice" -ge 1 ] && [ "$choice" -le "${#IDS[@]}" ] || die "out of range: $choice"
  SIGN_IDENTITY="${IDS[$((choice - 1))]}"
  info "using: $SIGN_IDENTITY"
fi
echo

# --- 2. The .p12 export -----------------------------------------------------
bold "2) Export the certificate to a .p12"
cat <<'P12'
In Keychain Access:
  * My Certificates -> right-click "Developer ID Application: ..." -> Export...
  * File Format: Personal Information Exchange (.p12)
  * Set a password (you will type it below), then save the file.
P12
printf "Path to the exported .p12 file: "
read -r P12_PATH
# tidy up common paste artifacts: leading ~, wrapping quotes, a trailing space
P12_PATH="${P12_PATH/#\~/$HOME}"
P12_PATH="${P12_PATH%\"}"; P12_PATH="${P12_PATH#\"}"
P12_PATH="${P12_PATH%\'}"; P12_PATH="${P12_PATH#\'}"
P12_PATH="${P12_PATH% }"
[ -f "$P12_PATH" ] || die "no file at: $P12_PATH"

printf "Password you set on the .p12: "
read -rs P12_PWD; echo
[ -n "$P12_PWD" ] || die "empty .p12 password."
echo

# --- 3. Apple credentials for notarytool ------------------------------------
bold "3) Apple credentials (for notarytool)"
printf "Apple ID email: "
read -r APPLE_ID
[ -n "$APPLE_ID" ] || die "empty Apple ID."

printf "Team ID (10 chars — developer.apple.com/account -> Membership): "
read -r APPLE_TEAM_ID
[ -n "$APPLE_TEAM_ID" ] || die "empty Team ID."

cat <<'ASP'
App-specific password — NOT your Apple ID login password. Create one at:
  https://appleid.apple.com  ->  Sign-In and Security  ->  App-Specific Passwords  ->  +
It looks like: xxxx-xxxx-xxxx-xxxx
ASP
printf "App-specific password: "
read -rs APPLE_APP_SPECIFIC_PASSWORD; echo
[ -n "$APPLE_APP_SPECIFIC_PASSWORD" ] || die "empty app-specific password."
echo

# --- 4. Confirm (no secrets shown) then upload ------------------------------
bold "About to set these GitHub Actions secrets on $REPO:"
info "MACOS_SIGN_IDENTITY        = $SIGN_IDENTITY"
info "APPLE_ID                   = $APPLE_ID"
info "APPLE_TEAM_ID              = $APPLE_TEAM_ID"
info "MACOS_CERTIFICATE_BASE64   = (from $P12_PATH, hidden)"
info "MACOS_CERTIFICATE_PWD      = (hidden)"
info "APPLE_APP_SPECIFIC_PASSWORD= (hidden)"
printf "Proceed? [y/N] "
read -r confirm
case "$confirm" in
  y|Y|yes|YES) ;;
  *) echo "Aborted — nothing was uploaded."; exit 1 ;;
esac
echo

bold "4) Uploading secrets"
# The base64 blob goes in via stdin (avoids putting a big value on the command line).
base64 < "$P12_PATH" | gh secret set MACOS_CERTIFICATE_BASE64 --repo "$REPO"
info "set MACOS_CERTIFICATE_BASE64"

gh secret set MACOS_CERTIFICATE_PWD        --repo "$REPO" --body "$P12_PWD";               info "set MACOS_CERTIFICATE_PWD"
gh secret set MACOS_SIGN_IDENTITY          --repo "$REPO" --body "$SIGN_IDENTITY";         info "set MACOS_SIGN_IDENTITY"
gh secret set APPLE_ID                     --repo "$REPO" --body "$APPLE_ID";              info "set APPLE_ID"
gh secret set APPLE_TEAM_ID                --repo "$REPO" --body "$APPLE_TEAM_ID";         info "set APPLE_TEAM_ID"
gh secret set APPLE_APP_SPECIFIC_PASSWORD  --repo "$REPO" --body "$APPLE_APP_SPECIFIC_PASSWORD"; info "set APPLE_APP_SPECIFIC_PASSWORD"

echo
bold "Done — all six secrets are set on $REPO."
info "Cut a release (git tag vX.Y.Z && git push --tags) and the workflow will"
info "sign + notarize the macOS build automatically."
