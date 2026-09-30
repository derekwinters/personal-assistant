package com.derekwinters.personalassistant

import android.content.Intent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HomeScreenTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    // APP-010: the launcher intent resolves to MainActivity, which opens the home screen.
    @Test
    fun `APP-010 launcher intent opens MainActivity`() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)

        assertEquals(MainActivity::class.java.name, launch?.component?.className)
        assertEquals(Intent.ACTION_MAIN, launch?.action)
    }

    // APP-011: the home screen shows the app name from the app_name string resource.
    @Test
    fun `APP-011 home screen shows the app name`() {
        val appName = composeRule.activity.getString(R.string.app_name)

        composeRule.onNodeWithText(appName).assertIsDisplayed()
    }
}
