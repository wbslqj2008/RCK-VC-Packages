# 자동 패키지 배포

화면에서 따라 할 수 있는 업로드·patch/minor/major 절차와 문제 해결은 [ADDON_UPDATE_MANUAL_KO.md](ADDON_UPDATE_MANUAL_KO.md)를 참고하십시오.

저장소 쓰기 권한이 있는 기여자가 `packages/<패키지>/`의 DLL/VCMX와 package.json을 올리면 자동 배포합니다. 버전 선택 작업은 일반 업로드에서 필요하지 않습니다. 실제 파일 또는 설명이 변경된 패키지만 patch 버전을 증가시킵니다.

자동화가 ZIP 내부 버전, ZIP 이름, 다운로드 URL, manifest 버전 및 SHA-256을 함께 만듭니다. manifest의 version만 직접 수정하지 마십시오. 기존 불일치는 다음 자동 실행에서 일치하는 새 패키지로 복구합니다.

일반 업로드는 자동 patch입니다. Actions에서 patch와 package_id를 지정해 수동 실행해도 파일 변경이 없으면 다시 버전을 올리지 않습니다. 업로드 후 수동 patch를 눌러 버전이 두 번 올라가는 문제를 방지합니다. major/minor 예외 배포에는 package_id를 반드시 지정합니다. RCKStudio는 `rck.rckstudio`이며 `rck.studio` 별칭도 지원합니다. 지정한 패키지 외의 변경분은 별도의 일반 업로드 배포에서 처리합니다.

Release 업로드가 성공한 뒤에 저장소의 package.json 버전과 manifest 버전을 함께 반영합니다. 미리 저장소 버전만 올리지 않습니다. 같은 파일을 의도적으로 새 버전으로 재배포하는 CLI 작업에는 명시적인 `--force`가 필요합니다.

기존 package.json에 초기 버전이 남아 있는 경우에도 새 Release를 만들지 않고 현재 manifest의 배포 버전으로 기록을 맞춥니다. 버전이 같아 보이지 않아 생기는 혼동을 방지합니다.

매니저의 수동 설치 버전 비교를 위해 최근 manifest Git 기록과 신규 배포의 파일 해시를 `versions[]`에 보존합니다. 기존 Git 기록의 해시도 최대 100개 manifest 커밋에서 읽으며, 패키지별 최근 30개 비교 기록을 유지합니다. 파일 변경이 없으면 기록만 보완하고 패치 버전은 증가하지 않습니다. DLL 파일 버전과 자동 배포의 패키지 버전은 화면에서 별도로 표시합니다.

eCatalog의 `type`은 `ecatalog`, 목적지는 `ecatalog/<패키지 ID>/<파일>.vcmx`, `restartRequired`는 false로 지정합니다. eCatalog가 VC 실행 폴더에 파일을 쓰는 패키지는 거절합니다.

Manager 본체는 `rck.addon-manager`입니다. `name`은 `RCK Addon Manager`, 파일은 `Plugin.RCKAddonManager.dll`, 목적지는 `vcRoot/Plugin.RCKAddonManager.dll`, `systemPackage`는 true입니다. 사용자 PC의 Bootstrap은 이 패키지를 받아 사용자 캐시에서 로드합니다. 본체 DLL의 AssemblyVersion을 매번 수정할 필요가 없습니다.

Contributor 목록의 이름은 업로드 권한이 아닙니다. 저장소 collaborator의 write/maintain/admin 권한으로 업로드 대상을 제한합니다. 일반 사용자의 공개 제출 자동화는 사용하지 않습니다.
