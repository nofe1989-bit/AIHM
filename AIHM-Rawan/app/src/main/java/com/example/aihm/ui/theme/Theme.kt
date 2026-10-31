package com.example.aihm.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val AIHMColorScheme = darkColorScheme(
    primary = Cyan,
    onPrimary = Navy,
    secondary = Muted,
    tertiary = Cyan,
    background = Navy,
    onBackground = Color.White,
    surface = NavyCard,
    onSurface = Color.White,
    surfaceVariant = NavyCard,
    onSurfaceVariant = Muted
)

@Composable
fun AIHMTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = AIHMColorScheme,
        typography = Typography,
        content = content
    )
}