package com.example.aihm.profile

import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import com.example.aihm.auth.AuthButton
import com.example.aihm.auth.AuthField
import com.example.aihm.auth.AuthLink
import com.example.aihm.auth.AuthMessage
import com.example.aihm.auth.AuthPage
import com.example.aihm.data.HealthProfile
import com.example.aihm.data.ProfileRepository
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(onDone: () -> Unit) {
    val repo = remember { ProfileRepository() }

    var name by remember { mutableStateOf("") }
    var dateOfBirth by remember { mutableStateOf("") }
    var showPicker by remember { mutableStateOf(false) }
    val pickerState = rememberDatePickerState(yearRange = 1920..LocalDate.now().year)
    var gender by remember { mutableStateOf("") }
    var conditions by remember { mutableStateOf("") }
    var medications by remember { mutableStateOf("") }
    var emergency by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }

    // Load the saved profile once
    LaunchedEffect(Unit) {
        repo.loadProfile { profile, error ->
            loading = false
            if (profile != null) {
                name = profile.name
                dateOfBirth = profile.dateOfBirth
                gender = profile.gender
                conditions = profile.conditions
                medications = profile.medications
                emergency = profile.emergencyContact
            } else {
                message = error
            }
        }
    }

    AuthPage(
        title = "Health profile",
        subtitle = "This helps the app choose relevant general guidance."
    ) {
        AuthField(name, { name = it }, "Name")

        Text(
            if (dateOfBirth.isEmpty()) "Date of birth: not selected"
            else "Date of birth: $dateOfBirth   (Age: ${calculateAge(dateOfBirth)})",
            color = Color.White
        )
        AuthButton(text = "Choose date of birth", enabled = true) { showPicker = true }

        if (showPicker) {
            DatePickerDialog(
                onDismissRequest = { showPicker = false },
                confirmButton = {
                    TextButton(onClick = {
                        pickerState.selectedDateMillis?.let { millis ->
                            dateOfBirth = Instant.ofEpochMilli(millis)
                                .atZone(ZoneOffset.UTC).toLocalDate().toString()
                        }
                        showPicker = false
                    }) { Text("OK") }
                },
                dismissButton = {
                    TextButton(onClick = { showPicker = false }) { Text("Cancel") }
                }
            ) {
                DatePicker(state = pickerState)
            }
        }

        AuthField(gender, { gender = it }, "Gender")
        AuthField(conditions, { conditions = it }, "Medical conditions", singleLine = false)
        AuthField(medications, { medications = it }, "Medications", singleLine = false)
        AuthField(emergency, { emergency = it }, "Emergency contact")

        AuthButton(
            text = if (loading) "Please wait..." else "Save profile",
            enabled = !loading
        ) {
            if (!isValidBirthDate(dateOfBirth)) {
                message = "Choose a valid date of birth. You must be 18 or older."
            } else {
                loading = true
                repo.saveProfile(
                    HealthProfile(name, dateOfBirth, gender, conditions, medications, emergency)
                ) { ok, error ->
                    loading = false
                    if (ok) onDone() else message = error ?: "Could not save"
                }
            }
        }

        AuthLink("Skip for now", onDone)

        AuthMessage(message)
    }
}