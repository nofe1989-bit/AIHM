package com.example.aihm.data

import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import java.util.Date

class ReadingRepository {

    private val db = FirebaseFirestore.getInstance()
    private val auth = FirebaseAuth.getInstance()

    private var lastSavedTime = 0L

    // Saves one reading under users/{uid}/readings.
    // The watch sends a reading every 5 seconds, so we keep at most one
    // per minute to stay inside Firestore's free daily limit.
    fun saveReading(
        bpm: Double,
        timestamp: Long,
        activity: String,
        deviceId: String?
    ) {
        val user = auth.currentUser ?: return
        if (timestamp - lastSavedTime < 60_000L) return
        lastSavedTime = timestamp

        val data = mapOf(
            "bpm" to bpm,
            "timestamp" to Timestamp(Date(timestamp)),
            "activity" to activity,
            "deviceId" to deviceId
        )

        // The timestamp is the document ID, so the same reading is never saved twice
        db.collection("users").document(user.uid)
            .collection("readings").document(timestamp.toString())
            .set(data)
    }
}