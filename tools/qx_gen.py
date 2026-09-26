#!/usr/bin/env python3
"""Generate a Quantumult X profile from openclash-rules.ini (subconverter [custom] format).

Design
------
* Clash semantics = first-match over the ordered ruleset list, GEOSITE/GEOIP resolved with
  MetaCubeX meta-rules-dat (the same dataset OpenClash/mihomo uses).
* Quantumult X cannot load geosite.dat, so every GEOSITE category is inlined into
  [filter_local] as host / host-suffix rules, except the two huge ones:
    GEOSITE,cn  -> blackmatrix7 China.list (filter_remote, force-policy=direct) + geoip cn
    GEOSITE,gfw -> blackmatrix7 Proxy.list (filter_remote, force-policy=<gfw group>)
* QX does NOT evaluate rules in plain list order (priority is by rule type and local>remote,
  and the exact behaviour is not formally documented).  To be independent of that, every
  local rule gets the policy Clash would pick for *that exact domain*, conflicting
  sub-domains are pinned explicitly, and the result is verified against several plausible
  QX matching models (see Model below).  Generation fails if any model disagrees with Clash.

Usage:  python3 tools/qx_gen.py [--refresh]      (writes quantumultx.conf)
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import ipaddress
import os
import random
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INI = os.path.join(ROOT, "openclash-rules.ini")
OUT = os.path.join(ROOT, "quantumultx.conf")                  # public, committed: no subscription
OUT_PRIVATE = os.path.join(ROOT, "quantumultx.private.conf")  # gitignored: with your subscription
SUBS = os.path.join(ROOT, "qx-subscriptions.local")           # gitignored: one subscription per line
CACHE = os.path.join(ROOT, "tools", ".cache")
REFRESH = "--refresh" in sys.argv

MC = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo"
BM7 = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX"

# GEOSITE tags that are too large to inline -> remote QX-native lists
REMOTE_GEOSITE = {
    "cn": (f"{BM7}/China/China.list", "China"),
    "gfw": (f"{BM7}/Proxy/Proxy.list", "Proxy"),
}
# GEOIP tags: how to express them in QX
GEOIP_INLINE = {"private", "telegram", "netflix", "twitter", "facebook"}   # inline ip-cidr from MetaCubeX geoip
GEOIP_ASN = {"google": ["15169"]}                      # 8k CIDRs -> use Google's ASN instead
FAKE_IP = ipaddress.ip_network("198.18.0.0/15")       # QX placeholder range, never route it

# v2fly "regexp:" entries are dropped from MetaCubeX .list files; re-add as host-wildcard.
REGEXP_SUPPLEMENT = {
    "openai": ["chatgpt-async-webps-prod-*.webpubsub.azure.com"],
    "category-ai-!cn": ["chatgpt-async-webps-prod-*.webpubsub.azure.com"],
    "netflix": ["*apiproxy-device-prod-nlb-*.amazonaws.com", "*apiproxy-website-nlb-prod-*.amazonaws.com",
                "*dualstack.apiproxy-*.amazonaws.com", "*dualstack.ichnaea-web-*.amazonaws.com"],
    "category-games@cn": ["*-mihayo.akamaized.net", "cdn?-epicgames-*.file.myqcloud.com",
                          "epicgames-download?-*.file.myqcloud.com"],
}

# Policy names containing U+FE0F / U+200D are renamed (invisible code points are a common
# source of "policy not found" after copy/paste or editing inside the app).
RENAME = {
    "✈️ Cathay Pacific": "🛫 Cathay Pacific",
    "☁️ cloudflare": "⛅ Cloudflare",
    "🧑‍💻 GitHub": "🐙 GitHub",
    "♻️ 自动选择": "🔄 自动选择",
}
BUILTIN = {"DIRECT": "direct", "REJECT": "reject"}


# ----------------------------------------------------------------------------- fetch
def fetch(url: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._@!-]+", "_", url.split("://", 1)[1]))
    if os.path.exists(fn) and not REFRESH:
        return open(fn, encoding="utf-8").read()
    req = urllib.request.Request(url, headers={"User-Agent": "qx-gen/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} {url}")
        txt = r.read().decode("utf-8")
    if not txt.strip() or txt.startswith("404"):
        raise RuntimeError(f"empty/404 {url}")
    open(fn, "w", encoding="utf-8").write(txt)
    return txt


DOMAIN_RE = re.compile(r"^[a-z0-9_]([a-z0-9_.-]*[a-z0-9_])?$")


def geosite(tag: str):
    """-> list of (kind, domain); kind in {'exact','suffix'} (mihomo .list semantics)."""
    txt = fetch(f"{MC}/geosite/{urllib.parse.quote(tag)}.list")
    out = []
    for raw in txt.splitlines():
        s = raw.strip().lower()
        if not s or s.startswith("#"):
            continue
        if s.startswith("+."):
            kind, d = "suffix", s[2:]
        elif s.startswith("."):          # sub-domains only; host-suffix is the closest QX form
            kind, d = "suffix", s[1:]
        else:
            kind, d = "exact", s
        if not DOMAIN_RE.match(d):
            raise ValueError(f"unexpected geosite entry {raw!r} in {tag}")
        out.append((kind, d))
    if not out:
        raise ValueError(f"empty geosite {tag}")
    return out


def geoip(tag: str):
    out = []
    for s in fetch(f"{MC}/geoip/{tag}.list").split():
        net = ipaddress.ip_network(s.strip(), strict=False)
        out.append(net)
    return out


class RemoteList:
    def __init__(self, url, policy, tag):
        self.url, self.policy, self.tag = url, policy, tag
        self.host, self.suffix, self.keyword, self.wildcard = {}, {}, [], []
        self.counts = {}
        for i, raw in enumerate(fetch(url).splitlines()):
            s = raw.strip()
            if not s or s.startswith(("#", ";", "//")):
                continue
            parts = [p.strip() for p in s.split(",")]
            t, v = parts[0].upper(), parts[1]
            self.counts[t] = self.counts.get(t, 0) + 1
            if t == "HOST":
                self.host.setdefault(v.lower(), i)
            elif t == "HOST-SUFFIX":
                self.suffix.setdefault(v.lower(), i)
            elif t == "HOST-KEYWORD":
                self.keyword.append((i, v.lower()))
            elif t == "HOST-WILDCARD":
                self.wildcard.append((i, re.compile(fnmatch.translate(v.lower()))))
            elif t in ("USER-AGENT", "IP-CIDR", "IP6-CIDR", "IP-ASN", "GEOIP"):
                pass                     # not domain rules
            else:
                raise ValueError(f"{url}: unknown rule type {t}")


# ----------------------------------------------------------------------------- ini
def fix_name(n: str) -> str:
    n = n.strip()
    if n in BUILTIN:
        return BUILTIN[n]
    n = RENAME.get(n, n)
    if "\ufe0f" in n or "\u200d" in n or "," in n or "=" in n:
        raise ValueError(f"policy name needs a RENAME entry: {n!r}")
    return n


def parse_ini():
    rules, groups, exclude = [], [], None
    for ln, raw in enumerate(open(INI, encoding="utf-8"), 1):
        s = raw.strip()
        if not s or s.startswith((";", "#")) or s.startswith("["):
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if k == "ruleset":
            grp, _, body = v.partition(",")
            if not body.startswith("[]"):
                raise ValueError(f"line {ln}: only inline []RULE supported: {s}")
            parts = [p.strip() for p in body[2:].split(",")]
            rules.append({"ln": ln, "policy": fix_name(grp), "raw": body[2:], "type": parts[0].upper(),
                          "args": parts[1:]})
        elif k == "custom_proxy_group":
            f = v.split("`")
            name, typ = fix_name(f[0]), f[1]
            if typ not in ("select", "url-test", "fallback"):
                raise ValueError(f"line {ln}: unsupported group type {typ}")
            body = f[2:]
            g = {"name": name, "type": typ, "ln": ln}
            if typ != "select":           # ...`test_url`interval[,timeout][,tolerance]
                if len(body) < 3:
                    raise ValueError(f"line {ln}: {typ} needs test url + interval")
                body, g["url"], times = body[:-2], body[-2], body[-1]
                interval, _timeout, tol = (times.split(",") + ["", "", ""])[:3]
                g["interval"], g["tolerance"] = int(interval or 300), int(tol or 0)
            g["members"] = [fix_name(m[2:]) for m in body if m.startswith("[]")]
            g["regexes"] = [m for m in body if not m.startswith("[]")]
            groups.append(g)
        elif k in ("exclude_remarks", "exclude"):
            exclude = v.strip()
    return rules, groups, exclude


# ----------------------------------------------------------------------------- helpers
def _alts(rx: str) -> list[str]:
    """Top-level alternatives of the outermost group: '(?i)(a|b|(c|d))' -> ['a','b','(c|d)']."""
    rx = strip_flags(rx)
    if not (rx.startswith("(") and rx.endswith(")")):
        raise ValueError(f"expected '(...)' region regex: {rx}")
    body, out, depth_, cur, esc = rx[1:-1], [], 0, "", False
    for ch in body:
        if esc:
            cur, esc = cur + ch, False
            continue
        if ch == "\\":
            cur, esc = cur + ch, True
            continue
        if ch == "(":
            depth_ += 1
        elif ch == ")":
            depth_ -= 1
        if ch == "|" and depth_ == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def check_cold_group(groups):
    """The 'cold' pool is ^(?!.*(<union of region regexes>)).* — keep it in sync automatically.
    Region regex = a plain '(?i)(a|b|…)' member of an auto (url-test/fallback) group; the
    premium-first '(?i)^(?=…)' member is a subset of it and is ignored here."""
    regions = [(g["name"], r) for g in groups if g["type"] != "select"
               for r in g["regexes"] if strip_flags(r).startswith("(") and not strip_flags(r).startswith("(?")]
    cold = [(g, r) for g in groups for r in g["regexes"] if COLD_RE.match(strip_flags(r))]
    want = [a for _, r in regions for a in _alts(r)]
    for c, r in cold:
        inner = COLD_RE.sub("^(?!.*(", strip_flags(r), count=1)   # drop extra leading (?!.*xxx) guards
        if not inner.endswith(")).*"):
            raise ValueError(f"ini:{c['ln']} cold-group regex must look like ^(?!.*(...)).*")
        got = _alts(inner[len("^(?!.*"):-len(").*")])
        missing = [a for a in want if a not in got]
        extra = [a for a in got if a not in want]
        if missing or extra:
            raise SystemExit(f"ini:{c['ln']} {c['name']} 与地区组正则不同步：缺少 {missing}，多余 {extra}")
    # every premium-first regex must be "premium AND <that group's own region regex>"
    for g in groups:
        plain = [r for r in g["regexes"] if strip_flags(r).startswith("(") and not strip_flags(r).startswith("(?")]
        for r in g["regexes"]:
            b = strip_flags(r)
            if b.startswith("^(?=") and plain and not b.endswith(f"(?=.*{strip_flags(plain[0])})"):
                raise SystemExit(f"ini:{g['ln']} {g['name']} 的专线正则与该组地区正则不一致")
    check_private_nodes(groups, cold)
    return len(cold)


COLD_RE = re.compile(r"^\^(?:\(\?!\.\*[^()|]+\))*\(\?!\.\*\(")
PRIVATE_RE = re.compile(r"^\^([A-Za-z0-9_-]+)$")          # e.g. (?i)^233boy -> self-hosted node prefix


def check_private_nodes(groups, cold):
    """A group whose only regex is '^prefix' is a private pool (self-hosted VPS). Its nodes must be
    kept out of every automatic catch-all pool and every cold pool via (?!.*prefix)."""
    for g in groups:
        pref = [PRIVATE_RE.match(strip_flags(r)).group(1) for r in g["regexes"] if PRIVATE_RE.match(strip_flags(r))]
        for p in pref:
            guard = f"(?!.*{p})"
            pools = [(h, r) for h in groups if h["type"] != "select" for r in h["regexes"]
                     if strip_flags(r).endswith(".*") and h is not g] + list(cold)
            leaks = sorted({h["name"] for h, r in pools if guard not in r})
            if leaks:
                raise SystemExit(f"ini:{g['ln']} {g['name']}（前缀 {p}）的节点会漏进 {leaks}：给这些组的正则加上 {guard}")


def parents(d: str):
    """d, then each parent domain (a.b.c -> a.b.c, b.c, c)."""
    while True:
        yield d
        i = d.find(".")
        if i < 0:
            return
        d = d[i + 1:]


def depth(d: str) -> int:
    return d.count(".") + 1


class Clash:
    """First-match Clash model for domains (rank = effective rule position)."""

    def __init__(self):
        self.exact, self.suffix, self.keyword = {}, {}, []   # value -> (rank, policy, label)

    def add(self, kind, d, rank, pol, label):
        if kind == "keyword":
            self.keyword.append((rank, d, pol, label))
        else:
            (self.exact if kind == "exact" else self.suffix).setdefault(d, (rank, pol, label))

    def _best(self, d, include_exact):
        best = None
        if include_exact and d in self.exact:
            best = self.exact[d]
        for p in parents(d):
            h = self.suffix.get(p)
            if h and (best is None or h[0] < best[0]):
                best = h
        for (r, kw, pol, lab) in self.keyword:
            if best is not None and r > best[0]:
                break
            if kw in d:
                best = (r, pol, lab) if (best is None or r < best[0]) else best
                break
        return best

    def match(self, d):
        return self._best(d, True)


# ----------------------------------------------------------------------------- QX model
class QX:
    """Evaluates a domain under several plausible Quantumult X matching models.

    A*: local rules first (host > host-suffix > wildcard > keyword), then remote lists.
    B*: global type priority (host > suffix > wildcard > keyword), local before remote per type.
    D : like B but host-suffix = longest match across local+remote.
    E : list-major: local (in emitted order), then each remote list in file order.
    *deep = longest suffix inside a remote list; *file = first suffix line in file order.
    """
    MODELS = ("A-deep", "A-file", "B-deep", "B-file", "D", "E")

    def __init__(self, lex, lsx, lwild, lkw, remotes):
        self.lex, self.lsx, self.remotes = lex, lsx, remotes
        self.lwild = [(re.compile(fnmatch.translate(w)), p) for w, p in lwild]
        self.lkw = lkw

    # -- local
    def l_exact(self, d):
        return self.lex.get(d)

    def l_suffix(self, d):
        for p in parents(d):
            if p in self.lsx:
                return self.lsx[p], depth(p)
        return None

    def l_wild(self, d):
        for rx, p in self.lwild:
            if rx.match(d):
                return p
        return None

    def l_kw(self, d):
        for kw, p in self.lkw:
            if kw in d:
                return p
        return None

    def local(self, d):
        r = self.l_exact(d)
        if r:
            return r
        s = self.l_suffix(d)
        if s:
            return s[0]
        return self.l_wild(d) or self.l_kw(d)

    # -- remote, per type
    def r_host(self, d):
        for rl in self.remotes:
            if d in rl.host:
                return rl.policy
        return None

    def r_suffix_deep(self, d):
        for p in parents(d):
            for rl in self.remotes:
                if p in rl.suffix:
                    return rl.policy, depth(p)
        return None

    def r_suffix_list_deep(self, d):
        for rl in self.remotes:
            for p in parents(d):
                if p in rl.suffix:
                    return rl.policy
        return None

    def r_suffix_list_file(self, d):
        for rl in self.remotes:
            idx = [rl.suffix[p] for p in parents(d) if p in rl.suffix]
            if idx:
                return rl.policy
        return None

    def r_wild(self, d):
        for rl in self.remotes:
            for _, rx in rl.wildcard:
                if rx.match(d):
                    return rl.policy
        return None

    def r_kw(self, d):
        for rl in self.remotes:
            for _, kw in rl.keyword:
                if kw in d:
                    return rl.policy
        return None

    def r_typed(self, d, suffix_fn):
        return self.r_host(d) or suffix_fn(d) or self.r_wild(d) or self.r_kw(d)

    def r_file(self, d):
        for rl in self.remotes:
            best = None
            if d in rl.host:
                best = rl.host[d]
            for p in parents(d):
                if p in rl.suffix and (best is None or rl.suffix[p] < best):
                    best = rl.suffix[p]
            for i, kw in rl.keyword:
                if kw in d and (best is None or i < best):
                    best = i
            for i, rx in rl.wildcard:
                if (best is None or i < best) and rx.match(d):
                    best = i
            if best is not None:
                return rl.policy
        return None

    def evaluate(self, d):
        loc = self.local(d)
        res = {}
        res["A-deep"] = loc or self.r_typed(d, self.r_suffix_list_deep)
        res["A-file"] = loc or self.r_typed(d, self.r_suffix_list_file)
        res["E"] = loc or self.r_file(d)
        ls = self.l_suffix(d)
        for name, sfn in (("B-deep", self.r_suffix_list_deep), ("B-file", self.r_suffix_list_file)):
            res[name] = (self.l_exact(d) or self.r_host(d) or (ls[0] if ls else None) or sfn(d)
                         or self.l_wild(d) or self.r_wild(d) or self.l_kw(d) or self.r_kw(d))
        rs = self.r_suffix_deep(d)
        if ls and rs:
            suf = ls[0] if ls[1] >= rs[1] else rs[0]
        else:
            suf = (ls or rs or (None,))[0]
        res["D"] = (self.l_exact(d) or self.r_host(d) or suf
                    or self.l_wild(d) or self.r_wild(d) or self.l_kw(d) or self.r_kw(d))
        return res


# ----------------------------------------------------------------------------- build
def build():
    rules, groups, exclude = parse_ini()
    check_cold_group(groups)
    group_names = {g["name"] for g in groups}
    notes = []

    # effective order: rules after MATCH are dead in Clash; the user clearly wants them, so they
    # are moved in front of the GFW fallback (or MATCH) and this is reported.
    mi = next(i for i, r in enumerate(rules) if r["type"] == "MATCH")
    pre, post = rules[:mi], rules[mi + 1:]
    if post:
        gi = next((i for i, r in enumerate(pre) if r["type"] == "GEOSITE" and r["args"][0] == "gfw"), len(pre))
        for r in post:
            notes.append(f"ini:{r['ln']} `{r['raw']}` 位于 MATCH 之后（Clash 中永不生效），QX 中前移到 GFW 兜底之前使其生效")
        pre = pre[:gi] + post + pre[gi:]
    eff = pre + [rules[mi]]

    clash = Clash()
    base_exact, base_suffix = {}, {}          # domain -> label (policy filled later)
    lwild, lkw = [], []                       # (value, policy, label)
    ip_rules, remotes = [], []
    exact_src, suffix_src = set(), set()
    final = None

    for rank, r in enumerate(eff):
        t, a, pol = r["type"], r["args"], r["policy"]
        if pol not in group_names and pol not in BUILTIN.values():
            raise ValueError(f"ini:{r['ln']} unknown policy {pol}")
        label = f"{r['raw']}"
        if t == "GEOSITE":
            tag = a[0]
            ents = geosite(tag)
            for kind, d in ents:
                clash.add(kind, d, rank, pol, label)
                (exact_src if kind == "exact" else suffix_src).add(d)
            if tag in REMOTE_GEOSITE:
                url, name = REMOTE_GEOSITE[tag]
                remotes.append(RemoteList(url, pol, name))
            else:
                for kind, d in ents:
                    (base_exact if kind == "exact" else base_suffix).setdefault(d, label)
                for w in REGEXP_SUPPLEMENT.get(tag, []):
                    if all(w != x[0] for x in lwild):
                        lwild.append((w, pol, label))
        elif t in ("DOMAIN-SUFFIX", "DOMAIN", "DOMAIN-KEYWORD"):
            d = a[0].lower()
            kind = {"DOMAIN-SUFFIX": "suffix", "DOMAIN": "exact", "DOMAIN-KEYWORD": "keyword"}[t]
            clash.add(kind, d, rank, pol, label)
            if kind == "keyword":
                lkw.append((d, pol, label))
            else:
                (exact_src if kind == "exact" else suffix_src).add(d)
                (base_exact if kind == "exact" else base_suffix).setdefault(d, label)
        elif t == "GEOIP":
            tag = a[0]
            if tag in GEOIP_INLINE:
                for net in geoip(tag):
                    if net.version == 4 and net.overlaps(FAKE_IP):
                        notes.append(f"GEOIP,{tag}: 跳过 {net}（QX 的 fake-ip 占位网段，不能写分流）")
                        continue
                    if net.version == 6 and int(net.network_address) == 0:
                        continue          # ::/127 (unspecified+loopback) never enters the tunnel
                    ip_rules.append(("ip-cidr" if net.version == 4 else "ip6-cidr", str(net), pol, label))
            elif tag == "cn":
                ip_rules.append(("geoip", "cn", pol, label))
            elif tag in GEOIP_ASN:
                for asn in GEOIP_ASN[tag]:
                    ip_rules.append(("ip-asn", asn, pol, label + f"（QX 无 {tag} geoip 标签，用 ASN{asn} 等价）"))
            else:
                notes.append(f"`{r['raw']}`：MetaCubeX GeoIP 中不存在 `{tag}` 标签（Clash 中该条也匹配不到任何 IP），已略过")
        elif t in ("IP-CIDR", "IP-CIDR6"):
            net = ipaddress.ip_network(a[0], strict=False)
            ip_rules.append(("ip-cidr" if net.version == 4 else "ip6-cidr", str(net), pol, label))
        elif t in ("DST-PORT", "SRC-PORT"):
            notes.append(f"`{r['raw']}`：Quantumult X 没有端口类分流规则，无法转换（见 README）")
        elif t == "MATCH":
            final = pol
        else:
            raise ValueError(f"ini:{r['ln']} unsupported rule type {t}")

    # dedupe ip rules (first wins, same as Clash)
    seen, ipr = set(), []
    for x in ip_rules:
        if (x[0], x[1]) not in seen:
            seen.add((x[0], x[1]))
            ipr.append(x)
    ip_rules = ipr

    # -------- local rules: policy = what Clash decides for that exact domain / its sub-domains
    L_ex, L_sx, pinned = {}, {}, set()
    for d, lab in base_suffix.items():
        m = clash._best("zz-qx-probe." + d, False)      # policy for sub-domains of d
        L_sx[d] = (m[1], m[2])
        me = clash.match(d)
        if me[1] != m[1]:
            L_ex.setdefault(d, (me[1], me[2]))
    for d, lab in base_exact.items():
        m = clash.match(d)
        L_ex[d] = (m[1], m[2])

    # -------- prune redundant base rules (verified afterwards anyway)
    def nearest_ancestor(d, table):
        for p in list(parents(d))[1:]:
            if p in table:
                return p
        return None

    for d in sorted(list(L_sx), key=depth):
        anc = nearest_ancestor(d, L_sx)
        if anc and L_sx[anc][0] == L_sx[d][0]:
            del L_sx[d]
    for d in list(L_ex):
        cov = next((p for p in parents(d) if p in L_sx), None)
        if cov and L_sx[cov][0] == L_ex[d][0]:
            del L_ex[d]

    # -------- candidates for verification
    for rl in remotes:
        exact_src.update(rl.host)
        suffix_src.update(rl.suffix)
    probes = {"zz-qx-probe." + d: d for d in suffix_src}
    exact_c = exact_src | suffix_src

    def mk_qx():
        return QX({d: v[0] for d, v in L_ex.items()}, {d: v[0] for d, v in L_sx.items()},
                  [(w, p) for w, p, _ in lwild], [(k, p) for k, p, _ in lkw], remotes)

    def expected(d):
        m = clash.match(d)
        return m

    remote_labels = {r["raw"] for r in eff if r["type"] == "GEOSITE" and r["args"][0] in REMOTE_GEOSITE}

    def check(q):
        bad = []
        for d in list(exact_c) + list(probes):
            m = expected(d)
            if m is None:
                continue
            _, want, lab = m
            res = q.evaluate(d)
            for model, got in res.items():
                if got == want:
                    continue
                # remote-only categories: a miss falls through to geoip/final exactly like
                # QX users expect; only a *wrong* hit is an error.
                if got is None and lab in remote_labels:
                    continue
                bad.append((d, model, got, want, lab))
                break
        return bad

    rounds = 0
    while True:
        rounds += 1
        bad = check(mk_qx())
        print(f"verify round {rounds}: {len(bad)} mismatches", file=sys.stderr)
        if not bad:
            break
        if rounds > 12:
            for b in bad[:30]:
                print("  ", b, file=sys.stderr)
            raise SystemExit("did not converge")
        for d, model, got, want, lab in bad:
            if d in probes:
                base = probes[d]
                L_sx[base] = (want, lab)
                pinned.add(("s", base))
            else:
                L_ex[d] = (want, lab)
                pinned.add(("e", d))

    return {
        "rules": rules, "eff": eff, "groups": groups, "exclude": exclude, "notes": notes,
        "L_ex": L_ex, "L_sx": L_sx, "pinned": pinned, "lwild": lwild, "lkw": lkw,
        "ip_rules": ip_rules, "remotes": remotes, "final": final, "clash": clash,
        "exact_c": exact_c, "probes": probes, "rounds": rounds,
    }


# ----------------------------------------------------------------------------- policy section
def strip_flags(rx: str) -> str:
    rx = rx.strip()
    if rx.startswith("(?i)"):
        rx = rx[4:]
    return rx


def group_regex(rxs, ex: str | None) -> str:
    """One QX server-tag-regex from one or more Clash member regexes (their union).
    QX orders matched servers itself, so the Clash "premium first" ordering cannot be kept."""
    if isinstance(rxs, str):
        rxs = [rxs]
    ex = strip_flags(ex) if ex else ex    # the whole regex already starts with (?i)
    exl = f"(?!.*(?:{ex}))" if ex else ""
    parts = []
    for rx in rxs:
        body = strip_flags(rx)
        if body in (".*", ""):
            parts = [".*"]
            break
        parts.append(body[1:] if body.startswith("^") else f".*(?:{body})")
    out = f"(?i)^{exl}" + (parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")")
    if "," in out:
        raise ValueError(f"comma in regex not allowed in QX: {out}")
    re.compile(out)
    return out


QX_NOTES = []


def policy_lines(groups, exclude):
    by = {g["name"]: g for g in groups}
    order, seen = [], set()

    def visit(n):
        if n in seen or n not in by:
            return
        seen.add(n)
        for m in by[n].get("members") or []:
            visit(m)
        order.append(n)

    for g in groups:
        visit(g["name"])
    urls = [g["url"] for g in groups if g["type"] != "select"]
    check_url = max(set(urls), key=urls.count) if urls else "http://www.gstatic.com/generate_204"
    lines = []
    for n in order:
        g = by[n]
        mem, rxs = g["members"], g["regexes"]
        for m in mem:
            if m not in by and m not in ("direct", "reject", "proxy"):
                raise ValueError(f"group {n}: unknown member {m}")
        if rxs:
            # regex groups: QX cannot mix server-tag-regex with named members. The only named
            # member allowed is the trailing REJECT placeholder (guards Clash against an empty
            # group turning into DIRECT); QX leaves an empty regex group empty, so drop it.
            if [m for m in mem if m != "reject"]:
                raise ValueError(f"group {n}: regex + named members unsupported in QX")
            rx = group_regex(rxs, exclude)
            if g["type"] == "select":
                lines.append(f"static={n}, server-tag-regex={rx}")
            elif g["type"] == "fallback":
                lines.append(f"available={n}, server-tag-regex={rx}")
            else:
                lines.append(f"url-latency-benchmark={n}, server-tag-regex={rx}, "
                             f"check-interval={g['interval']}, tolerance={g['tolerance']}, alive-checking=false")
        elif g["type"] == "select":
            lines.append(f"static={n}, " + ", ".join(mem))
        elif g["type"] == "fallback":
            # QX "available" may only contain servers, not other policies -> static, default = first.
            # A private pool (self-hosted VPS) may not be imported on the phone and an empty QX policy
            # breaks traffic, so never make it the static default.
            private = {h["name"] for h in groups if any(PRIVATE_RE.match(strip_flags(r)) for r in h["regexes"])}
            qmem = [m for m in mem if m not in private] + [m for m in mem if m in private]
            QX_NOTES.append(f"{n}：Clash 中是 fallback（{' → '.join(mem)}），QX 的 available 不能嵌套策略组，"
                            f"改为 static（默认 {qmem[0]}，跨组兜底需手动切）")
            lines.append(f"static={n}, " + ", ".join(qmem))
        else:
            raise ValueError(f"group {n}: url-test with only named members unsupported in QX")
    return lines, check_url


# ----------------------------------------------------------------------------- emit
def emit(B):
    L_ex, L_sx, clash = B["L_ex"], B["L_sx"], B["clash"]
    rank_of = {r["raw"]: i for i, r in enumerate(B["eff"])}

    def sx_parent_policy(d, include_self):
        ps = list(parents(d)) if include_self else list(parents(d))[1:]
        for p in ps:
            if p in L_sx:
                return L_sx[p][0]
        return None

    ov_ex, ov_sx, cat = [], [], {}
    for d, (pol, lab) in L_ex.items():
        cp = sx_parent_policy(d, True)
        if cp is not None and cp != pol:
            ov_ex.append((d, pol, lab))
        else:
            cat.setdefault(lab, []).append(("host", d, pol))
    for d, (pol, lab) in L_sx.items():
        pp = sx_parent_policy(d, False)
        if pp is not None and pp != pol:
            ov_sx.append((d, pol, lab))
        else:
            cat.setdefault(lab, []).append(("host-suffix", d, pol))

    ov_ex.sort(key=lambda x: x[0])
    ov_sx.sort(key=lambda x: (-depth(x[0]), x[0]))

    out = []
    w = out.append
    w("# ---- 0. 冲突覆盖：更具体的子域名与父域名策略不同（按 Clash 先匹配原则计算），必须放最前 ----")
    for d, pol, lab in ov_ex:
        w(f"host, {d}, {pol}")
    for d, pol, lab in ov_sx:
        w(f"host-suffix, {d}, {pol}")
    for lab in sorted(cat, key=lambda l: rank_of.get(l, 10 ** 6)):
        items = cat[lab]
        items.sort(key=lambda x: (x[0] != "host-suffix", x[1]))
        w("")
        w(f"# ---- {lab} -> {items[0][2]}  ({len(items)} 条) ----")
        for t, d, pol in items:
            w(f"{t}, {d}, {pol}")
    w("")
    w("# ---- 通配 / 关键词（v2fly regexp 条目的近似 + ini 中的 DOMAIN-KEYWORD）----")
    for v, pol, lab in B["lwild"]:
        w(f"host-wildcard, {v}, {pol}")
    for v, pol, lab in B["lkw"]:
        w(f"host-keyword, {v}, {pol}")
    w("")
    w("# ---- IP 规则（顺序同 Clash；QX 不支持 no-resolve 参数，IP 规则只在域名规则都未命中后才会解析判断）----")
    last = None
    for t, v, pol, lab in B["ip_rules"]:
        if lab != last:
            w(f"# {lab}")
            last = lab
        w(f"{t}, {v}, {pol}")
    w("")
    w(f"final, {B['final']}")
    return out


def load_subs():
    """qx-subscriptions.local: one per line; either a bare URL or a full QX server_remote line.
    Bare URL -> QX-native (…list=quantumultx / target=quanx) gets opt-parser=false, others true."""
    if not os.path.exists(SUBS):
        return []
    out = []
    for i, raw in enumerate(open(SUBS, encoding="utf-8"), 1):
        s = raw.strip()
        if not s or s.startswith(("#", ";", "//")):
            continue
        if "," in s:
            out.append(s)
            continue
        native = re.search(r"(list|target|flag|client)=(quantumultx|quanx|qx)\b", s, re.I)
        tag = "机场" if not out else f"机场{len(out) + 1}"
        out.append(f"{s}, tag={tag}, update-interval=86400, opt-parser={'false' if native else 'true'}, enabled=true")
    return out


def render(B, subs=None):
    QX_NOTES.clear()
    pol_lines, check_url = policy_lines(B["groups"], B["exclude"])
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    w = L.append
    w("# Quantumult X 配置 —— 由 tools/qx_gen.py 从 openclash-rules.ini 自动生成，请勿手改后再重新生成覆盖")
    w(f"# 生成时间 {now}；GEOSITE/GEOIP 数据：MetaCubeX/meta-rules-dat（与 OpenClash 相同）；")
    w("# 远程规则：blackmatrix7/ios_rule_script（GEOSITE,cn / GEOSITE,gfw 体量太大，用其 QX 原生列表代替）")
    w("#")
    w("# 使用：导入后在 [server_remote] 添加你的机场订阅（或 App 内 节点 → 引用 → 添加）。")
    w("#       策略组靠节点名正则自动归类，无需手动把节点加入各组。")
    for n in B["notes"]:
        w(f"# 注意：{n}")
    w("# 注意：地区组在 Clash 中是「专线优先」的 fallback；QX 的 available 按订阅顺序选第一个可用节点，无法按正则排序")
    for n in QX_NOTES:
        w(f"# 注意：{n}")
    w("")
    w("[general]")
    w("network_check_url=http://connect.rom.miui.com/generate_204")
    w(f"server_check_url={check_url}")
    w("server_check_timeout=5000")
    w("resource_parser_url=https://raw.githubusercontent.com/KOP-XIAO/QuantumultX/master/Scripts/resource-parser.js")
    w("dns_exclusion_list=*.cmpassport.com, *.jegotrip.com.cn, *.icitymobile.mobi, id6.me, *.lan, *.local, *.ts.net")
    w("fallback_udp_policy=reject")
    w(";excluded_routes=192.168.0.0/16, 172.16.0.0/12, 10.0.0.0/8, 100.64.0.0/10")
    w("")
    w("[dns]")
    w("no-ipv6")
    w("server=223.5.5.5")
    w("server=119.29.29.29")
    w("")
    w("[policy]")
    L.extend(pol_lines)
    w("")
    w("[server_remote]")
    if subs:
        w("# 来自 qx-subscriptions.local（本文件含订阅地址，已 gitignore，切勿提交/公开）")
        L.extend(subs)
    else:
        w("# 订阅不写在这里：App 内 节点 → 引用(订阅) → 添加；或写进 qx-subscriptions.local 后重新生成 quantumultx.private.conf")
        w(";https://example.com/your-subscription, tag=机场, update-interval=86400, opt-parser=true, enabled=true")
    w("")
    w("[server_local]")
    w("")
    w("[filter_remote]")
    for rl in B["remotes"]:
        w(f"{rl.url}, tag={rl.tag}, force-policy={rl.policy}, update-interval=86400, opt-parser=false, enabled=true")
    w("")
    w("[filter_local]")
    L.extend(emit(B))
    w("")
    for s in ("[rewrite_remote]", "[rewrite_local]", "[task_local]", "[http_backend]"):
        w(s)
        w("")
    w("[mitm]")
    w("")
    return "\n".join(L)


# ----------------------------------------------------------------------------- re-verify emitted text
def reverify(B, text):
    """Parse the emitted [filter_local] back and re-run models + a true list-order model."""
    sec, rows = None, []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            sec = s
            continue
        if sec == "[filter_local]" and s and not s.startswith(("#", ";")):
            rows.append([p.strip() for p in s.split(",")])
    lex, lsx, lw, lk = {}, {}, [], []
    for r in rows:
        if r[0] == "host":
            if r[1] in lex:
                raise SystemExit(f"duplicate host {r[1]}")
            lex[r[1]] = r[2]
        elif r[0] == "host-suffix":
            if r[1] in lsx:
                raise SystemExit(f"duplicate host-suffix {r[1]}")
            lsx[r[1]] = r[2]
        elif r[0] == "host-wildcard":
            lw.append((r[1], r[2]))
        elif r[0] == "host-keyword":
            lk.append((r[1], r[2]))
    q = QX(lex, lsx, lw, lk, B["remotes"])
    clash = B["clash"]
    remote_labels = {r["raw"] for r in B["eff"] if r["type"] == "GEOSITE" and r["args"][0] in REMOTE_GEOSITE}
    cands = list(B["exact_c"]) + list(B["probes"])
    bad = 0
    for d in cands:
        m = clash.match(d)
        if not m:
            continue
        for model, got in q.evaluate(d).items():
            if got != m[1] and not (got is None and m[2] in remote_labels):
                bad += 1
                if bad < 10:
                    print("  REVERIFY MISMATCH", d, model, got, m, file=sys.stderr)
                break
    # literal list-order over local rows (first match wins) for a random sample + all local keys
    dom_rows = [r for r in rows if r[0] in ("host", "host-suffix", "host-wildcard", "host-keyword")]
    compiled = []
    for r in dom_rows:
        if r[0] == "host-wildcard":
            compiled.append((r[0], re.compile(fnmatch.translate(r[1])), r[2]))
        else:
            compiled.append((r[0], r[1], r[2]))

    def listorder(d):
        for t, v, p in compiled:
            if (t == "host" and d == v) or (t == "host-suffix" and (d == v or d.endswith("." + v))) \
                    or (t == "host-wildcard" and v.match(d)) or (t == "host-keyword" and v in d):
                return p
        return None

    rnd = random.Random(7)
    sample = set(lex) | set(lsx) | {"zz-qx-probe." + d for d in lsx}
    sample |= set(rnd.sample(cands, min(3000, len(cands))))
    lo_bad = 0
    for d in sample:
        lo = listorder(d)
        if lo is not None and lo != q.local(d):
            lo_bad += 1
            if lo_bad < 10:
                print("  LIST-ORDER MISMATCH", d, lo, q.local(d), file=sys.stderr)
    print(f"reverify: {len(cands)} candidates x {len(QX.MODELS)} models -> {bad} mismatches; "
          f"list-order sample {len(sample)} -> {lo_bad} mismatches", file=sys.stderr)
    if bad or lo_bad:
        raise SystemExit("re-verification failed")
    return q


SPOT = ["chatgpt.com", "api.openai.com", "cdn.oaistatic.com", "claude.ai", "api.anthropic.com",
        "gemini.google.com", "aistudio.google.com", "generativelanguage.googleapis.com",
        "copilot.microsoft.com", "api.githubcopilot.com", "www.perplexity.ai", "www.google.com",
        "www.google.cn", "fonts.gstatic.com", "www.youtube.com", "rr1---sn-abc.googlevideo.com",
        "www.netflix.com", "www.tiktok.com", "www.instagram.com", "x.com", "twitter.com",
        "github.com", "raw.githubusercontent.com", "www.speedtest.net", "store.steampowered.com",
        "steamcdn-a.akamaihd.net", "discord.com", "web.whatsapp.com", "www.reddit.com",
        "www.facebook.com", "dash.cloudflare.com", "www.apple.com", "www.icloud.com",
        "login.microsoftonline.com", "www.bing.com", "www.adobe.com", "t.me", "telegram.org",
        "www.baidu.com", "www.qq.com", "www.bilibili.com", "controlplane.tailscale.com",
        "derp10.tailscale.com", "myhost.tail1234.ts.net", "wccczy.online", "www.cathaypacific.com",
        "www.wikipedia.org", "localhost", "router.asus.com", "example.invalid",
        "claude.com", "notebooklm.google.com", "bard.google.com", "sydney.bing.com",
        "googleads.g.doubleclick.net", "pagead2.googlesyndication.com", "ad.doubleclick.net"]


def main():
    B = build()
    text = render(B)
    q = reverify(B, text)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    subs = load_subs()
    if subs:
        with open(OUT_PRIVATE, "w", encoding="utf-8", newline="\n") as f:
            f.write(render(B, subs))
        print(f"wrote {OUT_PRIVATE} with {len(subs)} subscription(s) (gitignored)", file=sys.stderr)
    else:
        print(f"no {os.path.basename(SUBS)} -> only public {os.path.basename(OUT)} written", file=sys.stderr)
    n_local = sum(1 for l in text.split("[filter_local]")[1].split("[rewrite_remote]")[0].splitlines()
                  if l.strip() and not l.startswith("#"))
    print(f"wrote {OUT}: {len(text.encode())} bytes, filter_local rules={n_local}, "
          f"pins={len(B['pinned'])}, rounds={B['rounds']}", file=sys.stderr)
    print(f"{'domain':38s} {'Clash':22s} QX(A/B/D/E)", file=sys.stderr)
    for d in SPOT:
        m = B["clash"].match(d)
        want = m[1] if m else "(geoip/final)"
        got = sorted({str(v) for v in q.evaluate(d).values()})
        flag = "" if (m is None or got == [want]) else "   <-- DIFF"
        print(f"{d:38s} {want:22s} {'/'.join(got)}{flag}", file=sys.stderr)


if __name__ == "__main__":
    main()
