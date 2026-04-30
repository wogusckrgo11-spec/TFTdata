# TFTdata — MetaTFT 통계 자동 수집 저장소

MetaTFT(`metatft.com`)의 랭크 통계 데이터를 매일 한국시간(KST) 오전 6시에 자동으로 수집해 저장하는 파이프라인.

- **GitHub 저장소**: `https://github.com/wogusckrgo11-spec/TFTdata`
- **수집 주기**: 매일 06:00 KST (= 전날 21:00 UTC, GitHub Actions)
- **수집 카테고리**: units / comps / items (normal · artifact · emblem · radiant · trait)

상세 내용은 아래 문서를 참조한다.

| 문서 | 내용 |
|---|---|
| [DATA_SPEC.md](DATA_SPEC.md) | 수집 조건 이력, 디렉터리 구조, 카테고리별 스키마, 인코딩 |
| [PATCH_SPEC.md](PATCH_SPEC.md) | 패치별 변경 내용, 메타 영향, 패치 전환 방법 |

---

## 스크래퍼 동작 방식

`scraper.py`는 세 함수(`scrape_units`, `scrape_comps`, `scrape_items`)로 구성되며 순차 실행된다.

### 필터 적용

MetaTFT `.StatsFilterContainer`의 4개 드롭다운을 고정값으로 세팅한다.

| idx | 필터 | 값 | 방식 |
|---|---|---|---|
| 0 | Queue | `Ranked` | 단일 선택 |
| 1 | Patch | `17.2` | 단일 선택 |
| 2 | Time | `Last 3 Days` | 단일 선택 |
| 3 | Rank | `Master+` | 멀티 선택 + Apply |

랭크 필터는 `li` 요소의 CSS 클래스 `Active` 포함 여부로 선택 상태를 판별하고 `img[alt]`로 티어명을 추출한다. `Master / Grandmaster / Challenger`만 활성화 후 Apply 클릭.

### 컴프 가상 스크롤

`/comps`는 IntersectionObserver 기반 지연 렌더링이다. `scrollBy(0, 800)`을 반복하며 `.CompRowPlaceholder` 수가 0이 될 때까지 최대 60회 스크롤 후 파싱한다.

### 아이템 타입 칩 전환

`/items`에서 5개 타입 칩을 하나씩 선택 전환하며 테이블을 파싱한다. 뷰포트를 10,000px로 설정해 전체 행을 한 번에 hydrate한다.

---

## 자동화 파이프라인

```
매일 21:00 UTC (= KST 06:00)
  → ubuntu-latest 러너 기동
  → Python 3.12 + Playwright Chromium 설치
  → python scraper.py 실행
  → data/ 변경사항 커밋 & 푸시
```

커밋 메시지: `data: YYYY-MM-DD 수집 결과 (Master+, 17.2)`  
수동 트리거: GitHub 저장소 Actions 탭 → `workflow_dispatch`

---

## 로컬 실행

```bash
pip install -r requirements.txt
playwright install chromium

python scraper.py
```

실패 시 `logs/` 폴더에 스크린샷 및 HTML 저장 (`gitignore` 처리).
