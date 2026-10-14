# Desktop form for creating GitHub-ready metadata. No GitHub writes or VC installation.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = 'RCK 패키지 등록 도구'
$form.Size = New-Object Drawing.Size(700, 670)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('맑은 고딕', 10)
$form.MinimumSize = $form.Size
$form.MaximizeBox = $false

function Add-Label([string]$Text, [int]$Top) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $Text; $label.Location = New-Object Drawing.Point(20, $Top)
    $label.Size = New-Object Drawing.Size(145, 25)
    $form.Controls.Add($label)
}
function Add-Text([int]$Top, [int]$Width = 480) {
    $box = New-Object Windows.Forms.TextBox
    $box.Location = New-Object Drawing.Point(170, $Top); $box.Size = New-Object Drawing.Size($Width, 28)
    $form.Controls.Add($box)
    return $box
}
function Add-Button([string]$Text, [int]$Left, [int]$Top, [int]$Width = 80) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $Text; $button.Location = New-Object Drawing.Point($Left, $Top)
    $button.Size = New-Object Drawing.Size($Width, 30)
    $form.Controls.Add($button)
    return $button
}
Add-Label '종류' 20
$kind = New-Object Windows.Forms.ComboBox
$kind.DropDownStyle = 'DropDownList'; $kind.Location = New-Object Drawing.Point(170, 20)
$kind.Size = New-Object Drawing.Size(200, 28)
$kind.Items.AddRange(@('애드온 DLL', 'eCatalog VCMX')); $kind.SelectedIndex = 0
$form.Controls.Add($kind)
Add-Label '메인 파일' 65
$fileBox = Add-Text 65 390; $fileBox.ReadOnly = $true
$fileButton = Add-Button '선택' 570 65
Add-Label '표시 이름' 110; $nameBox = Add-Text 110
Add-Label '패키지 ID' 155; $idBox = Add-Text 155
Add-Label '개발자 (선택)' 200; $developerBox = Add-Text 200
Add-Label '설명' 245; $descriptionBox = Add-Text 245
$descriptionBox.Multiline = $true; $descriptionBox.ScrollBars = 'Vertical'; $descriptionBox.Height = 130
Add-Label '함께 배포할 파일' 390
$extraBox = Add-Text 390 390; $extraBox.ReadOnly = $true
$extraButton = Add-Button '선택' 570 390
Add-Label '사용 안내 PDF' 435
$pdfBox = Add-Text 435 390; $pdfBox.ReadOnly = $true
$pdfButton = Add-Button '선택' 570 435
$pdfButton.Enabled = $false
Add-Label 'VC 호환 버전' 480; $versionsBox = Add-Text 480; $versionsBox.Text = '5.0, 5.1'
$hint = New-Object Windows.Forms.Label
$hint.Text = '등록 정보를 입력하면 JSON과 업로드용 파일을 생성합니다. 생성 후 GitHub main에 업로드하세요.'
$hint.Location = New-Object Drawing.Point(20, 530); $hint.Size = New-Object Drawing.Size(640, 40)
$form.Controls.Add($hint)
$createButton = Add-Button '업로드 폴더 만들기' 450 580 200
$script:extraFiles = @()
$script:componentFiles = @()

$kind.Add_SelectedIndexChanged({
    $fileBox.Clear(); $idBox.Clear(); $nameBox.Clear(); $extraBox.Clear(); $pdfBox.Clear()
    $script:extraFiles = @(); $script:componentFiles = @()
    $pdfButton.Enabled = $kind.SelectedIndex -eq 1
    $extraButton.Enabled = $kind.SelectedIndex -eq 0
})
$fileButton.Add_Click({
    $dialog = New-Object Windows.Forms.OpenFileDialog
    $dialog.Filter = if ($kind.SelectedIndex -eq 0) { '애드온 DLL (*.dll)|*.dll' } else { 'VC 컴포넌트 (*.vcmx)|*.vcmx' }
    $dialog.Multiselect = $kind.SelectedIndex -eq 1
    try {
        if ($dialog.ShowDialog($form) -ne 'OK') { return }
        $fileBox.Text = $dialog.FileName
        $script:componentFiles = @($dialog.FileNames)
        $base = [IO.Path]::GetFileNameWithoutExtension($dialog.FileName) -replace '^Plugin\.', ''
        $nameBox.Text = $base
        $slug = ($base.ToLowerInvariant() -replace '[^a-z0-9._-]', '-').Trim('.', '-', '_')
        $idBox.Text = if ($slug -and $slug -match '^[a-z0-9]') { $(if ($kind.SelectedIndex -eq 0) { 'rck.' } else { 'rck.ecatalog.' }) + $slug } else { '' }
    } finally { $dialog.Dispose() }
})
$extraButton.Add_Click({
    $dialog = New-Object Windows.Forms.OpenFileDialog
    $dialog.Filter = '함께 배포할 파일 (*.*)|*.*'; $dialog.Multiselect = $true
    try {
        if ($dialog.ShowDialog($form) -eq 'OK') {
            $script:extraFiles = @($dialog.FileNames)
            $extraBox.Text = ($dialog.FileNames | ForEach-Object { [IO.Path]::GetFileName($_) }) -join ', '
        }
    } finally { $dialog.Dispose() }
})
$pdfButton.Add_Click({
    $dialog = New-Object Windows.Forms.OpenFileDialog; $dialog.Filter = '사용 안내 PDF (*.pdf)|*.pdf'
    try { if ($dialog.ShowDialog($form) -eq 'OK') { $pdfBox.Text = $dialog.FileName } } finally { $dialog.Dispose() }
})
$createButton.Add_Click({
    try {
        if (-not $fileBox.Text -or [string]::IsNullOrWhiteSpace($nameBox.Text) -or [string]::IsNullOrWhiteSpace($idBox.Text) -or [string]::IsNullOrWhiteSpace($descriptionBox.Text)) { throw '메인 파일, 표시 이름, 패키지 ID, 설명을 입력하십시오.' }
        $versions = @($versionsBox.Text -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if (-not $versions -or @($versions | Where-Object { $_ -notmatch '^\d+\.\d+$' }).Count) { throw 'VC 호환 버전은 5.0, 5.1처럼 입력하십시오.' }
        $createButton.Enabled = $false
        if ($kind.SelectedIndex -eq 0) {
            $result = & (Join-Path $PSScriptRoot 'New-AddonPackage.ps1') -DllPath $fileBox.Text -Name $nameBox.Text -PackageId $idBox.Text -Description $descriptionBox.Text -Developer $developerBox.Text -DependencyFiles $script:extraFiles -VcVersions $versions
            $output = $result.PackageFolder
        } else {
            $outputRoot = Join-Path (Split-Path $PSScriptRoot -Parent) ('artifacts/package-drafts/' + [Guid]::NewGuid().ToString('N'))
            & (Join-Path $PSScriptRoot 'New-EcatalogPackage.ps1') -Files $script:componentFiles -PackageId $idBox.Text -Name $nameBox.Text -Description $descriptionBox.Text -Developer $developerBox.Text -PdfPath $pdfBox.Text -VcVersions $versions -OutputFolder $outputRoot | Out-Null
            $output = Join-Path $outputRoot 'repository-package'
        }
        [Windows.Forms.MessageBox]::Show($form, "생성 완료! 이 폴더의 package.json과 배포 파일을 GitHub packages 아래 새 폴더에 함께 올리고 main에 반영하세요.`n`n$output", '패키지 등록 도구', 'OK', 'Information') | Out-Null
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $output + '"')
    } catch {
        [Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, '등록 정보 확인', 'OK', 'Error') | Out-Null
    } finally { $createButton.Enabled = $true }
})
try { [void]$form.ShowDialog() } finally { $form.Dispose() }
