Rendering Optimization eCatalog 배포

- 개발: 이준용 연구원
- VC 호환: 5.1
- 패키지 ID: rck.ecatalog.rendering-optimization
- 최초 버전: 1.0.0
- 실제 포함 파일: Rendering Optimization.vcmx, Rendering_Optimization_사용안내.pdf
- 원본 VCMX/PDF 내용을 변경하지 않고 VCMX 파일명의 `(1)`만 제거했습니다.
- 사용자가 제공한 설명 전체를 패키지 설명에 저장했습니다. 설명에 언급된 평치구역+_최적화.vcmx는 이번에 제공되지 않아 배포 파일에 포함하지 않았습니다.

설치 경로

매니저에 설정한 eCatalog 경로 아래 AddonManager 폴더에 두 파일을 설치합니다.
예: 문서\Visual Components\5.1\My Models\AddonManager\Rendering Optimization.vcmx
폴더가 없으면 생성하고, 있으면 그대로 사용합니다. 다른 패키지 파일은 유지합니다.
처음 사용하는 사용자의 기본 eCatalog 경로는 My Models입니다. 기존 사용자 설정 경로는 유지하므로 필요하면 매니저 설정에서 실제 VC eCatalog 소스 폴더를 선택합니다.

사용 안내

매니저 1.10.2부터 eCatalog 목록의 PDF 열기와 상세 화면의 사용 안내 PDF 열기로 안내서를 엽니다.
설치 후에는 로컬 PDF를 열며, 설치 전에는 GitHub에 등록된 PDF를 HTTPS로 엽니다.
상세 화면과 eCatalog 목록에서 개발자를 표시하며 개발자 이름으로 검색할 수도 있습니다.

VC 재시작

eCatalog만 설치·업데이트·삭제할 때는 VC를 종료하거나 재시작하지 않습니다.
VC eCatalog 목록이 갱신되지 않으면 해당 로컬 소스에서 Refresh(새로고침)를 실행합니다.
이미 레이아웃에 놓은 컴포넌트는 파일을 다운로드해도 자동 교체되지 않습니다. 제공된 설명에 따라 기존 컴포넌트를 Unoptimize한 다음 제거하고 새 컴포넌트를 배치합니다.
매니저 본체 업데이트와 애드온 DLL 업데이트에는 별도 업데이트 절차가 적용됩니다.

다음 eCatalog 업데이트

GitHub packages/RenderingOptimization 폴더에서 새 VCMX/PDF를 교체하고 main에 반영하면 자동 patch 배포가 실행됩니다.
개발자·설명·PDF 연결 정보를 수정하려면 같은 폴더의 package.json을 편집합니다.
package.json의 version이나 manifest.json을 직접 올리지 않습니다.
