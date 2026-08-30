# AGENTS.md

## Project overview

이 프로젝트는 Python과 pywebview를 사용하는 데스크톱 애플리케이션이다.

제품 요구사항은 `REQUIREMENTS.md`를 따른다.
설계 및 주요 기술 결정은 `ARCHITECTURE.md`를 따른다.
설치, 실행 및 배포 방법은 `README.md`를 따른다.

## Architecture

애플리케이션은 다음 영역으로 분리한다.

- Python: 시스템 접근, 파일 처리, 데이터 저장 및 비즈니스 로직
- JavaScript: 화면 상태, 사용자 입력 및 UI 렌더링
- pywebview bridge: Python과 JavaScript 사이의 명시적인 통신

기본 통신 방식은 pywebview의 JS API bridge다.

- JavaScript는 `window.pywebview.api`를 통해 Python API를 호출한다.
- Python은 필요한 경우에만 `window.evaluate_js()` 또는
  `window.run_js()`를 사용한다.
- 별도의 HTTP API 서버는 요구사항에 명시된 경우에만 추가한다.
- Python 비즈니스 로직이 pywebview에 직접 의존하지 않게 한다.

## Repository map

- `src/main.py`: 애플리케이션 진입점과 pywebview 초기화
- `src/api/`: JavaScript에 노출되는 bridge API
- `src/services/`: 비즈니스 로직
- `src/models/`: 내부 데이터 모델
- `src/storage/`: 파일 및 데이터 저장 처리
- `frontend/`: HTML, CSS, JavaScript 소스
- `tests/`: Python 자동화 테스트
- `scripts/`: 빌드 및 검증 스크립트
- `assets/`: 아이콘 및 정적 리소스
- `docs/`: 상세 설계와 운영 문서

실제 저장소 구조가 다르면 이 목록을 실제 구조에 맞게 수정한다.

## Layer responsibilities

### Entry point

`src/main.py`는 다음 역할만 담당한다.

- 설정 로드
- 서비스와 API 객체 생성
- `webview.create_window()` 호출
- 이벤트 연결
- `webview.start()` 호출

비즈니스 로직을 `main.py`에 구현하지 않는다.

### Bridge API

`src/api/`는 JavaScript에서 호출할 수 있는 얇은 인터페이스다.

Bridge API는 다음 역할만 담당한다.

- 입력값 검증
- 서비스 계층 호출
- 결과를 직렬화 가능한 형태로 변환
- 예외를 안정적인 오류 응답으로 변환

파일 처리, 데이터베이스 접근 및 복잡한 계산을 API 메서드에
직접 구현하지 않는다.

### Services

`src/services/`에는 UI 및 pywebview와 독립적인 비즈니스 로직을 둔다.

서비스는 가능한 한 다음 항목에 직접 의존하지 않는다.

- `webview.Window`
- DOM 구조
- JavaScript 함수 이름
- 운영체제별 UI 객체

서비스 계층은 pywebview 없이 단위 테스트할 수 있어야 한다.

### Frontend

프런트엔드는 다음만 담당한다.

- 화면 렌더링
- 사용자 입력
- UI 상태 관리
- bridge API 호출
- 성공, 진행 중, 빈 상태 및 오류 표시

Python에서 HTML 문자열을 조합해 UI를 만들지 않는다.

## Python–JavaScript bridge contract

JavaScript에 노출되는 API는 public API로 취급한다.

- 공개할 메서드만 bridge 객체에 둔다.
- 내부 함수는 bridge 객체에 추가하지 않는다.
- 메서드 이름과 인자 형식을 임의로 변경하지 않는다.
- API 변경 시 Python과 JavaScript 호출부를 함께 수정한다.
- 반환값은 JSON으로 표현 가능한 기본 자료형을 사용한다.
- Python 객체, 파일 핸들 및 Window 객체를 직접 반환하지 않는다.
- 오류 형식은 모든 API에서 일관되게 유지한다.

기본 반환 형식:

```python
{
    "ok": True,
    "data": {}
}