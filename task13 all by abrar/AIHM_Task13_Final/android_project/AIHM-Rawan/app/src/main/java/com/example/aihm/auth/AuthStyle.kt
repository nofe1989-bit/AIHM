package com.example.aihm.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

object AIHMColors {
    val Background = Color(0xFF0D1D2D)
    val Card = Color(0xFF0F2439)
    val Field = Color(0xFF0D2A3C)
    val Accent = Color(0xFF24C6E2)
    val Text = Color(0xFFFFFFFF)
    val Secondary = Color(0xFF9AA9B8)
    val Border = Color(0xFF2A4A63)
    val Error = Color(0xFFFF6B6B)
}

// Pink page with the AIHM name on top and a white rounded card for the content
@Composable
fun AuthPage(
    title: String,
    subtitle: String,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(AIHMColors.Background)
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "AIHM",
            color = AIHMColors.Accent,
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold
        )
        Text("\u2665\uFE0F", fontSize = 40.sp)
        Spacer(Modifier.height(12.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = AIHMColors.Card)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    title,
                    color = AIHMColors.Text,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(subtitle, color = AIHMColors.Secondary, fontSize = 14.sp)
                content()
            }
        }
    }
}

@Composable
fun AuthField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    password: Boolean = false,
    singleLine: Boolean = true
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = singleLine,
        visualTransformation =
            if (password) PasswordVisualTransformation() else VisualTransformation.None,
        shape = RoundedCornerShape(16.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = AIHMColors.Accent,
            unfocusedBorderColor = AIHMColors.Border,
            focusedLabelColor = AIHMColors.Accent,
            unfocusedLabelColor = AIHMColors.Secondary,
            cursorColor = AIHMColors.Accent,
            focusedTextColor = AIHMColors.Text,
            unfocusedTextColor = AIHMColors.Text,
            focusedContainerColor = AIHMColors.Field,
            unfocusedContainerColor = AIHMColors.Field
        ),
        modifier = Modifier.fillMaxWidth()
    )
}

@Composable
fun AuthButton(text: String, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = AIHMColors.Accent,
            contentColor = AIHMColors.Background,
            disabledContainerColor = AIHMColors.Border,
            disabledContentColor = Color.White
        ),
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
    ) {
        Text(text, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun AuthLink(text: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Text(text, color = AIHMColors.Accent, textAlign = TextAlign.Center)
    }
}

@Composable
fun AuthMessage(text: String?) {
    if (text != null) {
        Text(text, color = AIHMColors.Error, fontSize = 13.sp)
    }
}