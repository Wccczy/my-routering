#!/usr/bin/env python3
"""Generate a Clash Verge (Rev) Merge profile from openclash-rules.ini.

The ini stays the single source of truth; this script derives the desktop variant:
Clash Verge runs mihomo locally with plenty of RAM, so the full template is used
(ads / gfw / Netflix / TikTok / Spotify included, no low-memory trimming).

Differences vs the OpenClash/subconverter pipeline, and why:
* Output is a Merge file (全局扩展配置), not a full config: nodes come from the
  subscription profile imported in Verge; this file only rewrites groups and rules.
* subconverter turns regex groups into proxy-providers (one filter per group);
  Verge profiles have inline proxies, so every regex group becomes
  `include-all: true` + `filter` — the native mihomo equivalent.
* The VPS whitelist group gets a REJECT base member: provider-name spoofing is a
  router concern, but an absent VPS node would otherwise collapse to COMPATIBLE
  (which is direct). REJECT fails the group's URL probe, so the AI fallback chain
  skips it instead of leaking.
* exclude_remarks cannot be expressed here — Verge imports every node the
  subscription ships. Filter-based groups already exclude 流量/到期 info nodes
  by regex; only 🧭 手动选择 (deliberately .*) shows them.
* Rules are emitted as prepend-rules ending in our own MATCH, so the profile's
  built-in rules never get a chance to diverge.

Usage:  python3 tools/verge_gen.py        (writes clash-verge.yaml)
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INI = os.path.join(ROOT, "openclash-rules.ini")
OUT = os.path.join(ROOT, "clash-verge.yaml")

VPS_GROUP = "🏠 自建 VPS"


def parse_ini():
    rules, groups = [], []
    for ln, raw in enumerate(open(INI, encoding="utf-8"), 1):
        s = raw.strip()
        if not s or s.startswith((";", "#")) or s.startswith("["):
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if k == "ruleset":
            policy, _, body = v.partition(",")
            if not body.startswith("[]"):
                raise ValueError(f"line {ln}: only inline []RULE supported: {s}")
            parts = [p.strip() for p in body[2:].split(",")]
            no_resolve = bool(parts and parts[-1] == "no-resolve")
            if no_resolve:
                parts.pop()
            rules.append(",".join(parts + [policy] + (["no-resolve"] if no_resolve else [])))
        elif k == "custom_proxy_group":
            f = v.split("`")
            name, typ = f[0], f[1]
            body = f[2:]
            url, interval, tolerance = None, None, None
            if typ != "select":
                if len(body) < 3:
                    raise ValueError(f"line {ln}: {typ} needs test url + interval")
                body, url, times = body[:-2], body[-2], body[-1]
                parts = (times.split(",") + ["", "", ""])[:3]
                interval, tolerance = parts[0], parts[2]
            members = [m[2:] for m in body if m.startswith("[]")]
            regexes = [m for m in body if not m.startswith("[]")]
            if len(regexes) > 1:
                raise ValueError(f"line {ln}: mihomo groups take a single filter")
            groups.append({"name": name, "type": typ, "proxies": members,
                           "filter": regexes[0] if regexes else None,
                           "url": url, "interval": interval, "tolerance": tolerance})
    return rules, groups


def emit(rules, groups):
    known = {g["name"] for g in groups} | {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
    for g in groups:
        for m in g["proxies"]:
            if m not in known:
                raise ValueError(f"{g['name']}: unknown member {m}")
    out = [
        "# Clash Verge (Rev) 全局扩展配置 —— 由 tools/verge_gen.py 从 openclash-rules.ini 生成,勿手改。",
        "# 用法:Verge 里订阅作主 profile,本文件通过「订阅右键 → 编辑 Merge」或全局扩展配置接入。",
        "# 桌面端内存充足,使用全量规则(含广告/gfw/Netflix);低内存版不适用本文件。",
        "# 节点来自订阅本身:VPS 节点(CF-WS-443)需要在订阅里存在,缺失时 AI 链自动跳过它(见脚本头注)。",
        "",
        "prepend-rules:",
    ]
    for r in rules:
        out.append(f"  - {r}")
    out += ["", "proxy-groups:"]
    for g in groups:
        out.append(f"  - name: \"{g['name']}\"")
        out.append(f"    type: {g['type']}")
        proxies = list(g["proxies"])
        if g["name"] == VPS_GROUP and "REJECT" not in proxies:
            proxies.append("REJECT")
        if proxies:
            out.append("    proxies:")
            for m in proxies:
                out.append(f"      - \"{m}\"")
        if g["filter"]:
            # 单引号:双引号 YAML 会把正则里的 \b \s 当成 YAML 转义序列吃掉
            out.append(f"    include-all: true")
            out.append(f"    filter: '{g['filter'].replace(chr(39), chr(39) * 2)}'")
        if g["url"]:
            out.append(f"    url: {g['url']}")
            out.append(f"    interval: {g['interval']}")
            if g["type"] == "url-test" and g["tolerance"]:
                out.append(f"    tolerance: {g['tolerance']}")
    return "\n".join(out) + "\n"


def main():
    rules, groups = parse_ini()
    if not rules or rules[-1].split(",")[0] != "MATCH":
        raise ValueError("template must end with MATCH")
    text = emit(rules, groups)
    open(OUT, "w", encoding="utf-8").write(text)
    print(f"wrote {OUT}: {len(rules)} rules, {len(groups)} groups")


if __name__ == "__main__":
    sys.exit(main())
