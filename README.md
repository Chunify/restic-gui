# restic-gui

Windows용 restic 데스크톱 GUI입니다.

사용 전에 Windows에 restic을 설치해야 합니다. 설치되지 않은 상태에서 앱을
실행하면 설치 안내를 표시하고 공식 Windows 설치 페이지를 엽니다.

## 실행

```powershell
py -m pip install -r requirements.txt
py -m src.main
```

저장소와 정책 정보는 `data/restic-gui.db`에, 무작위 키 파일은
`data/keys/`에 생성됩니다. 백업 실행 스크립트는 `data/backup-scripts/`에,
restic 실행 로그는 `data/logs/YY-MM-DD.log`에 누적됩니다.

## Windows 실행 파일 빌드

PowerShell에서 다음 명령을 실행합니다.

```powershell
.\scripts\build.ps1
```

빌드 의존성을 이미 설치했다면 `.\scripts\build.ps1 -SkipInstall`을 사용할 수
있습니다. 결과물은 `dist/restic-gui.exe` 단일 파일입니다. restic은 실행 파일에
포함되지 않으며, Windows PATH에서 설치된 `restic.exe`를 찾습니다.

## 주요 기능

- restic 저장소 생성 및 실제 저장소/키 삭제
- 저장소별 스냅샷 조회와 `restic ls` 결과 파일 저장
- 백업 정책과 Forget 정책의 독립 관리
- 백업 정책별 Windows 실행 스크립트 생성 및 수동 갱신
- 날짜별 restic 로그 조회 및 삭제
- Windows 작업 스케줄러 기반 자동 백업 설정
- 마스터 스크립트를 통한 전체 정책 수동 백업

## 테스트

```powershell
py -m unittest discover -s tests
```
