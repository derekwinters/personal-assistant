# personal-assistant

## Installing a debug build

Every pull request and every push to `main` builds a debug APK in GitHub Actions. To install one
on an Android phone (Android 8 or later):

1. Open the **Actions** tab, choose the **android-tests** workflow, and open the run for the
   commit or pull request you want.
2. Under **Artifacts**, download **personal-assistant-debug-apk**. It is a zip file; unzip it to
   get `app-debug.apk`.
3. Install it, either way:
   - **On the phone:** copy the APK to the phone and open it. Android asks you to allow the app you
     opened it from (Files, Chrome, …) to install unknown apps; allow it, then install.
   - **Over USB:** with USB debugging enabled, run `adb install -r app-debug.apk`.

Debug builds are all signed with the same key, committed at `app/debug.keystore`, so a newer APK
from any run installs as an update over an older one and keeps the app's data. Its certificate's
SHA-256 fingerprint is
`6b:a0:b2:71:3e:bc:63:b8:86:76:7f:28:08:4a:91:ea:6f:b8:97:f1:11:f3:bf:c8:32:77:de:b9:fd:71:f7:28`,
and CI checks every APK it builds against it. That key is public, so a debug build is for testing
only.

## Installing a release

Each GitHub release carries a signed APK, `personal-assistant-vX.Y.Z.apk`, and its SHA-256 in
`personal-assistant-vX.Y.Z.apk.sha256`.

1. Open the repository's **Releases** page and choose a release.
2. Under **Assets**, download `personal-assistant-vX.Y.Z.apk`. To check it arrived intact, compare
   its SHA-256 with the `.sha256` file (`sha256sum -c personal-assistant-vX.Y.Z.apk.sha256`).
3. Install it the same way as a debug build: open it on the phone, or run
   `adb install -r personal-assistant-vX.Y.Z.apk`.

Every release is signed with the same stable release key, so a newer release installs as an update
over an older one and keeps the app's data.

Debug builds and release builds are signed with **different keys**, so one cannot be installed as an
update over the other: Android refuses it. To switch between them, uninstall the app first, which
deletes its data.

## Releases

Versions and `CHANGELOG.md` are managed by [release-please](https://github.com/googleapis/release-please)
from the Conventional Commit squash titles merged to `main`. It keeps a release pull request open
with the next version and changelog; merging it tags `vX.Y.Z` and publishes a GitHub release. Do
not edit the version by hand.

The same workflow then builds the release APK from the tag, signs it with the release key, checks
that it carries the release certificate and no other, and attaches it to the release. The key is
held only as repository secrets (`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS`, `ANDROID_KEY_ALIAS_PASSWORD`, and the certificate's fingerprint in
`ANDROID_KEYSTORE_SHA256`); without them the release job fails rather than publishing anything.
A local `./gradlew assembleRelease` produces an unsigned APK unless `ANDROID_KEYSTORE_PATH`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_ALIAS_PASSWORD` are set in the
environment. To attach an APK to an existing release that lacks one, run the **release-please**
workflow by hand with `backfill_tag` set to its tag. See `docs/spec/app.md`, section 5.
