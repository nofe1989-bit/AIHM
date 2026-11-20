package com.example.aihm.profile

import java.time.LocalDate
import java.time.Period

fun calculateAge(dateOfBirth: String): Int {
    return try {
        Period.between(LocalDate.parse(dateOfBirth), LocalDate.now()).years
    } catch (e: Exception) {
        0   // empty or invalid date
    }
}

fun isValidBirthDate(dateOfBirth: String): Boolean {
    return try {
        val dob = LocalDate.parse(dateOfBirth)
        !dob.isAfter(LocalDate.now()) && calculateAge(dateOfBirth) >= 18
    } catch (e: Exception) {
        false
    }
}