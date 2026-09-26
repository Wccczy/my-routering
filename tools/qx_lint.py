#!/usr/bin/env python3
"""Independent syntax / reference linter for quantumultx.conf (does not import qx_gen).

Checks: known sections; [policy] line grammar + member references + regex compiles + no commas;
[filter_remote] URL reachable, parsable, force-policy exists, unique tags; [filter_local] rule
types, field count, valid IP/CIDR, policy exists, no duplicates, final last; node-name regex
behaviour on sample names.   Usage: python3 tools/qx_lint.py [--offline]
"""
import ipaddress
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = next((os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("--")),
            os.path.join(ROOT, "quantumultx.conf"))
OFFLINE = "--offline" in sys.argv

SECTIONS = {"general", "dns", "policy", "server_remote", "filter_remote", "rewrite_remote", "server_local",
            "filter_local", "rewrite_local", "task_local", "http_backend", "mitm"}
POLICY_TYPES = {"static", "available", "round-robin", "dest-hash", "url-latency-benchmark", "ssid"}
POLICY_PARAMS = {"img-url", "server-tag-regex", "resource-tag-regex", "check-interval", "alive-checking",
                 "tolerance"}
BUILTIN = {"direct", "reject", "proxy", "reject-200", "reject-img", "reject-dict", "reject-array", "reject-no-drop"}
LOCAL_TYPES = {"host", "host-suffix", "host-keyword", "host-wildcard", "user-agent", "ip-cidr", "ip6-cidr",
               "geoip", "ip-asn", "final"}
REMOTE_PARAMS = {"tag", "force-policy", "update-interval", "opt-parser", "enabled", "require-devices",
                 "inserted-resource"}

errors, warns = [], []


def err(ln, msg):
    errors.append(f"L{ln}: {msg}")


text = open(CONF, encoding="utf-8").read()
if text.startswith("\ufeff"):
    err(1, "BOM")
if "\r" in text:
    err(0, "CRLF line endings")

sec, lines = None, {s: [] for s in SECTIONS}
for ln, raw in enumerate(text.split("\n"), 1):
    s = raw.strip()
    if not s or s.startswith(("#", ";", "//")):
        continue
    m = re.fullmatch(r"\[([a-z_]+)\]", s)
    if m:
        sec = m.group(1)
        if sec not in SECTIONS:
            err(ln, f"unknown section [{sec}]")
        continue
    if sec is None:
        err(ln, "content before first section")
        continue
    lines[sec].append((ln, s))

# ---------------- policy
policies, members = {}, {}
for ln, s in lines["policy"]:
    typ, eq, rest = s.partition("=")
    typ = typ.strip()
    if not eq or typ not in POLICY_TYPES:
        err(ln, f"bad policy type {typ!r}")
        continue
    parts = [p.strip() for p in rest.split(",")]
    name, items = parts[0], parts[1:]
    if not name or name in policies:
        err(ln, f"empty/duplicate policy name {name!r}")
    if any(c in name for c in "\ufe0f\u200d="):
        err(ln, f"invisible char or '=' in name {name!r}")
    params, mem = {}, []
    for it in items:
        if "=" in it:
            k, _, v = it.partition("=")
            if k not in POLICY_PARAMS:
                err(ln, f"unknown policy param {k}")
            params[k] = v
        else:
            mem.append(it)
    if "server-tag-regex" in params:
        try:
            re.compile(params["server-tag-regex"])
        except re.error as e:
            err(ln, f"regex error {e}")
        if mem:
            err(ln, "mixing members and server-tag-regex")
    elif not mem:
        err(ln, "policy without members or regex")
    if typ == "url-latency-benchmark":
        for k in ("check-interval", "tolerance"):
            if k in params and not params[k].isdigit():
                err(ln, f"{k} not integer")
    policies[name] = (typ, params)
    members[name] = (ln, mem)
for name, (ln, mem) in members.items():
    for m in mem:
        if m not in policies and m not in BUILTIN:
            err(ln, f"{name}: member {m!r} is not a defined policy")


def pol_ok(p):
    return p in policies or p in BUILTIN


# cycle check
def cyc(n, stack):
    if n in stack:
        return True
    return any(cyc(m, stack | {n}) for m in members.get(n, (0, []))[1] if m in members)


for n in members:
    if cyc(n, frozenset()):
        err(members[n][0], f"cyclic policy reference via {n}")

# ---------------- filter_remote
tags = set()
for ln, s in lines["filter_remote"]:
    parts = [p.strip() for p in s.split(",")]
    url, kv = parts[0], {}
    for p in parts[1:]:
        k, eq, v = p.partition("=")
        if not eq or k not in REMOTE_PARAMS:
            err(ln, f"bad filter_remote param {p!r}")
        kv[k] = v
    if kv.get("tag") in tags:
        err(ln, f"duplicate tag {kv.get('tag')}")
    tags.add(kv.get("tag"))
    if "force-policy" in kv and not pol_ok(kv["force-policy"]):
        err(ln, f"force-policy {kv['force-policy']!r} undefined")
    if not OFFLINE:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "qx-lint"}), timeout=60) as r:
                body = r.read().decode("utf-8")
            types = {}
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    t = line.split(",")[0].strip().upper()
                    types[t] = types.get(t, 0) + 1
            bad_t = set(types) - {"HOST", "HOST-SUFFIX", "HOST-KEYWORD", "HOST-WILDCARD", "USER-AGENT", "IP-CIDR",
                                  "IP6-CIDR", "IP-ASN", "GEOIP"}
            print(f"  remote {kv.get('tag')}: HTTP {r.status}, {sum(types.values())} rules {types}")
            if bad_t:
                err(ln, f"remote list has non-QX rule types {bad_t}")
        except Exception as e:  # noqa
            err(ln, f"cannot fetch {url}: {e}")

# ---------------- filter_local
seen, final_ln, last_ln = set(), None, None
for ln, s in lines["filter_local"]:
    parts = [p.strip() for p in s.split(",")]
    t = parts[0].lower()
    last_ln = ln
    if t not in LOCAL_TYPES:
        err(ln, f"unknown rule type {t}")
        continue
    if t == "final":
        if len(parts) != 2 or not pol_ok(parts[1]):
            err(ln, "bad final")
        final_ln = ln
        continue
    if len(parts) != 3:
        err(ln, f"expected 3 fields: {s}")
        continue
    v, p = parts[1], parts[2]
    if not pol_ok(p):
        err(ln, f"policy {p!r} undefined")
    if (t, v) in seen:
        err(ln, f"duplicate rule {t},{v}")
    seen.add((t, v))
    if t in ("ip-cidr", "ip6-cidr"):
        try:
            net = ipaddress.ip_network(v, strict=True)
            if (net.version == 4) != (t == "ip-cidr"):
                err(ln, "ip version / rule type mismatch")
            if net.version == 4 and net.overlaps(ipaddress.ip_network("198.18.0.0/15")):
                err(ln, "rule overlaps QX fake-ip range 198.18.0.0/15")
        except ValueError as e:
            err(ln, f"bad cidr {v}: {e}")
    elif t == "geoip" and not re.fullmatch(r"[a-z]{2}", v):
        err(ln, f"geoip needs ISO country code: {v}")
    elif t == "ip-asn" and not v.isdigit():
        err(ln, f"bad asn {v}")
    elif t in ("host", "host-suffix") and not re.fullmatch(r"[a-z0-9_]([a-z0-9_.-]*[a-z0-9_])?", v):
        err(ln, f"bad domain {v!r}")
if final_ln is None or final_ln != last_ln:
    err(final_ln or 0, "final must exist and be the last filter_local rule")

# ---------------- node-name regex behaviour
SAMPLES = {
    "🇭🇰 香港 01": "🇭🇰 HK", "HK-IEPL-02": "🇭🇰 HK", "Hong Kong 03 | x2": "🇭🇰 HK", "香港HKT": "🇭🇰 HK",
    "🇹🇼 台湾 Hinet": "🇹🇼 TW", "TW 01": "🇹🇼 TW", "🇯🇵 日本 Tokyo": "🇯🇵 JP", "JP-Osaka": "🇯🇵 JP",
    "🇸🇬 新加坡 01": "🇸🇬 SG", "SG | Singapore": "🇸🇬 SG", "🇺🇸 美国 Los Angeles": "🇺🇸 US", "US-SJC": "🇺🇸 US",
    "🇩🇪 德国 01": "🧊 冷门节点", "🇬🇧 UK London": "🧊 冷门节点", "🇰🇷 韩国 首尔": "🧊 冷门节点",
    "剩余流量：100G": None, "套餐到期：2026-01-01": None, "官网 https://x.y": None, "Traffic Reset: 3 days": None,
    "香港节点 01": "🇭🇰 HK", "ATLS 日本-05 | x1 *原生": "🇯🇵 JP", "IEPL 新加坡-01 *稳定奈飞 | x1": "🇸🇬 SG",
    "殊-加拿大 | x1": "🧊 冷门节点", "注：若无法使用请【更新订阅】": None, "EXPIRE: 2026-10-01": None,
    "IEPL 香港-01 *稳定奈飞 | x1": "🇭🇰 HK", "🇺🇸 美国 IPLC 专线 02": "🇺🇸 US", "Premium|SG-03": "🇸🇬 SG",
}
for g in ("🇭🇰 HK", "🇹🇼 TW", "🇯🇵 JP", "🇸🇬 SG", "🇺🇸 US"):
    if g in policies and policies[g][0] not in ("available", "url-latency-benchmark"):
        err(members[g][0], f"{g} should be an automatic (available/url-latency-benchmark) policy")
# self-hosted VPS: only in its own pool + manual, never in auto / cold / region pools
VPS_SAMPLE, VPS_POOL = "233boy-reality-203.0.113.9", "🏠 自建 VPS"
if VPS_POOL in policies:
    rx = {n: p[1]["server-tag-regex"] for n, p in policies.items() if "server-tag-regex" in p[1]}
    hit = sorted(n for n, r in rx.items() if re.search(r, VPS_SAMPLE))
    if hit != sorted([VPS_POOL, "🧭 手动选择"]):
        err(members[VPS_POOL][0], f"VPS node {VPS_SAMPLE!r} lands in {hit}")
region = ["🇭🇰 HK", "🇹🇼 TW", "🇯🇵 JP", "🇸🇬 SG", "🇺🇸 US", "🧊 冷门节点"]
for node, want in SAMPLES.items():
    hits = [g for g in region if g in policies and re.search(policies[g][1]["server-tag-regex"], node)]
    manual = re.search(policies["🧭 手动选择"][1]["server-tag-regex"], node) if "🧭 手动选择" in policies else None
    exp = [want] if want else []
    if hits != exp or bool(manual) != bool(want):
        err(0, f"node {node!r}: regions={hits} manual={bool(manual)} expected {exp}")

n_local = len(lines["filter_local"])
print(f"policies={len(policies)} filter_remote={len(lines['filter_remote'])} filter_local={n_local}")
for w in warns:
    print("WARN", w)
for e in errors:
    print("ERROR", e)
print("LINT", "FAILED" if errors else "OK")
sys.exit(1 if errors else 0)
