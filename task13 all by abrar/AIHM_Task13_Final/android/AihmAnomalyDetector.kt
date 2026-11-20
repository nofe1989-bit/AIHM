package com.example.aihm.ml

import android.content.Context
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import org.json.JSONObject
import java.io.File

/** Receives one complete five-minute mean-HR window and optional step count. */
class AihmAnomalyDetector(context: Context) : AutoCloseable {
    data class Prediction(val score: Float, val flagged: Boolean)

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val threshold: Float

    init {
        val config = JSONObject(context.assets.open("scaler_and_inference.json").bufferedReader().use { it.readText() })
        require(config.getString("input_name") == "X")
        require(config.getString("output_name") == "score_samples")
        threshold = config.getDouble("threshold").toFloat()
        val model = File(context.filesDir, "selected_figshare_isolation_forest.onnx")
        if (!model.exists()) {
            context.assets.open("selected_figshare_isolation_forest.onnx").use { input ->
                model.outputStream().use { output -> input.copyTo(output) }
            }
        }
        OrtSession.SessionOptions().use { options ->
            session = env.createSession(model.absolutePath, options)
        }
    }

    fun scoreWindow(meanHrBpm: Float, stepsTotal: Float?): Prediction {
        require(meanHrBpm.isFinite() && meanHrBpm > 0f && meanHrBpm < 300f)
        require(stepsTotal == null || (stepsTotal.isFinite() && stepsTotal >= 0f))
        // Exact Python feature order: hr_bpm, steps_total, steps_missing.
        val input = arrayOf(floatArrayOf(meanHrBpm, stepsTotal ?: Float.NaN,
            if (stepsTotal == null) 1f else 0f))
        OnnxTensor.createTensor(env, input).use { tensor ->
            session.run(mapOf("X" to tensor)).use { result ->
                val output = result.get("score_samples").orElseThrow {
                    IllegalStateException("Missing score_samples output")
                } as OnnxTensor
                val score = (output.value as Array<FloatArray>)[0][0]
                return Prediction(score, score <= threshold)
            }
        }
    }

    override fun close() {
        session.close()
    }
}
