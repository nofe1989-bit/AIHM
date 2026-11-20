package com.example.aihm.ml

/** Builds a five-minute mean from received watch readings; never treats one sample as a window. */
class FiveMinuteHrAggregator {
    data class CompletedWindow(val startMillis: Long, val meanHrBpm: Double, val samples: Int)

    private var sourceId: String? = null
    private var bucketStart: Long? = null
    private var firstTime = 0L
    private var lastTime = 0L
    private var count = 0
    private var sum = 0.0

    fun reset() {
        sourceId = null
        bucketStart = null
        firstTime = 0L
        lastTime = 0L
        count = 0
        sum = 0.0
    }

    fun add(timestamp: Long, bpm: Double, watchNodeId: String?): CompletedWindow? {
        if (timestamp <= 0L || !bpm.isFinite() || bpm <= 0.0 || bpm >= 300.0) return null
        if (sourceId != watchNodeId) {
            reset()
            sourceId = watchNodeId
        }
        val window = timestamp - timestamp % 300_000L
        val previous = bucketStart
        if (previous != null && (window < previous || timestamp <= lastTime)) return null
        val completed = if (previous != null && window > previous && count >= 12 &&
            lastTime - firstTime >= 240_000L) {
            CompletedWindow(previous, sum / count, count)
        } else null
        if (previous != window) {
            bucketStart = window
            firstTime = timestamp
            count = 0
            sum = 0.0
        }
        lastTime = timestamp
        count++
        sum += bpm
        return completed
    }
}
