package com.ahmet.edge.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface MatchDao {
    @Transaction
    @Query("""SELECT * FROM matches
              WHERE kickoffEpoch BETWEEN :from AND :to
              ORDER BY hasValue DESC, kickoffEpoch ASC""")
    fun observeWindow(from: Long, to: Long): Flow<List<MatchWithTeams>>

    @Transaction
    @Query("SELECT * FROM matches WHERE id = :id")
    fun observeOne(id: Long): Flow<MatchWithTeams?>

    @Transaction
    @Query("""SELECT * FROM matches
              WHERE hasValue = 1 AND kickoffEpoch > :now
              ORDER BY bestEdgePct DESC LIMIT :limit""")
    fun observeValueBoard(now: Long, limit: Int = 30): Flow<List<MatchWithTeams>>

    @Upsert suspend fun upsert(matches: List<MatchEntity>)
    @Upsert suspend fun upsertTeams(teams: List<TeamEntity>)
    @Upsert suspend fun upsertLeagues(leagues: List<LeagueEntity>)

    @Query("DELETE FROM matches WHERE kickoffEpoch < :before")
    suspend fun pruneOlderThan(before: Long)
}

@Dao
interface OddsDao {
    @Query("""SELECT * FROM odds WHERE matchId = :matchId AND market = :market
              AND capturedEpoch = (SELECT MAX(capturedEpoch) FROM odds
                                   WHERE matchId = :matchId AND market = :market)""")
    fun observeLatest(matchId: Long, market: String): Flow<List<OddsEntity>>

    /** Oran hareketi eğrisi — PRO özelliği. */
    @Query("""SELECT * FROM odds WHERE matchId = :matchId AND market = :market
              AND selection = :selection ORDER BY capturedEpoch ASC""")
    fun observeMovement(matchId: Long, market: String, selection: String): Flow<List<OddsEntity>>

    @Query("SELECT * FROM odds WHERE matchId = :matchId AND isClosing = 1")
    suspend fun closingLines(matchId: Long): List<OddsEntity>

    @Query("SELECT DISTINCT bookmaker FROM odds WHERE matchId = :matchId")
    fun observeBookmakers(matchId: Long): Flow<List<String>>

    @Upsert suspend fun upsert(rows: List<OddsEntity>)
}

@Dao
interface ContextDao {
    @Query("SELECT * FROM context_factors WHERE matchId = :matchId ORDER BY ABS(impact) DESC")
    fun observe(matchId: Long): Flow<List<ContextFactorEntity>>
    @Upsert suspend fun upsert(rows: List<ContextFactorEntity>)
}

@Dao
interface BetDao {
    @Query("SELECT * FROM bets ORDER BY placedAtEpoch DESC")
    fun observeAll(): Flow<List<BetEntity>>

    @Query("SELECT * FROM bets WHERE outcome = 'OPEN'")
    fun observeOpen(): Flow<List<BetEntity>>

    @Query("SELECT COALESCE(SUM(stake), 0) FROM bets WHERE outcome = 'OPEN' AND wasPlaced = 1")
    fun observeOpenExposure(): Flow<Double>

    /** madde 95: lig/market bazında ayrı ölçüm. */
    @Query("""SELECT market, COUNT(*) AS n, SUM(stake) AS staked,
                     SUM(COALESCE(pnl,0)) AS pnl,
                     AVG(CASE WHEN closingPrice IS NOT NULL
                              THEN takenPrice/closingPrice - 1 END) AS meanClv
              FROM bets WHERE outcome != 'OPEN' GROUP BY market""")
    fun observeByMarket(): Flow<List<MarketPerformance>>

    @Query("SELECT * FROM bets WHERE id = :id")
    suspend fun byId(id: Long): BetEntity?

    /** Martingale tespiti için son sonuçlar (madde 93). */
    @Query("""SELECT outcome FROM bets WHERE outcome != 'OPEN' AND wasPlaced = 1
              ORDER BY placedAtEpoch DESC LIMIT :limit""")
    fun observeRecentOutcomes(limit: Int = 10): Flow<List<String>>

    @Query("SELECT AVG(stake) FROM bets WHERE wasPlaced = 1")
    fun observeAverageStake(): Flow<Double?>

    @Insert suspend fun insert(bet: BetEntity): Long
    @Update suspend fun update(bet: BetEntity)

    @Query("""UPDATE bets SET outcome = :outcome, pnl = :pnl,
                              closingPrice = COALESCE(:closing, closingPrice)
              WHERE id = :id""")
    suspend fun settle(id: Long, outcome: String, pnl: Double, closing: Double?)

    @Query("UPDATE bets SET closingPrice = :price WHERE matchId = :matchId AND selection = :sel")
    suspend fun fillClosing(matchId: Long, sel: String, price: Double)
}

data class MarketPerformance(
    val market: String, val n: Int, val staked: Double,
    val pnl: Double, val meanClv: Double?
) {
    val roi get() = if (staked > 0) pnl / staked else 0.0
}

@Dao
interface BankrollDao {
    @Query("SELECT * FROM bankroll_state WHERE id = 1")
    fun observe(): Flow<BankrollEntity?>
    @Upsert suspend fun upsert(state: BankrollEntity)
}
