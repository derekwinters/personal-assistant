package com.derekwinters.personalassistant

import java.io.File
import java.security.KeyStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Checks the signing configuration Gradle resolved for this build. `app/build.gradle.kts` hands
 * the resolved values to the test JVM as `app.signing.*` system properties, so these tests read
 * what the build will actually use rather than a copy of it.
 */
class DebugSigningTest {

    private fun property(name: String): String =
        requireNotNull(System.getProperty("app.signing.$name")) {
            "system property app.signing.$name is not set by app/build.gradle.kts"
        }

    // APP-003: the debug build type signs with the keystore committed at app/debug.keystore,
    // not a key generated on the build machine (APP invariant), using the standard credentials.
    @Test
    fun `APP-003 debug builds sign with the committed debug keystore`() {
        // Unit tests run with the app module as their working directory.
        val committed = File("debug.keystore").canonicalFile
        assertEquals(committed.path, File(property("debug.storeFile")).canonicalPath)
        assertEquals("android", property("debug.storePassword"))
        assertEquals("androiddebugkey", property("debug.keyAlias"))
        assertEquals("android", property("debug.keyPassword"))

        assertTrue("$committed is not committed", committed.isFile)
        val keyStore = KeyStore.getInstance(committed, "android".toCharArray())
        assertNotNull(
            "androiddebugkey has no private key readable with password android",
            keyStore.getKey("androiddebugkey", "android".toCharArray()),
        )
    }

    // APP-004, APP-040: release signing is configured exactly when all four release-key
    // environment variables are set and non-blank. CI's unit-test job has none of them, so there
    // this asserts a release build is unsigned; a machine holding the key gets it configured.
    @Test
    fun `APP-004 APP-040 release builds are signed only when the release key is supplied`() {
        val keyVariables = listOf(
            "ANDROID_KEYSTORE_PATH",
            "ANDROID_KEYSTORE_PASSWORD",
            "ANDROID_KEY_ALIAS",
            "ANDROID_KEY_ALIAS_PASSWORD",
        )
        // Gradle reports whether it saw all four; this JVM inherits Gradle's environment, so the
        // report must agree with what is actually set here.
        val keySupplied = property("release.keySupplied").toBooleanStrict()
        assertEquals(
            "app.signing.release.keySupplied must say whether all of $keyVariables were set",
            keyVariables.all { !System.getenv(it).isNullOrBlank() },
            keySupplied,
        )
        assertEquals(keySupplied.toString(), property("release.configured"))
    }

    // APP-041: whatever the environment, release never uses the public debug key.
    @Test
    fun `APP-041 release builds never use the debug signing configuration`() {
        assertEquals("false", property("release.usesDebugConfig"))
        val releaseStore = property("release.storeFile")
        if (releaseStore.isNotEmpty()) {
            assertNotEquals(
                File("debug.keystore").canonicalPath,
                File(releaseStore).canonicalPath,
            )
        }
    }
}
