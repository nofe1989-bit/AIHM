package com.example.aihm.auth

import androidx.compose.runtime.*

@Composable
fun RegisterScreen(
    authRepository: AuthRepository,
    onRegisterSuccess: () -> Unit,
    onGoToLogin: () -> Unit
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }

    AuthPage(
        title = "Create account",
        subtitle = "Register to start monitoring your heart rate."
    ) {
        AuthField(email, { email = it }, "Email")
        AuthField(password, { password = it }, "Password (min 6 characters)", password = true)
        AuthField(confirm, { confirm = it }, "Confirm password", password = true)

        AuthButton(
            text = if (loading) "Please wait..." else "Register",
            enabled = !loading
        ) {
            when {
                email.isBlank() || password.isBlank() ->
                    message = "Please fill in all fields"
                password.length < 6 ->
                    message = "Password must be at least 6 characters"
                password != confirm ->
                    message = "Passwords do not match"
                else -> {
                    loading = true
                    authRepository.register(email.trim(), password) { ok, error ->
                        loading = false
                        if (ok) onRegisterSuccess() else message = error ?: "Registration failed"
                    }
                }
            }
        }

        AuthLink("I already have an account", onGoToLogin)

        AuthMessage(message)
    }
}
