package com.example.aihm.auth

import androidx.compose.runtime.*

@Composable
fun LoginScreen(
    authRepository: AuthRepository,
    onLoginSuccess: () -> Unit,
    onGoToRegister: () -> Unit
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }

    AuthPage(
        title = "Welcome back",
        subtitle = "Log in to see your heart rate and health profile."
    ) {
        AuthField(email, { email = it }, "Email")
        AuthField(password, { password = it }, "Password", password = true)

        AuthButton(
            text = if (loading) "Please wait..." else "Log in",
            enabled = !loading
        ) {
            if (email.isBlank() || password.isBlank()) {
                message = "Please enter email and password"
            } else {
                loading = true
                authRepository.login(email.trim(), password) { ok, error ->
                    loading = false
                    if (ok) onLoginSuccess() else message = error ?: "Login failed"
                }
            }
        }

        AuthLink("Forgot password?") {
            if (email.isBlank()) {
                message = "Enter your email first, then tap Forgot password"
            } else {
                authRepository.resetPassword(email.trim()) { ok, error ->
                    message = if (ok) "Reset email sent" else error ?: "Failed"
                }
            }
        }

        AuthLink("Create an account", onGoToRegister)

        AuthMessage(message)
    }
}