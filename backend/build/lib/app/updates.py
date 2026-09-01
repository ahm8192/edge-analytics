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

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_dist")


@router.get("/app/version")
def app_version():
    path = os.path.join(_DIST, "version.json")
    if not os.path.exists(path):
        return JSONResponse({"versionCode": 0, "versionName": "0", "notes": ""})
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


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
