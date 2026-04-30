@echo off
REM ============================================================
REM Borsa Portföy Seçici — Windows .exe Build Scripti
REM Windows'ta çalıştırma: build_windows.bat
REM ============================================================

echo ========================================
echo   Borsa Portföy Seçici — Windows Build
echo ========================================

REM Eski build klasörlerini temizle
echo [1/5] Temizleniyor...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM İkon
echo [2/5] İkon kontrol ediliyor...
if not exist icon.ico (
    python create_icon.py
)

REM Bağımlılık kontrolü
echo [3/5] Bağımlılıklar kontrol ediliyor...
python -c "import streamlit, yfinance, pandas, numpy, ta, plotly, sqlite3, openpyxl, requests" || (
    echo HATA: Eksik modül var!
    pause
    exit /b 1
)
echo    Tüm modüller mevcut.

REM Build
echo [4/5] Build yapılıyor...
python -m PyInstaller --clean --noconfirm BorsaPortfoySecici.spec

REM Sonuç
if exist dist\BorsaPortfoySecici\BorsaPortfoySecici.exe (
    echo [5/5] Build tamamlandi!
    echo.
    echo ========================================
    echo   EXE: dist\BorsaPortfoySecici\BorsaPortfoySecici.exe
    echo ========================================
    echo.
    echo Tum dist\BorsaPortfoySecici\ klasorunu
    echo baska bilgisayarlara kopyalayabilirsiniz.
) else (
    echo HATA: Build basarisiz.
)
pause
