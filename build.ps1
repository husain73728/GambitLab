# Build the C++ engine with the MSYS2 UCRT64 g++ toolchain.
#   ./build.ps1            # release build -> engine/build/engine.exe
#   ./build.ps1 -Debug     # debug build  -> engine/build/engine-debug.exe
param(
    [switch]$Debug
)

$ErrorActionPreference = 'Stop'

$gxx = 'C:\msys64\ucrt64\bin\g++.exe'
if (-not (Test-Path $gxx)) {
    throw "g++ not found at $gxx. Install MSYS2 UCRT64 or edit build.ps1."
}

$root = $PSScriptRoot
$srcDir = Join-Path $root 'engine\src'
$outDir = Join-Path $root 'engine\build'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$sources = Get-ChildItem -Path $srcDir -Filter *.cpp -Recurse | ForEach-Object { $_.FullName }
if ($sources.Count -eq 0) { throw "No .cpp sources found in $srcDir" }

if ($Debug) {
    $flags = @('-std=c++20', '-O0', '-g', '-Wall', '-Wextra', '-static-libgcc', '-static-libstdc++')
    $exe = Join-Path $outDir 'engine-debug.exe'
} else {
    $flags = @('-std=c++20', '-O3', '-march=native', '-Wall', '-Wextra', '-static-libgcc', '-static-libstdc++')
    $exe = Join-Path $outDir 'engine.exe'
}

Write-Host "Compiling $($sources.Count) source(s) -> $exe"
& $gxx @flags @sources '-o' $exe
if ($LASTEXITCODE -ne 0) {
    throw "Build failed (g++ exit $LASTEXITCODE)"
}
Write-Host "Built $exe"
