# NexAgent derleme (Windows): .\build.ps1 [-Rid win-x64]
param([string]$Rid = 'win-x64')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
dotnet publish -c Release -r $Rid --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o "..\build\agent\$Rid"
Write-Host "Hazır: build\agent\$Rid"
