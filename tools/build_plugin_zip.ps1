param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$pluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pluginName = Split-Path $pluginRoot -Leaf
$outputRoot = Join-Path $pluginRoot $OutputDir
$stagingRoot = Join-Path $outputRoot "_staging"
$stagingPlugin = Join-Path $stagingRoot $pluginName
$zipPath = Join-Path $outputRoot "$pluginName.zip"

if (Test-Path $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingPlugin -Force | Out-Null

$excludeDirs = @(
    ".agents",
    ".git",
    ".github",
    ".qodo",
    "__pycache__",
    "dist",
    "koji_MapBundle_imported_packages",
    "tools"
)

$excludeFiles = @(
    ".editorconfig",
    ".gitignore",
    "ChatGPT Image*.png",
    "*.pyc",
    "*.pyo",
    "*.zip"
)

Get-ChildItem -LiteralPath $pluginRoot -Force | ForEach-Object {
    $skip = $excludeDirs -contains $_.Name
    if (-not $skip -and -not $_.PSIsContainer) {
        foreach ($pattern in $excludeFiles) {
            if ($_.Name -like $pattern) {
                $skip = $true
                break
            }
        }
    }
    if (-not $skip) {
        Copy-Item -LiteralPath $_.FullName -Destination $stagingPlugin -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $stagingPlugin -Recurse -Force | Where-Object {
    ($_.PSIsContainer -and $excludeDirs -contains $_.Name) -or
    (-not $_.PSIsContainer -and (
        $_.Name -like "*.pyc" -or
        $_.Name -like "*.pyo"
    ))
} | Sort-Object FullName -Descending | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stagingRootPath = (Resolve-Path $stagingRoot).Path
if (-not $stagingRootPath.EndsWith([IO.Path]::DirectorySeparatorChar)) {
    $stagingRootPath = "$stagingRootPath$([IO.Path]::DirectorySeparatorChar)"
}
$zip = [IO.Compression.ZipFile]::Open(
    (Join-Path (Resolve-Path $outputRoot).Path "$pluginName.zip"),
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Get-ChildItem -LiteralPath $stagingPlugin -Recurse -File -Force | ForEach-Object {
        $relativePath = $_.FullName.Substring($stagingRootPath.Length).Replace([IO.Path]::DirectorySeparatorChar, "/")
        $relativePath = $relativePath.Replace([IO.Path]::AltDirectorySeparatorChar, "/")
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip,
            $_.FullName,
            $relativePath,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $zip.Dispose()
}

Remove-Item -LiteralPath $stagingRoot -Recurse -Force

Write-Host "Created $zipPath"
