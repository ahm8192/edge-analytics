"""Uygulamanın kendi kendini güncellemesi (Play Store yok).

`app_dist/version.json` ve `app_dist/edge-latest.apk` Docker imajına gömülür.
Yeni sürüm yayınlamak: yeni APK'yı app_dist/'e koy, version.json'u güncelle, deploy et.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["updates"])


def _dist_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(os.path.dirname(here), "app_dist"),  # backend/app_dist
        os.path.join(os.getcwd(), "app_dist"),            # /app/app_dist (Docker)
        "/app/app_dist",
    ):
        if os.path.isdir(cand):
            return cand
    return os.path.join(os.path.dirname(here), "app_dist")


_DIST = _dist_dir()


@router.get("/app/version")
def app_version():
    path = os.path.join(_DIST, "version.json")
    if not os.path.exists(path):
        return JSONResponse({"versionCode": 0, "versionName": "0", "notes": ""})
    try:
        # utf-8-sig: PowerShell'in eklediği BOM'u da tolere eder
        with open(path, encoding="utf-8-sig") as f:
            return JSONResponse(json.load(f))
    except (OSError, ValueError):
        return JSONResponse({"versionCode": 0, "versionName": "0", "notes": ""})


@router.get("/app/download")
def app_download():
    path = os.path.join(_DIST, "edge-latest.apk")
    if not os.path.exists(path):
        return JSONResponse({"error": "no_apk"}, status_code=404)
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename="edge-latest.apk",
    )
