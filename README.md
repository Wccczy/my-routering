# my-routering

| 文件 | 用途 |
| --- | --- |
| `openclash-rules.ini` | OpenClash / subconverter 用的分流模板（源头，改规则只改这里） |
| `quantumultx.conf` | **Quantumult X 完整配置**（不含订阅，可公开），由脚本从 ini 生成 |
| `qx-subscriptions.local` | 机场订阅地址，每行一个（**gitignore，勿提交**） |
| `quantumultx.private.conf` | 带订阅的 QX 配置，存在 `qx-subscriptions.local` 时生成（**gitignore，勿提交**） |
| `tools/qx_gen.py` | 生成器：`python3 tools/qx_gen.py [--refresh]` |
| `tools/qx_lint.py` | 独立语法/引用检查：`python3 tools/qx_lint.py [文件] [--offline]` |

## 导入 Quantumult X

> 订阅地址等同账号密码。仓库是公开的，**不要把带订阅的配置推到 GitHub**。

推荐做法（二选一）：

- **A. 本地文件导入（带订阅，一步到位）**：把 `quantumultx.private.conf` 用 AirDrop / iCloud Drive
  放进「文件 → Quantumult X → Profiles」，App 里 配置文件 → 选中它。
- **B. 远程下载公开版 + App 内加订阅**：先 `git push` 让 `quantumultx.conf` 出现在
  `https://raw.githubusercontent.com/Wccczy/my-routering/main/quantumultx.conf`（**没推之前该链接是 404，
  导入会“没反应”**），然后 节点 → 引用(订阅) → 添加订阅。注意首次导入时手机还没代理，
  raw.githubusercontent.com 在国内可能下载失败，失败就用 A。

其他说明：

1. 该机场订阅带 `list=quantumultx`，已是 QX 原生格式，生成器自动设为 `opt-parser=false`（不依赖解析器脚本）；
   其他格式的订阅（Clash / V2Ray）裸 URL 会自动设为 `opt-parser=true`。
2. 订阅里一半节点是 `anytls` 协议，需要 Quantumult X ≥ 1.5.5；旧版本会看不到这些节点，请先更新 App。
3. 策略组按节点名正则自动归类（🇭🇰 HK / 🇹🇼 TW / 🇯🇵 JP / 🇸🇬 SG / 🇺🇸 US / 🧊 冷门节点 / 🧭 手动选择 / 🔄 自动选择），
   无需手动往组里加节点；ini 里 `exclude_remarks=` 的“流量/到期/官网…”信息节点在所有组中都被排除。

## 策略组设计（Clash）

| 层 | 组 | 类型 | 说明 |
| --- | --- | --- | --- |
| 节点池 | 🇭🇰 HK / 🇹🇼 TW / 🇯🇵 JP / 🇸🇬 SG / 🇺🇸 US / 🇰🇷 KR / 🇵🇭 PH | fallback 300s | = [「专线」组, 「全部」组]：专线（IEPL/IPLC/专线/Premium）有可用的就用专线，全挂才用全部节点；挂了才切，出口 IP 不随延迟抖动 |
| 节点池 | 🇭🇰 HK 专线 / 🇭🇰 HK 全部 …（每区 2 个） | fallback 300s | 上面地区组的内部层，也可以手动选 |
| 节点池 | ♻️ 自动选择 | url-test 300s / 容差 150ms | 只测速 7 个地区组，不再直接测速全部节点；只在地区间明显更快时切换 |
| 节点池 | 🧊 冷门节点 / 🧊 冷门自动 | select / url-test | 七个地区之外的机场节点（排除自建 VPS），手动挑 or 自动 |
| 节点池 | 🏠 自建 VPS | fallback 300s | 名称以 `233boy` 开头的节点，只给 AI 用 |
| 节点池 | 🧭 手动选择 | select | 全部节点（含自建 VPS） |
| 兜底链 | 🔐 AI 稳定 | fallback 300s | 自建 VPS → US → SG → JP → TW（不含 HK、不含 DIRECT） |
| 兜底链 | 🌐 Default | fallback 300s | HK → JP → SG → TW → US → KR → PH → 🧊 冷门自动 |
| 应用 | AI、ChatGPT | select | 默认 🔐 AI 稳定（VPS 优先、挂了自动落到机场 US）；也可直接选 🏠 自建 VPS 或 🧭 手动选择 |
| 应用 | Google、YouTube、X、Instagram、TikTok、GitHub、Apple | select | 默认地区稳定组（TikTok 默认 JP） |
| 应用 | 其余代理类 / 🚀 代理兜底 / 🐟 漏网之鱼 | select | 默认 ♻️ 自动选择 |
| 应用 | 测速、Steam、Microsoft | select | 默认 DIRECT |

- **多订阅**：OpenClash 订阅转换里一行一个地址，合并为一个配置。重名节点 subconverter 会自动加 ` 2` 后缀；
  同地区同线路按订阅顺序排列，所以**最稳定的机场放第一行**。
- **转换后端的限制（重要）**：OpenClash 默认后端 `api.asailor.org`（SubConverter-Extended）遇到订阅链接会生成
  `proxy-providers`，每个正则组变成 `use: 订阅` + `filter: 第一段正则`，并把组里的 `[]成员` 排到订阅节点**前面**。
  所以本 ini 里**一个正则组只写一段正则、不混放 `[]` 成员**；需要优先级时拆成嵌套组（如「专线」+「全部」）。
  组为空时 mihomo 自动填 `COMPATIBLE`（不可用、不会直连）。`qx_gen.py` 会校验这两条约束。
- **不要用 load-balance**：同一网站多出口 IP 会触发风控；池内节点挂掉时被分到它的站点全部失败，直到下次健康检查。
- **可选 Smart 内核**：OpenClash「Smart 设置」开启后会把所有 url-test/load-balance 组（本配置只有 ♻️ 自动选择、
  🧊 冷门自动）替换为 smart 组；fallback 组不受影响。

## 与 Clash 版的对应关系 / 差异

- 规则顺序与策略完全按 ini 计算：每条本地规则的策略 = Clash 先匹配原则下该域名会命中的策略。
  QX 的匹配优先级按规则类型（host > host-suffix > wildcard > keyword > IP）且本地优先于远程，
  和 Clash 的纯顺序不同，所以生成器会把“子域名策略与父域名不同”的冲突条目放到 `[filter_local]` 最前面，
  并在 6 种可能的 QX 匹配模型下对约 25 万个域名做回归校验，全部与 Clash 结果一致才会写出文件。
- GEOSITE 数据来自 MetaCubeX/meta-rules-dat（OpenClash 同源），直接内联；只有 `GEOSITE,cn`、`GEOSITE,gfw`
  体量太大，改用 blackmatrix7 的 QX 原生 `China.list`（direct）和 `Proxy.list`（🚀 代理兜底）远程引用，
  国内另有 `geoip, cn, direct` 兜底。
- 以下 ini 规则在 QX 中无法/无需表达（配置头部也有注释）：
  - `DST-PORT,3478`、`DST-PORT,41641`、`SRC-PORT,41641`：QX 没有端口类分流规则。iOS 上 QX 与 Tailscale
    同为 VPN，无法同时开启，这几条本来也用不上；Tailscale 的域名与 IP 段直连规则都已保留。
  - `GEOIP,adobe/tiktok/github/microsoft` 已从 ini 删除（MetaCubeX GeoIP 中没有这些标签）；
    `GEOIP,twitter`、`GEOIP,facebook` 直接内联为 ip-cidr。
  - `GEOIP,google` 有 8000+ 段，改为等价的 `ip-asn, 15169`。
  - `no-resolve`：QX 无此参数；QX 只有在所有域名规则都未命中时才会解析并判断 IP 规则。
  - 若 ini 里有规则写在 `MATCH` 之后（Clash 中永不生效），生成器会把它前移到 GFW 兜底之前并在配置头部提示。
- 策略组名中带不可见字符（U+FE0F 变体选择符 / U+200D 连接符）的已改名，避免在 App 内编辑或复制后“找不到策略”：
  `✈️ Cathay Pacific→🛫 Cathay Pacific`、`☁️ cloudflare→⛅ Cloudflare`、`🧑‍💻 GitHub→🐙 GitHub`、`♻️ 自动选择→🔄 自动选择`。
- url-test 组对应 `url-latency-benchmark`（间隔/容差同 ini），测速地址统一为 `server_check_url`。
- fallback 地区组对应 `available`，但 QX 按订阅顺序选第一个可用节点，**无法做到“专线优先”**。
- QX 的 `available` 不能嵌套策略组，所以 🔐 AI 稳定、🌐 Default 在 QX 里是 static（默认 US / HK），
  地区内仍会自动换节点，但跨地区兜底需要手动切。🏠 自建 VPS 在 QX 里排在 AI 稳定的最后
  （手机上可能没导入 VPS，空策略不能当默认）；手机上要走 VPS 就手动选它。
- 🧊 冷门节点 / 🧊 冷门自动 的负向正则必须等于 7 个地区组正则的并集，专线正则也必须和本组地区正则一致；
  🏠 自建 VPS 的前缀（`^233boy`）必须在 🧊 冷门组里用 `(?!.*233boy)` 排除；♻️ 自动选择只引用 7 个地区组，天然不含 VPS。
  `qx_gen.py` 每次生成都会校验，不同步直接报错并列出差异。
- 🛑 广告拦截（`GEOSITE,category-ads-all`，默认 reject）排在国内直连之前，会一并拦掉国内 App 的广告/统计域名
  （如 `app-measurement.com`、穿山甲、广点通）。某个 App 异常时先把该组切到 direct 排查。

## 修改规则后重新生成

```sh
python3 tools/qx_gen.py --refresh   # 拉最新 geo 数据并生成 + 自校验（有 qx-subscriptions.local 时同时生成 private 版）
python3 tools/qx_lint.py            # 语法、策略引用、远程列表可用性、节点正则检查
python3 tools/qx_lint.py quantumultx.private.conf --offline
```

## 防泄露

- 订阅、节点、路由器导出的配置一律不入库：`.gitignore` 已排除 `*.local`、`*.private.*`、`*.yaml/*.yml`、`*.bak`、`.env` 等。
- 提交前扫描：`git config core.hooksPath tools/git-hooks`（本仓库已启用），发现订阅 token、`vless://` 等节点链接、
  controller secret、GitHub token、私钥会直接阻止提交。
- ini 里保留的自建信息只有 Tailscale DERP 直连规则（`wccczy.online` / `8.148.145.218`），这是公网服务地址、不含凭据。
