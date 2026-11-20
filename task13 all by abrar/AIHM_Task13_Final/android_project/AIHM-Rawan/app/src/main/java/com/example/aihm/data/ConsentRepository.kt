package com.example.aihm.data

import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class ConsentRepository {

    private val db = FirebaseFirestore.getInstance()
    private val auth = FirebaseAuth.getInstance()

    fun saveConsents(types: List<String>, onResult: (Boolean, String?) -> Unit) {
        val user = auth.currentUser
        if (user == null) {
            onResult(false, "Not logged in")
            return
        }

        val consents = db.collection("users").document(user.uid).collection("consents")
        val batch = db.batch()

        types.forEach { type ->
            batch.set(
                consents.document(),
                mapOf(
                    "type" to type,
                    "granted" to true,
                    "timestamp" to Timestamp.now()
                )
            )
        }

        batch.commit()
            .addOnSuccessListener { onResult(true, null) }
            .addOnFailureListener { onResult(false, it.message) }
    }
}