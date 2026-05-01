"""
TFT 데이터 한국어 변환 스크립트
- Community Dragon ko_kr.json + en_us.json으로 영→한 매핑 구축
- data/{units,comps,items/*}/{date}.json 을 data_ko/ 에 한글 복사본 생성
- 기존 data/ 는 절대 수정하지 않음

사용법:
    python3 translate_to_ko.py 2026-04-30
"""

import json
import csv
import os
import sys
import urllib.request
from pathlib import Path

# 경로 상수
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_KO_DIR = ROOT / "data_ko"
DICT_DIR = DATA_KO_DIR / "_dict"

KO_URL = "https://raw.communitydragon.org/latest/cdragon/tft/ko_kr.json"
EN_URL = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
KO_CACHE = DICT_DIR / "ko_kr.json"
EN_CACHE = DICT_DIR / "en_us.json"
MAPPINGS_CACHE = DICT_DIR / "ko_kr_mappings.json"

ITEM_TYPES = ["normal", "artifact", "radiant", "emblem", "trait"]


# ── 다운로드 ──────────────────────────────────────────────────────────────────

def download_if_missing(url: str, path: Path) -> None:
    if path.exists():
        print(f"  캐시 사용: {path.name}")
        return
    print(f"  다운로드: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)
    print(f"  저장: {path} ({path.stat().st_size // 1024 // 1024}MB)")


# ── 매핑 추출 ─────────────────────────────────────────────────────────────────

def build_mappings() -> tuple[dict, dict, dict]:
    """
    (unit_map, trait_map, item_map) 반환 — 영문 displayName → 한글 displayName
    """
    if MAPPINGS_CACHE.exists():
        print("  매핑 캐시 사용")
        d = json.loads(MAPPINGS_CACHE.read_text())
        return d["units"], d["traits"], d["items"]

    download_if_missing(KO_URL, KO_CACHE)
    download_if_missing(EN_URL, EN_CACHE)

    print("  JSON 파싱 중 (대용량)...")
    ko_data = json.loads(KO_CACHE.read_text())
    en_data = json.loads(EN_CACHE.read_text())

    # Set17 정규 데이터만 사용
    ko17 = next(s for s in ko_data["setData"] if s.get("mutator") == "TFTSet17")
    en17 = next(s for s in en_data["setData"] if s.get("mutator") == "TFTSet17")

    # ─ 유닛 매핑 ─
    ko_ch = {c["apiName"]: c["name"] for c in ko17["champions"] if c.get("name")}
    en_ch = {c["apiName"]: c["name"] for c in en17["champions"] if c.get("name")}
    unit_map = {en_ch[api]: ko_ch[api] for api in en_ch if api in ko_ch and en_ch[api]}

    # ─ 특성 매핑 (중복 apiName 제거: 영문명 기준 첫 번째만) ─
    ko_tr = {t["apiName"]: t["name"] for t in ko17["traits"] if t.get("name")}
    en_tr = {t["apiName"]: t["name"] for t in en17["traits"] if t.get("name")}
    trait_map: dict[str, str] = {}
    for api in en_tr:
        en_name = en_tr[api]
        ko_name = ko_tr.get(api, "")
        if en_name and ko_name and en_name not in trait_map:
            trait_map[en_name] = ko_name

    # ─ 아이템 매핑 (전체 items 풀에서 영문명 → 한글명) ─
    ko_items = {i["apiName"]: i["name"] for i in ko_data.get("items", []) if i.get("name")}
    en_items = {i["apiName"]: i["name"] for i in en_data.get("items", []) if i.get("name")}
    item_map: dict[str, str] = {}
    for api in en_items:
        en_name = en_items[api]
        ko_name = ko_items.get(api, "")
        if en_name and ko_name and en_name not in item_map:
            item_map[en_name] = ko_name

    # 캐시 저장
    MAPPINGS_CACHE.write_text(
        json.dumps({"units": unit_map, "traits": trait_map, "items": item_map},
                   ensure_ascii=False, indent=2)
    )
    print(f"  매핑 완료 — 유닛:{len(unit_map)} 특성:{len(trait_map)} 아이템:{len(item_map)}")
    return unit_map, trait_map, item_map


# ── 이름 변환 유틸 ────────────────────────────────────────────────────────────

def translate_name(name: str, *maps: dict) -> str:
    """토큰을 왼쪽부터 greedy 최장 매칭으로 변환."""
    combined: dict[str, str] = {}
    for m in maps:
        combined.update(m)
    tokens = name.split(" ")
    result, i = [], 0
    while i < len(tokens):
        matched = False
        for length in range(min(4, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + length])
            if phrase in combined:
                result.append(combined[phrase])
                i += length
                matched = True
                break
        if not matched:
            result.append(tokens[i])
            i += 1
    return " ".join(result)


def t_unit(name: str, unit_map: dict) -> str:
    return unit_map.get(name, name)


def t_item(name: str, item_map: dict) -> str:
    return item_map.get(name, name)


# ── 파일별 변환 ───────────────────────────────────────────────────────────────

def translate_units(date: str, unit_map: dict) -> list[str]:
    src = DATA_DIR / "units" / f"{date}.json"
    dst_dir = DATA_KO_DIR / "units"
    dst_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(src.read_text())
    unmapped = []
    for u in data["units"]:
        en = u["Unit"]
        ko = unit_map.get(en, en)
        if ko == en:
            unmapped.append(("unit", en))
        u["Unit"] = ko

    # JSON 저장
    (dst_dir / f"{date}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )

    # CSV 저장
    _write_csv(dst_dir / f"{date}.csv", data["units"],
               ["Unit", "Cost", "Avg Place", "Top 4%", "Games", "Win%"])
    return unmapped


def translate_items(date: str, item_type: str, unit_map: dict, item_map: dict) -> list[str]:
    src = DATA_DIR / "items" / item_type / f"{date}.json"
    dst_dir = DATA_KO_DIR / "items" / item_type
    dst_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(src.read_text())
    unmapped = []
    for it in data["items"]:
        en = it["Item"]
        ko = item_map.get(en, en)
        if ko == en:
            unmapped.append(("item", en))
        it["Item"] = ko
        it["PopularUnits"] = [unit_map.get(u, u) for u in (it.get("PopularUnits") or [])]

    (dst_dir / f"{date}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )
    _write_csv(dst_dir / f"{date}.csv", data["items"],
               ["Item", "Tier", "Avg Place", "Place Change", "Win Rate",
                "Games", "Frequency", "PopularUnits"],
               list_fields={"PopularUnits"})
    return unmapped


def translate_comps(date: str, unit_map: dict, trait_map: dict, item_map: dict) -> list[str]:
    src = DATA_DIR / "comps" / f"{date}.json"
    dst_dir = DATA_KO_DIR / "comps"
    dst_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(src.read_text())
    unmapped = []
    for comp in data["comps"]:
        # Name: 특성+유닛 조합 greedy 변환
        en_name = comp["Name"]
        ko_name = translate_name(en_name, trait_map, unit_map)
        if ko_name == en_name:
            unmapped.append(("comp_name", en_name))
        comp["Name"] = ko_name

        # Units 배열
        comp["Units"] = [unit_map.get(u, u) for u in (comp.get("Units") or [])]

        # UnitDetails
        for ud in (comp.get("UnitDetails") or []):
            ud["name"] = unit_map.get(ud["name"], ud["name"])
            ud["items"] = [item_map.get(i, i) for i in (ud.get("items") or [])]

    (dst_dir / f"{date}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )

    # CSV (Units·UnitDetails 직렬화)
    rows = []
    for c in data["comps"]:
        ud_strs = []
        for ud in (c.get("UnitDetails") or []):
            s = ud["name"] + ("★" if ud.get("three_star") else "")
            if ud.get("items"):
                s += f" ({', '.join(ud['items'])})"
            ud_strs.append(s)
        rows.append({
            "Tier": c.get("Tier", ""),
            "Name": c.get("Name", ""),
            "Level": c.get("Level", ""),
            "Difficulty": c.get("Difficulty", ""),
            "Avg Place": c.get("Avg Place", ""),
            "Pick Rate": c.get("Pick Rate", ""),
            "Win Rate": c.get("Win Rate", ""),
            "Top 4 Rate": c.get("Top 4 Rate", ""),
            "Units": " | ".join(c.get("Units") or []),
            "UnitDetails": " | ".join(ud_strs),
        })
    _write_csv(dst_dir / f"{date}.csv", rows,
               ["Tier", "Name", "Level", "Difficulty", "Avg Place",
                "Pick Rate", "Win Rate", "Top 4 Rate", "Units", "UnitDetails"])
    return unmapped


# ── CSV 공통 저장 ─────────────────────────────────────────────────────────────

def _write_csv(path: Path, rows: list[dict], fieldnames: list[str],
               list_fields: set[str] | None = None) -> None:
    list_fields = list_fields or set()
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for field in list_fields:
                v = flat.get(field, "")
                if isinstance(v, list):
                    flat[field] = " | ".join(v)
            writer.writerow(flat)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python3 translate_to_ko.py YYYY-MM-DD")
        sys.exit(1)
    date = sys.argv[1]

    print(f"\n[{date}] 한국어 변환 시작")
    print("─" * 50)

    print("\n▶ 매핑 딕셔너리 로드")
    unit_map, trait_map, item_map = build_mappings()

    all_unmapped: list[tuple[str, str]] = []

    print("\n▶ units 변환")
    all_unmapped += translate_units(date, unit_map)
    print(f"  ✅ data_ko/units/{date}.json")

    print("\n▶ items 변환")
    for itype in ITEM_TYPES:
        src = DATA_DIR / "items" / itype / f"{date}.json"
        if not src.exists():
            print(f"  ⏭  {itype} — 파일 없음")
            continue
        all_unmapped += translate_items(date, itype, unit_map, item_map)
        print(f"  ✅ data_ko/items/{itype}/{date}.json")

    print("\n▶ comps 변환")
    all_unmapped += translate_comps(date, unit_map, trait_map, item_map)
    print(f"  ✅ data_ko/comps/{date}.json")

    # 누락 항목 저장
    unmapped_path = DICT_DIR / f"unmapped_{date}.json"
    if all_unmapped:
        unmapped_path.write_text(
            json.dumps(all_unmapped, ensure_ascii=False, indent=2)
        )
        print(f"\n⚠️  미변환 항목 {len(all_unmapped)}개 → {unmapped_path}")
        for kind, name in all_unmapped[:10]:
            print(f"   [{kind}] {name}")
    else:
        unmapped_path.write_text("[]")
        print("\n✅ 미변환 항목 없음")

    # 샘플 출력
    _print_samples(date, unit_map, trait_map, item_map)
    print("\n완료!")


def _print_samples(date: str, unit_map: dict, trait_map: dict, item_map: dict) -> None:
    print("\n─── 변환 샘플 ───")
    check_units = ["Jhin", "Briar", "Tahm Kench", "Nunu & Willump", "Kai'Sa"]
    for u in check_units:
        print(f"  유닛  {u:25s} → {unit_map.get(u, '(없음)')}")

    check_comps_path = DATA_KO_DIR / "comps" / f"{date}.json"
    if check_comps_path.exists():
        comps = json.loads(check_comps_path.read_text())["comps"]
        print()
        for c in comps[:5]:
            print(f"  컴프  {c['Name']}")

    check_items = ["Giant Slayer", "Gargoyle Stoneplate", "Guinsoo's Rageblade",
                   "Evenshroud", "Thresh's Lantern"]
    print()
    for it in check_items:
        print(f"  아이템 {it:35s} → {item_map.get(it, '(없음)')}")


if __name__ == "__main__":
    main()
