# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

MetaTFT(`metatft.com`)의 TFT 랭크 통계 데이터를 Playwright로 스크래핑해 날짜별 스냅샷으로 저장하는 파이프라인. GitHub Actions가 매일 KST 06:00(UTC 21:00)에 자동 실행한다.

## 로컬 실행

```bash
pip install -r requirements.txt
playwright install chromium

python scraper.py                        # 전체 수집 (units → comps → items 순)
python translate_to_ko.py YYYY-MM-DD     # 특정 날짜 영→한 변환
```

수집 결과는 `data/`에 저장되며, 실패 시 `logs/`에 스크린샷·HTML이 남는다(`logs/`는 `.gitignore`).

## 아키텍처

### 수집 파이프라인 (`scraper.py`)

- `scrape_units()` → `scrape_comps()` → `scrape_items()` 순서로 순차 실행
- 각 함수는 독립적인 Playwright 브라우저 세션을 열고 닫는다
- 세 함수 모두 `apply_stats_filters(page, tag)` 로 동일한 필터(Queue/Patch/Time/Rank)를 고정한 뒤 파싱
- **필터 상수**(`FILTER_PATCH` 등)는 파일 상단에 모여 있음 — 패치 전환 시 여기만 수정

수집 특이사항:
- `/comps`는 IntersectionObserver 기반 가상 스크롤 — `scrollBy(0, 800)`을 최대 60회 반복해 `.CompRowPlaceholder`가 0이 될 때까지 hydrate
- `/items`는 10,000px 뷰포트로 전체 행을 한 번에 hydrate, 5개 타입 칩을 JavaScript로 순차 전환

### 한국어 변환 파이프라인 (`translate_to_ko.py`)

- Community Dragon `ko_kr.json` + `en_us.json` (TFTSet17)에서 영문→한글 매핑 구축
- 딕셔너리는 `data_ko/_dict/ko_kr_mappings.json`에 캐시 (이후 재실행 시 재다운로드 없음)
- 원본 24MB JSON 2개(`ko_kr.json`, `en_us.json`)는 `.gitignore` 처리 — 첫 실행 시 자동 다운로드
- `data/` 원본을 수정하지 않고 `data_ko/`에 별도 복사본 생성
- 컴프 이름은 특성+유닛 단어를 greedy 최장 매칭으로 변환 (`translate_name()`)

### 캐시 갱신 시점

`data_ko/_dict/`의 3개 파일을 모두 삭제 후 재실행:
- 신규 챔피언/아이템/특성이 추가된 패치
- 한글 표기 변경
- Set 전환 (코드의 `TFTSet17` mutator도 함께 수정 필요)

밸런스 수치 변경(코스트·스탯·스킬 수치)은 캐시 갱신 불필요 — 매핑은 이름만 저장.

### 데이터 구조

```
data/                      # 영문 원본 (GitHub Actions가 자동 커밋)
├── units/YYYY-MM-DD.{csv,json}
├── comps/YYYY-MM-DD.{csv,json}
└── items/{normal,artifact,radiant,emblem,trait}/YYYY-MM-DD.{csv,json}

data_ko/                   # 한국어 번역본 (수동 실행)
├── _dict/                 # ko_kr_mappings.json (캐시), unmapped_*.json
└── (동일 구조)
```

CSV는 `utf-8-sig`(BOM), JSON은 `utf-8`(`ensure_ascii=False`).

## 패치 전환 방법

1. `scraper.py` 상단의 `FILTER_PATCH` 값을 새 패치명으로 변경 (`"17.2b"` → `"17.3"` 등)
2. `PATCH_SPEC.md`에 새 패치 항목 추가, 이전 패치 종료일 기록
3. `DATA_SPEC.md` 수집 조건 이력 테이블 및 누적 기간 테이블 갱신
4. GitHub Actions 워크플로우의 커밋 메시지 패치명도 동기화

## 참고 문서

| 문서 | 내용 |
|---|---|
| `DATA_SPEC.md` | 수집 조건 이력, 컬럼 스키마, 파일 인코딩 |
| `PATCH_SPEC.md` | 패치별 변경 내용, 메타 영향 메모 |

> 2026-04-16~18(17.1), 2026-04-19~29(17.1b Platinum+), 2026-04-30(17.2 Master+), 2026-05-01~(17.2b Master+) 네 구간은 수집 조건이 달라 수치를 직접 비교할 수 없다.
