"""
MetaTFT 스크래퍼
- 유닛 통계(/units) + 컴프 통계(/comps) + 아이템 통계(/items) 데이터 수집
- JSON, CSV 형식으로 저장
"""

import json
import csv
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

# 설정
UNITS_URL = "https://www.metatft.com/units"
COMPS_URL = "https://www.metatft.com/comps"
ITEMS_URL = "https://www.metatft.com/items"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

# 서브디렉터리 경로 상수
UNITS_DIR  = os.path.join(DATA_DIR, "units")
COMPS_DIR  = os.path.join(DATA_DIR, "comps")
ITEMS_DIRS = {slug: os.path.join(DATA_DIR, "items", slug) for _, slug in [
    ("Normal Item", "normal"), ("Artifact Item", "artifact"),
    ("Radiant Item", "radiant"), ("Emblem", "emblem"), ("Trait Item", "trait"),
]}

# /items 페이지 Type 필터 — (img alt 값, 파일명 슬러그)
ITEM_TYPES = [
    ("Normal Item", "normal"),
    ("Artifact Item", "artifact"),
    ("Radiant Item", "radiant"),
    ("Emblem", "emblem"),
    ("Trait Item", "trait"),
]

# 수집 필터 — 사용자가 직접 수정할 때까지 고정.
FILTER_QUEUE = "Ranked"
FILTER_PATCH = "17.2"
FILTER_TIME = "Last 3 Days"
FILTER_RANK = "Master+"  # 검증/로그용 레이블
# 랭크 드롭다운은 멀티 선택 방식 — 아래 티어를 모두 선택 후 Apply
FILTER_RANK_TIERS = ["Master", "Grandmaster", "Challenger"]

# 공통 Playwright launch args (CI 환경 호환)
BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

# 파일명/로그용 기준 타임존 (KST)
# GitHub Actions는 UTC에서 실행되므로 datetime.now()를 그냥 쓰면
# 한국시간 자정~오전 9시에 실행된 작업이 전날짜 파일명으로 저장되어 덮어쓰기 발생
KST = ZoneInfo("Asia/Seoul")


def today_kst():
    """한국시간(KST) 기준 오늘 날짜 문자열 (YYYY-MM-DD)"""
    return datetime.now(KST).strftime("%Y-%m-%d")


def _apply_rank_filter(page, tag: str, today: str, trigger, current_text: str):
    """랭크 필터 멀티 선택 처리 (Master + Grandmaster + Challenger → Apply).

    선택 상태는 li 클래스의 'Active' 포함 여부로 판별.
    티어명은 li 내부 img[alt]로 추출 (텍스트노드가 수치와 붙어있어 분리가 어려움).
    """
    current_lower = current_text.lower()
    # 필터 바에 목표 티어 중 하나라도 있고 원치 않는 티어가 없으면 스킵
    target_set = {t.lower() for t in FILTER_RANK_TIERS}
    already_has_target = any(t in current_lower for t in target_set)
    has_unwanted = any(t in current_lower for t in ["platinum", "emerald", "diamond",
                                                     "gold", "silver", "bronze", "iron"])
    if already_has_target and not has_unwanted:
        print(f"  [{tag}] rank: 이미 '{current_text}' — 스킵")
        return

    trigger.click()
    menu = page.locator(".StatsFilterMenu")
    try:
        menu.wait_for(state="visible", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(400)

    # li 요소를 평가: img alt로 티어명 추출, 'Active' 클래스로 선택 상태 판별
    option_info = page.evaluate("""() => {
        const menu = document.querySelector('.StatsFilterMenu');
        if (!menu) return [];
        return Array.from(menu.querySelectorAll('li')).map(li => ({
            tier: li.querySelector('img')?.alt || '',
            active: li.className.includes('Active'),
        }));
    }""")

    changed = []
    for info in option_info:
        tier = info["tier"]
        is_active = info["active"]
        if not tier:
            continue
        is_target = tier in FILTER_RANK_TIERS
        if is_target and not is_active:
            # 선택 안 됐는데 대상 → 클릭해서 활성화
            img = page.locator(f'.StatsFilterMenu li img[alt="{tier}"]').first
            img.locator("..").click()
            changed.append(f"+{tier}")
            page.wait_for_timeout(150)
        elif not is_target and is_active:
            # 선택됐는데 대상 아님 → 클릭해서 해제
            img = page.locator(f'.StatsFilterMenu li img[alt="{tier}"]').first
            img.locator("..").click()
            changed.append(f"-{tier}")
            page.wait_for_timeout(150)

    # Apply 클릭
    try:
        apply_btn = menu.get_by_text("Apply", exact=True).first
        apply_btn.wait_for(state="visible", timeout=3000)
        apply_btn.click()
    except Exception:
        page.keyboard.press("Escape")

    try:
        menu.wait_for(state="hidden", timeout=3000)
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_timeout(800)

    elements = page.query_selector_all(".StatsFilterContainer .FilterElement")
    result_text = (elements[3].inner_text() or "").strip() if len(elements) > 3 else ""
    print(f"  [{tag}] rank: '{current_text}' → '{result_text}' (변경: {changed or ['없음']})")


def apply_stats_filters(page, tag: str):
    """MetaTFT `.StatsFilterContainer`의 4개 드롭다운을 상수값으로 강제 세팅.

    기본값이 이미 맞는 필터도 명시적으로 클릭해 확정한다. 옵션을 찾지 못하면
    RuntimeError를 던져서 "조용히 잘못된 패치 데이터를 수집하는" 사고를 막는다.

    `tag`: 디버그 스크린샷 파일명 접두사 ("units" / "comps" / "items").
    """
    today = today_kst()
    # (필터 인덱스, 원하는 값, 라벨)
    #  — .StatsFilterContainer 내부 .FilterElement 순서: 큐 / 패치 / 기간 / 티어
    targets = [
        (0, FILTER_QUEUE, "queue"),
        (1, FILTER_PATCH, "patch"),
        (2, FILTER_TIME, "time"),
        (3, FILTER_RANK, "rank"),
    ]

    # 필터 바가 렌더될 때까지 대기
    page.wait_for_selector(".StatsFilterContainer .FilterElement", timeout=15000)

    for idx, value, label in targets:
        # 매 반복마다 새로 쿼리 (클릭 후 DOM이 재렌더될 수 있음)
        elements = page.query_selector_all(".StatsFilterContainer .FilterElement")
        if idx >= len(elements):
            raise RuntimeError(
                f"[{tag}] 필터 요소 부족: index={idx}, 발견된 개수={len(elements)}"
            )
        trigger = elements[idx]
        current_text = (trigger.inner_text() or "").strip()

        # 랭크 필터는 멀티 선택 + Apply 방식으로 별도 처리
        if label == "rank":
            _apply_rank_filter(page, tag, today, trigger, current_text)
            continue

        # 현재값이 이미 목표값을 포함하면 스킵
        if value.lower() in current_text.lower():
            print(f"  [{tag}] {label}: 이미 '{current_text}' — 스킵")
            continue

        trigger.click()
        menu = page.locator(".StatsFilterMenu")
        try:
            menu.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(300)

        candidates = [value]
        option = None
        for cand in candidates:
            loc = menu.get_by_text(cand, exact=True)
            try:
                loc.first.wait_for(state="visible", timeout=2500)
                option = loc.first
                break
            except Exception:
                continue

        if option is None:
            page.screenshot(
                path=os.path.join(LOGS_DIR, f"filter_{tag}_{label}_fail_{today}.png"),
                full_page=True,
            )
            with open(
                os.path.join(LOGS_DIR, f"filter_{tag}_{label}_fail_{today}.html"),
                "w", encoding="utf-8",
            ) as f:
                f.write(page.content())
            raise RuntimeError(
                f"[{tag}] {label} 드롭다운에서 '{value}' 옵션을 찾지 못함"
            )

        option.click()
        try:
            menu.wait_for(state="hidden", timeout=3000)
        except Exception:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        page.wait_for_timeout(300)

    # 전체 적용 후 테이블 재렌더 대기
    page.wait_for_timeout(1500)

    # 검증: 현재 필터 바 텍스트 읽기
    final_texts = [
        (el.inner_text() or "").strip()
        for el in page.query_selector_all(".StatsFilterContainer .FilterElement")
    ]
    expected = [FILTER_QUEUE, FILTER_PATCH, FILTER_TIME, FILTER_RANK]
    for i, exp in enumerate(expected):
        if i >= len(final_texts):
            raise RuntimeError(f"[{tag}] 필터 검증 실패: idx={i} 텍스트 없음")
        actual_lower = final_texts[i].lower()
        # 랭크는 사이트가 "Master+" / "Master,Grandmaster..." 등 다양하게 표시
        # 최소한 FILTER_RANK_TIERS 중 하나라도 포함되면 통과
        if i == 3:
            ok = any(t.lower() in actual_lower for t in FILTER_RANK_TIERS)
        else:
            ok = exp.lower() in actual_lower
        if not ok:
            page.screenshot(
                path=os.path.join(LOGS_DIR, f"filter_{tag}_verify_fail_{today}.png"),
                full_page=True,
            )
            raise RuntimeError(
                f"[{tag}] 필터 검증 실패: idx={i} 기대='{exp}' 실제='{final_texts[i]}'"
            )

    # 성공 스크린샷 & 로그
    page.screenshot(
        path=os.path.join(LOGS_DIR, f"filter_{tag}_{today}.png"),
        full_page=False,
    )
    print(f"  [{tag}] 필터 적용: {FILTER_QUEUE} / {FILTER_PATCH} / {FILTER_TIME} / {FILTER_RANK}")


def scrape_units():
    """MetaTFT에서 유닛 통계 데이터를 스크래핑"""
    today = today_kst()
    print(f"[{today}] MetaTFT 유닛 데이터 수집 시작...")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    units = []

    with sync_playwright() as p:
        # CI 환경(GitHub Actions Ubuntu) 호환을 위한 args 추가
        browser = p.chromium.launch(
            headless=True,
            args=BROWSER_ARGS
        )
        page = browser.new_page()

        try:
            print(f"페이지 로딩 중: {UNITS_URL}")
            page.goto(UNITS_URL, wait_until="domcontentloaded", timeout=60000)

            # SPA 렌더링 대기
            page.wait_for_timeout(10000)

            # 필터 고정 (Ranked / 17.1b / Last 3 Days / Platinum+)
            apply_stats_filters(page, "units")

            # 페이지 스크린샷 (디버깅용)
            screenshot_path = os.path.join(LOGS_DIR, f"units_{today}.png")
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"스크린샷 저장: {screenshot_path}")

            # 페이지 HTML 저장 (디버깅용)
            html_path = os.path.join(LOGS_DIR, f"units_{today}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"HTML 저장: {html_path}")

            # 테이블 행 찾기 - 여러 셀렉터 시도
            selectors = [
                "table tbody tr",
                "[class*='table'] [class*='row']",
                "[class*='unit'] [class*='row']",
                "div[class*='Table'] div[class*='Row']",
            ]

            rows = []
            used_selector = None
            for selector in selectors:
                rows = page.query_selector_all(selector)
                if rows:
                    used_selector = selector
                    print(f"셀렉터 '{selector}'로 {len(rows)}개 행 발견")
                    break

            if not rows:
                print("⚠️ 테이블 행을 찾을 수 없습니다. 스크린샷과 HTML을 확인하세요.")
                # 대체: 모든 텍스트 추출 시도
                all_text = page.inner_text("body")
                text_path = os.path.join(LOGS_DIR, f"text_{today}.txt")
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(all_text)
                print(f"페이지 텍스트 저장: {text_path}")
            else:
                for row in rows:
                    cells = row.query_selector_all("td")
                    if not cells or len(cells) < 3:
                        continue

                    # 셀 텍스트 추출
                    cell_texts = [cell.inner_text().strip() for cell in cells]

                    # 첫 번째 셀에서 유닛 이름 추출
                    unit_name = cell_texts[0] if cell_texts[0] else ""
                    if not unit_name:
                        continue

                    unit_data = {
                        "Unit": unit_name,
                    }

                    # 나머지 셀 데이터 매핑
                    headers = ["Cost", "Avg Place", "Top 4%", "Win%"]
                    for i, header in enumerate(headers):
                        idx = i + 1
                        if idx < len(cell_texts):
                            value = cell_texts[idx]
                            # Win% 필드: "2,530 23.8%" → Games와 Win% 분리
                            if header == "Win%":
                                parts = value.rsplit(" ", 1)
                                if len(parts) == 2:
                                    unit_data["Games"] = parts[0]
                                    unit_data["Win%"] = parts[1]
                                else:
                                    unit_data["Win%"] = value
                            else:
                                unit_data[header] = value

                    units.append(unit_data)

        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            # 에러 시에도 스크린샷 저장 시도
            try:
                page.screenshot(path=os.path.join(LOGS_DIR, f"error_{today}.png"))
            except:
                pass
        finally:
            browser.close()

    # 데이터 저장
    if units:
        os.makedirs(UNITS_DIR, exist_ok=True)
        # JSON 저장
        json_data = {
            "date": today,
            "count": len(units),
            "units": units
        }
        json_path = os.path.join(UNITS_DIR, f"{today}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 저장 완료: {json_path} ({len(units)}개 유닛)")

        # CSV 저장 (BOM 포함)
        csv_path = os.path.join(UNITS_DIR, f"{today}.csv")
        if units:
            fieldnames = list(units[0].keys())
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(units)
            print(f"✅ CSV 저장 완료: {csv_path}")
    else:
        print("⚠️ 수집된 유닛 데이터가 없습니다.")

    return units

def scrape_comps():
    """MetaTFT에서 컴프(team comp) 통계 데이터를 스크래핑"""
    today = today_kst()
    print(f"\n[{today}] MetaTFT 컴프 데이터 수집 시작...")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    comps = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        page = browser.new_page()

        try:
            print(f"페이지 로딩 중: {COMPS_URL}")
            page.goto(COMPS_URL, wait_until="domcontentloaded", timeout=60000)

            # SPA 렌더링 대기
            page.wait_for_timeout(10000)

            # 필터 고정 — 스크롤 hydrate 전에 적용해야 올바른 데이터가 렌더됨
            apply_stats_filters(page, "comps")

            # 컴프 리스트는 가상 스크롤/지연 렌더링을 사용하므로
            # 스크롤로 모든 placeholder를 실제 데이터로 hydrate 시킨 뒤 파싱해야 함
            print("스크롤로 모든 컴프 hydrate 진행...")
            last_state = None
            stable_iters = 0
            for i in range(60):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(700)
                state = page.evaluate(
                    "() => ({"
                    "total: document.querySelectorAll('.CompRow').length,"
                    "placeholder: document.querySelectorAll('.CompRowPlaceholder').length"
                    "})"
                )
                if state == last_state:
                    stable_iters += 1
                else:
                    stable_iters = 0
                    last_state = state
                # placeholder가 모두 해소되었고 상태가 안정되면 종료
                if state.get("placeholder", 1) == 0 and stable_iters >= 2:
                    print(f"  모든 placeholder 해소 (총 {state['total']}개, 스크롤 {i+1}회)")
                    break
                # 페이지 맨 아래에서 5회 변화 없으면 종료 (안전장치)
                if stable_iters >= 5:
                    print(f"  스크롤 {i+1}회 후 안정화 (total={state['total']}, placeholder={state['placeholder']})")
                    break

            # 맨 위로 돌아가서 파싱 (hydrate된 상태 유지됨)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)

            # 디버깅용 스크린샷 & HTML
            page.screenshot(
                path=os.path.join(LOGS_DIR, f"comps_{today}.png"),
                full_page=True,
            )
            with open(os.path.join(LOGS_DIR, f"comps_{today}.html"), "w", encoding="utf-8") as f:
                f.write(page.content())

            # CompRow 요소 찾기 (placeholder 제외)
            all_rows = page.query_selector_all(".CompRow")
            rows = [r for r in all_rows if not r.query_selector(".CompRowPlaceholder")]
            placeholder_count = len(all_rows) - len(rows)
            print(f"셀렉터 '.CompRow'로 {len(all_rows)}개 발견 "
                  f"(실제 데이터: {len(rows)}, 미로드: {placeholder_count})")

            for row in rows:
                # Tier: 클래스명에서 TierX 추출 (fallback은 badge 텍스트)
                class_attr = row.get_attribute("class") or ""
                tier_match = re.search(r"Tier([A-Z])", class_attr)
                tier = tier_match.group(1) if tier_match else ""
                if not tier:
                    badge = row.query_selector(".CompRowTierBadge")
                    tier = badge.inner_text().strip() if badge else ""

                # 컴프 이름
                title_el = row.query_selector(".Comp_Title")
                name = title_el.inner_text().strip() if title_el else ""

                # 태그 (lvl, 난이도)
                tag_els = row.query_selector_all(".CompRowTag")
                tags = [t.inner_text().strip() for t in tag_els]
                level = ""
                difficulty = ""
                for tag in tags:
                    if tag.lower().startswith("lvl"):
                        level = tag.replace("lvl", "").strip()
                    elif tag.lower() in ("easy", "medium", "hard"):
                        difficulty = tag

                # 유닛 상세 파싱: 이미지 src 경로로 유닛/아이템/3성 구분
                # - /champions/ → 유닛 아이콘
                # - /items/    → 아이템 아이콘
                # - /tiers/    → 3성 표시 배지 (다음에 등장하는 유닛이 3성)
                units = []
                unit_blocks = []  # 상세 블록 (이름, 3성 여부, 아이템 리스트)
                all_imgs = row.query_selector_all(".CompUnitStatsContainer img")
                pending_three_star = False
                current_unit = None
                for img in all_imgs:
                    src = img.get_attribute("src") or ""
                    alt = (img.get_attribute("alt") or "").strip()
                    if "/champions/" in src:
                        # 새 유닛 블록 시작
                        current_unit = {
                            "name": alt,
                            "three_star": pending_three_star,
                            "items": [],
                        }
                        unit_blocks.append(current_unit)
                        if alt:
                            units.append(alt)
                        pending_three_star = False
                    elif "/items/" in src:
                        if current_unit is not None and alt:
                            current_unit["items"].append(alt)
                    elif "/tiers/" in src:
                        # 다음에 나오는 유닛이 3성 추천
                        pending_three_star = True

                # 통계: Comp_Stats_Row (중복 있으므로 dedupe)
                stats_rows = row.query_selector_all(".Comp_Stats_Row")
                stats = {}
                for sr in stats_rows:
                    text = sr.inner_text().strip()
                    parts = text.split("\n")
                    if len(parts) >= 2:
                        label = parts[0].strip()
                        value = parts[1].strip()
                        if label and label not in stats:
                            stats[label] = value

                comp_data = {
                    "Tier": tier,
                    "Name": name,
                    "Level": level,
                    "Difficulty": difficulty,
                    "Avg Place": stats.get("Avg Place", ""),
                    "Pick Rate": stats.get("Pick Rate", ""),
                    "Win Rate": stats.get("Win Rate", ""),
                    "Top 4 Rate": stats.get("Top 4 Rate", ""),
                    "Units": units,
                    "UnitDetails": unit_blocks,  # 유닛별 이름/3성/아이템 상세
                }
                comps.append(comp_data)

        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            try:
                page.screenshot(path=os.path.join(LOGS_DIR, f"comps_error_{today}.png"))
            except:
                pass
        finally:
            browser.close()

    # 데이터 저장
    if comps:
        os.makedirs(COMPS_DIR, exist_ok=True)
        # JSON 저장
        json_data = {
            "date": today,
            "count": len(comps),
            "comps": comps,
        }
        json_path = os.path.join(COMPS_DIR, f"{today}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 저장 완료: {json_path} ({len(comps)}개 컴프)")

        # CSV 저장 (Units, UnitDetails를 텍스트로 직렬화)
        csv_path = os.path.join(COMPS_DIR, f"{today}.csv")
        fieldnames = ["Tier", "Name", "Level", "Difficulty",
                      "Avg Place", "Pick Rate", "Win Rate", "Top 4 Rate",
                      "Units", "UnitDetails"]
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in comps:
                row = {k: c.get(k, "") for k in fieldnames}
                row["Units"] = " | ".join(c.get("Units", []))
                # UnitDetails 예: "Viktor★(Drone Uplink, Archangel's Staff) | Illaoi★(Ionic Spark)"
                detail_strs = []
                for u in c.get("UnitDetails", []):
                    name_part = u.get("name", "")
                    if u.get("three_star"):
                        name_part += "★"
                    items = u.get("items", [])
                    if items:
                        name_part += f" ({', '.join(items)})"
                    detail_strs.append(name_part)
                row["UnitDetails"] = " | ".join(detail_strs)
                writer.writerow(row)
        print(f"✅ CSV 저장 완료: {csv_path}")
    else:
        print("⚠️ 수집된 컴프 데이터가 없습니다.")

    return comps


def scrape_items():
    """MetaTFT에서 아이템 통계 데이터를 Type별로 스크래핑.

    /items 페이지는 5개 Type 칩(Normal/Artifact/Radiant/Emblem/Trait)이 있고,
    초기 상태는 전부 미선택(=전체 표시). 각 타입을 개별로 선택한 상태의 테이블을
    items_{type}_{date}.json / .csv 로 분리 저장한다.
    """
    today = today_kst()
    print(f"\n[{today}] MetaTFT 아이템 데이터 수집 시작...")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    results = {}  # {type_slug: [items...]}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        # 행 단위 hydrate가 IntersectionObserver 기반이므로,
        # 뷰포트를 넉넉히 키워 전체 행을 한 번에 로드한다.
        page = browser.new_page(viewport={"width": 1280, "height": 10000})

        try:
            print(f"페이지 로딩 중: {ITEMS_URL}")
            page.goto(ITEMS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)

            # 필터 고정 — Type 칩 루프 전에 1회 적용 (이후 Type 토글 시에도 유지됨)
            apply_stats_filters(page, "items")

            for alt, slug in ITEM_TYPES:
                print(f"\n--- Type: {alt} ({slug}) ---")

                # 타깃 칩만 ChipSelected로, 그 외는 해제되도록 클릭 조정
                page.evaluate(
                    """(target) => {
                        const chips = document.querySelectorAll('.ItemTypeChip');
                        for (const chip of chips) {
                            const alt = chip.querySelector('img')?.alt;
                            const selected = chip.className.includes('ChipSelected');
                            const isTarget = alt === target;
                            if (isTarget && !selected) chip.click();
                            else if (!isTarget && selected) chip.click();
                        }
                    }""",
                    alt,
                )
                page.wait_for_timeout(1500)
                # hydrate 보장: 끝까지 스크롤 후 맨 위로 복귀
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(800)

                # 디버그 스크린샷/HTML
                page.screenshot(
                    path=os.path.join(LOGS_DIR, f"items_{slug}_{today}.png"),
                    full_page=False,  # 10000px 뷰포트라 full_page는 매우 큼
                )
                with open(
                    os.path.join(LOGS_DIR, f"items_{slug}_{today}.html"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(page.content())

                # 행 파싱 (evaluate로 한 번에 추출)
                rows_data = page.evaluate(
                    """() => {
                        const rows = document.querySelectorAll('table tbody tr');
                        const out = [];
                        rows.forEach(tr => {
                            const tds = tr.querySelectorAll('td');
                            if (tds.length < 6) return;
                            // 셀별 텍스트
                            const cells = Array.from(tds).map(td => (td.textContent || '').trim());
                            // 비어있는 행(=placeholder, hydrate 안 된 행) 스킵
                            if (!cells[0] || !cells[1]) return;
                            // Popular Units: 이미지 alt 수집
                            const unitImgs = tds[6]?.querySelectorAll('img') || [];
                            const units = Array.from(unitImgs).map(i => i.alt).filter(a => a);
                            out.push({
                                item: cells[0],
                                tier: cells[1],
                                avg_place: cells[2],
                                place_change: cells[3],
                                win_rate: cells[4],
                                frequency_raw: cells[5],
                                units: units,
                            });
                        });
                        return out;
                    }"""
                )

                items = []
                for r in rows_data:
                    # frequency_raw 예: "57,558 38.7%" → Games + Frequency 분리
                    freq_raw = r.get("frequency_raw", "")
                    parts = freq_raw.rsplit(" ", 1)
                    if len(parts) == 2:
                        games = parts[0].replace(",", "")
                        frequency = parts[1]
                    else:
                        games = ""
                        frequency = freq_raw

                    items.append({
                        "Item": r.get("item", ""),
                        "Tier": r.get("tier", ""),
                        "Avg Place": r.get("avg_place", ""),
                        "Place Change": r.get("place_change", ""),
                        "Win Rate": r.get("win_rate", ""),
                        "Games": games,
                        "Frequency": frequency,
                        "PopularUnits": r.get("units", []),
                    })

                print(f"  {len(items)}개 아이템 수집")
                results[slug] = items

        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            try:
                page.screenshot(path=os.path.join(LOGS_DIR, f"items_error_{today}.png"))
            except Exception:
                pass
        finally:
            browser.close()

    # Type별 저장
    saved_any = False
    for alt, slug in ITEM_TYPES:
        items = results.get(slug, [])
        if not items:
            print(f"⚠️ {alt}: 수집 데이터 없음")
            continue
        saved_any = True

        item_dir = ITEMS_DIRS[slug]
        os.makedirs(item_dir, exist_ok=True)

        # JSON
        json_path = os.path.join(item_dir, f"{today}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {"date": today, "type": alt, "count": len(items), "items": items},
                f, ensure_ascii=False, indent=2,
            )
        print(f"✅ JSON 저장 완료: {json_path} ({len(items)}개)")

        # CSV (PopularUnits는 파이프로 직렬화)
        csv_path = os.path.join(item_dir, f"{today}.csv")
        fieldnames = ["Item", "Tier", "Avg Place", "Place Change",
                      "Win Rate", "Games", "Frequency", "PopularUnits"]
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for it in items:
                row = {k: it.get(k, "") for k in fieldnames}
                row["PopularUnits"] = " | ".join(it.get("PopularUnits", []))
                writer.writerow(row)
        print(f"✅ CSV 저장 완료: {csv_path}")

    return results if saved_any else {}


if __name__ == "__main__":
    import sys

    unit_results = scrape_units()
    print(f"\n총 {len(unit_results)}개 유닛 데이터 수집 완료")

    comp_results = scrape_comps()
    print(f"\n총 {len(comp_results)}개 컴프 데이터 수집 완료")

    item_results = scrape_items()
    total_items = sum(len(v) for v in item_results.values()) if item_results else 0
    print(f"\n총 {total_items}개 아이템 데이터 수집 완료 ({len(item_results)}개 타입)")

    # CI에서 실패 감지를 위한 exit code (셋 중 하나라도 실패 시 non-zero)
    if not unit_results or not comp_results or not item_results:
        sys.exit(1)
