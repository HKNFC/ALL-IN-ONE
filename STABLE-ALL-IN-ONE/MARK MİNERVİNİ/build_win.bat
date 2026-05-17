@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM build_win.bat  —  Windows .exe üretir
REM Kullanım: build_win.bat
REM ─────────────────────────────────────────────────────────────────────────────

SET APP_NAME=SEPA Stock Scanner

echo ============================================
echo  SEPA Stock Scanner -- Windows Build
echo ============================================

REM Bağımlılıkları kur
echo [1/3] Bagimliliklar kuruluyor...
pip install pywebview pyinstaller --quiet

REM Eski build temizle
rmdir /s /q build 2>nul
rmdir /s /q "dist\%APP_NAME%" 2>nul

REM Build
echo [2/3] Build baslatiliyor...
pyinstaller sepa_scanner.spec --noconfirm

echo [3/3] Tamamlandi!
echo.
echo Cikti: dist\%APP_NAME%\%APP_NAME%.exe
pause
