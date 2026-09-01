package com.ahmet.edge.work

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import com.ahmet.edge.data.repo.EntitlementRepository
import com.ahmet.edge.data.repo.MatchRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Arka plan tazeleme. İki iş yapar:
 *  1. Maç ve oran verisini günceller (uygulama açılınca hazır olsun)
 *  2. Yetkiyi tazeler — abonelik RTDN ile değişmiş olabilir
 */
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val matches: MatchRepository,
    private val entitlements: EntitlementRepository
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val err = matches.refreshWindow(Instant.now(), Instant.now().plusSeconds(7 * 86400))
        entitlements.refresh()
        matches.prune()
        return if (err == null) Result.success() else Result.retry()
    }

    companion object {
        private const val NAME = "edge_sync"

        fun schedule(context: Context) {
            val req = PeriodicWorkRequestBuilder<SyncWorker>(6, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .setRequiresBatteryNotLow(true)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                NAME, ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}
