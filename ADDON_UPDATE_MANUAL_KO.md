# 애드온 업데이트·배포 매뉴얼

대상 저장소: [wbslqj2008/RCK-VC-Packages](https://github.com/wbslqj2008/RCK-VC-Packages)

**일반 수정은 새 DLL을 올리면 patch가 자동으로 올라갑니다. minor/major는 새 DLL 업로드의 자동 배포가 끝난 뒤 Actions에서 해당 패키지를 지정해 한 번 실행합니다.**

## 1. 버전이 올라가는 기준

2026-10-14에 GitHub의 실제 코드와 RCKStudio 3.1.8 파일의 격리된 복사본으로 확인한 결과입니다. 아래 검증은 실제 운영 버전을 올리지 않고 수행했습니다.

| 실행 | 조건 | 3.1.8 기준 결과 |
|---|---|---|
| patch 자동 배포 | DLL/의존 파일 또는 배포 설명에 변경이 있음 | 3.1.9 |
| patch 수동 실행 | 패키지 ID를 지정했지만 파일/설명이 그대로임 | 3.1.8 유지, 배포 건너뜀 |
| minor 수동 실행 | `minor` + 대상 패키지 ID 지정 | 3.2.0 |
| major 수동 실행 | `major` + 대상 패키지 ID 지정 | 4.0.0 |
| minor/major + ID 공란 | 대상을 지정하지 않음 | 오류 안내, 배포하지 않음 |
| package.json의 version만 수정 | 실제 파일/설명은 그대로 | 새 버전 발행 없이 현재 배포 버전으로 기록 복구 |

minor/major는 하위 번호를 0으로 초기화합니다. `3.1.8 → 3.2.0`, `3.1.8 → 4.0.0`입니다.

GitHub가 관리하는 **배포 버전**과 DLL 내부의 **AssemblyVersion/FileVersion**은 별도입니다. DLL 파일 버전이 2.1.4.0이고 배포 버전이 3.1.8일 수 있습니다. 매니저에서는 DLL 버전, 설치 배포 버전, 최신 배포 버전을 구분합니다.

## 2. 일반 업데이트: patch 자동 배포

RCKStudio를 예로 설명합니다.

1. **코드를 수정하고 빌드합니다.** 배포할 새 `Plugin.RCKStudio.dll`이 실제로 생성됐는지 확인합니다. 일반 배포에는 Release 빌드 결과를 사용합니다.
2. 해당 VC에서 새 DLL의 동작을 확인합니다. VC 설치 폴더에 붙여넣는 것만으로 GitHub 배포 파일은 바뀌지 않습니다.
3. GitHub의 [packages/RCKStudio/payload](https://github.com/wbslqj2008/RCK-VC-Packages/tree/main/packages/RCKStudio/payload) 폴더를 엽니다.
4. **Add file → Upload files**를 선택합니다. 새 DLL을 업로드하고, 기존 `Plugin.RCKStudio.dll`과 같은 경로·이름으로 교체합니다. 변경된 의존 DLL이 있으면 함께 올립니다.
5. 변경 설명을 입력합니다. 예: `RCKStudio: Ctrl+휠 확대 오류 수정`. 이 설명은 기본 배포 노트에도 사용됩니다.
6. 변경 사항을 **main에 반영**합니다. 별도 브랜치에 올렸다면 PR을 main에 병합한 시점에 자동 배포됩니다. 이 작업에는 저장소 쓰기 권한이 필요합니다.
7. [Actions → 패키지 업로드 자동 배포](https://github.com/wbslqj2008/RCK-VC-Packages/actions/workflows/auto-publish.yml)에서 방금 업로드로 생긴 실행을 엽니다. 가장 최근 업로드의 실행인지 커밋과 시각을 확인합니다.
8. 완료되면 실행의 **Summary → 배포 결과**에서 `rck.rckstudio: 3.1.8 → 3.1.9` 같은 결과를 확인합니다.
9. VC의 애드온 매니저에서 새로고침합니다. 현재 파일과 새 배포 파일이 다르면 업데이트 가능으로 표시됩니다.

**일반 patch는 여기까지입니다. 자동 배포 뒤 patch를 다시 수동 실행할 필요가 없습니다.**

소스 코드만 GitHub에 올리고 배포용 DLL을 교체하지 않으면 이 저장소는 새 DLL을 빌드하지 않습니다. 현재 자동화는 `packages/`에 올라온 완성된 DLL/VCMX를 포장·배포하는 방식입니다.

## 3. minor/major로 올리는 방법

새 기능을 minor로 배포하거나 큰 변경을 major로 배포하려면 다음 순서로 진행합니다.

1. 새 DLL을 위 절차대로 올립니다.
2. 업로드에 따른 **자동 patch 실행이 성공할 때까지 기다립니다.**
3. [Actions → 패키지 업로드 자동 배포](https://github.com/wbslqj2008/RCK-VC-Packages/actions/workflows/auto-publish.yml)를 엽니다.
4. **Run workflow**를 누르고 Branch는 **main**을 선택합니다.
5. 아래 값을 입력합니다.

| 입력 항목 | minor 예시 | major 예시 |
|---|---|---|
| `bump` / 버전 증가 방식 | `minor` | `major` |
| `package_id` / 특정 패키지 | `rck.rckstudio` | `rck.rckstudio` |
| `release_notes` / 릴리즈 노트 | `스크립트 검색 기능 추가` | `프로젝트 구조 개편` |

6. Run workflow로 한 번 실행합니다.
7. 완료 후 Summary의 버전 변경 결과와 대상 패키지를 확인합니다.

예를 들어 시작이 3.1.8이면 새 DLL 업로드로 3.1.9가 먼저 배포됩니다. 이어 minor를 실행하면 3.2.0, major를 실행하면 4.0.0이 됩니다. **현재 방식에서는 자동 patch와 이후의 minor/major가 각각 별도 Release로 남습니다.**

minor/major를 반복해서 실행하면 매번 올라갑니다. 같은 DLL이어도 명시적인 버전 변경 요청으로 처리합니다. 원하는 버전이 만들어졌으면 다시 실행하지 마십시오.

**major/minor를 먼저 실행하고 나중에 DLL을 올리지 마십시오.** 먼저 실행하면 기존 DLL에 새 버전이 붙고, 나중에 DLL을 올릴 때 그 버전의 patch가 또 올라갑니다.

## 4. 정확한 업로드 위치와 패키지 ID

아래는 현재 저장소에서 직접 확인한 위치입니다. 폴더 이름과 package_id는 다릅니다.

| 애드온 | DLL 업로드 위치 | Actions의 `package_id` |
|---|---|---|
| RCKStudio | `packages/RCKStudio/payload/Plugin.RCKStudio.dll` | `rck.rckstudio` |
| Addon Manager 본체 | `packages/AddonManager/Plugin.RCKAddonManager.dll` | `rck.addon-manager` |
| CodeLens | `packages/CodeLens/payload/Plugin.CodeLens.dll` | `rck.codelens` |
| CycleTime | `packages/CycleTime/payload/Plugin.CycleTime.dll` | `rck.cycletime` |
| Productify | `packages/Productify/payload/Plugin.Productify.dll` | `rck.productify` |
| ShortCut | `packages/ShortCut/payload/Plugin.ShortCut.dll` | `rck.shortcut` |
| SignalLinker | `packages/SignalLinker/payload/Plugin.SignalLinker.dll` | `rck.signallinker` |
| TurboRename | `packages/TurboRename/payload/Plugin.TurboRename.dll` | `rck.turborename` |

RCKStudio의 정식 ID는 **`rck.rckstudio`**입니다. `rck.studio` 별칭도 지원하지만 매뉴얼에서는 정식 ID를 사용합니다.

RCKStudio에 파일을 추가하거나 제거한다면 `packages/RCKStudio/package.json`의 `files`도 같이 수정해야 합니다. 기존 목록에 없는 파일은 폴더에만 올려도 설치 패키지에 포함되지 않습니다.

## 5. 배포가 정말 끝났는지 확인

Actions 실행이 초록색이어도 **새 패키지가 만들어졌는지**를 확인해야 합니다. 변경이 없어 건너뛴 실행도 성공으로 표시될 수 있습니다.

새 배포가 있는 경우 다음 세 단계가 모두 성공해야 합니다.

1. **변경된 패키지 생성:** 대상 ID와 변경 전/후 버전이 Summary에 표시됩니다.
2. **GitHub Release 게시:** [Releases](https://github.com/wbslqj2008/RCK-VC-Packages/releases)에 대상 ZIP이 올라옵니다.
3. **Manifest 반영:** [manifest.json](https://github.com/wbslqj2008/RCK-VC-Packages/blob/main/manifest.json)에 버전·다운로드 URL·SHA-256이 갱신되고, 대상 package.json 버전도 일치합니다.

RCKStudio 3.2.0이라면 다음 항목이 모두 3.2.0이어야 합니다.

- `packages/RCKStudio/package.json`의 version
- 배포 ZIP 안 package.json의 version
- ZIP 파일명 `rck.rckstudio-3.2.0.zip`
- manifest의 `rck.rckstudio` 항목 version 및 downloadUrl

DLL 내부 FileVersion은 위 네 항목과 별개입니다.

`GitHub Release 게시`가 성공하고 `Manifest 반영`이 실패하면 ZIP만 올라간 상태입니다. 사용자는 이전 목록을 보게 됩니다. 마지막 단계까지 성공한 실행을 기준으로 배포 완료를 판단합니다.

## 6. 버전이 안 올라갈 때 확인할 것

| 상황 | 이유 또는 확인할 항목 | 처리 |
|---|---|---|
| 같은 DLL을 다시 올렸는데 patch가 안 오름 | 파일 내용이 동일함 | 정상 동작. 새 빌드 DLL인지 확인 |
| 로컬 VC에서는 바뀌었는데 GitHub 버전은 그대로임 | VC 폴더만 교체함 | 새 DLL을 GitHub의 정확한 packages 경로에 업로드 |
| 코드만 수정했는데 새 버전이 안 나옴 | 배포 DLL을 빌드·업로드하지 않음 | 빌드 결과 DLL 업로드 |
| package.json의 version만 바꿨는데 버전이 유지됨 | 기존 패키지의 배포 번호는 manifest를 기준으로 계산함 | version 직접 변경 대신 새 DLL 업로드 또는 minor/major 실행 |
| minor/major가 안 오름 | package_id 공란 또는 잘못된 ID | 정식 ID 입력. RCKStudio는 rck.rckstudio |
| 다른 브랜치에 업로드했는데 자동 배포가 안 됨 | 자동 배포는 main 반영을 감지함 | main에 병합 |
| 기존 Actions 이름만 보임 | 이전 화면/실행을 보고 있음 | 새로고침 후 현재 워크플로와 최근 실행 확인 |
| 성공이라고 뜨지만 새 Release가 없음 | 변경 없음으로 건너뜀 또는 기록 동기화만 수행함 | Summary의 배포 결과 확인 |
| Release에 ZIP은 있지만 매니저 목록은 그대로임 | Manifest 반영 단계 실패 가능 | 해당 실행의 마지막 단계 로그 확인 |
| 매니저가 최신이라고 하는데 DLL 내부 숫자가 낮음 | DLL 내부 버전과 배포 버전이 다른 기준임 | 목록의 설치 배포 버전·최신 배포 버전과 파일 비교 근거를 확인 |

## 7. Addon Manager 본체를 업데이트할 때

`packages/AddonManager/Plugin.RCKAddonManager.dll`에 **새 매니저 본체 DLL**을 올립니다. Bootstrap DLL을 이 파일 대신 올리지 않습니다.

파일 변경이 있으면 매니저의 patch 버전이 자동 증가합니다. 예: 1.10.1 → 1.10.2. 사용자 PC에서는 다음 VC 시작 시 Bootstrap이 새 매니저를 감지하고, 사용자가 예를 누르면 새 본체를 받습니다.

## 8. 이번 점검 결과

- 과거 [major 실행 기록](https://github.com/wbslqj2008/RCK-VC-Packages/actions/runs/38515831848)은 major를 선택했지만 패키지 ID가 공란이었고 배포 개수가 0이었습니다. 당시에는 이 상태도 성공으로 끝났습니다.
- 현재 코드는 minor/major에 ID가 없으면 오류를 내므로 묵묵히 건너뛰지 않습니다.
- RCKStudio 3.1.8의 실제 파일과 GitHub 코드를 복제하여 patch 3.1.9, minor 3.2.0, major 4.0.0을 검증했습니다. ZIP 내부 버전·파일명·manifest·package.json도 일치했습니다.
- 기존 일부 package.json에 남은 초기 버전은 새로운 Release를 발행하지 않고 현재 배포 버전으로 맞추도록 보완했습니다.
- 동일 파일 patch 건너뛰기, 잘못된 ID 거절, 다른 패키지 버전 보존 등을 포함한 테스트를 통과했습니다.

검증 파일: `artifacts/version-audit/version-mode-results.json`. 위 3.1.9/3.2.0/4.0.0은 검증용 결과이며 이 점검 때문에 운영에 발행하지 않았습니다.

### GitHub 화면 안내 출처

- [파일 업로드 안내](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
- [현재 배포 워크플로](https://github.com/wbslqj2008/RCK-VC-Packages/blob/main/.github/workflows/auto-publish.yml)

## 9. 배포 번호를 지정한 값으로 정리할 때

일반 업로드는 기존처럼 자동 patch로 배포합니다. 과거 배포 번호를 바로잡을 때만 루트의 `release-plan.json`을 사용합니다.

- `schemaVersion`은 `1`, `id`는 이 정리 작업만의 새로운 식별자, `versions`는 패키지 ID와 정확한 배포 버전의 대응표입니다.
- 패키지별 변경 내용은 해당 `packages/<폴더>/package.json`의 `releaseNotes`에 적습니다.
- `main`에 반영하면 지정 번호로 ZIP을 새로 만들고 ZIP 내부 버전·파일명·manifest·원본 package.json을 일치시킵니다. 같은 번호 또는 낮은 번호로 정정하는 경우도 포함합니다.
- Release 업로드가 성공한 뒤에만 manifest의 `appliedReleasePlans`에 작업 ID를 기록합니다. 같은 ID는 다시 적용하지 않아 이후 실제 변경은 정리된 번호 다음 patch로 증가합니다.
- 새로운 정정 작업에는 반드시 새로운 ID를 사용합니다. 아직 적용하지 않은 정정 작업과 수동 minor/major 실행을 혼합하지 않습니다.

2026-10-15 정리: CodeLens 2.1.2, CycleTime 1.0.0, Productify 1.0.1, Addon Manager 2.0.5, RCKStudio 3.1.8(변경 내용 수정), ShortCut 1.0.4, SignalLinker 1.0.1, TurboRename 2.0.1.

Addon Manager 2.0.5부터 목록의 DLL 버전 열을 제거했습니다. 현재 배포 파일과 완전히 일치하면 과거 설치 기록의 번호보다 현재 배포 번호를 우선하여 표시합니다.
