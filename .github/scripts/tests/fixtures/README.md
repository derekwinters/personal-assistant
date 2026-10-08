# Captured apksigner output

These three files are **verbatim `apksigner` stdout**, copied byte for byte from
[`derekwinters/Interval-trainer-android`](https://github.com/derekwinters/Interval-trainer-android)
(`.github/scripts/tests/fixtures/`, same filenames), where they were captured or collected. None of
them was captured in this repository, and none of them carries this repository's release
certificate. Nothing in them was edited, and nothing should be: a comment header added here would
make them authored files that merely look captured, which is precisely the failure they exist to
prevent.

They pin `apksigner`'s output **shape**, which is what the release-signature gate
(`.github/scripts/verify_release_signature.py`, `docs/spec/app.md` `APP-043`) parses. Whether a
release APK carries *this* repository's certificate is decided at release time against the
`ANDROID_KEYSTORE_SHA256` secret (`APP-042`, `APP-044`), not by anything committed here.

There is no `apksigner` in the development environment used to write the gate, and the Android SDK
cannot be downloaded into it, so a captured fixture is the only honest way to test the parser.

## `apksigner-verify-print-certs-verbose.txt` and `apksigner-verify-print-certs-nonverbose.txt`

The stdout of apksigner 31.0.2 run over one real signed APK in the two modes the gate could use:

```
apksigner verify --print-certs --verbose signed.apk    # -> the -verbose fixture
apksigner verify --print-certs           signed.apk    # -> the -nonverbose fixture
```

Interval-trainer-android copied them from
[`derekwinters/lucas-doggiehood`](https://github.com/derekwinters/lucas-doggiehood), where they
were first captured. Doggiehood shipped a release with no assets at all: its gate ran
`apksigner verify --print-certs` without `--verbose`, while its parser required the
`Number of signers:` header that only `--verbose` prints, and every apksigner sample in its green
test suite had been hand-written from the tool's documentation. So both modes are kept: the verbose
one is the format the gate asks for and reads, and the non-verbose one is the real output that broke
that release, kept as a case the parser must **reject**.

The certificate in them is a throwaway key generated only to produce the capture.

## `apksigner-verify-print-certs-verbose-scheme-signer.txt`

The stdout of `apksigner verify --print-certs --verbose` from build-tools 35.0.0, run in
Interval-trainer-android's release workflow over that repository's own correctly-signed v0.2.2
release APK, and copied from that job's log (Interval-trainer-android issues #120 and #122). Its
certificate is **Interval-trainer-android's release certificate**, not this repository's.

It exists because build-tools 35.0.0 labels a signer block by the signature scheme that verified
it — `V2 Signer:` — rather than by a numeric index, at least when exactly one scheme verifies.
`Signer #<N>` and `V2 Signer:` are two real shapes `apksigner` emits for the same command line on
different SDK versions, and a parser that knew only the first rejected that correctly-signed APK.
