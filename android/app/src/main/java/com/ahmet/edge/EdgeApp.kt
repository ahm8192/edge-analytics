package com.ahmet.edge

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class EdgeApp : Application() {
    override fun onCreate() {
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            android.util.Log.e("EDGE", "UNCAUGHT [${t.name}]: ${e.javaClass.name}: ${e.message}", e)
            prev?.uncaughtException(t, e)
        }
        super.onCreate()
        android.util.Log.i("EDGE", "EdgeApp onCreate, API_BASE=${BuildConfig.API_BASE}")
    }
}
