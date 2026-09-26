package com.example.aihm

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.health.services.client.HealthServices
import androidx.health.services.client.MeasureCallback
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.DeltaDataType
import com.example.aihm.ui.theme.AIHMTheme
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import java.time.Instant
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {

    private var heartRate by mutableStateOf("--")
    private var status by mutableStateOf("Permission needed")
    private var syncStatus by mutableStateOf("")
    private var permissionGranted by mutableStateOf(false)

    private var screenActive = false
    private var registered = false
    private var checkingSupport = false
    private var latestTimestamp = 0L

    private val measureClient by lazy {
        HealthServices.getClient(this).measureClient
    }

    private val dataClient by lazy {
        Wearable.getDataClient(this)
    }

    private val heartRatePermission: String
        get() = if (Build.VERSION.SDK_INT >= 36) {
            "android.permission.health.READ_HEART_RATE"
        } else {
            Manifest.permission.BODY_SENSORS
        }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        permissionGranted = granted

        if (granted) {
            startMeasurement()
        } else {
            status = "Please allow heart rate access"
        }
    }

    private val heartRateCallback = object : MeasureCallback {

        override fun onAvailabilityChanged(
            dataType: DeltaDataType<*, *>,
            availability: Availability
        ) {
            // Wait for a valid reading.
        }

        override fun onDataReceived(data: DataPointContainer) {
            if (!screenActive) return

            val sample = data.getData(DataType.HEART_RATE_BPM)
                .filter { it.value.isFinite() && it.value > 0 }
                .maxByOrNull { it.timeDurationFromBoot }
                ?: return

            val bootInstant = Instant.ofEpochMilli(
                System.currentTimeMillis() - SystemClock.elapsedRealtime()
            )

            val timestamp = sample.getTimeInstant(bootInstant)
                .toEpochMilli()

            if (timestamp <= latestTimestamp) return
            latestTimestamp = timestamp

            heartRate = sample.value.roundToInt().toString()
            status = "Heart rate"

            sendHeartRate(sample.value, timestamp)
        }

        override fun onRegistrationFailed(throwable: Throwable) {
            registered = false
            status = "Could not start measurement"
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        )

        setContent {
            AIHMTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.Black)
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text(
                        text = "AIHM",
                        color = Color.White,
                        fontSize = 18.sp
                    )

                    Text(
                        text = heartRate,
                        color = Color(0xFF80CBC4),
                        fontSize = 44.sp
                    )

                    Text(
                        text = "BPM",
                        color = Color.White,
                        fontSize = 14.sp
                    )

                    Text(
                        text = status,
                        color = Color.LightGray,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center
                    )

                    if (syncStatus.isNotEmpty()) {
                        Text(
                            text = syncStatus,
                            color = Color(0xFF80CBC4),
                            fontSize = 11.sp,
                            textAlign = TextAlign.Center
                        )
                    }

                    if (!permissionGranted) {
                        Button(
                            onClick = {
                                permissionLauncher.launch(
                                    heartRatePermission
                                )
                            }
                        ) {
                            Text("Allow")
                        }
                    }
                }
            }
        }
    }

    private fun sendHeartRate(bpm: Double, timestamp: Long) {
        val request = PutDataMapRequest.create("/heart_rate").apply {
            dataMap.putDouble("bpm", bpm)
            dataMap.putLong("timestamp", timestamp)
        }.asPutDataRequest().setUrgent()

        syncStatus = "Syncing..."

        dataClient.putDataItem(request)
            .addOnSuccessListener {
                if (screenActive && timestamp == latestTimestamp) {
                    syncStatus = "Queued for phone sync"
                }
            }
            .addOnFailureListener {
                if (screenActive && timestamp == latestTimestamp) {
                    syncStatus = "Sync failed"
                }
            }
    }

    override fun onResume() {
        super.onResume()
        screenActive = true

        permissionGranted = ContextCompat.checkSelfPermission(
            this,
            heartRatePermission
        ) == PackageManager.PERMISSION_GRANTED

        if (permissionGranted) {
            startMeasurement()
        } else {
            status = "Permission needed"
        }
    }

    private fun startMeasurement() {
        if (!screenActive || registered || checkingSupport) return

        status = "Checking sensor..."
        checkingSupport = true

        val capabilities = measureClient.getCapabilitiesAsync()

        capabilities.addListener({
            checkingSupport = false

            if (screenActive && permissionGranted) {
                try {
                    val supported = capabilities.get()
                        .supportedDataTypesMeasure
                        .contains(DataType.HEART_RATE_BPM)

                    if (supported) {
                        heartRate = "--"
                        status = "Waiting for a reading..."
                        registered = true

                        measureClient.registerMeasureCallback(
                            DataType.HEART_RATE_BPM,
                            heartRateCallback
                        )
                    } else {
                        status = "Heart rate is not supported"
                    }
                } catch (exception: Exception) {
                    registered = false
                    status = "Sensor connection failed"
                }
            }
        }, ContextCompat.getMainExecutor(this))
    }

    override fun onPause() {
        screenActive = false

        if (registered) {
            measureClient.unregisterMeasureCallbackAsync(
                DataType.HEART_RATE_BPM,
                heartRateCallback
            )
            registered = false
        }

        heartRate = "--"
        syncStatus = ""
        super.onPause()
    }
}