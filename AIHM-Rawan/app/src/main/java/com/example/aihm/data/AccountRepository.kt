package com.example.aihm.data

import com.google.firebase.auth.EmailAuthProvider
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.CollectionReference
import com.google.firebase.firestore.FirebaseFirestore

class AccountRepository {

    private val db = FirebaseFirestore.getInstance()
    private val auth = FirebaseAuth.getInstance()

    private val subcollections =
        listOf("consents", "readings", "classifications", "alerts")

    fun deleteAccount(password: String, onResult: (Boolean, String?) -> Unit) {
        val user = auth.currentUser
        val email = user?.email
        if (user == null || email == null) {
            onResult(false, "Not logged in")
            return
        }

        val credential = EmailAuthProvider.getCredential(email, password)

        user.reauthenticate(credential)
            .addOnSuccessListener {
                deleteUserData(user.uid) { error ->
                    if (error != null) {
                        onResult(false, error)
                    } else {
                        user.delete()
                            .addOnSuccessListener { onResult(true, null) }
                            .addOnFailureListener { onResult(false, it.message) }
                    }
                }
            }
            .addOnFailureListener { onResult(false, "Wrong password") }
    }

    // Deletes every subcollection, then the user document itself
    private fun deleteUserData(uid: String, onDone: (String?) -> Unit) {
        val userDoc = db.collection("users").document(uid)

        fun next(index: Int) {
            if (index >= subcollections.size) {
                userDoc.delete()
                    .addOnSuccessListener { onDone(null) }
                    .addOnFailureListener { onDone(it.message) }
            } else {
                deleteCollection(userDoc.collection(subcollections[index])) { error ->
                    if (error != null) onDone(error) else next(index + 1)
                }
            }
        }
        next(0)
    }

    // Deletes up to 400 documents at a time until the collection is empty
    private fun deleteCollection(ref: CollectionReference, onDone: (String?) -> Unit) {
        ref.limit(400).get()
            .addOnSuccessListener { snapshot ->
                if (snapshot.isEmpty) {
                    onDone(null)
                } else {
                    val batch = db.batch()
                    snapshot.documents.forEach { batch.delete(it.reference) }
                    batch.commit()
                        .addOnSuccessListener { deleteCollection(ref, onDone) }
                        .addOnFailureListener { onDone(it.message) }
                }
            }
            .addOnFailureListener { onDone(it.message) }
    }
}