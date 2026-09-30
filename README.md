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
only; release builds are unsigned until stable signing keys are configured.
