@echo off
echo Building CSharpSender locally...
echo.

cd /d "%~dp0csharpsender"

echo Restoring NuGet packages...
dotnet restore

echo Building Release version...
dotnet build -c Release -o ./bin/Release

echo.
echo Build complete!
echo Executable location: csharpsender\bin\Release\CSharpSender.exe
echo.
pause
