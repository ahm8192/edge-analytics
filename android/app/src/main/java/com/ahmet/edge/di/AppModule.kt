package com.ahmet.edge.di

import android.content.Context
import androidx.room.Room
import com.ahmet.edge.BuildConfig
import com.ahmet.edge.core.AnonId
import com.ahmet.edge.data.local.*
import com.ahmet.edge.data.remote.AuthInterceptor
import com.ahmet.edge.data.remote.EdgeApi
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides @Singleton
    fun json() = Json { ignoreUnknownKeys = true; explicitNulls = false }

    @Provides @Singleton
    fun okHttp(anonId: AnonId): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor(anonId) { null })
        .apply {
            if (BuildConfig.DEBUG) addInterceptor(
                HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BASIC))
        }
        // Render ucretsiz plan 15 dk sonra uykuya dalar; ilk istek 30-60 sn surebilir.
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(90, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    @Provides @Singleton
    fun retrofit(client: OkHttpClient, json: Json): EdgeApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(EdgeApi::class.java)

    @Provides @Singleton
    fun database(@ApplicationContext ctx: Context): EdgeDatabase =
        Room.databaseBuilder(ctx, EdgeDatabase::class.java, "edge.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides fun matchDao(db: EdgeDatabase) = db.matchDao()
    @Provides fun oddsDao(db: EdgeDatabase) = db.oddsDao()
    @Provides fun contextDao(db: EdgeDatabase) = db.contextDao()
    @Provides fun betDao(db: EdgeDatabase) = db.betDao()
    @Provides fun bankrollDao(db: EdgeDatabase) = db.bankrollDao()

    @Provides @Singleton
    fun appScope(): CoroutineScope = CoroutineScope(SupervisorJob())

    @Provides @Singleton
    fun anonId(@ApplicationContext ctx: Context) = AnonId(ctx)
}
