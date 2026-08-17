param(
    [string]$Dest = "..\AlasGG-GGHandler-Export"
)

Write-Host "Exporting GG handler and dependencies to: $Dest"

$items = @(
    'module/gg_handler',
    'module/base',
    'module/logger.py',
    'module/config',
    'module/ocr',
    'module/device',
    'module/submodule',
    'module/gg_handler/assets'
)

foreach ($it in $items) {
    if (Test-Path $it) {
        $target = Join-Path $Dest $it
        Write-Host "Copying $it -> $target"
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item -Path $it -Destination $target -Recurse -Force -ErrorAction Stop
    } else {
        Write-Host "Skipped (not found): $it"
    }
}

Write-Host "Export finished. Please review the exported folder and resolve any missing third-party deps or configs." 
