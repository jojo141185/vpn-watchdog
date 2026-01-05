@echo off
:: =============================================================================
:: VPN WATCHDOG - WINDOWS INSTALLER
:: =============================================================================

SET APP_NAME=vpn-watchdog
SET BINARY_NAME=vpn-watchdog.exe
SET INSTALL_DIR=%LOCALAPPDATA%\VPNWatchdog
SET START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
SET SHORTCUT_SCRIPT=%TEMP%\CreateShortcut.vbs

echo ======================================================
echo    VPN WATCHDOG - SETUP MANAGER (WINDOWS)
echo ======================================================

:: 1. CHECK IF BINARY EXISTS
IF NOT EXIST "%~dp0%BINARY_NAME%" (
    echo [ERROR] %BINARY_NAME% not found in current folder!
    echo Please make sure you extracted the zip file correctly.
    pause
    exit /b
)

:: 2. CREATE INSTALL DIRECTORY
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
echo [INFO] Installing to %INSTALL_DIR%...
copy /Y "%~dp0%BINARY_NAME%" "%INSTALL_DIR%\%BINARY_NAME%"

:: 3. CREATE SHORTCUTS (Using VBScript helper)
echo [INFO] Creating Shortcuts...

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%SHORTCUT_SCRIPT%"
echo sLinkFile = "%START_MENU%\VPN Watchdog.lnk" >> "%SHORTCUT_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%SHORTCUT_SCRIPT%"
echo oLink.TargetPath = "%INSTALL_DIR%\%BINARY_NAME%" >> "%SHORTCUT_SCRIPT%"
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%SHORTCUT_SCRIPT%"
echo oLink.Description = "VPN Connection Monitor" >> "%SHORTCUT_SCRIPT%"
echo oLink.Save >> "%SHORTCUT_SCRIPT%"

cscript /nologo "%SHORTCUT_SCRIPT%"
del "%SHORTCUT_SCRIPT%"

echo.
echo [SUCCESS] Installation complete!
echo You can now find 'VPN Watchdog' in your Start Menu.
echo.
pause