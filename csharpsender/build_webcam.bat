@echo off
echo Building CSharpSender with webcam support (Single File)...
echo.

cd /d "%~dp0"

echo Cleaning previous builds...
if exist "bin\Release\SingleFile" rmdir /s /q "bin\Release\SingleFile"

echo.
echo Restoring NuGet packages (including AForge.NET)...
dotnet restore --verbosity normal

echo.
echo Building Release version with webcam support...
dotnet build -c Release --verbosity normal

echo.
echo Publishing Single File executable with all dependencies...
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true --verbosity normal

echo.
echo Build complete!
echo.
echo ==================================================
echo OUTPUT LOCATION:
echo bin\Release\net8.0-windows\win-x64\publish\CSharpSender.exe
echo.
echo SIZE: (calculating...)
if exist "bin\Release\net8.0-windows\win-x64\publish\CSharpSender.exe" (
    for %%A in ("bin\Release\net8.0-windows\win-x64\publish\CSharpSender.exe") do echo %%~zA bytes
)
echo ==================================================
echo.
echo FEATURES INCLUDED:
echo - Real webcam capture via AForge.NET
echo - Desktop streaming
echo - Remote control
echo - File management
echo - System telemetry
echo - Recovery tools
echo - All dependencies bundled
echo.
echo TO TEST WEBCAM:
echo 1. Run CSharpSender.exe
echo 2. Connect with Qt viewer  
echo 3. Click "📷 Webcam" button
echo 4. Real webcam feed should appear!
echo.
echo The executable is completely self-contained - no installation required.
echo.

pause
