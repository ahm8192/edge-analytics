package com.ahmet.edge.data.local

import androidx.room.*

@Entity(tableName = "leagues")
data class LeagueEntity(
    @PrimaryKey val id: Long,
    val name: String, val country: String, val tier: Int,
    val dataQuality: Double, val strengthCoef: Double
)

@Entity(tableName = "teams")
data class TeamEntity(
    @PrimaryKey val id: Long,
    val name: String, val shortName: String, val crestUrl: String?
)

@Entity(
    tableName = "matches",
    indices = [Index("kickoffEpoch"), Index("leagueId"), Index("hasValue")]
)
data class MatchEntity(
    @PrimaryKey val id: Long,
    val leagueId: Long,
    val homeTeamId: Long,
    val awayTeamId: Long,
    val kickoffEpoch: Long,
    val status: String,
    val homeGoals: Int?,
    val awayGoals: Int?,
    val lambdaHome: Double?,
    val lambdaAway: Double?,
    val rho: Double,
    val modelConfidence: Double,
    val bestEdgePct: Double?,
    val hasValue: Boolean,
    val pHome: Double? = null,
    val pDraw: Double? = null,
    val pAway: Double? = null,
    val pOver25: Double? = null,
    val pBtts: Double? = null,
    val minute: Int? = null,
    /** Önbellek tazeliği — çevrimdışıyken kullanıcıya "eski veri" uyarısı için. */
    val fetchedAtEpoch: Long
)

/** Oran anlık görüntüleri. Hareket grafiği bunlardan çizilir (madde 7, 83). */
@Entity(tableName = "odds", primaryKeys = ["matchId", "bookmaker", "market", "selection", "capturedEpoch"])
data class OddsEntity(
    val matchId: Long,
    val bookmaker: String,
    val market: String,
    val line: Double?,
    val selection: String,
    val price: Double,
    val capturedEpoch: Long,
    val isClosing: Boolean,
    val isSharp: Boolean
)

@Entity(tableName = "context_factors", primaryKeys = ["matchId", "label"])
data class ContextFactorEntity(
    val matchId: Long, val label: String, val value: String,
    val impact: Double, val note: String?
)

@Entity(tableName = "bets", indices = [Index("matchId"), Index("placedAtEpoch")])
data class BetEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val matchId: Long,
    val matchLabel: String,
    val market: String,
    val selection: String,
    val modelProb: Double,
    val takenPrice: Double,
    val stake: Double,
    val placedAtEpoch: Long,
    val closingPrice: Double?,
    val outcome: String,
    val pnl: Double?,
    val wasPlaced: Boolean,
    val bankrollBefore: Double
)

@Entity(tableName = "bankroll_state")
data class BankrollEntity(
    @PrimaryKey val id: Int = 1,
    val starting: Double,
    val current: Double,
    val peak: Double,
    val updatedAtEpoch: Long
)

data class MatchWithTeams(
    @Embedded val match: MatchEntity,
    // Nullable: ilişkili satır henüz yazılmamışsa Room sorgusu NPE atmasin.
    @Relation(parentColumn = "homeTeamId", entityColumn = "id") val home: TeamEntity?,
    @Relation(parentColumn = "awayTeamId", entityColumn = "id") val away: TeamEntity?,
    @Relation(parentColumn = "leagueId", entityColumn = "id") val league: LeagueEntity?
)
