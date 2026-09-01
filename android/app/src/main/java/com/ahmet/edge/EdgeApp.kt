package com.ahmet.edge

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.SvgDecoder
import coil.util.DebugLogger
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class EdgeApp : Application(), ImageLoaderFactory {
    override fun onCreate() {
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            android.util.Log.e("EDGE", "UNCAUGHT [${t.name}]: ${e.javaClass.name}: ${e.message}", e)
            prev?.uncaughtException(t, e)
        }
        super.onCreate()
        android.util.Log.i("EDGE", "EdgeApp onCreate, API_BASE=${BuildConfig.API_BASE}")
    }

    // Takım armaları .png ve .svg gelebiliyor — ikisini de çöz.
    override fun newImageLoader(): ImageLoader =
        ImageLoader.Builder(this)
            .components { add(SvgDecoder.Factory()) }
            .crossfade(true)
            .apply { if (BuildConfig.DEBUG) logger(DebugLogger()) }
            .build()
}
