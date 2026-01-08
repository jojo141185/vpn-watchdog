@echo off
:: =============================================================================
:: VPN WATCHDOG - WINDOWS INSTALLER
:: =============================================================================

SET APP_NAME=vpn-watchdog
SET BINARY_NAME=vpn-watchdog.exe
SET INSTALL_DIR=%LOCALAPPDATA%\VPNWatchdog
SET START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
SET STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
SET CONFIG_DIR=%USERPROFILE%\.config\vpn-watchdog
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

:: 2. DETECT EXISTING INSTALLATION
IF EXIST "%INSTALL_DIR%\%BINARY_NAME%" (
    echo.
    echo [INFO] Existing installation detected!
    echo.
    echo   Binary Location:    %INSTALL_DIR%
    echo   Config Location:    %CONFIG_DIR%
    echo   Startup Shortcut:   %STARTUP_FOLDER%
    echo.
    echo What do you want to do?
    echo   [1] Update / Re-Install (Default)
    echo   [2] Uninstall completely
    echo.
    set /p choice="Select option [1-2]: "
    if "%choice%"=="2" goto UNINSTALL
)

:INSTALL
:: 3. CREATE INSTALL DIRECTORY
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
echo.
echo [INFO] Stopping running processes...
taskkill /IM "%BINARY_NAME%" /F >nul 2>&1

echo [INFO] Installing to %INSTALL_DIR%...
copy /Y "%~dp0%BINARY_NAME%" "%INSTALL_DIR%\%BINARY_NAME%"

:: 4. CREATE SHORTCUTS (Using VBScript helper)
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
exit /b

:UNINSTALL
echo.
echo [INFO] Uninstalling...
taskkill /IM "%BINARY_NAME%" /F >nul 2>&1

echo   - Removing Binary...
del "%INSTALL_DIR%\%BINARY_NAME%"

echo   - Removing Start Menu Shortcut...
if exist "%START_MENU%\VPN Watchdog.lnk" del "%START_MENU%\VPN Watchdog.lnk"

echo   - Removing Autostart Shortcut...
if exist "%STARTUP_FOLDER%\vpn-watchdog.lnk" del "%STARTUP_FOLDER%\vpn-watchdog.lnk"

echo   - Cleaning Directory...
rmdir /S /Q "%INSTALL_DIR%"

echo.
echo [INFO] Configuration files were KEPT at:
echo   %CONFIG_DIR%
echo (You can delete this folder manually if you want a clean slate).
echo.
echo [SUCCESS] Uninstalled.
pause