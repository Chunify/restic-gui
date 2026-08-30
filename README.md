# restic-gui

Windows용 restic 데스크톱 GUI입니다.

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
있습니다. 스크립트는 최신 Windows x64용 restic을 함께 포함하며, 결과물은
`dist/restic-gui.exe` 단일 파일입니다. 이 파일만 복사해 실행할 수 있고 처음
실행할 때 실행 파일과 같은 위치에 `data/` 폴더와 내장 restic이 생성됩니다.
특정 버전을 포함하려면 `-ResticVersion 0.18.0`처럼 지정할 수 있습니다.

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
