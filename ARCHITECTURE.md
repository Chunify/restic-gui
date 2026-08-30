# Architecture

애플리케이션은 pywebview 진입점, JSON 직렬화 가능한 bridge API, UI와 독립적인
서비스, SQLite 저장소, 정적 프런트엔드로 분리한다. `src/main.py`는 객체 조립과
파일 선택 대화상자 연결만 담당한다.

`RepositoryStore`가 Repository, BackupPolicy, ForgetPolicy 영속화를 담당한다.
Repository/BackupPolicy/ForgetPolicy/Snapshot 서비스는 각 도메인 동작을 맡고,
Log/Configuration/Script 서비스는 로그 파일, Windows 작업 스케줄러 설정,
정책별 및 마스터 실행 스크립트를 관리한다. JavaScript는 `AppApi` 이외의 Python
구현에 의존하지 않는다.

모든 bridge 응답은 성공 시 `{ "ok": true, "data": {} }`, 실패 시
`{ "ok": false, "error": { "message": "..." } }` 형식을 사용한다.
