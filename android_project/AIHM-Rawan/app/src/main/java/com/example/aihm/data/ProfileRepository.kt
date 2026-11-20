package com.example.aihm.data

import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions

data class HealthProfile(
    val name: String = "",
    val dateOfBirth: String = "",
    val gender: String = "",
    val conditions: String = "",
    val medications: String = "",
    val emergencyContact: String = ""
)

class ProfileRepository {

    private val db = FirebaseFirestore.getInstance()
    private val auth = FirebaseAuth.getInstance()

    fun saveProfile(profile: HealthProfile, onResult: (Boolean, String?) -> Unit) {
        val user = auth.currentUser
        if (user == null) {
            onResult(false, "Not logged in")
            return
        }

        val data = mapOf(
            "email" to user.email,
            "updatedAt" to Timestamp.now(),
            "profile" to mapOf(
                "name" to profile.name,
                "dateOfBirth" to profile.dateOfBirth,
                "gender" to profile.gender,
                "conditions" to profile.conditions,
                "medications" to profile.medications,
                "emergencyContact" to profile.emergencyContact
            )
        )

        db.collection("users").document(user.uid)
            .set(data, SetOptions.merge())
            .addOnSuccessListener { onResult(true, null) }
            .addOnFailureListener { onResult(false, it.message) }
    }

    fun loadProfile(onResult: (HealthProfile?, String?) -> Unit) {
        val user = auth.currentUser
        if (user == null) {
            onResult(null, "Not logged in")
            return
        }

        db.collection("users").document(user.uid).get()
            .addOnSuccessListener { doc ->
                val m = doc.get("profile") as? Map<*, *>
                val profile = if (m == null) {
                    HealthProfile()
                } else {
                    HealthProfile(
                        name = m["name"] as? String ?: "",
                        dateOfBirth = m["dateOfBirth"] as? String ?: "",
                        gender = m["gender"] as? String ?: "",
                        conditions = m["conditions"] as? String ?: "",
                        medications = m["medications"] as? String ?: "",
                        emergencyContact = m["emergencyContact"] as? String ?: ""
                    )
                }
                onResult(profile, null)
            }
            .addOnFailureListener { onResult(null, it.message) }
    }
}