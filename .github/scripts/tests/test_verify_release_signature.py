"""Unit tests for the release-signature gate (issue #30, `docs/spec/app.md` APP-042–046).

Release builds of this app are signed with one stable key. Android identifies an
installed app by its signing certificate: an APK signed by a different key will
not install over an existing one, and the only way through is to uninstall
first, which destroys the app's data. For a sideloaded app there is no key
recovery, so the key is chosen once and never changed.

`verify_release_signature.py` is what stops a wrongly-signed APK reaching a
release. The expected certificate fingerprint comes from the
`ANDROID_KEYSTORE_SHA256` environment variable, and any artifact signed by a
different key fails the gate. The dangerous case, and the reason the gate exists
at all, is a silent fall-back to the debug key: a mis-wired keystore input does
not fail a build, it produces a valid APK that installs, runs, and only breaks
the *next* release, on a user's device.

These tests pin the pure decisions — `read_expected_fingerprint` and
`normalize_fingerprint` (APP-042), `parse_apksigner_certs` (APP-043) and
`assess` (APP-044) — and the wiring that has to agree with them (APP-043–046).
They need no Android SDK, no keystore and no APK.

A note on the apksigner samples. The single-signer transcripts are **captured,
not authored**, and were captured in derekwinters/Interval-trainer-android (and,
before it, derekwinters/lucas-doggiehood), not here; see `fixtures/README.md`.
None of them carries this repository's release certificate: what they pin is
apksigner's output shape. `TWO_SIGNER_OUTPUT`, `DEBUG_OUTPUT` and
`SDK_RANGE_OUTPUT` are hand-written — neither a two-key APK nor a debug-signed
one is something this environment can produce — and are used only for the cases
no capture covers.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verify_release_signature import (  # noqa: E402
    EXPECTED_FINGERPRINT_VARIABLE,
    MalformedApksignerOutput,
    MalformedFingerprint,
    SignerFacts,
    assess,
    find_apksigner,
    main,
    normalize_fingerprint,
    parse_apksigner_certs,
    print_certs,
    read_expected_fingerprint,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


CAPTURED_VERBOSE_OUTPUT = _read(os.path.join(FIXTURES, "apksigner-verify-print-certs-verbose.txt"))
CAPTURED_NON_VERBOSE_OUTPUT = _read(
    os.path.join(FIXTURES, "apksigner-verify-print-certs-nonverbose.txt"))
SCHEME_SIGNER_OUTPUT = _read(
    os.path.join(FIXTURES, "apksigner-verify-print-certs-verbose-scheme-signer.txt"))

# The certificate inside the -verbose / -nonverbose captures: a throwaway key.
CAPTURED_SHA256 = "10d315258da7c4c4830814ae6f876e84145f2195cfb077bc0bb04e3df0a61ed8"
CAPTURED_KEYTOOL_FORM = (
    "10:D3:15:25:8D:A7:C4:C4:83:08:14:AE:6F:87:6E:84:"
    "14:5F:21:95:CF:B0:77:BC:0B:B0:4E:3D:F0:A6:1E:D8")
CAPTURED_DN = "CN=Doggiehood Release, O=Derek Winters, L=Somewhere, C=US"

# The certificate inside the scheme-signer capture: Interval-trainer-android's
# release certificate, not this repository's. See fixtures/README.md.
SCHEME_SIGNER_SHA256 = "2f596b227b890f5fcec72c176f0e325623e6261f00ddb102c4f936e9da108e09"
SCHEME_SIGNER_DN = "CN=Interval-Trainer, O=Derek Winters, C=US"

# Stands in for this repository's release certificate, which no test knows.
RELEASE_SHA256 = "fedcba9876543210" * 4
OTHER_SHA256 = "0123456789abcdef" * 4

DEBUG_OUTPUT = """Verifies
Verified using v1 scheme (JAR signing): true
Number of signers: 1
Signer #1 certificate DN: CN=Android Debug, O=Android, C=US
Signer #1 certificate SHA-256 digest: {0}
""".format(OTHER_SHA256)

TWO_SIGNER_OUTPUT = """Verifies
Number of signers: 2
Signer #1 certificate DN: CN=Personal Assistant Release, O=Derek Winters, C=US
Signer #1 certificate SHA-256 digest: {0}
Signer #2 certificate DN: CN=Somebody Else, O=Elsewhere, C=US
Signer #2 certificate SHA-256 digest: {1}
""".format(CAPTURED_SHA256, OTHER_SHA256)

# apksigner's per-SDK-range form, which carries the same signer index.
SDK_RANGE_OUTPUT = """Verifies
Number of signers: 1
Signer (minSdkVersion=24, maxSdkVersion=32) #1 certificate DN: {0}
Signer (minSdkVersion=24, maxSdkVersion=32) #1 certificate SHA-256 digest: {1}
""".format(CAPTURED_DN, CAPTURED_SHA256)

# A signer shape the parser does not recognise, standing for a future format drift.
UNDECODABLE_OUTPUT = "Number of signers: 1\nSigner: certificate DN: CN=Nobody\n"


def _colon_form(bare_hex):
    """The same bytes in keytool's uppercase colon-separated shape."""
    return ":".join(
        bare_hex[index:index + 2] for index in range(0, len(bare_hex), 2)).upper()


class ExpectedFingerprintTests(unittest.TestCase):
    """APP-042: the expected fingerprint comes from ANDROID_KEYSTORE_SHA256, or it is an error."""

    def test_the_variable_is_android_keystore_sha256(self):
        self.assertEqual(EXPECTED_FINGERPRINT_VARIABLE, "ANDROID_KEYSTORE_SHA256")

    def test_reads_apksigners_bare_hex(self):
        self.assertEqual(
            read_expected_fingerprint({"ANDROID_KEYSTORE_SHA256": CAPTURED_SHA256}),
            CAPTURED_SHA256)

    def test_reads_keytools_colon_form_behind_a_label(self):
        self.assertEqual(
            read_expected_fingerprint(
                {"ANDROID_KEYSTORE_SHA256": "SHA256: {0}\n".format(CAPTURED_KEYTOOL_FORM)}),
            CAPTURED_SHA256)

    def test_reads_the_process_environment_by_default(self):
        with mock.patch.dict(os.environ, {"ANDROID_KEYSTORE_SHA256": CAPTURED_KEYTOOL_FORM}):
            self.assertEqual(read_expected_fingerprint(), CAPTURED_SHA256)

    def test_a_missing_variable_is_an_error_naming_it(self):
        with self.assertRaises(MalformedFingerprint) as raised:
            read_expected_fingerprint({})
        self.assertIn("ANDROID_KEYSTORE_SHA256", str(raised.exception))

    def test_a_blank_variable_is_an_error(self):
        with self.assertRaises(MalformedFingerprint) as raised:
            read_expected_fingerprint({"ANDROID_KEYSTORE_SHA256": "  \n"})
        self.assertIn("ANDROID_KEYSTORE_SHA256", str(raised.exception))

    def test_a_malformed_variable_is_an_error_that_does_not_repeat_the_value(self):
        """APP-042, and the invariant that key material is never logged.

        The variable is a secret slot: a malformed value in it may be some
        other secret pasted into the wrong place, so the error names the
        variable and the problem, never the value.
        """
        pasted = "correct-horse-battery-staple"
        for value in (pasted, "2F:59:6B:22", "zz" + RELEASE_SHA256[2:]):
            with self.subTest(value=value):
                with self.assertRaises(MalformedFingerprint) as raised:
                    read_expected_fingerprint({"ANDROID_KEYSTORE_SHA256": value})
                self.assertIn("ANDROID_KEYSTORE_SHA256", str(raised.exception))
                self.assertNotIn(value, str(raised.exception))


class NormalizeFingerprintTests(unittest.TestCase):
    """APP-042. keytool and apksigner print the same 32 bytes differently.

    `keytool -list -v` prints `SHA256: 2F:59:...` — uppercase, colon-separated,
    behind a label — and apksigner prints bare lowercase hex. Both are SHA-256
    over the DER-encoded certificate, so either is accepted.
    """

    def test_accepts_the_keytool_colon_form(self):
        self.assertEqual(normalize_fingerprint(CAPTURED_KEYTOOL_FORM), CAPTURED_SHA256)

    def test_accepts_apksigners_bare_hex(self):
        self.assertEqual(normalize_fingerprint(CAPTURED_SHA256), CAPTURED_SHA256)

    def test_a_fingerprint_survives_a_round_trip_through_both_forms(self):
        self.assertEqual(normalize_fingerprint(_colon_form(RELEASE_SHA256)), RELEASE_SHA256)

    def test_accepts_a_leading_label_and_surrounding_whitespace(self):
        self.assertEqual(
            normalize_fingerprint("  SHA256: {0}\n".format(CAPTURED_KEYTOOL_FORM)),
            CAPTURED_SHA256)
        self.assertEqual(
            normalize_fingerprint("SHA-256: {0}".format(CAPTURED_SHA256)), CAPTURED_SHA256)

    def test_rejects_a_fingerprint_of_the_wrong_length(self):
        with self.assertRaises(MalformedFingerprint):
            normalize_fingerprint("2F:59:6B:22")

    def test_rejects_a_fingerprint_that_is_not_hex(self):
        with self.assertRaises(MalformedFingerprint):
            normalize_fingerprint("zz" + RELEASE_SHA256[2:])

    def test_rejects_an_empty_fingerprint(self):
        with self.assertRaises(MalformedFingerprint):
            normalize_fingerprint("   \n")
        with self.assertRaises(MalformedFingerprint):
            normalize_fingerprint(None)


class ParseApksignerCertsTests(unittest.TestCase):
    """APP-043."""

    def test_reads_the_dn_and_digest_of_a_single_signer_from_a_real_capture(self):
        signers = parse_apksigner_certs(CAPTURED_VERBOSE_OUTPUT)
        self.assertEqual(len(signers), 1)
        self.assertEqual(signers[0].index, 1)
        self.assertEqual(signers[0].dn, CAPTURED_DN)
        self.assertEqual(signers[0].sha256, CAPTURED_SHA256)

    def test_reads_the_per_sdk_range_signer_form(self):
        signers = parse_apksigner_certs(SDK_RANGE_OUTPUT)
        self.assertEqual([signer.index for signer in signers], [1])
        self.assertEqual(signers[0].dn, CAPTURED_DN)
        self.assertEqual(signers[0].sha256, CAPTURED_SHA256)

    def test_reads_the_scheme_labelled_signer_form_from_a_real_capture(self):
        """build-tools 35.0.0 labels a signer `V2 Signer:` rather than `Signer #1`."""
        signers = parse_apksigner_certs(SCHEME_SIGNER_OUTPUT)
        self.assertEqual(len(signers), 1)
        self.assertEqual(signers[0].dn, SCHEME_SIGNER_DN)
        self.assertEqual(signers[0].sha256, SCHEME_SIGNER_SHA256)

    def test_reads_every_signer(self):
        signers = parse_apksigner_certs(TWO_SIGNER_OUTPUT)
        self.assertEqual([signer.index for signer in signers], [1, 2])
        self.assertEqual(
            [signer.sha256 for signer in signers], [CAPTURED_SHA256, OTHER_SHA256])

    def test_uppercase_digests_are_normalized(self):
        signers = parse_apksigner_certs(
            CAPTURED_VERBOSE_OUTPUT.replace(CAPTURED_SHA256, CAPTURED_SHA256.upper()))
        self.assertEqual(signers[0].sha256, CAPTURED_SHA256)

    def test_reports_no_signers_when_apksigner_found_none(self):
        """An unsigned APK parses to an empty list, which `assess` then fails."""
        self.assertEqual(parse_apksigner_certs("Number of signers: 0\n"), [])

    def test_a_signer_count_that_disagrees_with_the_blocks_raises(self):
        """Format drift fails loudly rather than dropping a signer."""
        truncated = TWO_SIGNER_OUTPUT.replace(
            "Signer #2 certificate DN: CN=Somebody Else, O=Elsewhere, C=US\n", "")
        truncated = truncated.replace(
            "Signer #2 certificate SHA-256 digest: {0}\n".format(OTHER_SHA256), "")
        with self.assertRaises(MalformedApksignerOutput):
            parse_apksigner_certs(truncated)

    def test_a_signer_count_mismatch_carries_the_raw_output_verbatim(self):
        """A summary alone names the symptom; the raw text is what explains it."""
        with self.assertRaises(MalformedApksignerOutput) as raised:
            parse_apksigner_certs(UNDECODABLE_OUTPUT)
        self.assertIn(UNDECODABLE_OUTPUT, str(raised.exception))

    def test_output_without_a_signer_count_raises_and_carries_the_raw_output(self):
        with self.assertRaises(MalformedApksignerOutput) as raised:
            parse_apksigner_certs("Verifies\n")
        self.assertIn("Verifies\n", str(raised.exception))

    def test_real_non_verbose_output_is_rejected(self):
        """Against the capture that broke a real release elsewhere.

        This is apksigner's genuine `--print-certs` output with no `--verbose`:
        the DN and digest blocks are present and the `Number of signers:`
        header is absent. It must keep raising. The cure for asking apksigner
        for the wrong format is to ask for the right one, never to teach the
        parser to accept a header-less one.
        """
        self.assertNotIn("Number of signers:", CAPTURED_NON_VERBOSE_OUTPUT)
        self.assertIn("certificate SHA-256 digest:", CAPTURED_NON_VERBOSE_OUTPUT)
        with self.assertRaises(MalformedApksignerOutput) as raised:
            parse_apksigner_certs(CAPTURED_NON_VERBOSE_OUTPUT)
        self.assertIn("Number of signers:", str(raised.exception))

    def test_the_captured_verbose_output_carries_the_header_the_parser_needs(self):
        self.assertIn("Number of signers: 1", CAPTURED_VERBOSE_OUTPUT)
        self.assertEqual(
            [signer.sha256 for signer in parse_apksigner_certs(CAPTURED_VERBOSE_OUTPUT)],
            [CAPTURED_SHA256])

    def test_the_verbose_only_extra_lines_do_not_confuse_the_parser(self):
        """SHA-1, MD5 and public-key digests are not certificates."""
        self.assertIn("Signer #1 public key SHA-256 digest:", CAPTURED_VERBOSE_OUTPUT)
        self.assertIn("Signer #1 certificate SHA-1 digest:", CAPTURED_VERBOSE_OUTPUT)
        signers = parse_apksigner_certs(CAPTURED_VERBOSE_OUTPUT)
        self.assertEqual(len(signers), 1)
        self.assertEqual(signers[0].sha256, CAPTURED_SHA256)

    def test_two_different_certificates_for_one_signer_raise(self):
        """Contradictory output is not silently resolved."""
        contradictory = CAPTURED_VERBOSE_OUTPUT + (
            "Signer #1 certificate SHA-256 digest: {0}\n".format(OTHER_SHA256))
        with self.assertRaises(MalformedApksignerOutput):
            parse_apksigner_certs(contradictory)


class ApksignerInvocationTests(unittest.TestCase):
    """APP-043: the command line must produce the format the parser reads.

    `parse_apksigner_certs` requires the `Number of signers:` header, and
    apksigner prints it only under `--verbose`. This pins the flags.
    """

    def _run_print_certs(self, returncode=0, stdout=None, stderr=""):
        completed = subprocess.CompletedProcess(
            args=[], returncode=returncode,
            stdout=CAPTURED_VERBOSE_OUTPUT if stdout is None else stdout, stderr=stderr)
        with mock.patch("verify_release_signature.subprocess.run",
                        return_value=completed) as run:
            output = print_certs("app-release.apk", apksigner="/usr/bin/apksigner")
        self.assertEqual(run.call_count, 1)
        return list(run.call_args[0][0]), output

    def test_the_invocation_asks_for_the_verbose_output_the_parser_reads(self):
        argv, _ = self._run_print_certs()
        self.assertIn(
            "--verbose", argv,
            "apksigner prints 'Number of signers:' only under --verbose, and "
            "parse_apksigner_certs requires that line: {0}".format(argv))

    def test_the_invocation_verifies_and_prints_certs_for_the_apk(self):
        argv, _ = self._run_print_certs()
        self.assertEqual(argv[0], "/usr/bin/apksigner")
        self.assertIn("verify", argv)
        self.assertIn("--print-certs", argv)
        self.assertEqual(argv[-1], "app-release.apk")

    def test_a_nonzero_apksigner_exit_is_a_failure_not_an_empty_parse(self):
        with self.assertRaises(MalformedApksignerOutput):
            self._run_print_certs(returncode=1, stdout="", stderr="DOES NOT VERIFY")


class FindApksignerTests(unittest.TestCase):
    """APP-045: apksigner comes from PATH or from the SDK, or it is an error."""

    def test_prefers_apksigner_on_the_path(self):
        with mock.patch("verify_release_signature.shutil.which",
                        return_value="/usr/bin/apksigner"):
            self.assertEqual(find_apksigner(), "/usr/bin/apksigner")

    def _sdk_with_build_tools(self, sdk, versions):
        for version in versions:
            tools = os.path.join(sdk, "build-tools", version)
            os.makedirs(tools)
            open(os.path.join(tools, "apksigner"), "w").close()

    def test_falls_back_to_the_newest_build_tools_copy_under_android_home(self):
        with tempfile.TemporaryDirectory() as sdk:
            self._sdk_with_build_tools(sdk, ("34.0.0", "35.0.0"))
            with mock.patch("verify_release_signature.shutil.which", return_value=None), \
                    mock.patch.dict(os.environ, {"ANDROID_HOME": sdk,
                                                 "ANDROID_SDK_ROOT": ""}, clear=False):
                self.assertEqual(
                    find_apksigner(),
                    os.path.join(sdk, "build-tools", "35.0.0", "apksigner"))

    def test_newest_means_numerically_newest(self):
        with tempfile.TemporaryDirectory() as sdk:
            self._sdk_with_build_tools(sdk, ("9.0.0", "35.0.0", "34.0.0"))
            with mock.patch("verify_release_signature.shutil.which", return_value=None), \
                    mock.patch.dict(os.environ, {"ANDROID_HOME": sdk,
                                                 "ANDROID_SDK_ROOT": ""}, clear=False):
                self.assertEqual(
                    find_apksigner(),
                    os.path.join(sdk, "build-tools", "35.0.0", "apksigner"))

    def test_falls_back_to_android_sdk_root(self):
        with tempfile.TemporaryDirectory() as sdk:
            self._sdk_with_build_tools(sdk, ("35.0.0",))
            with mock.patch("verify_release_signature.shutil.which", return_value=None), \
                    mock.patch.dict(os.environ, {"ANDROID_HOME": "",
                                                 "ANDROID_SDK_ROOT": sdk}, clear=False):
                self.assertEqual(
                    find_apksigner(),
                    os.path.join(sdk, "build-tools", "35.0.0", "apksigner"))

    def test_not_finding_apksigner_is_an_error_never_a_pass(self):
        with mock.patch("verify_release_signature.shutil.which", return_value=None), \
                mock.patch.dict(os.environ, {"ANDROID_HOME": "",
                                             "ANDROID_SDK_ROOT": ""}, clear=False):
            with self.assertRaises(OSError):
                find_apksigner()


class AssessTests(unittest.TestCase):
    """APP-044."""

    def test_the_expected_certificate_passes(self):
        verdict = assess(parse_apksigner_certs(CAPTURED_VERBOSE_OUTPUT), CAPTURED_SHA256)
        self.assertTrue(verdict.ok, verdict.reasons)
        self.assertEqual(verdict.reasons, [])

    def test_the_scheme_labelled_capture_passes_against_its_own_certificate(self):
        verdict = assess(parse_apksigner_certs(SCHEME_SIGNER_OUTPUT), SCHEME_SIGNER_SHA256)
        self.assertTrue(verdict.ok, verdict.reasons)

    def test_a_different_certificate_fails_and_names_both_fingerprints(self):
        verdict = assess(
            [SignerFacts(index=1, dn="CN=Somebody Else", sha256=OTHER_SHA256)],
            RELEASE_SHA256)
        self.assertFalse(verdict.ok)
        joined = " ".join(verdict.reasons)
        self.assertIn(OTHER_SHA256, joined)
        self.assertIn(RELEASE_SHA256, joined)

    def test_the_android_debug_certificate_fails_as_a_debug_fallback(self):
        """The dangerous case gets its own name in the error."""
        verdict = assess(parse_apksigner_certs(DEBUG_OUTPUT), RELEASE_SHA256)
        self.assertFalse(verdict.ok)
        self.assertTrue(
            any("debug" in reason.lower() for reason in verdict.reasons),
            "a debug-signed release APK must be reported as a debug fallback, not "
            "merely as a fingerprint mismatch: {0}".format(verdict.reasons))

    def test_an_unsigned_apk_fails(self):
        verdict = assess([], RELEASE_SHA256)
        self.assertFalse(verdict.ok)
        self.assertTrue(any("unsigned" in reason.lower() for reason in verdict.reasons))

    def test_an_extra_signer_fails_even_when_the_release_key_is_present(self):
        verdict = assess(parse_apksigner_certs(TWO_SIGNER_OUTPUT), CAPTURED_SHA256)
        self.assertFalse(verdict.ok)

    def test_the_expected_fingerprint_may_be_given_in_keytool_form(self):
        verdict = assess(
            parse_apksigner_certs(CAPTURED_VERBOSE_OUTPUT), CAPTURED_KEYTOOL_FORM)
        self.assertTrue(verdict.ok, verdict.reasons)


class GateExitCodeTests(unittest.TestCase):
    """APP-042 and APP-044: what the gate returns, and how it reports."""

    def _main(self, outputs, expected=RELEASE_SHA256):
        """Run `main` over as many APKs as `outputs` has entries."""
        apks = ["app-release-{0}.apk".format(index) for index in range(len(outputs))]
        with mock.patch("verify_release_signature.print_certs", side_effect=outputs), \
                mock.patch.dict(os.environ, {"ANDROID_KEYSTORE_SHA256": expected}), \
                mock.patch("sys.stdout", new=io.StringIO()) as out:
            code = main(apks)
        return code, out.getvalue()

    def _release_signed_output(self):
        return CAPTURED_VERBOSE_OUTPUT.replace(CAPTURED_SHA256, RELEASE_SHA256)

    def test_a_correctly_signed_apk_exits_zero(self):
        code, output = self._main([self._release_signed_output()])
        self.assertEqual(code, 0, output)

    def test_the_expected_fingerprint_may_be_in_keytool_form(self):
        code, output = self._main(
            [self._release_signed_output()], expected=_colon_form(RELEASE_SHA256))
        self.assertEqual(code, 0, output)

    def test_a_missing_expected_fingerprint_fails_without_running_apksigner(self):
        """APP-042: no fingerprint is an error, never a pass."""
        with mock.patch("verify_release_signature.print_certs") as print_certs_mock, \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch("sys.stdout", new=io.StringIO()) as out:
            os.environ.pop("ANDROID_KEYSTORE_SHA256", None)
            code = main(["app-release.apk"])
        self.assertEqual(code, 1)
        self.assertIn("::error title=Release signature::", out.getvalue())
        self.assertIn("ANDROID_KEYSTORE_SHA256", out.getvalue())
        print_certs_mock.assert_not_called()

    def test_a_blank_or_malformed_expected_fingerprint_fails(self):
        for value in ("", "   ", "not-a-fingerprint"):
            with self.subTest(value=value):
                code, output = self._main([self._release_signed_output()], expected=value)
                self.assertEqual(code, 1)
                self.assertIn("::error title=Release signature::", output)

    def test_a_wrongly_signed_apk_exits_one_with_an_error_annotation(self):
        code, output = self._main([CAPTURED_VERBOSE_OUTPUT])
        self.assertEqual(code, 1)
        self.assertIn("::error title=Release signature::", output)

    def test_a_debug_signed_apk_exits_one_and_says_so(self):
        code, output = self._main([DEBUG_OUTPUT])
        self.assertEqual(code, 1)
        self.assertIn("::error title=Release signature::", output)
        self.assertIn("debug", output.lower())

    def test_an_unsigned_apk_exits_one(self):
        code, output = self._main(["Number of signers: 0\n"])
        self.assertEqual(code, 1)
        self.assertIn("unsigned", output.lower())

    def test_every_apk_is_checked_rather_than_stopping_at_the_first_failure(self):
        code, output = self._main([DEBUG_OUTPUT, CAPTURED_VERBOSE_OUTPUT])
        self.assertEqual(code, 1)
        self.assertEqual(output.count("::error title=Release signature::"), 2)

    def test_one_bad_apk_among_good_ones_fails_the_gate(self):
        code, _ = self._main([self._release_signed_output(), DEBUG_OUTPUT])
        self.assertEqual(code, 1)

    def test_unreadable_apksigner_output_fails_rather_than_passing(self):
        code, output = self._main([CAPTURED_NON_VERBOSE_OUTPUT])
        self.assertEqual(code, 1)
        self.assertIn("Number of signers:", output)

    def test_a_signer_count_mismatch_prints_the_raw_apksigner_output(self):
        """APP-043, end to end: the CI log carries the text that broke parsing."""
        code, output = self._main([UNDECODABLE_OUTPUT])
        self.assertEqual(code, 1)
        self.assertIn(UNDECODABLE_OUTPUT, output)


class StandardLibraryOnlyTests(unittest.TestCase):
    """APP-046: the gate and its tests run on a bare runner with no pip install."""

    STDLIB = {
        "argparse", "collections", "glob", "io", "os", "re", "shutil",
        "subprocess", "sys", "tempfile", "unittest",
    }
    LOCAL = {"verify_release_signature"}

    def _imports(self, path):
        return set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)",
                              _read(path), re.MULTILINE))

    def test_the_gate_and_its_tests_import_only_the_standard_library(self):
        paths = [os.path.join(os.path.dirname(HERE), "verify_release_signature.py")] + [
            os.path.join(HERE, name) for name in sorted(os.listdir(HERE))
            if name.startswith("test_") and name.endswith(".py")]
        for path in paths:
            with self.subTest(path=os.path.basename(path)):
                imported = self._imports(path)
                self.assertTrue(imported)
                self.assertEqual(
                    sorted(name for name in imported
                           if name.split(".")[0] not in self.STDLIB | self.LOCAL), [])


if __name__ == "__main__":
    unittest.main()
