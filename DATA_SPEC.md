# 데이터 명세서

## 수집 조건 이력

데이터 구간별 패치 버전 및 필터 조건이 다르므로 분석 시 반드시 구분해야 한다.

| 기간 | Queue | Patch | Time | Rank | 비고 |
|---|---|---|---|---|---|
| 2026-04-16 ~ 2026-04-18 | 불명 | 17.1 | 불명 | 불명 | 시즌 초반, MetaTFT 자동 기본 필터 추정 |
| 2026-04-19 ~ 2026-04-29 | Ranked | 17.1b | Last 3 Days | **Platinum+** | 외부 스크래퍼 수집 |
| 2026-04-30 ~ 2026-04-30 | Ranked | 17.2 | Last 3 Days | **Master+** | 본 파이프라인 자동 수집 |
| 2026-05-01 ~ 2026-05-13 | Ranked | 17.2b | Last 3 Days | **Master+** | 본 파이프라인 자동 수집 |
| 2026-05-14 ~ 2026-05-28 | Ranked | 17.3 | Last 3 Days | **Master+** | 본 파이프라인 자동 수집 |
| 2026-05-29 ~ | Ranked | 17.4 | Last 3 Days | **Master+** | 본 파이프라인 자동 수집 |

> **Platinum+**: Platinum / Emerald / Diamond / Master / Grandmaster / Challenger 전체 포함  
> **Master+**: Master / Grandmaster / Challenger 만 포함  
> 네 구간은 패치 버전 또는 모집단이 달라 수치를 직접 비교할 수 없다.  
> 특히 2026-04-16 ~ 2026-04-18 구간은 수집 필터가 불명확하므로 분석에서 제외하거나 참고용으로만 사용할 것.  
> 17.2와 17.2b는 동일한 Master+ 모집단이지만 패치 밸런스 변경이 있으므로 구간을 구분해 해석할 것.

---

## 디렉터리 구조

```
data/
├── units/
│   ├── YYYY-MM-DD.csv
│   └── YYYY-MM-DD.json
├── comps/
│   ├── YYYY-MM-DD.csv
│   └── YYYY-MM-DD.json
└── items/
    ├── normal/
    │   ├── YYYY-MM-DD.csv
    │   └── YYYY-MM-DD.json
    ├── artifact/
    ├── emblem/
    ├── radiant/
    └── trait/
```

파일명은 KST 기준 수집일. 하루 한 스냅샷.

---

## 누적 기간

| 카테고리 | 시작일 (17.1 불명) | 17.1b 시작일 | 17.2 시작일 | 17.2b 시작일 | 17.3 시작일 | 17.4 시작일 |
|---|---|---|---|---|---|---|
| units | 2026-04-16 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| comps | 2026-04-16 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| items/normal | 2026-04-17 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| items/artifact | 2026-04-17 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| items/emblem | 2026-04-17 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| items/radiant | 2026-04-17 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |
| items/trait | 2026-04-17 | 2026-04-19 | 2026-04-30 | 2026-05-01 | 2026-05-14 | 2026-05-29 |

---

## 스키마

### units

파일 경로: `data/units/YYYY-MM-DD.{csv,json}`

| 컬럼 | 타입 | 예시 | 설명 |
|---|---|---|---|
| `Unit` | string | `Jhin` | 유닛 이름 |
| `Cost` | string | `S`, `4` | 코스트 (1~5 또는 S) |
| `Avg Place` | float | `3.86` | 평균 순위 |
| `Top 4%` | percent | `22.0%` | 상위 4위 이내 비율 |
| `Games` | string | `1,325,573` | 샘플 게임 수 (콤마 포함 문자열) |
| `Win%` | percent | `17.6%` | 1위 비율 |

JSON 최상위 구조:
```json
{ "date": "YYYY-MM-DD", "count": N, "units": [ {...} ] }
```

---

### comps

파일 경로: `data/comps/YYYY-MM-DD.{csv,json}`

| 컬럼 | 타입 | 예시 | 설명 |
|---|---|---|---|
| `Tier` | string | `S` | 메타 티어 (S/A/B/C) |
| `Name` | string | `Voyager Viktor` | 컴프 이름 |
| `Level` | int | `7` | 권장 레벨 |
| `Difficulty` | string | `Medium` | 난이도 (Easy/Medium/Hard) |
| `Avg Place` | float | `3.90` | 평균 순위 |
| `Pick Rate` | float | `0.49` | 픽률 |
| `Win Rate` | percent | `12.6%` | 1위 비율 |
| `Top 4 Rate` | percent | `62.3%` | 상위 4위 비율 |
| `Units` | string | `Viktor \| Illaoi \| ...` | 유닛 목록 (파이프 구분) |
| `UnitDetails` | string | `Viktor★ (아이템) \| ...` | 유닛별 3성 여부 + 아이템 (파이프 구분) |

`UnitDetails` 형식: `유닛명[★] [(아이템1, 아이템2, ...)]`  
예: `Viktor★ (Drone Uplink, Jeweled Gauntlet)` / `Nami` (아이템 없는 경우 괄호 생략)

JSON 최상위 구조:
```json
{
  "date": "YYYY-MM-DD",
  "count": N,
  "comps": [
    {
      "Tier": "S",
      "Name": "...",
      "Level": 7,
      "Difficulty": "Medium",
      "Avg Place": "3.90",
      "Pick Rate": "0.49",
      "Win Rate": "12.6%",
      "Top 4 Rate": "62.3%",
      "Units": ["Viktor", "Illaoi", ...],
      "UnitDetails": [
        { "name": "Viktor", "three_star": true, "items": ["Drone Uplink", ...] },
        ...
      ]
    }
  ]
}
```

---

### items

파일 경로: `data/items/{type}/YYYY-MM-DD.{csv,json}`

타입 목록: `normal` / `artifact` / `emblem` / `radiant` / `trait`

| 컬럼 | 타입 | 예시 | 설명 |
|---|---|---|---|
| `Item` | string | `Giant Slayer` | 아이템 이름 |
| `Tier` | string | `S` | 아이템 티어 (S/A/B/C) |
| `Avg Place` | float | `4.21` | 평균 순위 |
| `Place Change` | float | `-0.36` | 전일 대비 순위 변화 |
| `Win Rate` | percent | `13.8%` | 1위 비율 |
| `Games` | int | `3441963` | 샘플 게임 수 |
| `Frequency` | percent | `45.0%` | 사용 빈도 |
| `PopularUnits` | string | `Urgot \| Vex \| ...` | 자주 사용하는 유닛 (파이프 구분) |

JSON 최상위 구조:
```json
{ "date": "YYYY-MM-DD", "type": "Normal Item", "count": N, "items": [ {...} ] }
```

---

## 파일 인코딩

| 포맷 | 인코딩 | 이유 |
|---|---|---|
| CSV | UTF-8-BOM (`utf-8-sig`) | Excel에서 한글 깨짐 방지 |
| JSON | UTF-8 (`ensure_ascii=False`) | 유니코드 문자 그대로 저장 |
