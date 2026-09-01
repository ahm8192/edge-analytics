package com.ahmet.edge.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [
        LeagueEntity::class, TeamEntity::class, MatchEntity::class,
        OddsEntity::class, ContextFactorEntity::class,
        BetEntity::class, BankrollEntity::class
    ],
    version = 1,
    exportSchema = true
)
abstract class EdgeDatabase : RoomDatabase() {
    abstract fun matchDao(): MatchDao
    abstract fun oddsDao(): OddsDao
    abstract fun contextDao(): ContextDao
    abstract fun betDao(): BetDao
    abstract fun bankrollDao(): BankrollDao
}
