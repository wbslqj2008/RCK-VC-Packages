param(
    [Parameter(Mandatory = $true)][string[]]$Files,
    [Parameter(Mandatory = $true)][string]$PackageId,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Description,
    [string]$Developer = '',
    [string]$PdfPath = '',
    [string]$DocumentationUrl = '',
    [string]$RepositoryFolder = '',
    [string[]]$VcVersions = @('5.0', '5.1'),
    [string]$Version = '',
    [string]$OutputFolder = '',
    [string]$Repository = 'wbslqj2008/RCK-VC-Packages',
    [string]$ReleaseTag = '',
    [string]$ManifestPath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PackageReleaseHelpers.ps1')
if ($PackageId -notmatch '^rck\.ecatalog\.[a-z0-9][a-z0-9_-]*$') { throw 'PackageId는 rck.ecatalog.sensor-conveyor처럼 입력하십시오.' }
if ([string]::IsNullOrWhiteSpace($Name) -or [string]::IsNullOrWhiteSpace($Description)) { throw '이름과 설명이 필요합니다.' }
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'GitHub 저장소는 OWNER/REPO 형식이어야 합니다.' }
if (-not $RepositoryFolder) { $RepositoryFolder = $PackageId.Substring('rck.ecatalog.'.Length) }
if ($RepositoryFolder -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw 'GitHub 패키지 폴더 이름이 올바르지 않습니다.' }
if (-not $Version) {
    $Version = '1.0.0'
    if ($ManifestPath) {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $existing = @($manifest.packages | Where-Object { $_.id -eq $PackageId })
        if ($existing.Count -gt 1) { throw 'Manifest에 중복 패키지 ID가 있습니다.' }
        if ($existing.Count -eq 1) {
            if ($existing[0].version -notmatch '^\d+\.\d+\.\d+$') { throw '기존 eCatalog 버전은 major.minor.patch 형식이어야 합니다.' }
            $previous = [version]$existing[0].version
            $Version = '{0}.{1}.{2}' -f $previous.Major, $previous.Minor, ($previous.Build + 1)
        }
    }
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version은 major.minor.patch 형식이어야 합니다.' }
if (-not $ReleaseTag) { $ReleaseTag = "$PackageId-v$Version" }
if ($ReleaseTag -notmatch '^[A-Za-z0-9_.-]+$') { throw 'Release tag가 올바르지 않습니다.' }
if (-not $OutputFolder) { $OutputFolder = Join-Path (Split-Path $PSScriptRoot -Parent) ("artifacts\$PackageId-$Version") }
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$OutputFolder = (Resolve-Path -LiteralPath $OutputFolder).Path
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('RCK_Package_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    $archiveFiles = @()
    $contentFiles = @()
    $seen = @{}
    foreach ($file in $Files) {
        $source = (Resolve-Path -LiteralPath $file).Path
        if ([IO.Path]::GetExtension($source) -ne '.vcmx' -or -not [IO.File]::Exists($source)) { throw "VCMX 파일만 선택하십시오: $file" }
        $fileName = [IO.Path]::GetFileName($source)
        if ($seen.ContainsKey($fileName)) { throw "파일 이름이 중복됩니다: $fileName" }
        $seen[$fileName] = $true
        Copy-Item -LiteralPath $source -Destination (Join-Path $tempRoot $fileName)
        $destination = "ecatalog/AddonManager/$fileName"
        $archiveFiles += [ordered]@{ source = $fileName; destination = $destination }
        $contentFiles += [ordered]@{ destination = $destination; sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash }
    }
    if ($archiveFiles.Count -eq 0) { throw 'VCMX 파일을 한 개 이상 선택하십시오.' }
    $documentationDestination = ''
    $pdfSource = ''
    if ($PdfPath) {
        $pdfSource = (Resolve-Path -LiteralPath $PdfPath).Path
        if ([IO.Path]::GetExtension($pdfSource) -ne '.pdf' -or -not [IO.File]::Exists($pdfSource)) { throw '사용 안내는 PDF 파일이어야 합니다.' }
        $pdfName = [IO.Path]::GetFileName($pdfSource)
        if (-not $DocumentationUrl) { $DocumentationUrl = "https://raw.githubusercontent.com/$Repository/main/packages/$RepositoryFolder/documentation/" + [Uri]::EscapeDataString($pdfName) }
    }
    $metadata = [ordered]@{
        schemaVersion = 1; id = $PackageId; name = $Name; type = 'ecatalog'; version = $Version; files = $archiveFiles
        description = $Description; developer = $Developer; documentationDestination = $documentationDestination; documentationUrl = $DocumentationUrl
        restartRequired = $false; vcVersions = @($VcVersions); releaseNotes = @('eCatalog 컴포넌트 배포')
    }
    Write-PackageJson (Join-Path $tempRoot 'package.json') $metadata
    $sourcePackage = Join-Path $OutputFolder 'repository-package'
    New-Item -ItemType Directory -Path $sourcePackage -Force | Out-Null
    foreach ($file in $archiveFiles) { Copy-Item -LiteralPath (Join-Path $tempRoot $file.source) -Destination (Join-Path $sourcePackage $file.source) -Force }
    if ($pdfSource) {
        $docs = Join-Path $sourcePackage 'documentation'
        New-Item -ItemType Directory -Path $docs -Force | Out-Null
        Copy-Item -LiteralPath $pdfSource -Destination (Join-Path $docs $pdfName) -Force
    }
    Write-PackageJson (Join-Path $sourcePackage 'package.json') $metadata
    $assetName = "$PackageId-$Version.zip"
    $zipPath = Join-Path $OutputFolder $assetName
    Compress-Archive -Path (Join-Path $tempRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal -Force
    $entry = [ordered]@{
        id = $PackageId; name = $Name; type = 'ecatalog'; version = $Version; description = $Description
        developer = $Developer; documentationDestination = $documentationDestination; documentationUrl = $DocumentationUrl
        downloadUrl = "https://github.com/$Repository/releases/download/$ReleaseTag/$assetName"
        sha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash; contentFiles = $contentFiles
        archiveType = 'zip'; restartRequired = $false; systemPackage = $false; vcVersions = @($VcVersions)
        releaseNotes = @('eCatalog 컴포넌트 배포'); publishedAt = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Save-RepositoryEntry $entry $OutputFolder $ManifestPath
    Write-Output "ZIP: $zipPath"
    Write-Output "Manifest: $(Join-Path $OutputFolder 'manifest-entry.json')"
    Write-Output "Release tag: $ReleaseTag"
    Write-Output "GitHub 폴더: packages/$RepositoryFolder (PDF는 documentation 폴더와 함께 업로드; 설치 ZIP에는 포함되지 않음)"
} finally { Remove-PackageTemp $tempRoot }
