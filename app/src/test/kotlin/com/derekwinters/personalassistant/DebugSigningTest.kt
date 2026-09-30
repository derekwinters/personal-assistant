package com.derekwinters.personalassistant

import java.io.File
import java.security.KeyStore
import org.junit.Assert.assertEquals
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

    // APP-004: release has no signing configuration, so the public debug key never signs it.
    @Test
    fun `APP-004 release builds have no signing configuration`() {
        assertEquals("false", property("release.configured"))
    }
}
