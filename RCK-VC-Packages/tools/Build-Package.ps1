[CmdletBinding()]
param(
    [string]$PackageName,
    [string]$Version,
    [switch]$All,
    [switch]$NoExplorer
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$PackagesRoot = Join-Path $RepoRoot 'packages'
$DistRoot = Join-Path $RepoRoot 'dist'

function Write-Title([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
    Write-Host (' ' + $Text) -ForegroundColor Cyan
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
}

function Get-PackageFolders {
    if (-not (Test-Path $PackagesRoot)) {
        throw "packages 폴더를 찾을 수 없습니다: $PackagesRoot"
    }

    return @(Get-ChildItem -Path $PackagesRoot -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName 'package.json')
    } | Sort-Object Name)
}

function Read-PackageJson([string]$Folder) {
    $path = Join-Path $Folder 'package.json'
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "package.json을 읽을 수 없습니다: $path`n$($_.Exception.Message)"
    }
}

function Save-PackageJson([string]$Folder, $Package) {
    $path = Join-Path $Folder 'package.json'
    $json = $Package | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

function Assert-SafeRelativePath([string]$Value, [string]$FieldName) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$FieldName 값이 비어 있습니다."
    }
    if ([System.IO.Path]::IsPathRooted($Value) -or $Value -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "$FieldName 경로가 안전하지 않습니다: $Value"
    }
}

function Build-OnePackage([System.IO.DirectoryInfo]$Folder, [string]$RequestedVersion) {
    $package = Read-PackageJson $Folder.FullName

    foreach ($required in @('id', 'name', 'type', 'version', 'description', 'files')) {
        if ($null -eq $package.$required -or ([string]$package.$required).Trim().Length -eq 0) {
            throw "$($Folder.Name)/package.json에 '$required' 값이 없습니다."
        }
    }

    if ($RequestedVersion) {
        if ($RequestedVersion -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') {
            throw "버전 형식이 올바르지 않습니다: $RequestedVersion (예: 1.2.0)"
        }
        $package.version = $RequestedVersion
        Save-PackageJson $Folder.FullName $package
    }

    $stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("RCKPackage_" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    try {
        Copy-Item -LiteralPath (Join-Path $Folder.FullName 'package.json') -Destination (Join-Path $stagingRoot 'package.json') -Force

        foreach ($file in @($package.files)) {
            $sourceRelative = [string]$file.source
            $destinationRelative = [string]$file.destination
            Assert-SafeRelativePath $sourceRelative 'source'
            Assert-SafeRelativePath $destinationRelative 'destination'

            $sourcePath = Join-Path $Folder.FullName ($sourceRelative -replace '/', [System.IO.Path]::DirectorySeparatorChar)
            if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
                throw "필수 파일이 없습니다: $sourcePath"
            }

            $stagingPath = Join-Path $stagingRoot ($sourceRelative -replace '/', [System.IO.Path]::DirectorySeparatorChar)
            $stagingDir = Split-Path -Parent $stagingPath
            New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null
            Copy-Item -LiteralPath $sourcePath -Destination $stagingPath -Force
        }

        New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
        $zipName = "$($package.id)-$($package.version).zip"
        $zipPath = Join-Path $DistRoot $zipName
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }

        Compress-Archive -Path (Join-Path $stagingRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal -Force
        $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash

        Write-Host "[생성] $zipName" -ForegroundColor Green
        Write-Host "       버전: $($package.version)"
        Write-Host "       파일: $(@($package.files).Count)개"
        Write-Host "       위치: $zipPath"
        Write-Host "       검증값은 GitHub Actions가 자동으로 Manifest에 반영합니다." -ForegroundColor DarkGray

        return [PSCustomObject]@{
            Id = [string]$package.id
            Name = [string]$package.name
            Version = [string]$package.version
            ZipPath = $zipPath
            Sha256 = $hash
        }
    }
    finally {
        if (Test-Path -LiteralPath $stagingRoot) {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Title 'RCK VC 패키지 생성기'
$folders = Get-PackageFolders
if ($folders.Count -eq 0) {
    throw '생성 가능한 패키지가 없습니다.'
}

$selected = @()
if ($All) {
    $selected = $folders
}
elseif ($PackageName) {
    $selected = @($folders | Where-Object { $_.Name -ieq $PackageName })
    if ($selected.Count -eq 0) {
        throw "패키지를 찾을 수 없습니다: $PackageName"
    }
}
else {
    Write-Host '[0] 전체 패키지 생성'
    for ($i = 0; $i -lt $folders.Count; $i++) {
        $p = Read-PackageJson $folders[$i].FullName
        Write-Host ("[{0}] {1}  (현재 버전 {2})" -f ($i + 1), $p.name, $p.version)
    }

    Write-Host ''
    $choice = Read-Host '생성할 번호를 입력하세요'
    if ($choice -eq '0') {
        $selected = $folders
    }
    elseif ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $folders.Count) {
        $index = [int]$choice - 1
        $selected = @($folders[$index])
    }
    else {
        throw "올바른 번호가 아닙니다: $choice"
    }
}

$results = @()
if ($selected.Count -eq 1) {
    $current = Read-PackageJson $selected[0].FullName
    if (-not $Version) {
        $inputVersion = Read-Host "새 버전 입력 (Enter: $($current.version) 유지)"
        if (-not [string]::IsNullOrWhiteSpace($inputVersion)) {
            $Version = $inputVersion.Trim()
        }
    }
    $results += Build-OnePackage $selected[0] $Version
}
else {
    Write-Host ''
    Write-Host '전체 생성에서는 각 package.json의 현재 버전을 사용합니다.' -ForegroundColor Yellow
    foreach ($folder in $selected) {
        $results += Build-OnePackage $folder $null
    }
}

$uploadList = Join-Path $DistRoot '이번_릴리즈에_업로드할_파일.txt'
$lines = @(
    'GitHub Release를 Draft 상태로 만든 뒤 아래 ZIP만 첨부하고 Publish release를 누르세요.',
    'SHA-256 및 manifest.json 수정은 GitHub Actions가 자동 처리합니다.',
    ''
) + @($results | ForEach-Object { [System.IO.Path]::GetFileName($_.ZipPath) })
[System.IO.File]::WriteAllLines($uploadList, $lines, [System.Text.UTF8Encoding]::new($false))

Write-Title '완료'
Write-Host "생성 폴더: $DistRoot" -ForegroundColor Green
Write-Host '다음 작업: GitHub의 Draft Release에 생성된 ZIP을 올리고 Publish release를 누르세요.'

if (-not $NoExplorer -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Start-Process explorer.exe $DistRoot
}
