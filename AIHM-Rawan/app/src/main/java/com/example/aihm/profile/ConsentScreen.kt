package com.example.aihm.profile

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.aihm.auth.AIHMColors
import com.example.aihm.auth.AuthButton
import com.example.aihm.auth.AuthMessage
import com.example.aihm.auth.AuthPage
import com.example.aihm.data.ConsentRepository

@Composable
fun ConsentScreen(onDone: () -> Unit) {
    val repo = remember { ConsentRepository() }

    var dataConsent by remember { mutableStateOf(false) }
    var monitoringConsent by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    val checkColors = CheckboxDefaults.colors(
        checkedColor = AIHMColors.Accent,
        uncheckedColor = AIHMColors.Border
    )

    AuthPage(
        title = "Your consent",
        subtitle = "Please read and agree before we collect any health data."
    ) {
        Text(
            "AIHM reads your heart rate from your smartwatch and stores it, " +
                    "together with your health profile, to help detect unusual " +
                    "patterns. This app is a prototype. It does not give medical " +
                    "advice or a diagnosis. You can delete your account and all " +
                    "your data at any time.",
            color = AIHMColors.Text
        )

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = dataConsent,
                onCheckedChange = { dataConsent = it },
                colors = checkColors
            )
            Text(
                "I agree to the storage of my health profile and heart rate data.",
                color = AIHMColors.Text
            )
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = monitoringConsent,
                onCheckedChange = { monitoringConsent = it },
                colors = checkColors
            )
            Text(
                "I agree to heart rate monitoring from my smartwatch.",
                color = AIHMColors.Text
            )
        }

        Spacer(Modifier.height(4.dp))

        AuthButton(
            text = if (loading) "Please wait..." else "Agree and continue",
            enabled = dataConsent && monitoringConsent && !loading
        ) {
            loading = true
            repo.saveConsents(
                listOf("data_storage", "heart_rate_monitoring")
            ) { ok, error ->
                loading = false
                if (ok) onDone() else message = error ?: "Could not save consent"
            }
        }

        AuthMessage(message)
    }
}