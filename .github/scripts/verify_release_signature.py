#!/usr/bin/env python3
"""Release gate: every release APK is signed by the one stable release key (#30).

**Why this exists.** Android identifies an installed app by the certificate
that signed it. An APK whose certificate differs from the installed one's is
refused outright, and the only way through is to uninstall first, which
destroys the app's data. This app is sideloaded, so there is no Play Store to
re-sign anything and no key recovery: the signing key is chosen once and never
changed. `docs/spec/app.md` (section 5, APP-040–053) specifies the release
signing this checks.

**The invariant this enforces.** *A published release artifact is signed by the
certificate whose SHA-256 fingerprint is `ANDROID_KEYSTORE_SHA256`, and by no
other key.* The failure it is really built for is the quiet one: if a keystore
input is mis-wired or a secret is renamed, the build need not fail; it can
produce an unsigned APK or one signed with the debug key. Such an APK looks
correct in every other respect, so nothing but the certificate distinguishes
it, and the damage appears at the *next* release, on a user's device.

Run it against each just-built APK *before* anything is uploaded, so a build
that lost the release key fails its job instead of reaching a release page.

The expected fingerprint is read from the environment variable
`ANDROID_KEYSTORE_SHA256`, in keytool's colon-separated form or apksigner's
bare hex (APP-042). A missing, blank or malformed value fails the gate, and the
error never repeats the value: the variable is a secret slot, and what is in it
by mistake may be another secret.

The decisions are pure functions, so they unit-test with no Android SDK, no
keystore and no APK: `normalize_fingerprint`, `read_expected_fingerprint`,
`parse_apksigner_certs` and `assess`. `main` wires them to apksigner and the
environment. Standard library only (APP-046).
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from collections import namedtuple

SignerFacts = namedtuple("SignerFacts", "index dn sha256")
Verdict = namedtuple("Verdict", "ok reasons")

EXPECTED_FINGERPRINT_VARIABLE = "ANDROID_KEYSTORE_SHA256"

# The default Android debug certificate's subject. A build signs with this key
# whenever it falls back to debug signing, so it is the signature of the exact
# mis-wiring this gate exists to catch — worth naming in the error rather than
# reporting as an anonymous fingerprint mismatch (APP-044).
ANDROID_DEBUG_DN_MARKER = "cn=android debug"

_SHA256_HEX_DIGITS = 64

# apksigner prints "Signer #1 certificate DN: ..." and, when signers differ per
# SDK range, "Signer (minSdkVersion=24, maxSdkVersion=32) #1 certificate DN:".
# Both shapes carry a numeric signer index, which is what identifies the block.
#
# build-tools 35.0.0 instead labels a signer block by which signature scheme
# verified it — "V2 Signer: certificate DN: ..." — rather than by a numeric
# index, at least when exactly one scheme verifies (APP-043). It carries no
# index at all, so the "index" group is absent for this shape and a synthetic
# one is assigned per distinct scheme label as blocks are found.
_SIGNER_LINE = re.compile(
    r"^(?:Signer\s*(?:\([^)]*\)\s*)?#(?P<index>\d+)\s+"
    r"|(?P<scheme>[A-Za-z0-9.]+)\s+Signer:\s+)"
    r"certificate\s+(?P<field>DN|SHA-256 digest):\s*(?P<value>.*)$")
_SIGNER_COUNT_LINE = re.compile(r"^Number of signers:\s*(\d+)\s*$")

_FINGERPRINT_LABEL = re.compile(r"^\s*SHA-?256\s*:", re.IGNORECASE)


class MalformedFingerprint(ValueError):
    """A certificate fingerprint that is not 32 hex-encoded bytes."""


class MalformedApksignerOutput(ValueError):
    """apksigner output this parser cannot read with confidence."""


def _with_raw_output(summary, raw_output):
    """A `MalformedApksignerOutput` message that carries the raw text too (APP-043).

    A summary sentence like "apksigner reported 1 signer(s) but 0 could be
    parsed" names the symptom but not the cause. Attaching the verbatim
    output, delimited, means the next format drift is diagnosable from the one
    log it produces, not a retry. apksigner's output holds certificate
    subjects and digests, which ship inside every APK and are public.
    """
    return (
        "{0}\n\nThe raw apksigner output follows, verbatim, so this failure "
        "is diagnosable without rerunning apksigner:\n"
        "----- apksigner output begin -----\n"
        "{1}"
        "----- apksigner output end -----".format(
            summary, raw_output if raw_output.endswith("\n") else raw_output + "\n"))


# --- Pure decisions ---------------------------------------------------------


def normalize_fingerprint(text):
    """A SHA-256 certificate fingerprint as 64 lowercase hex digits (APP-042).

    `keytool -list -v` prints `SHA256: 2F:59:...` and apksigner prints bare
    lowercase hex, but both are SHA-256 over the DER-encoded certificate — the
    same 32 bytes written two ways.
    """
    if text is None:
        raise MalformedFingerprint("no fingerprint given")

    bare = _FINGERPRINT_LABEL.sub("", text)
    bare = re.sub(r"[\s:]", "", bare).lower()

    if not bare:
        raise MalformedFingerprint("no fingerprint given")
    if len(bare) != _SHA256_HEX_DIGITS:
        raise MalformedFingerprint(
            "expected {0} hex digits for a SHA-256 fingerprint, got {1}: {2!r}".format(
                _SHA256_HEX_DIGITS, len(bare), text.strip()))
    if not re.fullmatch(r"[0-9a-f]+", bare):
        raise MalformedFingerprint(
            "fingerprint is not hexadecimal: {0!r}".format(text.strip()))
    return bare


def read_expected_fingerprint(environ=None):
    """The expected release fingerprint from `ANDROID_KEYSTORE_SHA256` (APP-042).

    Missing, blank and malformed are all errors, never a pass. The error names
    the variable and what is wrong with it but never its value, unlike
    `normalize_fingerprint`'s own messages, which quote apksigner's public
    output.
    """
    environ = os.environ if environ is None else environ
    name = EXPECTED_FINGERPRINT_VARIABLE
    value = environ.get(name)
    if value is None:
        raise MalformedFingerprint(
            "{0} is not set; it must hold the release certificate's SHA-256 "
            "fingerprint".format(name))
    if not value.strip():
        raise MalformedFingerprint(
            "{0} is blank; it must hold the release certificate's SHA-256 "
            "fingerprint".format(name))
    try:
        return normalize_fingerprint(value)
    except MalformedFingerprint:
        raise MalformedFingerprint(
            "{0} is not a SHA-256 certificate fingerprint (expected {1} hex digits, "
            "optionally colon-separated as keytool prints them); its value is not "
            "repeated here".format(name, _SHA256_HEX_DIGITS)) from None


def parse_apksigner_certs(text):
    """The signers described by `apksigner verify --print-certs --verbose` (APP-043).

    The `--verbose` half of that command line is load-bearing: it is what makes
    apksigner emit the `Number of signers:` header this parser requires. Read
    `print_certs` before changing either.

    Recognizes two shapes for a signer block's `certificate DN:` and
    `certificate SHA-256 digest:` lines: apksigner's numeric `Signer #<N>` (and
    its per-SDK-range variant), and build-tools 35.0.0's `<Scheme> Signer:` —
    labelled by which signature scheme verified it (e.g. `V2 Signer:`) rather
    than by index, at least when exactly one scheme verifies. The latter
    carries no index of its own, so one is assigned per distinct scheme label in
    the order first seen. Whether two *simultaneously* verifying schemes for one
    physical signer should collapse into a single entry is not something any
    captured output has shown yet, so it is left unhandled rather than guessed
    at.

    Raises `MalformedApksignerOutput` when the declared signer count disagrees
    with the blocks actually parsed. That check is the point: this parser reads
    a human-readable format that could change under us, and a silent "no
    signers found" would read as an unsigned APK, while a silently *short* list
    could let an unexamined signer through. Every such error carries the raw
    apksigner text verbatim, delimited, alongside the summary.
    """
    declared = None
    by_index = {}
    # Scheme label ("V2", "V3.1", ...) -> the synthetic index assigned to it,
    # in order of first appearance. Only used for the scheme-labelled shape.
    scheme_indices = {}

    for line in text.splitlines():
        count_match = _SIGNER_COUNT_LINE.match(line.strip())
        if count_match and declared is None:
            declared = int(count_match.group(1))
            continue

        signer_match = _SIGNER_LINE.match(line.strip())
        if not signer_match:
            continue

        if signer_match.group("index") is not None:
            index = int(signer_match.group("index"))
        else:
            label = signer_match.group("scheme")
            index = scheme_indices.setdefault(label, len(scheme_indices) + 1)
        field = signer_match.group("field")
        value = signer_match.group("value").strip()
        signer = by_index.setdefault(index, {"dn": "", "sha256": ""})

        if field == "DN":
            signer["dn"] = value
        else:
            digest = normalize_fingerprint(value)
            if signer["sha256"] and signer["sha256"] != digest:
                raise MalformedApksignerOutput(_with_raw_output(
                    "signer #{0} is reported with two different certificates, "
                    "{1} and {2}".format(index, signer["sha256"], digest), text))
            signer["sha256"] = digest

    if declared is None:
        raise MalformedApksignerOutput(_with_raw_output(
            "apksigner output has no 'Number of signers:' line — either it was not "
            "asked for --verbose, or the format this gate reads has changed. Either "
            "way its verdict cannot be trusted", text))

    if declared != len(by_index):
        raise MalformedApksignerOutput(_with_raw_output(
            "apksigner reported {0} signer(s) but {1} could be parsed — the format "
            "this gate reads has changed".format(declared, len(by_index)), text))

    return [
        SignerFacts(index=index, dn=by_index[index]["dn"], sha256=by_index[index]["sha256"])
        for index in sorted(by_index)
    ]


def assess(signers, expected_sha256):
    """Whether these signers are exactly the expected release certificate (APP-044)."""
    expected = normalize_fingerprint(expected_sha256)
    reasons = []

    if not signers:
        reasons.append(
            "the APK is unsigned — a release artifact must carry the release "
            "certificate {0}".format(expected))
        return Verdict(ok=False, reasons=reasons)

    if len(signers) != 1:
        reasons.append(
            "the APK has {0} signers; a release artifact is signed by the release key "
            "alone".format(len(signers)))

    for signer in signers:
        if signer.sha256 == expected:
            continue
        if ANDROID_DEBUG_DN_MARKER in signer.dn.lower():
            reasons.append(
                "signer #{0} is the Android debug certificate ({1}) — the build fell "
                "back to debug signing, so this APK can never be installed over a "
                "release build. The release keystore did not reach Gradle.".format(
                    signer.index, signer.dn))
        else:
            reasons.append(
                "signer #{0} certificate is {1}, expected the release certificate "
                "{2} (DN: {3})".format(signer.index, signer.sha256, expected, signer.dn))

    return Verdict(ok=not reasons, reasons=reasons)


# --- Wiring -----------------------------------------------------------------


def find_apksigner():
    """apksigner from PATH, else the newest build-tools copy in the SDK (APP-045)."""
    on_path = shutil.which("apksigner")
    if on_path:
        return on_path

    for root in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")):
        if not root:
            continue
        candidates = sorted(
            glob.glob(os.path.join(root, "build-tools", "*", "apksigner")),
            key=lambda path: _version_key(os.path.basename(os.path.dirname(path))))
        if candidates:
            return candidates[-1]

    raise OSError(
        "apksigner not found on PATH or in ANDROID_HOME/ANDROID_SDK_ROOT build-tools")


def _version_key(version):
    """Sort `build-tools` directory names numerically, so 35.0.0 beats 9.0.0."""
    return [(0, int(part)) if part.isdigit() else (1, part)
            for part in re.split(r"[.-]", version)]


def print_certs(apk, apksigner=None):
    """`apksigner verify --print-certs --verbose` output for one APK (APP-043).

    `--verbose` is not decoration: apksigner prints the `Number of signers: N`
    header only in verbose mode, while `--print-certs` alone emits the signer
    DN and SHA-256 blocks and nothing else. `parse_apksigner_certs`
    cross-checks that header against the blocks it parsed, so without the flag
    every real APK is rejected as malformed output. That is how a release in
    another repository shipped with no assets at all, and why
    `.github/scripts/tests/fixtures/` holds captured output for both modes.
    """
    tool = apksigner or find_apksigner()
    result = subprocess.run(
        [tool, "verify", "--print-certs", "--verbose", apk],
        capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MalformedApksignerOutput(
            "apksigner could not verify {0} (exit {1}): {2}".format(
                os.path.basename(apk), result.returncode,
                (result.stderr or result.stdout).strip()))
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="The expected certificate fingerprint is read from the {0} environment "
               "variable.".format(EXPECTED_FINGERPRINT_VARIABLE))
    parser.add_argument("apk", nargs="+", help="release APK(s) to check")
    args = parser.parse_args(argv)

    try:
        expected = read_expected_fingerprint()
    except MalformedFingerprint as exc:
        print("::error title=Release signature::{0}".format(exc))
        return 1

    failed = False
    for apk in args.apk:
        name = os.path.basename(apk)
        try:
            signers = parse_apksigner_certs(print_certs(apk))
        except (MalformedApksignerOutput, MalformedFingerprint, OSError) as exc:
            print("::error title=Release signature::{0}: {1}".format(name, exc))
            failed = True
            continue

        for signer in signers:
            print("{0}: signer #{1} {2}\n  DN: {3}".format(
                name, signer.index, signer.sha256, signer.dn))

        verdict = assess(signers, expected)
        if verdict.ok:
            print("OK: {0} is signed by the release certificate.".format(name))
            continue

        failed = True
        for reason in verdict.reasons:
            print("::error title=Release signature::{0}: {1}".format(name, reason))

    if failed:
        print(
            "\nA release artifact is not signed by the release certificate alone — "
            "refusing to publish it. Installing it would force an uninstall on every "
            "user's next upgrade, destroying their app data. See docs/spec/app.md, "
            "section 5.")
        return 1

    print("\nOK: every release artifact carries the release certificate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
