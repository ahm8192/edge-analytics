package com.ahmet.edge.core

sealed interface UiState<out T> {
    data object Loading : UiState<Nothing>
    data class Success<T>(val data: T, val isStale: Boolean = false) : UiState<T>
    data class Empty(val message: String) : UiState<Nothing>
    data class Failure(val message: String, val canRetry: Boolean = true) : UiState<Nothing>
}

inline fun <T, R> UiState<T>.map(f: (T) -> R): UiState<R> = when (this) {
    is UiState.Success -> UiState.Success(f(data), isStale)
    is UiState.Loading -> UiState.Loading
    is UiState.Empty -> this
    is UiState.Failure -> this
}

sealed interface AppError {
    data object Offline : AppError
    data class QuotaExceeded(val quota: String, val limit: Int, val resetsAt: String) : AppError
    data class UpgradeRequired(val feature: String, val requiredTier: String) : AppError
    data class Server(val message: String) : AppError
}
