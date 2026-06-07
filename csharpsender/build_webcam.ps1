# Build CSharpSender with Webcam Support (Single File)
Write-Host "Building CSharpSender with webcam support (Single File)..." -ForegroundColor Green
Write-Host ""

Set-Location $PSScriptRoot

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "bin\Release\SingleFile") {
    Remove-Item -Recurse -Force "bin\Release\SingleFile"
}

# Restore NuGet packages
Write-Host "Restoring NuGet packages (including AForge.NET)..." -ForegroundColor Yellow
dotnet restore --verbosity normal

# Build Release version
Write-Host "Building Release version with webcam support..." -ForegroundColor Yellow
dotnet build -c Release --verbosity normal

# Publish Single File
Write-Host "Publishing Single File executable with all dependencies..." -ForegroundColor Yellow
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true --verbosity normal

Write-Host ""
Write-Host "Build complete!" -ForegroundColor Green
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "OUTPUT LOCATION:" -ForegroundColor White
Write-Host "bin\Release\net8.0-windows\win-x64\publish\CSharpSender.exe" -ForegroundColor Yellow
Write-Host ""

# Show file size
$outputPath = "bin\Release\net8.0-windows\win-x64\publish\CSharpSender.exe"
if (Test-Path $outputPath) {
    $size = (Get-Item $outputPath).Length
    $sizeMB = [math]::Round($size / 1MB, 2)
    Write-Host "SIZE: $sizeMB MB" -ForegroundColor White
}
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "FEATURES INCLUDED:" -ForegroundColor White
Write-Host "- Real webcam capture via AForge.NET" -ForegroundColor Gray
Write-Host "- Desktop streaming" -ForegroundColor Gray
Write-Host "- Remote control" -ForegroundColor Gray
Write-Host "- File management" -ForegroundColor Gray
Write-Host "- System telemetry" -ForegroundColor Gray
Write-Host "- Recovery tools" -ForegroundColor Gray
Write-Host "- All dependencies bundled" -ForegroundColor Gray
Write-Host ""
Write-Host "TO TEST WEBCAM:" -ForegroundColor White
Write-Host "1. Run CSharpSender.exe" -ForegroundColor Gray
Write-Host "2. Connect with Qt viewer" -ForegroundColor Gray
Write-Host "3. Click '📷 Webcam' button" -ForegroundColor Gray
Write-Host "4. Real webcam feed should appear!" -ForegroundColor Gray
Write-Host ""
Write-Host "The executable is completely self-contained - no installation required." -ForegroundColor Green
Write-Host ""

# Ask if user wants to run it
$run = Read-Host "Do you want to run the sender now? (y/n)"
if ($run -eq 'y' -or $run -eq 'Y') {
    if (Test-Path $outputPath) {
        Write-Host "Starting CSharpSender..." -ForegroundColor Green
        Start-Process -FilePath $outputPath
    } else {
        Write-Host "Executable not found at $outputPath" -ForegroundColor Red
    }
}

Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
