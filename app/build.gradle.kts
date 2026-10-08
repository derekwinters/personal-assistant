plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// The stable release key reaches the build only through these environment variables, which the
// release workflow fills from repository secrets (docs/spec/app.md APP-040). Nothing that
// unlocks the key is committed. Release signing is configured only when all four are present;
// otherwise a release build is unsigned (APP-004).
val releaseKeyVariables = listOf(
    "ANDROID_KEYSTORE_PATH",
    "ANDROID_KEYSTORE_PASSWORD",
    "ANDROID_KEY_ALIAS",
    "ANDROID_KEY_ALIAS_PASSWORD",
)
val releaseKey: Map<String, String> = releaseKeyVariables
    .associateWith { providers.environmentVariable(it).orNull.orEmpty() }
val releaseKeySupplied = releaseKey.values.all { it.isNotBlank() }

android {
    namespace = "com.derekwinters.personalassistant"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.derekwinters.personalassistant"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0" // x-release-please-version
    }

    signingConfigs {
        // A debug key committed on purpose, so every machine and CI run signs debug
        // builds identically and one run's APK installs as an update over another's
        // (APP-003). Its passwords are public: it must never sign a release build.
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
        if (releaseKeySupplied) {
            create("release") {
                storeFile = file(releaseKey.getValue("ANDROID_KEYSTORE_PATH"))
                storePassword = releaseKey.getValue("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = releaseKey.getValue("ANDROID_KEY_ALIAS")
                keyPassword = releaseKey.getValue("ANDROID_KEY_ALIAS_PASSWORD")
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("debug")
        }
        getByName("release") {
            // The release key when it is supplied, and otherwise nothing: an unsigned release
            // build, never one signed with the public debug key (APP-004, APP-041).
            signingConfig = if (releaseKeySupplied) signingConfigs.getByName("release") else null
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            // Hand the resolved signing configuration to DebugSigningTest (APP-003, APP-004,
            // APP-040, APP-041). Only names, paths and a yes/no reach the test JVM for release,
            // never the release key's passwords or alias.
            val debugSigning = buildTypes.getByName("debug").signingConfig
            it.systemProperty("app.signing.debug.storeFile", debugSigning?.storeFile?.path ?: "")
            it.systemProperty("app.signing.debug.storePassword", debugSigning?.storePassword ?: "")
            it.systemProperty("app.signing.debug.keyAlias", debugSigning?.keyAlias ?: "")
            it.systemProperty("app.signing.debug.keyPassword", debugSigning?.keyPassword ?: "")
            val releaseSigning = buildTypes.getByName("release").signingConfig
            it.systemProperty("app.signing.release.keySupplied", releaseKeySupplied.toString())
            it.systemProperty("app.signing.release.configured", (releaseSigning != null).toString())
            it.systemProperty(
                "app.signing.release.usesDebugConfig",
                (releaseSigning != null && releaseSigning === signingConfigs.getByName("debug"))
                    .toString(),
            )
            it.systemProperty("app.signing.release.storeFile", releaseSigning?.storeFile?.path ?: "")
            // Robolectric's Android runtime reaches into JDK internals on JDK 17+.
            it.jvmArgs("--add-exports=java.base/jdk.internal.access=ALL-UNNAMED")
            it.testLogging {
                events("failed")
                exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
            }
        }
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)

    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.compose.ui.test.junit4)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
}
