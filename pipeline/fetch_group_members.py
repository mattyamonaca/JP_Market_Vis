"""企業グループ（系列）の会員会社一覧を、各グループの広報団体の公式サイトから取得して
data_raw/group_members.json に保存する（民間公表データ。Issue: 人的・グループ・提携の拡充）。

対象（いずれも公式の会員一覧ページ。静的 HTML で読める）:
  - 三菱グループ: 三菱広報委員会「会員会社」
  - 三井グループ: 三井広報委員会「会員会社」
  - 住友グループ: 住友グループ広報委員会「住友グループ各社のご案内」
  - 三和グループ: みどり会「メンバー会社一覧」
芙蓉グループ（芙蓉懇談会）・第一勧銀グループ（三金会）は公式の会員一覧が公開されていないため対象外。

保存する内容: グループごとに {group, organization, url, retrieved, members:[{name, url}]}。
上場企業への照合は build_masters.py が別名索引で行う。

使い方: python fetch_group_members.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys

import requests

from config import DATA_RAW

OUT_PATH = DATA_RAW / "group_members.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"

GROUPS = [
    {
        "group": "三菱グループ", "organization": "三菱広報委員会",
        "url": "https://www.mitsubishi.com/ja/profile/csr/mpac/companies/",
        # <li><a href="URL"><img alt="三菱商事株式会社"></a></li>（ロゴの alt が社名）
        "pattern": r'<li>\s*<a href="(?P<url>[^"]+)"[^>]*>\s*<img[^>]*alt="(?P<name>[^"]+)"',
    },
    {
        "group": "三井グループ", "organization": "三井広報委員会",
        "url": "https://www.mitsuipr.com/members/",
        # <p class="title bold"><a href="/members/X/"> 三井物産<br><small>MITSUI & CO., LTD.</small></a>
        "pattern": r'<p class="title[^"]*">\s*<a href="(?P<url>[^"]+)">\s*(?P<name>[^<]+?)\s*<br',
    },
    {
        "group": "住友グループ", "organization": "住友グループ広報委員会",
        "url": "https://www.sumitomo.gr.jp/org/company/",
        # <a class="link-cmn js-acc-trg c-inherit" href="URL">住友化学株式会社<span
        "pattern": r'<a class="link-cmn js-acc-trg[^"]*" href="(?P<url>[^"]+)">(?P<name>[^<]+?)<',
    },
    {
        "group": "三和グループ", "organization": "みどり会",
        "url": "https://www.midorikai.co.jp/member_company",
        # <li class="p-member-company__contentListItem"><a href="URL">岩谷産業</a></li>
        "pattern": r'<li class="p-member-company__contentListItem">\s*<a href="(?P<url>[^"]*)"[^>]*>(?P<name>[^<]+?)</a>',
    },
]


def fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def extract(spec: dict, page: str) -> list[dict]:
    members: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(spec["pattern"], page, re.S):
        name = html.unescape(re.sub(r"\s+", " ", m.group("name"))).strip()
        url = html.unescape(m.group("url") or "").strip()
        if not name or name in seen:
            continue
        # 三菱: ロゴ alt が「三菱オフィシャルサイト」等のサイト内リンクは除外
        if re.search(r"オフィシャルサイト|インスタグラム|Facebook|Twitter|YouTube", name):
            continue
        seen.add(name)
        members.append({"name": name, "url": url})
    return members


def main() -> int:
    retrieved = dt.date.today().isoformat()
    out = []
    for spec in GROUPS:
        try:
            page = fetch(spec["url"])
        except requests.RequestException as e:
            print(f"WARN: {spec['group']} 取得失敗: {e}", file=sys.stderr)
            continue
        members = extract(spec, page)
        if len(members) < 10:
            print(f"WARN: {spec['group']} の会員が {len(members)} 社しか読めません（ページ構造が変わった可能性）", file=sys.stderr)
        out.append({"group": spec["group"], "organization": spec["organization"], "url": spec["url"],
                    "retrieved": retrieved, "members": members})
        print(f"{spec['group']}（{spec['organization']}）: {len(members)} 社")
    DATA_RAW.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK -> {OUT_PATH}")
    return 0 if len(out) == len(GROUPS) else 1


if __name__ == "__main__":
    sys.exit(main())
