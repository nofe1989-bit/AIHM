package com.example.mobil

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.*
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.mobil.ui.theme.AIHMTheme
import com.google.android.gms.wearable.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

// =====================================================
// COLORS
// =====================================================

private val BackgroundColor = Color(0xFF0D1B2A)
private val MainCardColor = Color(0xFF0F2537)
private val InfoCardColor = Color(0xFF132A3E)
private val CyanColor = Color(0xFF00E5FF)

// أحمر غامق للقلب
private val HeartRed = Color(0xFFB71C1C)


// =====================================================
// MAIN ACTIVITY
// =====================================================

class MainActivity : ComponentActivity(),
    DataClient.OnDataChangedListener {

    private var heartRate by mutableStateOf<String?>(null)

    private var measurementTime by mutableStateOf<String?>(null)

    private var latestTimestamp by mutableLongStateOf(0L)

    private var errorMessage by mutableStateOf<String?>(null)

    private var isLoading by mutableStateOf(true)

    private var screenActive = false

    private val dataClient by lazy {
        Wearable.getDataClient(this)
    }


    override fun onCreate(savedInstanceState: Bundle?) {

        super.onCreate(savedInstanceState)

        setContent {

            AIHMTheme {

                Dashboard(
                    heartRate = heartRate,
                    measurementTime = measurementTime,
                    errorMessage = errorMessage,
                    isLoading = isLoading
                )
            }
        }
    }


    // =====================================================
    // START LISTENING
    // =====================================================

    override fun onResume() {

        super.onResume()

        screenActive = true
        errorMessage = null

        // فقط إذا لم توجد قراءة سابقة
        if (heartRate == null) {
            isLoading = true
        }

        dataClient
            .addListener(this)
            .addOnSuccessListener {

                if (screenActive) {
                    loadLatestReading()
                }
            }
            .addOnFailureListener {

                if (screenActive) {

                    isLoading = false

                    errorMessage =
                        "Could not connect to smartwatch."
                }
            }
    }


    // =====================================================
    // LOAD LAST READING
    // =====================================================

    private fun loadLatestReading() {

        dataClient.dataItems
            .addOnSuccessListener { items ->

                var found = false

                try {

                    if (screenActive) {

                        for (item in items) {

                            if (item.uri.path == "/heart_rate") {

                                found = true

                                readHeartRateItem(item)
                            }
                        }
                    }

                } finally {

                    items.release()

                    if (!found && screenActive) {

                        isLoading = true
                    }
                }
            }
            .addOnFailureListener {

                if (screenActive) {

                    isLoading = false

                    errorMessage =
                        "Could not load the last reading."
                }
            }
    }


    // =====================================================
    // RECEIVE NEW WATCH DATA
    // =====================================================

    override fun onDataChanged(
        dataEvents: DataEventBuffer
    ) {

        if (!screenActive) return

        for (event in dataEvents) {

            if (
                event.type == DataEvent.TYPE_CHANGED &&
                event.dataItem.uri.path == "/heart_rate"
            ) {

                errorMessage = null

                readHeartRateItem(
                    event.dataItem
                )
            }
        }
    }


    // =====================================================
    // READ HEART RATE
    // =====================================================

    private fun readHeartRateItem(
        item: DataItem
    ) {

        if (item.uri.path != "/heart_rate") {
            return
        }

        try {

            val data =
                DataMapItem
                    .fromDataItem(item)
                    .dataMap

            if (
                !data.containsKey("bpm") ||
                !data.containsKey("timestamp")
            ) {
                return
            }

            val bpm =
                data.getDouble("bpm")

            val timestamp =
                data.getLong("timestamp")

            if (
                !bpm.isFinite() ||
                bpm <= 0 ||
                timestamp <= 0
            ) {
                return
            }

            runOnUiThread {

                if (
                    screenActive &&
                    timestamp >= latestTimestamp
                ) {

                    latestTimestamp =
                        timestamp

                    heartRate =
                        bpm.roundToInt().toString()

                    measurementTime =
                        SimpleDateFormat(
                            "dd MMM yyyy • hh:mm:ss a",
                            Locale.ENGLISH
                        ).format(
                            Date(timestamp)
                        )

                    errorMessage = null
                    isLoading = false
                }
            }

        } catch (e: Exception) {

            runOnUiThread {

                if (screenActive) {

                    isLoading = false

                    errorMessage =
                        "Could not read watch data."
                }
            }
        }
    }


    // =====================================================
    // STOP LISTENING
    // =====================================================

    override fun onPause() {

        screenActive = false

        dataClient.removeListener(this)

        super.onPause()
    }
}


// =====================================================
// DASHBOARD
// =====================================================

@Composable
fun Dashboard(
    heartRate: String?,
    measurementTime: String?,
    errorMessage: String?,
    isLoading: Boolean
) {

    val scrollState =
        rememberScrollState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundColor)
            .verticalScroll(scrollState)
            .padding(16.dp),

        horizontalAlignment =
            Alignment.CenterHorizontally
    ) {

        // =================================================
        // HEADER
        // =================================================

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 12.dp),

            horizontalArrangement =
                Arrangement.SpaceBetween,

            verticalAlignment =
                Alignment.CenterVertically
        ) {

            Text(
                text = "AIHM",
                color = CyanColor,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold
            )

            Surface(
                color =
                    Color(0xFF1E3A8A)
                        .copy(alpha = 0.30f),

                shape =
                    RoundedCornerShape(12.dp)
            ) {

                Text(
                    text = "PROTOTYPE",
                    color = Color(0xFF60A5FA),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,

                    modifier =
                        Modifier.padding(
                            horizontal = 8.dp,
                            vertical = 4.dp
                        )
                )
            }
        }


        Spacer(
            modifier =
                Modifier.height(8.dp)
        )


        // =================================================
        // TITLE
        // =================================================

        Text(
            text = "Your heart rate",
            color = Color.White,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.fillMaxWidth()
        )

        Text(
            text =
                "Your latest smartwatch reading, in one place",

            color = Color.Gray,
            fontSize = 13.sp,
            modifier = Modifier.fillMaxWidth()
        )


        Spacer(
            modifier =
                Modifier.height(16.dp)
        )


        // =================================================
        // HEART RATE CARD
        // =================================================

        Card(
            modifier = Modifier
                .fillMaxWidth()
                .height(250.dp),

            colors =
                CardDefaults.cardColors(
                    containerColor =
                        MainCardColor
                ),

            shape =
                RoundedCornerShape(20.dp)
        ) {

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(20.dp)
            ) {

                Text(
                    text = "LATEST READING",
                    color = Color.Gray,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,

                    modifier =
                        Modifier.align(
                            Alignment.TopStart
                        )
                )


                // =========================================
                // ERROR
                // =========================================

                if (errorMessage != null) {

                    Column(
                        modifier =
                            Modifier.align(
                                Alignment.Center
                            ),

                        horizontalAlignment =
                            Alignment.CenterHorizontally
                    ) {

                        StableBrokenHeart()

                        Spacer(
                            modifier =
                                Modifier.height(5.dp)
                        )

                        Text(
                            text = "Connection Error",
                            color = HeartRed,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )

                        Text(
                            text = errorMessage,
                            color = Color.Gray,
                            fontSize = 11.sp
                        )
                    }
                }


                // =========================================
                // LOADING
                // =========================================

                else if (isLoading) {

                    Column(
                        modifier =
                            Modifier.align(
                                Alignment.Center
                            ),

                        horizontalAlignment =
                            Alignment.CenterHorizontally
                    ) {

                        StableChargingHeart()

                        Spacer(
                            modifier =
                                Modifier.height(5.dp)
                        )

                        Text(
                            text =
                                "Reading heart rate...",

                            color = Color.White,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )

                        Text(
                            text =
                                "Receiving data from watch",

                            color = Color.Gray,
                            fontSize = 11.sp
                        )
                    }
                }


                // =========================================
                // SUCCESS
                // =========================================

                else if (heartRate != null) {

                    Column(
                        modifier =
                            Modifier.align(
                                Alignment.Center
                            ),

                        horizontalAlignment =
                            Alignment.CenterHorizontally
                    ) {

                        StableBeatingHeart()

                        Row(
                            verticalAlignment =
                                Alignment.Bottom
                        ) {

                            Text(
                                text = heartRate,
                                color = Color.White,
                                fontSize = 62.sp,
                                fontWeight = FontWeight.Bold
                            )

                            Spacer(
                                modifier =
                                    Modifier.width(8.dp)
                            )

                            Text(
                                text = "BPM",
                                color = CyanColor,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,

                                modifier =
                                    Modifier.padding(
                                        bottom = 11.dp
                                    )
                            )
                        }
                    }

                    Text(
                        text =
                            measurementTime
                                ?: "Measured recently",

                        color = Color.LightGray,
                        fontSize = 12.sp,

                        modifier =
                            Modifier.align(
                                Alignment.BottomCenter
                            )
                    )
                }


                // =========================================
                // NO DATA
                // =========================================

                else {

                    Column(
                        modifier =
                            Modifier.align(
                                Alignment.Center
                            ),

                        horizontalAlignment =
                            Alignment.CenterHorizontally
                    ) {

                        StableChargingHeart()

                        Text(
                            text =
                                "Waiting for reading...",

                            color = Color.White,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }


        Spacer(
            modifier =
                Modifier.height(16.dp)
        )


        // =================================================
        // MEASUREMENT TIME
        // =================================================

        InfoCard(
            title = "Measurement time",

            value =
                measurementTime
                    ?: "Waiting for measurement..."
        )


        Spacer(
            modifier =
                Modifier.height(12.dp)
        )


        // =================================================
        // DATA UPDATES
        // =================================================

        InfoCard(
            title = "Data updates",

            value =
                when {

                    errorMessage != null ->
                        "Connection problem"

                    isLoading ->
                        "Receiving smartwatch data..."

                    heartRate != null ->
                        "✓ Watch data received"

                    else ->
                        "Waiting for watch..."
                }
        )


        Spacer(
            modifier =
                Modifier.height(12.dp)
        )


        // =================================================
        // CLASSIFICATION
        // =================================================

        val rateInt =
            heartRate?.toIntOrNull()

        Card(
            modifier =
                Modifier.fillMaxWidth(),

            colors =
                CardDefaults.cardColors(
                    containerColor =
                        InfoCardColor
                ),

            shape =
                RoundedCornerShape(16.dp)
        ) {

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),

                horizontalAlignment =
                    Alignment.CenterHorizontally
            ) {

                Text(
                    text =
                        "Heart rate classification",

                    color = Color.Gray,
                    fontSize = 11.sp
                )

                Spacer(
                    modifier =
                        Modifier.height(6.dp)
                )

                Text(
                    text =
                        when {

                            rateInt == null ->
                                "Not available yet"

                            rateInt in 60..100 ->
                                "Normal Heart Rate"

                            rateInt > 100 ->
                                "⚠ High Heart Rate"

                            else ->
                                "⚠ Low Heart Rate"
                        },

                    color =
                        when {

                            rateInt == null ->
                                Color.Gray

                            rateInt in 60..100 ->
                                CyanColor

                            else ->
                                HeartRed
                        },

                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }


        Spacer(
            modifier =
                Modifier.height(20.dp)
        )
    }
}


// =====================================================
// FIXED HEART CONTAINER
//
// مهم:
// حجم هذا الـ Box ثابت دائمًا.
// الحركة تحصل داخل القلب فقط.
// لذلك لا تتحرك أي بطاقة أو زر.
// =====================================================

@Composable
private fun HeartContainer(
    content: @Composable BoxScope.() -> Unit
) {

    Box(
        modifier = Modifier
            .width(90.dp)
            .height(82.dp),

        contentAlignment =
            Alignment.Center,

        content = content
    )
}


// =====================================================
// LOADING HEART
// =====================================================

@Composable
fun StableChargingHeart() {

    val transition =
        rememberInfiniteTransition(
            label = "chargingHeart"
        )


    val alpha by
    transition.animateFloat(

        initialValue = 0.25f,
        targetValue = 1f,

        animationSpec =
            infiniteRepeatable(

                animation =
                    tween(
                        durationMillis = 900,
                        easing =
                            LinearEasing
                    ),

                repeatMode =
                    RepeatMode.Reverse
            ),

        label = "chargingAlpha"
    )


    val scale by
    transition.animateFloat(

        initialValue = 0.78f,
        targetValue = 1f,

        animationSpec =
            infiniteRepeatable(

                animation =
                    tween(
                        durationMillis = 900,
                        easing =
                            FastOutSlowInEasing
                    ),

                repeatMode =
                    RepeatMode.Reverse
            ),

        label = "chargingScale"
    )


    HeartContainer {

        Text(
            text = "♥️",

            color = HeartRed,

            fontSize = 66.sp,

            fontWeight =
                FontWeight.Bold,

            modifier =
                Modifier.graphicsLayer {

                    /*
                     * هذه الحركة رسومية فقط.
                     * لا تغيّر حجم الـ Layout.
                     */

                    scaleX = scale
                    scaleY = scale
                    this.alpha = alpha
                }
        )
    }
}


// =====================================================
// SUCCESS HEART - BEATING
// =====================================================

@Composable
fun StableBeatingHeart() {

    val transition =
        rememberInfiniteTransition(
            label = "beatingHeart"
        )


    val scale by
    transition.animateFloat(

        initialValue = 0.90f,

        targetValue = 1.08f,

        animationSpec =
            infiniteRepeatable(

                animation =
                    tween(
                        durationMillis = 450,
                        easing =
                            FastOutSlowInEasing
                    ),

                repeatMode =
                    RepeatMode.Reverse
            ),

        label = "beatScale"
    )


    HeartContainer {

        Text(
            text = "♥️",

            color = HeartRed,

            fontSize = 66.sp,

            fontWeight =
                FontWeight.Bold,

            modifier =
                Modifier.graphicsLayer {

                    /*
                     * القلب نفسه ينبض.
                     * الـ Box الخارجي ثابت.
                     */

                    scaleX = scale
                    scaleY = scale
                }
        )
    }
}


// =====================================================
// ERROR HEART
// =====================================================

@Composable
fun StableBrokenHeart() {

    HeartContainer {

        Text(
            text = "💔",
            fontSize = 52.sp
        )
    }
}


// =====================================================
// INFORMATION CARD
// =====================================================

@Composable
fun InfoCard(
    title: String,
    value: String
) {

    Card(
        modifier =
            Modifier.fillMaxWidth(),

        colors =
            CardDefaults.cardColors(
                containerColor =
                    InfoCardColor
            ),

        shape =
            RoundedCornerShape(16.dp)
    ) {

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),

            horizontalAlignment =
                Alignment.CenterHorizontally
        ) {

            Text(
                text = title,
                color = Color.Gray,
                fontSize = 11.sp
            )

            Spacer(
                modifier =
                    Modifier.height(5.dp)
            )

            Text(
                text = value,
                color = Color.White,
                fontSize = 15.sp,
                fontWeight =
                    FontWeight.SemiBold
            )
        }
    }
}