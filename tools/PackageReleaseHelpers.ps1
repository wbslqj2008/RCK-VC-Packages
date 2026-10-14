# Dot-sourced by the release builders. This file never performs GitHub writes.
function Write-PackageJson([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($Path, $json, (New-Object Text.UTF8Encoding($false)))
}

function Save-RepositoryEntry($Entry, [string]$OutputFolder, [string]$ManifestPath) {
    Write-PackageJson (Join-Path $OutputFolder 'manifest-entry.json') $Entry
    if ($ManifestPath) {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.schemaVersion -ne 1 -or $null -eq $manifest.packages) {
            throw 'packages[]가 있는 schemaVersion 1 manifest가 필요합니다.'
        }
        $manifest.packages = @($manifest.packages | Where-Object { $_.id -ne $Entry.id }) + @($Entry)
        if ($manifest.PSObject.Properties.Name -contains 'updatedAt') { $manifest.updatedAt = [DateTimeOffset]::UtcNow.ToString('o') }
        else { $manifest | Add-Member NoteProperty updatedAt ([DateTimeOffset]::UtcNow.ToString('o')) }
        Write-PackageJson ([IO.Path]::GetFullPath($ManifestPath)) $manifest
    }
}

function Remove-PackageTemp([string]$Path) {
    $root = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolved) -notmatch '^RCK_Package_[a-f0-9]{32}$') { throw '임시 패키지 정리 경로가 올바르지 않습니다.' }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
