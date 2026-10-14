param(
    [Parameter(Mandatory = $true)][string]$DllPath,
    [Parameter(Mandatory = $true)][string]$Description,
    [string]$Name = '',
    [string]$PackageId = '',
    [string]$Developer = '',
    [string[]]$DependencyFiles = @(),
    [string]$Version = '1.0.0',
    [string[]]$VcVersions = @('5.0', '5.1'),
    [string]$OutputFolder = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PackageReleaseHelpers.ps1')
$sourceDll = (Resolve-Path -LiteralPath $DllPath).Path
if (-not [IO.File]::Exists($sourceDll) -or [IO.Path]::GetExtension($sourceDll) -ne '.dll') { throw '빌드한 애드온 DLL을 선택하십시오.' }
# Read assembly identity without executing the add-on.
$identity = [Reflection.AssemblyName]::GetAssemblyName($sourceDll)
$dllName = [IO.Path]::GetFileName($sourceDll)
$baseName = [IO.Path]::GetFileNameWithoutExtension($sourceDll) -replace '^Plugin\.', ''
if (-not $Name) { $Name = $baseName }
if ([string]::IsNullOrWhiteSpace($Name) -or [string]::IsNullOrWhiteSpace($Description)) { throw '이름과 설명을 입력하십시오.' }
if (-not $PackageId) {
    $slug = ($baseName.ToLowerInvariant() -replace '[^a-z0-9._-]', '-').Trim('.', '-', '_')
    if (-not $slug -or $slug -notmatch '^[a-z0-9]') { throw '자동 ID를 만들 수 없습니다. rck.myaddon처럼 PackageId를 입력하십시오.' }
    $PackageId = 'rck.' + $slug
}
if ($PackageId -notmatch '^rck\.[a-z0-9][a-z0-9._-]*$' -or $PackageId.StartsWith('rck.ecatalog.') -or $PackageId -eq 'rck.addon-manager') { throw '일반 애드온 ID는 rck.myaddon처럼 입력하십시오. eCatalog 및 매니저 ID는 사용할 수 없습니다.' }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw '최초 버전은 1.0.0처럼 입력하십시오.' }
if (-not $VcVersions -or @($VcVersions | Where-Object { $_ -notmatch '^\d+\.\d+$' }).Count) { throw 'VC 호환 버전은 5.0, 5.1처럼 입력하십시오.' }
$sourceFiles = @($sourceDll)
$seen = @{ $dllName = $true }
foreach ($dependency in $DependencyFiles) {
    $source = (Resolve-Path -LiteralPath $dependency).Path
    if (-not [IO.File]::Exists($source)) { throw "배포 파일이 아닙니다: $dependency" }
    if ($source.Equals($sourceDll, [StringComparison]::OrdinalIgnoreCase)) { continue }
    $fileName = [IO.Path]::GetFileName($source)
    if ($seen.ContainsKey($fileName)) { throw "배포 파일 이름이 중복됩니다: $fileName" }
    $seen[$fileName] = $true
    $sourceFiles += $source
}
if (-not $OutputFolder) {
    $OutputFolder = Join-Path (Split-Path $PSScriptRoot -Parent) ('artifacts/package-drafts/' + $PackageId + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
}
$fullOutput = [IO.Path]::GetFullPath($OutputFolder)
if (Test-Path -LiteralPath $fullOutput) { throw "기존 폴더를 덮어쓰지 않습니다. 새 출력 폴더를 선택하십시오: $fullOutput" }
foreach ($source in $sourceFiles) {
    if ($source.StartsWith($fullOutput.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw '원본 파일 폴더 안에 출력할 수 없습니다.' }
}
$files = @($sourceFiles | ForEach-Object {
    $fileName = [IO.Path]::GetFileName($_)
    [ordered]@{ source = "payload/$fileName"; destination = "vcRoot/$fileName" }
})
$metadata = [ordered]@{
    schemaVersion = 1; id = $PackageId; name = $Name; type = 'addon'; version = $Version
    description = $Description; developer = $Developer; mainDll = $dllName
    restartRequired = $true; systemPackage = $false; vcVersions = @($VcVersions)
    releaseNotes = @('최초 등록'); files = $files
}
$payload = Join-Path $fullOutput 'payload'
New-Item -ItemType Directory -Path $payload -Force | Out-Null
foreach ($source in $sourceFiles) { Copy-Item -LiteralPath $source -Destination (Join-Path $payload ([IO.Path]::GetFileName($source))) }
Write-PackageJson (Join-Path $fullOutput 'package.json') $metadata
$guide = @"
GitHub 최초 등록

1. GitHub RCK-VC-Packages 저장소에서 packages/$baseName 폴더를 만듭니다.
2. 이 폴더의 package.json과 payload 폴더를 함께 업로드합니다.
3. main에 반영하면 Actions가 ZIP/해시/배포 목록을 자동 생성합니다.
4. 이후에는 payload의 DLL을 교체하면 patch가 자동 증가합니다.

ID: $PackageId
개발자: $Developer
메인 DLL: $dllName
DLL 자체 버전: $($identity.Version)
최초 배포 버전: $Version

업로드안내.txt는 GitHub에 올릴 필요가 없습니다.
"@
[IO.File]::WriteAllText((Join-Path $fullOutput '업로드안내.txt'), $guide, (New-Object Text.UTF8Encoding($true)))
[pscustomobject]@{ Id = $PackageId; Name = $Name; PackageFolder = $fullOutput; PackageJson = (Join-Path $fullOutput 'package.json'); FileCount = $files.Count }
