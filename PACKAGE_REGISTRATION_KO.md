패키지 JSON 자동 생성 도구

[등록 도구 ZIP 다운로드](https://github.com/wbslqj2008/RCK-VC-Packages/raw/refs/heads/main/downloads/package-registration-tool.zip)

tools/패키지등록.cmd를 더블클릭하면 등록 창이 열립니다. 관리자 권한은 필요하지 않습니다.

1. 종류를 애드온 DLL 또는 eCatalog VCMX로 선택합니다.
2. 빌드한 DLL 또는 VCMX를 선택합니다. 이름과 고유 ID의 기본값이 자동 입력되므로 필요하면 바꿉니다.
3. 설명을 입력하고 개발자 이름과 VC 호환 버전을 확인합니다.
4. 애드온은 필요한 의존 파일을 함께 선택할 수 있습니다. eCatalog는 사용 안내 PDF를 선택할 수 있습니다.
5. 업로드 폴더 만들기를 누르면 package.json과 배포 파일이 생성되고 폴더가 열립니다.
6. 생성한 package.json과 payload/배포 파일을 GitHub RCK-VC-Packages의 packages 아래 새 폴더에 함께 업로드합니다. main 반영 후 Actions가 ZIP·SHA-256·배포 목록을 자동 생성합니다.

처음 생성한 배포 버전은 1.0.0입니다. 이후 기존 패키지의 DLL/VCMX/PDF를 교체하면 patch가 자동 증가합니다. JSON의 version을 직접 올리지 않습니다. 파일을 추가·제거하면 같은 등록 도구로 새 파일 목록을 생성해 기존 패키지의 package.json에 반영할 수 있습니다. 기존에 배포한 고유 ID를 유지해야 합니다.

애드온에는 type=addon, restartRequired=true, vcRoot/파일명을 생성합니다. 이름이 DLL 파일명과 달라도 mainDll에 선택한 메인 DLL을 기록하므로 의존 DLL과 구분됩니다.
eCatalog에는 type=ecatalog, restartRequired=false, ecatalog/AddonManager/파일명을 생성합니다. VCMX만 Public Documents\Visual Components\<VC 버전>\AddonManager에 설치합니다. PDF는 documentation 폴더로 GitHub에 업로드하고 사용 안내 링크로 제공합니다. eCatalog 최초 업로드 폴더는 생성 도구가 안내하는 packages/<eCatalog ID의 마지막 부분>을 사용해야 PDF 링크가 맞습니다. 애드온 DLL은 VC 설치 폴더에 설치합니다.

자동 생성 도구는 로컬 업로드 폴더를 만들며 GitHub 계정으로 업로드하거나 VC 설치 파일을 변경하지 않습니다. 새로운 출력 폴더를 사용하고 기존 패키지 폴더를 덮어쓰지 않습니다.

PowerShell로 바로 생성하는 방법

    .\tools\New-AddonPackage.ps1 -DllPath 'C:\Build\Plugin.MyAddon.dll' -Name 'My Addon' -Description '기능 설명' -Developer '개발자'

의존 파일이 있다면 -DependencyFiles 'C:\Build\Helper.dll'을 추가합니다. 고유 ID를 직접 지정하려면 -PackageId 'rck.myaddon'을 추가합니다.

배포 도구 ZIP을 사용하는 경우 압축을 모두 풀고 tools/패키지등록.cmd를 실행합니다. ZIP 안에서 직접 실행하지 않습니다.
