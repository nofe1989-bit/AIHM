package com.example.aihm

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataItem
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

// ---------------------------------------------------------
// COLORS
// ---------------------------------------------------------

private val BackgroundColor = Color(0xFFFFE4EC)   // Baby pink
private val MainCardColor = Color(0xFFFFF7FA)
private val InfoCardColor = Color(0xFFFFF0F5)
private val AccentColor = Color(0xFF9D3158)
private val MainTextColor = Color(0xFF40232F)
private val SecondaryTextColor = Color(0xFF765563)
private val HeartRed = Color(0xFFB71C1C)

// ---------------------------------------------------------
// ACTIVITY OPTIONS
// ---------------------------------------------------------

private val ActivityChoices = listOf(
    "rest" to "Rest",
    "walking" to "Walking",
    "exercise" to "Exercise",
    "recovery" to "Recovery after exercise"
)

private enum class ReadingState {
    LOADING,
    AVAILABLE,
    EMPTY,
    ERROR
}

private fun activityLabel(code: String): String {
    return ActivityChoices
        .firstOrNull { it.first == code }
        ?.second
        ?: "Not specified"
}

private fun formatTime(timestamp: Long): String {
    if (timestamp <= 0L) {
        return "No reading received"
    }

    return SimpleDateFormat(
        "dd MMM yyyy • hh:mm:ss a",
        Locale.ENGLISH
    ).format(Date(timestamp))
}

// ---------------------------------------------------------
// MAIN ACTIVITY - PHONE
// ---------------------------------------------------------

class MainActivity :
    ComponentActivity(),
    DataClient.OnDataChangedListener {

    private var heartRate by mutableStateOf<String?>(null)
    private var latestTimestamp by mutableLongStateOf(0L)
    private var activityCode by mutableStateOf("unspecified")

    private var errorMessage by mutableStateOf<String?>(null)
    private var waiting by mutableStateOf(true)
    private var screenActive by mutableStateOf(false)

    private var session by mutableIntStateOf(0)

    private var pendingActivity by mutableStateOf<String?>(null)
    private var activityFeedback by mutableStateOf<String?>(null)

    private var requestNumber by mutableIntStateOf(0)
    private var requestTimestamp = 0L

    // ID of the watch that supplied the last HR reading.
    private var sourceNodeId: String? = null

    private val dataClient by lazy {
        Wearable.getDataClient(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {

            MaterialTheme {

                // Stop showing "waiting" forever.
                LaunchedEffect(
                    screenActive,
                    session,
                    waiting
                ) {
                    if (screenActive && waiting) {
                        delay(20_000L)

                        if (screenActive && waiting) {
                            waiting = false
                        }
                    }
                }

                // Timeout while waiting for activity confirmation.
                LaunchedEffect(
                    pendingActivity,
                    requestNumber
                ) {
                    if (pendingActivity != null) {
                        delay(20_000L)

                        if (pendingActivity != null) {
                            pendingActivity = null

                            activityFeedback =
                                "No confirmation yet. Keep AIHM open on the watch and try again."
                        }
                    }
                }

                val state = when {
                    errorMessage != null ->
                        ReadingState.ERROR

                    heartRate != null ->
                        ReadingState.AVAILABLE

                    waiting ->
                        ReadingState.LOADING

                    else ->
                        ReadingState.EMPTY
                }

                Dashboard(
                    state = state,
                    heartRate = heartRate,
                    timestamp = latestTimestamp,
                    activityCode = activityCode,
                    errorMessage = errorMessage,
                    pendingActivity = pendingActivity,
                    activityFeedback = activityFeedback,
                    onRetry = {
                        retryReading()
                    },
                    onActivitySelected = { code ->
                        sendActivity(code)
                    }
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()

        screenActive = true
        session++

        errorMessage = null
        waiting = heartRate == null

        connectAndLoad(session)
    }

    override fun onPause() {
        screenActive = false

        session++
        requestNumber++

        if (pendingActivity != null) {
            pendingActivity = null
            activityFeedback =
                "Check the activity on the next received reading."
        }

        dataClient.removeListener(this)

        super.onPause()
    }

    private fun isCurrent(requestSession: Int): Boolean {
        return screenActive &&
                requestSession == session
    }

    // ---------------------------------------------------------
    // WATCH CONNECTION
    // ---------------------------------------------------------

    private fun connectAndLoad(requestSession: Int) {

        dataClient
            .addListener(this)
            .addOnSuccessListener {

                if (isCurrent(requestSession)) {
                    loadLatestReading(requestSession)
                }
            }
            .addOnFailureListener {

                if (isCurrent(requestSession)) {
                    waiting = false

                    errorMessage =
                        "Could not start receiving watch data."
                }
            }
    }

    private fun retryReading() {

        session++

        errorMessage = null
        waiting = heartRate == null

        connectAndLoad(session)
    }

    // ---------------------------------------------------------
    // LOAD LAST WATCH READING
    // ---------------------------------------------------------

    private fun loadLatestReading(requestSession: Int) {

        dataClient.dataItems
            .addOnSuccessListener { items ->

                try {

                    if (isCurrent(requestSession)) {

                        for (item in items) {

                            if (item.uri.path == "/heart_rate") {

                                readHeartRateItem(
                                    item = item,
                                    requestSession = requestSession
                                )
                            }
                        }
                    }

                } finally {

                    items.release()
                }
            }
            .addOnFailureListener {

                if (isCurrent(requestSession)) {

                    waiting = false

                    errorMessage =
                        "Could not load watch data."
                }
            }
    }

    // ---------------------------------------------------------
    // RECEIVE NEW DATA FROM WATCH
    // ---------------------------------------------------------

    override fun onDataChanged(dataEvents: DataEventBuffer) {

        val requestSession = session

        for (event in dataEvents) {

            if (
                event.type == DataEvent.TYPE_CHANGED &&
                event.dataItem.uri.path == "/heart_rate"
            ) {

                readHeartRateItem(
                    item = event.dataItem,
                    requestSession = requestSession
                )
            }
        }
    }

    private fun readHeartRateItem(
        item: DataItem,
        requestSession: Int
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

            val receivedActivity =
                data.getString("activity")
                    ?: "unspecified"

            val nodeId =
                item.uri.host

            if (
                !bpm.isFinite() ||
                bpm <= 0.0 ||
                timestamp <= 0L
            ) {
                return
            }

            runOnUiThread {

                if (
                    isCurrent(requestSession) &&
                    timestamp >= latestTimestamp
                ) {

                    heartRate =
                        bpm.roundToInt().toString()

                    latestTimestamp =
                        timestamp

                    activityCode =
                        receivedActivity

                    sourceNodeId =
                        nodeId

                    errorMessage =
                        null

                    waiting =
                        false

                    if (
                        pendingActivity != null &&
                        receivedActivity == pendingActivity &&
                        timestamp > requestTimestamp
                    ) {

                        pendingActivity = null

                        activityFeedback =
                            "Activity confirmed with a new reading."
                    }
                }
            }

        } catch (_: Exception) {

            runOnUiThread {

                if (isCurrent(requestSession)) {

                    waiting = false

                    errorMessage =
                        "Could not read the received data."
                }
            }
        }
    }

    // ---------------------------------------------------------
    // SEND ACTIVITY FROM PHONE TO WATCH
    // ---------------------------------------------------------

    private fun sendActivity(code: String) {

        if (
            ActivityChoices.none {
                it.first == code
            }
        ) {
            return
        }

        if (pendingActivity != null) {
            return
        }

        requestNumber++

        val thisRequest =
            requestNumber

        requestTimestamp =
            latestTimestamp

        pendingActivity =
            code

        activityFeedback =
            "Sending to watch..."

        fun requestStillPending(): Boolean {
            return (
                    thisRequest == requestNumber &&
                            pendingActivity == code
                    )
        }

        Wearable
            .getNodeClient(this)
            .connectedNodes
            .addOnSuccessListener { nodes ->

                if (!requestStillPending()) {
                    return@addOnSuccessListener
                }

                val target =
                    if (sourceNodeId != null) {

                        nodes.firstOrNull {
                            it.id == sourceNodeId
                        }

                    } else {

                        nodes.singleOrNull()
                    }

                if (target == null) {

                    pendingActivity = null

                    activityFeedback =
                        "Could not identify a connected watch. Open AIHM on the watch and receive a reading first."

                    return@addOnSuccessListener
                }

                Wearable
                    .getMessageClient(this)
                    .sendMessage(
                        target.id,
                        "/set_activity",
                        code.toByteArray(Charsets.UTF_8)
                    )
                    .addOnSuccessListener {

                        if (requestStillPending()) {

                            activityFeedback =
                                "Request sent. Waiting for a new watch reading."
                        }
                    }
                    .addOnFailureListener {

                        if (requestStillPending()) {

                            pendingActivity = null

                            activityFeedback =
                                "Could not send. Check the watch connection."
                        }
                    }
            }
            .addOnFailureListener {

                if (requestStillPending()) {

                    pendingActivity = null

                    activityFeedback =
                        "Could not check connected devices."
                }
            }
    }
}

// ---------------------------------------------------------
// PHONE DASHBOARD
// ---------------------------------------------------------

@Composable
private fun Dashboard(
    state: ReadingState,
    heartRate: String?,
    timestamp: Long,
    activityCode: String,
    errorMessage: String?,
    pendingActivity: String?,
    activityFeedback: String?,
    onRetry: () -> Unit,
    onActivitySelected: (String) -> Unit
) {

    var showChoices by remember {
        mutableStateOf(false)
    }

    val title = when (state) {

        ReadingState.LOADING ->
            "Waiting for watch data"

        ReadingState.AVAILABLE ->
            "Last received heart rate"

        ReadingState.EMPTY ->
            "No reading received"

        ReadingState.ERROR ->
            "Data error"
    }

    val description = when (state) {

        ReadingState.LOADING ->
            "Keep AIHM open on your watch and select an activity."

        ReadingState.AVAILABLE ->
            "Last received reading. Check the measurement time below."

        ReadingState.EMPTY ->
            "Open AIHM on your watch, allow access and select an activity."

        ReadingState.ERROR ->
            errorMessage ?: "Could not receive watch data."
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundColor)
            .systemBarsPadding()
            .verticalScroll(
                rememberScrollState()
            )
            .padding(16.dp),

        horizontalAlignment =
            Alignment.CenterHorizontally,

        verticalArrangement =
            Arrangement.spacedBy(12.dp)
    ) {

        // -------------------------------------------------
        // HEADER
        // -------------------------------------------------

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp),

            horizontalArrangement =
                Arrangement.SpaceBetween,

            verticalAlignment =
                Alignment.CenterVertically
        ) {

            Text(
                text = "AIHM",
                color = AccentColor,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )

            Surface(
                color = Color(0xFFF8CCD9),
                shape = RoundedCornerShape(12.dp)
            ) {

                Text(
                    text = "PROTOTYPE",
                    color = AccentColor,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(
                        horizontal = 10.dp,
                        vertical = 6.dp
                    )
                )
            }
        }

        Text(
            text = "Your heart rate",
            color = MainTextColor,
            fontSize = 27.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.fillMaxWidth()
        )

        Text(
            text = "Your smartwatch reading and activity",
            color = SecondaryTextColor,
            fontSize = 14.sp,
            modifier = Modifier.fillMaxWidth()
        )

        // -------------------------------------------------
        // HEART RATE CARD
        // -------------------------------------------------

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(
                containerColor = MainCardColor
            )
        ) {

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(24.dp),

                horizontalAlignment =
                    Alignment.CenterHorizontally,

                verticalArrangement =
                    Arrangement.spacedBy(8.dp)
            ) {

                Text(
                    text = title,
                    color = MainTextColor,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center
                )

                HeartVisual(state)

                Text(
                    text =
                        if (state == ReadingState.AVAILABLE) {
                            "${heartRate ?: "--"} BPM"
                        } else {
                            "-- BPM"
                        },

                    color = AccentColor,
                    fontSize = 44.sp,
                    fontWeight = FontWeight.Bold
                )

                Text(
                    text = description,
                    color = SecondaryTextColor,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center
                )

                if (
                    state == ReadingState.EMPTY ||
                    state == ReadingState.ERROR
                ) {

                    Button(
                        onClick = onRetry,
                        colors =
                            ButtonDefaults.buttonColors(
                                containerColor = AccentColor,
                                contentColor = Color.White
                            )
                    ) {

                        Text(
                            text = "Retry receiving"
                        )
                    }
                }
            }
        }

        // -------------------------------------------------
        // PREVIOUS READING
        // -------------------------------------------------

        if (
            heartRate != null &&
            state != ReadingState.AVAILABLE
        ) {

            InfoCard(
                title = "Previously received reading",
                value = "$heartRate BPM"
            )
        }

        // -------------------------------------------------
        // MEASUREMENT TIME
        // -------------------------------------------------

        InfoCard(
            title = "Measurement time",
            value = formatTime(timestamp)
        )

        // -------------------------------------------------
        // ACTIVITY CARD
        // -------------------------------------------------

        Card(
            onClick = {
                showChoices = true
            },

            enabled =
                pendingActivity == null,

            modifier =
                Modifier.fillMaxWidth(),

            shape =
                RoundedCornerShape(18.dp),

            colors =
                CardDefaults.cardColors(
                    containerColor =
                        InfoCardColor
                )
        ) {

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(18.dp),

                horizontalAlignment =
                    Alignment.CenterHorizontally,

                verticalArrangement =
                    Arrangement.spacedBy(6.dp)
            ) {

                Text(
                    text = "Activity at measurement",
                    color = SecondaryTextColor,
                    fontSize = 12.sp
                )

                Text(
                    text =
                        if (heartRate != null) {

                            activityLabel(
                                activityCode
                            )

                        } else {

                            "Choose activity"
                        },

                    color = AccentColor,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center
                )

                Text(
                    text =
                        if (pendingActivity != null) {

                            "Waiting for ${
                                activityLabel(
                                    pendingActivity
                                )
                            }..."

                        } else {

                            "Tap to change"
                        },

                    color = SecondaryTextColor,
                    fontSize = 12.sp
                )

                activityFeedback?.let { feedback ->

                    Text(
                        text = feedback,
                        color = SecondaryTextColor,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }

        Text(
            text =
                "Change activity here or on your watch. Keep AIHM open on the watch.",

            color =
                SecondaryTextColor,

            fontSize =
                12.sp,

            textAlign =
                TextAlign.Center
        )

        // -------------------------------------------------
        // CLASSIFICATION PLACEHOLDER
        // -------------------------------------------------

        InfoCard(
            title = "Heart rate classification",
            value = "Not enabled yet"
        )

        Text(
            text =
                "This prototype displays readings and activity. " +
                        "It does not assess whether a reading is normal or abnormal.",

            color =
                SecondaryTextColor,

            fontSize =
                12.sp,

            textAlign =
                TextAlign.Center
        )

        Text(
            text =
                "The heart animation is decorative. Check the time for the last measurement.",

            color =
                SecondaryTextColor,

            fontSize =
                11.sp,

            textAlign =
                TextAlign.Center
        )

        Spacer(
            modifier =
                Modifier.height(12.dp)
        )
    }

    // ---------------------------------------------------------
    // ACTIVITY SELECTION DIALOG
    // ---------------------------------------------------------

    if (showChoices) {

        AlertDialog(
            onDismissRequest = {
                showChoices = false
            },

            containerColor =
                MainCardColor,

            title = {

                Text(
                    text = "Choose activity",
                    color = MainTextColor
                )
            },

            text = {

                Column {

                    ActivityChoices.forEach {
                            (code, label) ->

                        TextButton(
                            modifier =
                                Modifier.fillMaxWidth(),

                            onClick = {

                                showChoices = false

                                onActivitySelected(
                                    code
                                )
                            }
                        ) {

                            Text(
                                text = label,
                                color = AccentColor
                            )
                        }
                    }
                }
            },

            confirmButton = {

                TextButton(
                    onClick = {
                        showChoices = false
                    }
                ) {

                    Text(
                        text = "Cancel",
                        color = AccentColor
                    )
                }
            }
        )
    }
}

// ---------------------------------------------------------
// HEART VISUAL
// ---------------------------------------------------------

@Composable
private fun HeartVisual(
    state: ReadingState
) {

    Box(
        modifier = Modifier.size(
            width = 110.dp,
            height = 100.dp
        ),

        contentAlignment =
            Alignment.Center
    ) {

        if (
            state == ReadingState.EMPTY ||
            state == ReadingState.ERROR
        ) {

            Text(
                text = "💔",
                fontSize = 64.sp
            )

        } else {

            val charging =
                state == ReadingState.LOADING

            val transition =
                rememberInfiniteTransition(
                    label = "heart"
                )

            val scale by transition.animateFloat(

                initialValue =
                    if (charging) {
                        0.80f
                    } else {
                        0.90f
                    },

                targetValue =
                    if (charging) {
                        1.0f
                    } else {
                        1.06f
                    },

                animationSpec =
                    infiniteRepeatable(

                        animation =
                            tween(
                                durationMillis =
                                    if (charging) {
                                        900
                                    } else {
                                        450
                                    },

                                easing =
                                    FastOutSlowInEasing
                            ),

                        repeatMode =
                            RepeatMode.Reverse
                    ),

                label =
                    "heartScale"
            )

            val opacity by transition.animateFloat(

                initialValue =
                    if (charging) {
                        0.20f
                    } else {
                        1.0f
                    },

                targetValue =
                    1.0f,

                animationSpec =
                    infiniteRepeatable(

                        animation =
                            tween(
                                durationMillis = 900
                            ),

                        repeatMode =
                            RepeatMode.Reverse
                    ),

                label =
                    "heartOpacity"
            )

            Text(
                text = "♥️",
                color = HeartRed,
                fontSize = 76.sp,

                modifier =
                    Modifier.graphicsLayer {

                        scaleX = scale
                        scaleY = scale
                        alpha = opacity
                    }
            )
        }
    }
}

// ---------------------------------------------------------
// INFORMATION CARD
// ---------------------------------------------------------

@Composable
private fun InfoCard(
    title: String,
    value: String
) {

    Card(
        modifier =
            Modifier.fillMaxWidth(),

        shape =
            RoundedCornerShape(18.dp),

        colors =
            CardDefaults.cardColors(
                containerColor =
                    InfoCardColor
            )
    ) {

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),

            horizontalAlignment =
                Alignment.CenterHorizontally,

            verticalArrangement =
                Arrangement.spacedBy(6.dp)
        ) {

            Text(
                text = title,
                color = SecondaryTextColor,
                fontSize = 12.sp
            )

            Text(
                text = value,
                color = MainTextColor,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center
            )
        }
    }
}