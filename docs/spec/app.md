# Specification — App skeleton (`APP`)

The Android application module: what builds, what it shows when it opens, and where it is tested.
It is deliberately the smallest app that builds and tests, so feature work has somewhere to land.

Every requirement below is `auto` (covered by a named test) unless marked otherwise. A test covers a
requirement by naming its identifier in the test name or a comment.

---

## Invariants

> **Invariant — the name the home screen shows is the `app_name` string resource, never a literal
> in the UI code.** The launcher label and the screen read the same resource, so they cannot drift
> apart.

> **Invariant — a release build is signed with the stable release key when the key is supplied,
> and is unsigned otherwise; it is never signed with the debug key.** The release key reaches
> Gradle only through the environment (`APP-040`). A build that does not have it produces an
> unsigned APK, which no phone will install, rather than one signed with something temporary that
> would install and then block every later release.

> **Invariant — a published release artifact is signed by the certificate whose SHA-256
> fingerprint is `ANDROID_KEYSTORE_SHA256`, and by no other key.** Android refuses to install an
> APK over one signed by a different key, and the only way through is uninstalling, which destroys
> the app's data. A mis-wired keystore input does not fail a build, so nothing but the certificate
> inside the APK shows that it is wrong; the release workflow checks it before uploading
> (`APP-044`).

> **Invariant — the release key material is secret: the keystore, its passwords and its alias are
> never committed, printed or written into a log, an issue or a comment.** They exist only as
> repository secrets, and the keystore exists on disk only inside the release job, under
> `$RUNNER_TEMP`, until that job ends.

> **Invariant — no workflow that a pull request can trigger can reach the release key.** A
> workflow triggered by `pull_request` or `pull_request_target` never references an
> `ANDROID_KEY*` secret, since a pull request can change what such a workflow runs.

> **Invariant — the release-signature gate that checks a release is always the copy on `main`,
> never the copy in the tag being released.** The gate is CI machinery, not part of the app: a fix
> to it must protect every release it checks, including one built from a tag cut before the fix.

> **Invariant — the committed debug key never signs a release build.** `app/debug.keystore` and its
> passwords are public by design, so anything it signs can be forged by anyone. It is attached to
> the `debug` build type only, and no other build type or signing configuration may reference it.

> **Invariant — debug builds are signed with the committed keystore, never with a key generated on
> the machine that builds them.** A per-machine key gives every CI runner a different signature,
> and an APK from one run then cannot install as an update over an APK from another.

> **Invariant — the version is written by release-please, never by hand.** `versionName` in
> `app/build.gradle.kts`, `version.txt`, `CHANGELOG.md` and the release manifest change only in
> release-please's release pull request; a version edited anywhere else drifts from the tags and
> the changelog.

---

## 1. Build

- **APP-001** The project is one Gradle `app` module written in Kotlin, built with the Kotlin DSL
  through the committed Gradle wrapper, with dependency versions in `gradle/libs.versions.toml`.
  *(manual: build structure; exercised by every CI run.)*
- **APP-002** The app supports Android 8 (API 26) and later, and compiles and targets the current
  stable API level. *(manual: build configuration in `app/build.gradle.kts`.)*
- **APP-003** Debug builds are signed with the debug keystore committed at `app/debug.keystore`,
  using the standard debug credentials: store password `android`, key alias `androiddebugkey`,
  key password `android`.
- **APP-004** When any of the four release-key environment variables in `APP-040` is unset or
  blank, the release build type has no signing configuration, so a release build is unsigned.

*`APP-004` used to say that the release build type has no signing configuration at all, and an
invariant said no release signing configuration is committed. That held while no stable release
key existed (issue #24). Issue #30 adds one, supplied through the environment rather than
committed, so `APP-004` now covers only the build that does not have the key, and section 5
specifies the build that does.*

## 2. Home screen

- **APP-010** The app declares a launcher activity, and launching the app opens the home screen.
- **APP-011** The home screen shows the app name, read from the `app_name` string resource.
- **APP-012** The UI is built with Jetpack Compose.
  *(manual: the home screen is a composable; APP-011's test drives it through Compose.)*

## 3. Continuous integration

- **APP-020** A GitHub Actions workflow runs `./gradlew test` on every pull request and on every
  push to `main`. *(manual: observed as the workflow run on each pull request.)*
- **APP-021** Every action the workflow uses is pinned to a full commit SHA, with the version it
  pins as a trailing comment. *(manual: workflow configuration.)*
- **APP-022** The workflow runs Android lint (`./gradlew lint`) on every pull request and on every
  push to `main`, and a lint error fails the check. *(manual: observed as the workflow run on each
  pull request.)*
- **APP-023** The workflow builds the debug APK (`./gradlew assembleDebug`) on every pull request
  and on every push to `main`, and uploads it as a workflow artifact that can be downloaded and
  installed on a phone. *(manual: observed as the workflow run and its artifact.)*
- **APP-024** The workflow checks that the debug APK it built is signed with the certificate in
  `app/debug.keystore`, and fails otherwise, so APKs from any two runs share one signing
  certificate. *(manual: a workflow step comparing `apksigner verify --print-certs` against the
  keystore; installing one run's APK over another's is a device check.)*

## 4. Releases

- **APP-030** A GitHub Actions workflow runs release-please on every push to `main`, and it keeps
  one release pull request open that proposes the next version and changelog, computed from the
  Conventional Commit squash titles merged since the last release. *(manual: observed as the
  workflow run on each push to `main` and the release pull request it maintains.)*
- **APP-031** Merging the release pull request tags the merge commit `vX.Y.Z` and publishes a
  GitHub release for that tag, carrying the changelog for the version. *(manual: observed as the
  tag and the release after the merge.)*
- **APP-032** The app's `versionName` in `app/build.gradle.kts` is written by release-please, and
  by nothing else, in the release pull request. *(manual: the `x-release-please-version` marker on
  the line and the `generic` extra file in `.github/release-please/config.json`.)*
- **APP-033** The first release is 0.1.0, set by `initial-version` in
  `.github/release-please/config.json`, because release-please ignores the manifest when no release
  tag exists yet. After that, before 1.0 a `feat` commit bumps the minor version rather than the
  major. *(manual: release configuration.)*
- **APP-034** Release pull requests carry the `no-closing-keyword` label, since a release closes no
  issue and the `closing-keyword` check would otherwise fail it. *(manual: observed on the release
  pull request.)*

## 5. Release signing

A release APK is signed with one stable key, held as repository secrets, so each release installs
as an update over the last. Android identifies an installed app by its signing certificate and
refuses an update signed by a different one, and there is no key recovery for a sideloaded app, so
the key is chosen once and never changed.

### The build

- **APP-040** When `ANDROID_KEYSTORE_PATH`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and
  `ANDROID_KEY_ALIAS_PASSWORD` are all set and non-blank in the environment, the release build
  type is signed with that keystore and key, with APK signature schemes v1, v2 and v3 enabled.
  The test covers the condition (signing is configured exactly when all four are present); that
  the resulting APK carries the key is checked on every release by `APP-044`.
- **APP-041** The release build type never uses the debug signing configuration or
  `app/debug.keystore`, whether or not the release key is present.

### The release-signature gate

`.github/scripts/verify_release_signature.py` is run against a release APK before anything is
uploaded. It needs no keystore, only the certificate fingerprint, which is public (it ships inside
every APK) but is held as the secret `ANDROID_KEYSTORE_SHA256` beside the key it describes.

- **APP-042** The gate reads the expected certificate fingerprint from the environment variable
  `ANDROID_KEYSTORE_SHA256`, accepting either `keytool`'s form (uppercase, colon-separated,
  optionally behind a `SHA256:` label) or `apksigner`'s bare lowercase hex. A missing, blank or
  malformed value is an error and fails the gate, and the error does not repeat the value.
- **APP-043** The gate reads the signers with `apksigner verify --print-certs --verbose`, and
  requires the `Number of signers:` line that only `--verbose` prints. It reads both of
  `apksigner`'s signer shapes, `Signer #N` and the scheme-labelled `V2 Signer:`, ignores the
  SHA-1, MD5 and public-key digests, and fails when the declared signer count disagrees with the
  signer blocks it parsed, when one signer is reported with two certificates, or when `apksigner`
  exits non-zero. Each of those failures carries `apksigner`'s raw output verbatim.
- **APP-044** The gate passes an APK only when it has exactly one signer and that signer's
  certificate matches `ANDROID_KEYSTORE_SHA256`. An unsigned APK, an APK with more than one signer,
  and an APK signed with any other certificate fail; a signer whose certificate subject is the
  Android debug certificate's is reported as a fall-back to debug signing. Every APK given is
  checked, each failure is printed as a GitHub `::error` annotation, and the gate exits non-zero if
  any failed.
- **APP-045** The gate finds `apksigner` on `PATH`, else in the newest `build-tools` directory
  under `ANDROID_HOME` or `ANDROID_SDK_ROOT`; not finding it is an error, never a pass.
- **APP-046** The gate and its tests use only the Python standard library.

### The release workflow

- **APP-047** When release-please publishes a release, the release workflow builds the release
  APK from the release's tag with the release key, runs the gate on it, and then attaches it to
  the GitHub release as `personal-assistant-<tag>.apk`, with its SHA-256 in
  `personal-assistant-<tag>.apk.sha256` (in `sha256sum` format). Nothing is uploaded unless the
  gate passed. *(manual: needs the repository's secrets; observed as the release's assets.)*
- **APP-048** The release job fails, before building anything, when any of the secrets
  `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
  `ANDROID_KEY_ALIAS_PASSWORD` or `ANDROID_KEYSTORE_SHA256` is missing, naming the missing ones and
  never printing any value. *(manual: needs the repository's secrets; observed as the job's
  annotation.)*
- **APP-049** The release job decodes the keystore to a file under `$RUNNER_TEMP`, readable only by
  the runner user, and deletes it in a step that runs whether or not the job failed.
  *(manual: workflow configuration.)*
- **APP-050** Running the release workflow by hand with the `backfill_tag` input set builds,
  verifies and attaches the APK for that existing tag the same way as `APP-047`, without running
  release-please. *(manual: a dispatch with the repository's secrets; observed as the release's
  assets.)*
- **APP-051** Both release jobs check out `main` to a separate path and run the gate from that
  checkout, never from the checkout of the tag being built.
- **APP-052** No workflow triggered by `pull_request` or `pull_request_target` references an
  `ANDROID_KEY*` secret.
- **APP-053** The android-tests workflow runs the gate's unit tests
  (`python3 -m unittest discover -s .github/scripts/tests`) on every pull request and on every
  push to `main`, with no Android SDK and no added action.

---

## Traceability

| Section | IDs | Tests |
|---|---|---|
| Build | APP-001–002 | manual |
| Build — signing | APP-003–004 | `app/src/test/kotlin/.../DebugSigningTest.kt` |
| Home screen | APP-010–012 | `app/src/test/kotlin/.../HomeScreenTest.kt` |
| Continuous integration | APP-020–024 | manual |
| Releases | APP-030–034 | manual |
| Release signing — build | APP-040–041 | `app/src/test/kotlin/.../DebugSigningTest.kt` |
| Release signing — gate | APP-042–046 | `.github/scripts/tests/test_verify_release_signature.py` |
| Release signing — workflow | APP-047–050 | manual |
| Release signing — workflow | APP-051–053 | `.github/scripts/tests/test_workflows.py` |

**31 requirements, 14 `auto` and 17 `manual`.**
