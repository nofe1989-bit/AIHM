package com.example.aihm.ml

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Place in app/src/androidTest; requires an Android device or emulator. */
@RunWith(AndroidJUnit4::class)
class Task13ParityInstrumentedTest {
    @Test fun modelMatchesPythonFixtures() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        AihmAnomalyDetector(context).use { model ->
            val lines = context.assets.open("android_parity_fixtures.csv")
                .bufferedReader().use { it.readLines() }.drop(1)
            for (line in lines) {
                val row = line.split(",")
                val hr = row[1].toFloat()
                val steps = row[2].takeIf { it.isNotBlank() }?.toFloat()
                val missing = row[3].toFloat().toInt()
                assertEquals("missing step flag", missing, if (steps == null) 1 else 0)
                val expectedScore = row[4].toFloat()
                val expectedFlag = row[5].toInt() == 1
                val actual = model.scoreWindow(hr, steps)
                assertEquals("score on $line", expectedScore, actual.score, 1e-4f)
                assertEquals("flag on $line", expectedFlag, actual.flagged)
            }
        }
    }
}
