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

> **Invariant — no release signing configuration is committed.** Release signing waits for stable
> keys; until then a release build is unsigned rather than signed with something temporary.

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
- **APP-004** The release build type has no signing configuration, so a release build is unsigned.

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

---

## Traceability

| Section | IDs | Tests |
|---|---|---|
| Build | APP-001–002 | manual |
| Build — signing | APP-003–004 | `app/src/test/kotlin/.../DebugSigningTest.kt` |
| Home screen | APP-010–012 | `app/src/test/kotlin/.../HomeScreenTest.kt` |
| Continuous integration | APP-020–024 | manual |
| Releases | APP-030–034 | manual |

**17 requirements, 4 `auto` and 13 `manual`.**
