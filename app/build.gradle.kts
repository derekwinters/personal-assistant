plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.derekwinters.personalassistant"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.derekwinters.personalassistant"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
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
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("debug")
        }
        // Release signing is deliberately not configured until stable keys exist
        // (APP-004), so release builds are unsigned.
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
            // Hand the resolved signing configuration to DebugSigningTest (APP-003, APP-004).
            val debugSigning = buildTypes.getByName("debug").signingConfig
            it.systemProperty("app.signing.debug.storeFile", debugSigning?.storeFile?.path ?: "")
            it.systemProperty("app.signing.debug.storePassword", debugSigning?.storePassword ?: "")
            it.systemProperty("app.signing.debug.keyAlias", debugSigning?.keyAlias ?: "")
            it.systemProperty("app.signing.debug.keyPassword", debugSigning?.keyPassword ?: "")
            it.systemProperty(
                "app.signing.release.configured",
                (buildTypes.getByName("release").signingConfig != null).toString(),
            )
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
