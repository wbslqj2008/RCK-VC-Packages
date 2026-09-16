# DLL 업로드 자동 업데이트

## 평소 사용법

저장소의 `packages/애드온이름/payload/`에 새 DLL을 업로드하고 main에 반영합니다.
작성자가 누구인지와 관계없이 같은 워크플로가 실행됩니다. 담당자는 DLL의 AssemblyVersion/FileVersion, package.json 버전, manifest.json, ZIP, SHA-256을 매번 수정하지 않습니다.
기존 7개 애드온의 package.json 정보를 그대로 재사용합니다. 새 애드온을 추가할 때만 이름, ID, 파일 위치 등 기본 정보를 한 번 등록합니다.

## 처리 순서

1. main 업로드를 감지합니다. 대기 중인 작업은 실행 시작 시 최신 main을 체크아웃합니다.
2. 각 package.json에 지정된 파일의 실제 바이트를 SHA-256으로 계산합니다.
3. 파일 경로/해시와 패키지 설명 등 metadata를 묶어서 contentSha256을 계산합니다. package.json의 version은 이 변경 검사에서 제외합니다.
4. manifest에 저장된 이전 contentSha256과 같으면 그 애드온을 건너뜁니다. 파일을 그대로 다시 올리거나 GitHub 수정 시간만 바뀌는 경우에는 배포하지 않습니다.
5. 다른 애드온은 그대로 두고, 변경된 애드온만 버전을 올리고 ZIP을 만듭니다.
6. ZIP을 Release에 게시한 후, 다운로드 URL/ZIP SHA-256/설치 파일별 SHA-256/패키지 버전을 manifest에 자동 반영합니다.
7. 매니저를 열거나 새로고침하면 설치 폴더의 실제 파일 해시를 manifest와 비교합니다. 모두 같으면 최신, 하나라도 다르거나 빠져 있으면 업데이트 가능입니다. 읽기 실패나 잘못된 비교 정보는 버전 확인 불가입니다.

패키지 버전과 DLL 내부 버전은 별개입니다. 패키지 버전이 1.0.2이고 DLL FileVersion이 계속 1.0.0.0이어도 정상적으로 비교합니다.
설치 이력이 없더라도 내용이 최신 파일과 같으면 해당 패키지 버전을 표시합니다. 다른 파일의 과거 버전은 알아낼 수 없으므로 설치 이력이 없으면 현재 버전을 '-'로 표시합니다.

## 버전 증가 규칙

일반 업로드는 마지막으로 게시된 해당 애드온의 패키지 버전에 patch +1을 적용합니다.
0.0.0 → 0.0.1, 1.3.7 → 1.3.8, 1.3.9 → 1.3.10입니다. 9에서 10으로 넘어갈 때 앞자리로 자동 올림하지 않습니다.
여러 애드온을 동시에 변경하면 각각 자기 버전에서 증가합니다. 버전은 Git 커밋 개수나 업로더별로 계산하지 않습니다.

Actions의 `DLL 업로드 자동 배포` → Run workflow에서 필요할 때 다음 옵션을 선택할 수 있습니다.

- bump=minor, package_id=rck.rckstudio: 해당 애드온 1.3.7 → 1.4.0
- bump=major, package_id=rck.rckstudio: 해당 애드온 1.3.7 → 2.0.0
- bump=patch, package_id=rck.rckstudio: 파일이 같아도 해당 애드온 강제 재배포
- package_id를 비우면 실제 변경된 애드온에만 선택한 bump를 적용

처음 자동화를 켤 때 기존 manifest에 contentSha256이 없으면 비교 기준을 만들기 위해 기존 패키지를 한 번 새로 배포합니다. 현재 1.0.0인 기존 패키지는 1.0.1이 됩니다. 이후부터 실제 변경 시에만 증가합니다.
신규 패키지는 package.json에 있는 초기 버전으로 처음 게시하고, 이후 게시 때부터 자동 증가합니다.

## 세 명이 함께 사용하는 경우

두 담당자를 GitHub Collaborator로 추가하고 쓰기 권한을 줍니다. 작업은 업로더가 아닌 저장소의 main 변경을 기준으로 실행됩니다.
하나의 concurrency 그룹으로 manifest 작업을 순차 실행하며, 대기 중의 연속 업로드는 최신 main 전체를 다시 검사합니다.
동일 애드온의 동일 파일을 서로 교체하면 GitHub main에 마지막으로 반영된 파일이 최종 기준이 됩니다.

## 최초 적용

이 변경본의 workflow와 scripts를 저장소 main에 반영하고, SHA-256 비교가 추가된 매니저 DLL을 설치합니다.
Repository Settings → Actions → General에서 Actions 사용 및 필요한 contents 쓰기 권한을 허용해야 합니다.
main 보호 규칙이 봇의 직접 커밋을 막고 있다면 manifest 자동 반영에 맞는 권한 정책이 필요합니다.
평소 사용자 동작은 DLL 업로드와 매니저 새로고침입니다. 자동 설치는 하지 않으며 기존 선택 설치/업데이트 버튼을 유지합니다.

## 검증

Python 테스트: `python -m unittest discover -s scripts -p test_auto_publish.py -v`
매니저 테스트: Release 빌드 후 `Tests/content-detection-tests.ps1` 실행
실제 7개 패키지 ZIP 생성과 각 ZIP payload/manifest 해시 일치 및 설치 이력 없는 최신 탐지를 확인했습니다.
