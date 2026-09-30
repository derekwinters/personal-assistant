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

---

## 1. Build

- **APP-001** The project is one Gradle `app` module written in Kotlin, built with the Kotlin DSL
  through the committed Gradle wrapper, with dependency versions in `gradle/libs.versions.toml`.
  *(manual: build structure; exercised by every CI run.)*
- **APP-002** The app supports Android 8 (API 26) and later, and compiles and targets the current
  stable API level. *(manual: build configuration in `app/build.gradle.kts`.)*
- **APP-003** Debug builds are signed with the standard Android debug key, and no release signing
  is configured. *(manual: needs an APK built and installed on a device.)*

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

---

## Traceability

| Section | IDs | Tests |
|---|---|---|
| Build | APP-001–003 | manual |
| Home screen | APP-010–012 | `app/src/test/kotlin/.../HomeScreenTest.kt` |
| Continuous integration | APP-020–021 | manual |

**8 requirements, 2 `auto` and 6 `manual`.**
