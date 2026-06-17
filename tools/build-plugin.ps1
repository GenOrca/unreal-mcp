<#
.SYNOPSIS
  Package UnrealMCPython as a precompiled binary plugin for one UE version, via RunUAT BuildPlugin.

.DESCRIPTION
  Produces a distributable zip (UnrealMCPython/ with Binaries + Source + Content + .uplugin)
  named UnrealMCPython_<engineLabel>_<pluginVersion>.zip. Run once per UE version on a machine
  that has that engine installed — the same model KawaiiPhysics uses for its per-version releases.
  GitHub-hosted CI cannot do this (no Unreal Engine on the runner), so this is a local build step.

.EXAMPLE
  ./tools/build-plugin.ps1 -UeRoot "C:\Program Files\Epic Games\UE_5.7"
  ./tools/build-plugin.ps1 -UeRoot "C:\Program Files\Epic Games\UE_5.8" -EngineLabel 5.8

  Then attach the zip to a release:
  gh release upload v2.2.0 .\Saved\PluginBuild\UnrealMCPython_5.7_2.2.0.zip
#>
param(
    [Parameter(Mandatory = $true)][string]$UeRoot,
    [string]$EngineLabel = "",
    [string]$OutDir = ""
)
$ErrorActionPreference = "Stop"

$repo    = (Resolve-Path "$PSScriptRoot\..").Path
$uplugin = Join-Path $repo "Plugins\UnrealMCPython\UnrealMCPython.uplugin"
$runuat  = Join-Path $UeRoot "Engine\Build\BatchFiles\RunUAT.bat"
if (-not (Test-Path $runuat))  { throw "RunUAT.bat not found at $runuat" }
if (-not (Test-Path $uplugin)) { throw ".uplugin not found at $uplugin" }
if (-not $OutDir) { $OutDir = Join-Path $repo "Saved\PluginBuild" }

# plugin version from the .uplugin
$ver = ([regex]'"VersionName"\s*:\s*"([^"]+)"').Match((Get-Content $uplugin -Raw)).Groups[1].Value
if (-not $ver) { throw "Could not read VersionName from $uplugin" }
# engine label: explicit, else derived from the UE_x.y folder name
if (-not $EngineLabel) { $EngineLabel = (Split-Path $UeRoot -Leaf) -replace '^UE_', '' }

$pkg = Join-Path $OutDir "UnrealMCPython"
if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "Building UnrealMCPython $ver for UE $EngineLabel ..." -ForegroundColor Cyan
& $runuat BuildPlugin -Plugin="$uplugin" -Package="$pkg" -TargetPlatforms=Win64 -Rocket
if ($LASTEXITCODE -ne 0) { throw "RunUAT BuildPlugin failed (exit $LASTEXITCODE)" }

# Intermediate is build scratch — not needed in the distributed plugin.
Remove-Item -Recurse -Force (Join-Path $pkg "Intermediate") -ErrorAction SilentlyContinue

$zip = Join-Path $OutDir "UnrealMCPython_${EngineLabel}_${ver}.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $pkg -DestinationPath $zip
Write-Host "BUILT: $zip" -ForegroundColor Green
