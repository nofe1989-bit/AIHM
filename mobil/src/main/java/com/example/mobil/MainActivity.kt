package com.example.mobil

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.mobil.ui.theme.AIHMTheme
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.delay
import kotlin.random.Random

// =====================================================
// AIHM WATCH APP
// =====================================================

// Colors
private val BackgroundColor = Color(0xFF101014)
private val CardColor = Color(0xFF201B1E)
private val AccentColor = Color(0xFFFF7FA5)
private val MainTextColor = Color.White
private val SecondaryTextColor = Color(0xFFD6C5CC)
private val HeartColor = Color(0xFFFF4D67)

// Activity choices
private val ActivityChoices = listOf(
    "rest" to "Rest",
    "walking" to "Walking",
    "exercise" to "Exercise",
    "recovery" to "Recovery"
)

class MainActivity :
    ComponentActivity(),
    MessageClient.OnMessageReceivedListener {

    // -------------------------------------------------
    // Activity is OPTIONAL
    // -------------------------------------------------

    private var selectedActivity by mutableStateOf("unspecified")

    // Heart rate displayed on watch
    private var heartRate by mutableIntStateOf(0)

    // Measurement status
    private var measuring by mutableStateOf(true)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // =================================================
        // KEEP WATCH SCREEN ON
        // =================================================

        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        )

        setContent {
            AIHMTheme {

                // -----------------------------------------
                // Start measurement automatically
                // No activity selection is required
                // -----------------------------------------

                LaunchedEffect(Unit) {
                    measuring = true

                    while (true) {

                        /*
                         * TEMPORARY PROTOTYPE VALUE
                         *
                         * This keeps the UI/data connection testable.
                         * Replace this section with the real
                         * Health Services heart-rate reading later.
                         */

                        heartRate = Random.nextInt(
                            from = 65,
                            until = 96
                        )

                        sendHeartRateToPhone(
                            bpm = heartRate.toDouble()
                        )

                        delay(5000)
                    }
                }

                WatchScreen(
                    heartRate = heartRate,
                    measuring = measuring,
                    selectedActivity = selectedActivity,
                    onActivitySelected = { activity ->

                        selectedActivity = activity

                        // Immediately send current reading
                        // with the new activity.
                        if (heartRate > 0) {
                            sendHeartRateToPhone(
                                bpm = heartRate.toDouble()
                            )
                        }
                    }
                )
            }
        }
    }

    // =================================================
    // SEND HEART RATE TO PHONE
    // =================================================

    private fun sendHeartRateToPhone(
        bpm: Double
    ) {

        if (bpm <= 0.0) return

        val request =
            PutDataMapRequest.create("/heart_rate")

        request.dataMap.putDouble(
            "bpm",
            bpm
        )

        request.dataMap.putLong(
            "timestamp",
            System.currentTimeMillis()
        )

        request.dataMap.putString(
            "activity",
            selectedActivity
        )

        // Forces Data Layer to treat each measurement
        // as a new update.
        request.dataMap.putLong(
            "update_id",
            System.nanoTime()
        )

        val dataItem =
            request
                .asPutDataRequest()
                .setUrgent()

        Wearable
            .getDataClient(this)
            .putDataItem(dataItem)
    }

    // =================================================
    // RECEIVE ACTIVITY FROM PHONE
    // =================================================

    override fun onMessageReceived(
        messageEvent: MessageEvent
    ) {

        if (
            messageEvent.path != "/set_activity"
        ) {
            return
        }

        val receivedActivity =
            messageEvent.data.toString(
                Charsets.UTF_8
            )

        val valid =
            ActivityChoices.any {
                it.first == receivedActivity
            }

        if (!valid) return

        runOnUiThread {

            selectedActivity =
                receivedActivity

            // Send a fresh reading so phone can
            // confirm the activity change.
            if (heartRate > 0) {

                sendHeartRateToPhone(
                    bpm = heartRate.toDouble()
                )
            }
        }
    }

    // =================================================
    // MESSAGE LISTENER
    // =================================================

    override fun onResume() {
        super.onResume()

        Wearable
            .getMessageClient(this)
            .addListener(this)
    }

    override fun onPause() {

        Wearable
            .getMessageClient(this)
            .removeListener(this)

        super.onPause()
    }
}

// =====================================================
// WATCH SCREEN
// =====================================================

@Composable
private fun WatchScreen(
    heartRate: Int,
    measuring: Boolean,
    selectedActivity: String,
    onActivitySelected: (String) -> Unit
) {

    var showActivities by remember {
        mutableStateOf(false)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundColor)
            .verticalScroll(
                rememberScrollState()
            )
            .padding(
                horizontal = 18.dp,
                vertical = 22.dp
            ),
        horizontalAlignment =
            Alignment.CenterHorizontally,
        verticalArrangement =
            Arrangement.spacedBy(10.dp)
    ) {

        Text(
            text = "AIHM",
            color = AccentColor,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold
        )

        Text(
            text = "♥️",
            color = HeartColor,
            fontSize = 54.sp
        )

        Text(
            text =
                if (heartRate > 0)
                    "$heartRate BPM"
                else
                    "-- BPM",
            color = MainTextColor,
            fontSize = 30.sp,
            fontWeight = FontWeight.Bold
        )

        Text(
            text =
                if (measuring)
                    "Monitoring heart rate"
                else
                    "Waiting",
            color = SecondaryTextColor,
            fontSize = 12.sp,
            textAlign = TextAlign.Center
        )

        Spacer(
            modifier = Modifier.height(4.dp)
        )

        // =============================================
        // ACTIVITY — OPTIONAL
        // =============================================

        Card(
            onClick = {
                showActivities = true
            },
            modifier =
                Modifier.fillMaxWidth(),
            shape =
                RoundedCornerShape(18.dp),
            colors =
                CardDefaults.cardColors(
                    containerColor = CardColor
                )
        ) {

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                horizontalAlignment =
                    Alignment.CenterHorizontally
            ) {

                Text(
                    text = "Activity",
                    color =
                        SecondaryTextColor,
                    fontSize = 10.sp
                )

                Text(
                    text =
                        activityLabel(
                            selectedActivity
                        ),
                    color = AccentColor,
                    fontSize = 14.sp,
                    fontWeight =
                        FontWeight.Bold,
                    textAlign =
                        TextAlign.Center
                )

                Text(
                    text = "Optional • Tap to change",
                    color =
                        SecondaryTextColor,
                    fontSize = 9.sp,
                    textAlign =
                        TextAlign.Center
                )
            }
        }

        Text(
            text =
                "AIHM Prototype",
            color =
                SecondaryTextColor,
            fontSize = 9.sp
        )

        Spacer(
            modifier = Modifier.height(20.dp)
        )
    }

    // =================================================
    // ACTIVITY POPUP
    // =================================================

    if (showActivities) {

        AlertDialog(
            onDismissRequest = {
                showActivities = false
            },

            title = {
                Text(
                    text = "Activity"
                )
            },

            text = {

                Column {

                    ActivityChoices.forEach {
                            (code, label) ->

                        TextButton(
                            onClick = {

                                showActivities =
                                    false

                                onActivitySelected(
                                    code
                                )
                            },
                            modifier =
                                Modifier.fillMaxWidth()
                        ) {

                            Text(
                                text = label
                            )
                        }
                    }
                }
            },

            confirmButton = {

                TextButton(
                    onClick = {
                        showActivities =
                            false
                    }
                ) {

                    Text(
                        text = "Cancel"
                    )
                }
            }
        )
    }
}

// =====================================================
// ACTIVITY LABEL
// =====================================================

private fun activityLabel(
    code: String
): String {

    return ActivityChoices
        .firstOrNull {
            it.first == code
        }
        ?.second
        ?: "Not specified"
}