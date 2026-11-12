# my-routering

| 文件 | 用途 |
| --- | --- |
| `openclash-rules.ini` | OpenClash / subconverter 用的分流模板（源头，改规则只改这里） |
| `openclash-rules-small.ini` | 🪶 低内存路由器专用精简模板（480MB 设备防 OOM，见文件头注；策略组与全量版一致，仅砍大规则集） |
| `quantumultx.conf` | **Quantumult X 完整配置**（不含订阅，可公开），由脚本从 ini 生成 |
| `qx-subscriptions.local` | 机场订阅地址，每行一个（**gitignore，勿提交**） |
| `quantumultx.private.conf` | 带订阅的 QX 配置，存在 `qx-subscriptions.local` 时生成（**gitignore，勿提交**） |
| `tools/qx_gen.py` | 生成器：`python3 tools/qx_gen.py [--refresh]` |
| `tools/qx_lint.py` | 独立语法/引用检查：`python3 tools/qx_lint.py [文件] [--offline]` |
| `clash-verge.yaml` | Clash Verge (Rev) 全局扩展配置（Merge），由脚本从 ini 生成，桌面端用全量规则 |
| `tools/verge_gen.py` | 生成器：`python3 tools/verge_gen.py`（改规则仍只改 ini，再重跑） |
| `router/openclash_custom_overwrite.sh` | 路由器侧覆写钩子的存档版（关闭 provider 级健康检查，见下文「路由器侧」；改完要同步到 `/etc/openclash/custom/`） |
| `router/openclash_policy.rb` | 两版共用的策略覆写及只读核验，精简版使用 `apply-small` / `audit-small` |
| `router/openclash_small_overwrite.sh` | 小路由器专用钩子，不设置大网关的 IP/MTU；需在目标设备另行安装 |
| `tools/test_openclash_policy.rb` | 白名单、空组、幂等性、规则优先级及运行核验回归测试 |

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
| 节点池 | 🇭🇰 HK / 🇹🇼 TW / 🇯🇵 JP / 🇸🇬 SG / 🇺🇸 US / 🇰🇷 KR / 🇵🇭 PH | fallback 600s | = [「专线」组, 「全部」组]：专线（IEPL/IPLC/专线/Premium）有可用的就用专线，全挂才用全部节点；挂了才切，出口 IP 不随延迟抖动 |
| 节点池 | 🇭🇰 HK 专线 / 🇭🇰 HK 全部 …（每区 2 个） | fallback 600s | 上面地区组的内部层，也可以手动选 |
| 节点池 | ♻️ 自动选择 | url-test 600s / 容差 300ms | 只测速 7 个地区组，不再直接测速全部节点；只在地区间明显更快时切换 |
| 节点池 | 🧊 冷门节点 / 🧊 冷门自动 | select / url-test | 七个地区之外的机场节点（排除自建 VPS），手动挑 or 自动 |
| 节点池 | 🏠 自建 VPS | fallback 600s | 精确节点白名单，当前 `CF-WS-443` |
| 节点池 | 🧭 手动选择 | select | 全部节点（含自建 VPS） |
| 专用出口 | 🔐 AI 稳定 | fallback 600s | VPS → 新加坡 → 日本 → 美国；地区内专线优先，空组 REJECT，不直连 |
| 兜底链 | 🌐 Default | fallback 600s | HK → JP → SG → TW → US → KR → PH → 🧊 冷门自动 |
| 应用 | AI、ChatGPT | select | 仅 🔐 AI 稳定 / REJECT，出口链只包含 VPS、SG、JP、US，不引用其他通用池 |
| 应用 | 游戏下载 | select | 默认 DIRECT，下载 CDN 异常时可手动切代理 |
| 应用 | Google、YouTube、X、Instagram、TikTok、GitHub、Apple | select | 默认地区稳定组（TikTok 默认 JP） |
| 应用 | 其余代理类 / 🚀 代理兜底 / 🐟 漏网之鱼 | select | 默认 ♻️ 自动选择 |
| 应用 | 测速、Steam、Microsoft | select | 默认 DIRECT |

- **多订阅**：OpenClash 订阅转换里一行一个地址，合并为一个配置。重名节点 subconverter 会自动加 ` 2` 后缀；
  同地区同线路按订阅顺序排列，所以**最稳定的机场放第一行**。
- **转换后端的限制（重要）**：OpenClash 默认后端 `api.asailor.org`（SubConverter-Extended）遇到订阅链接会生成
  `proxy-providers`，每个正则组变成 `use: 订阅` + `filter: 第一段正则`，并把组里的 `[]成员` 排到订阅节点**前面**。
  所以本 ini 里**一个正则组只写一段正则、不混放 `[]` 成员**；需要优先级时拆成嵌套组（如「专线」+「全部」）。
  组为空时默认的 `COMPATIBLE` 实际是直连；全量版路由器覆写为 `empty-fallback: REJECT`。
  `qx_gen.py` 会校验正则和成员混用约束，运行核验检查空组保护。
- **不要用 load-balance**：同一网站多出口 IP 会触发风控；池内节点挂掉时被分到它的站点全部失败，直到下次健康检查。
- **可选 Smart 内核**：OpenClash「Smart 设置」开启后会把所有 url-test/load-balance 组（本配置只有 ♻️ 自动选择、
  🧊 冷门自动）替换为 smart 组；fallback 组不受影响。

## 路由器侧（OpenClash 0.47.156 / iStoreOS）

本 ini 覆盖规则和策略组；OpenClash 自身还会改写一部分参数。踩过的坑记在这里，避免重复取证。

### 严格 AI 与持久化策略（2026-11-12）

本节描述 `192.168.100.1` 已部署的全量版 `sum-air.yaml`。精简模板及配套脚本已在本地同步，
尚未部署到小路由器，安装差异见下方「低内存路由器」。

- AI、ChatGPT 的批准出口链为 VPS → 新加坡 → 日本 → 美国。机场节点来自现有三地区池，
  同地区仍优先专线；不允许 HK、TW、其他地区、全节点手动、Default 或 DIRECT。
  节点按机场名称分类，名称和探针成功本身不证明真实出口地区或 AI 解锁。
- 自建 VPS 白名单由 ini 的 `🏠 自建 VPS` 精确正则定义，当前为 `^CF-WS-443$`，
  多节点可写 `^(?:CF-WS-443|CF-WS-2)$`。网关只从顶层 `proxies` 导入 VPS，拒绝
  provider 同名注入、非代理类型及带 `dialer-proxy` 的 VPS。
  VPS 缺失或失败后可尝试 SG / JP / US；全部失败不降级直连。
- 覆写验证三地区组的层级和过滤规则，运行核验继续检查区域池中的节点名称，
  避免通过中间组重新引入其他地区或 DIRECT。它不代替对机场真实出口的验证。
- 已识别的 AI 域名规则前置，所有配置策略组设置 `empty-fallback: REJECT`。
  限制作用于进入 mihomo 且被 AI 规则识别的连接，并非设备级防火墙隔离；
  未收录域名、客户端自行绕过网关、无法识别的裸 IP 不在此保证范围内。
- `category-game-platforms-download` 使用「游戏下载」，默认 DIRECT。
  fast.com 显式使用 Netflix，避免页面和测试服务器选择不同策略；其他测速工具独立选择。
- 覆写钩子每次启动/配置更新都应用本地副本 `my-routering-policy.ini` 中的 AI 和下载策略，
  因而远程 GitHub 模板尚未更新也不会撤销这几项保护。其余规则仍来自订阅转换结果。
  修改这些策略后需要重新部署本地副本；不要只编辑生成的 YAML。
- 钩子自动启动一次有 60 秒等待上限的只读核验，输出 `/tmp/openclash-policy-audit.log`。
  核验不会测速、重启或清除选择；无效 `fixed`、空组等告警需要人工判断。
  节点健康从 `/providers/proxies` 读取，缺失状态按 unknown 处理，不能把组级失败等同全池失败。

测试及部署（部署前备份已有脚本和配置）：

```sh
ruby tools/test_openclash_policy.rb
scp router/openclash_policy.rb router/openclash_custom_overwrite.sh root@192.168.100.1:/etc/openclash/custom/
scp openclash-rules.ini root@192.168.100.1:/etc/openclash/custom/my-routering-policy.ini
ssh root@192.168.100.1 'ruby /etc/openclash/custom/openclash_policy.rb audit /etc/openclash/sum-air.yaml /etc/openclash/custom/my-routering-policy.ini'
```

上传文件本身不会重新加载当前连接；应先校验候选 YAML，再通过 OpenClash 重载或内核配置 API 加载。
AI 配置生效后核验菜单、实际出口及旧连接；其他应用的有效手动选择不应批量清除。

### 1. 「覆写设置」三项必须留空（=0）

`/usr/share/openclash/yml_rules_change.sh` 每次生成配置时，会把**所有** url-test/fallback/load-balance 组的
`url`/`interval`/`tolerance`、以及**所有** provider 的 `health-check.url`/`interval`，覆盖成「覆写设置」里的值：

| uci key | 旧值 | 现值 |
| --- | --- | --- |
| `openclash.config.urltest_address_mod` | `https://www.gstatic.com/generate_204` | `0`（空） |
| `openclash.config.urltest_interval_mod` | `300` | `0`（空） |
| `openclash.config.tolerance` | `150` | `0`（空） |

只要非 0，ini 里的测速地址/间隔/容差就是「装饰品」（2026-10-10 改完 ini、更新订阅却毫无变化，原因即此）。
查当前值：`uci show openclash | grep -E "urltest|tolerance"`。
另外：`custom_proxy_group` 里 interval 后的 **timeout 值 subconverter 不会写进配置**（生成的 yaml 里
`timeout:` 计数为 0），实际超时是内核默认值——`600,10` 的 `10` 是无效的。

### 2. provider（订阅）级健康检查已在路由器上关闭

ini 管不到 `proxy-providers.health-check`（由转换后端写成 gstatic + 300s + 5s 超时）。而它在这台路由器上
**会把大量可用节点误判成 Down**：

- 2026-10-11 实测：209 个节点里 138 个被判失败（66%）。
- 抽 16 个「被判死」节点复测：11 个 cf/8s 通、7 个 gstatic/5s 通、**0 个两种都不通**。
- 节点历史里到处是 `0,0,0,0,0,0,0,46,0,0` 这种「只成功一次」的形态；真死节点不可能偶尔干净成功 46ms。
- 放宽为 cloudflare + 600s + 10s 后仍 83/83 失败，而同一时刻**组级检查 31/31 通过** →
  判定是批量测速风暴自身造成的假死（机场节点名里也写着"批量测试可能导致 GFW 干扰连接"）。

处理：`router/openclash_custom_overwrite.sh`（存档版）落到 `/etc/openclash/custom/openclash_custom_overwrite.sh`，
即 OpenClash 官方钩子（在它自己脚本之后运行），把 provider 的 `health-check.enable` 改为 `false`；
`url/interval/timeout` 仍写成 cloudflare/600s/10s，将来若重新开启也不会退回 gstatic/5s。
组级检查（600s / cloudflare）照常负责可用性判定。

```sh
scp router/openclash_custom_overwrite.sh root@192.168.100.1:/etc/openclash/custom/openclash_custom_overwrite.sh
ssh root@192.168.100.1 'chmod +x /etc/openclash/custom/openclash_custom_overwrite.sh;
  sh -n /etc/openclash/custom/openclash_custom_overwrite.sh &&
  rm -f /tmp/openclash.change && /etc/init.d/openclash restart'
# 生效验证：日志出现 "Tip: Provider Health-Check Disabled (blocks: N, disabled: N)"，
# 且生成的 yaml 里 5 个 provider 都是 enable: false
```

> 覆写脚本会作用于**每个** provider，所以新增订阅也自动生效；改完 ini 只需在面板更新订阅，
> 不用再动路由器。

### 3. 排查命令（mihomo API，secret 见生成的 yaml）

```sh
A="Authorization: Bearer <secret>"; C=http://192.168.100.1:9090
# 各 provider 节点数与已记录的「最近一次失败」数（无历史不是失败）
curl -s -H "$A" $C/providers/proxies | jq '.providers | to_entries[] | select(.value.vehicleType=="HTTP")
  | [.key, (.value.proxies|length), ([.value.proxies[]|select((.history|length)>0 and (.history|last|.delay)==0)]|length)]'
# 用指定 URL 强制复测某组全部成员（会刷新节点状态，可把 fallback 从死节点上挪开）
G=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=""))' '🇹🇼 TW 全部')
curl -s -H "$A" "$C/group/$G/delay?timeout=8000&url=https%3A%2F%2Fcp.cloudflare.com%2Fgenerate_204"
```

`cache.db`（`/etc/openclash/history/<配置名>.db`）会持久化节点状态与手动选择：重启/更新后可能带着旧的
「dead」标记或旧的手动选择（例如 `🍎 Apple` / `🔎 Google` 被固定在 `🇹🇼 TW`），必要时用上面的 `/group/.../delay` 刷一次。

### 4. 已知残留问题（属真实故障，不是误杀）

- `Provider_B10CBD`（`nvenix.shop` 订阅）长期拉到 0 个节点，日志报 `net/http: TLS handshake timeout`。
- `🇹🇼 TW 专线` 整池（如 `IEPL 台湾-01 | x1`，服务器 `twdx1.cdnflow.help:9378`）曾整段时间全部超时，
  组级 fallback 会自动落到 `🇹🇼 TW 全部`；这类问题只能等机场修或手动换地区。

## 低内存路由器

`openclash-rules-small.ini` 当前为 **60 条规则、43 个策略组、21 个 GEOSITE 分类**。
规则条数多于全量版，是因为 Telegram 用静态 CIDR 替代 GEOIP 分类，不意味着内存更多。
已同步 AI 的 VPS → SG → JP → US、游戏下载切换、Steam 代理例外及 Adobe 移除；
不恢复广告、GFW、Netflix、TikTok、Spotify 分类及特殊 GEOIP。
fast.com 与主要测速域名 `nflxvideo.net` 共用「漏网之鱼」，无需 Netflix 分类。
`91.108.8.0/21` 和 `91.108.16.0/21` 不能合并为一个对齐的 `/20`，现已分开。

### 配套安装

以下文件仅完成本地同步，尚未在 Cudy 上测试或部署。不要直接覆盖另一台设备原有的自定义钩子，
先备份并合并其中的设备特有设置；也不要把大网关的控制器 IP、MTU、provider 改名逻辑复制过去。

1. 确认小路由器内核支持 `empty-fallback`，转换配置采用 `proxy-providers` + `use/filter` 模式。
2. 将 `router/openclash_policy.rb` 放到 `/etc/openclash/custom/openclash_policy.rb`。
3. 将精简 ini 放到 `/etc/openclash/custom/my-routering-small.ini`，订阅转换也使用精简模板。
4. 合并/安装 `router/openclash_small_overwrite.sh` 为 `/etc/openclash/custom/openclash_custom_overwrite.sh`。
5. 校验候选 YAML 后重载，再执行核验；把命令里的路径替换成实际生效配置。

```sh
# 本地回归测试，不接触路由器
ruby tools/test_openclash_policy.rb
ruby tools/test_openclash_policy.rb openclash-rules-small.ini

# 在小路由器上，启动稳定后按实际路径执行
ruby /etc/openclash/custom/openclash_policy.rb audit-small \
  /etc/openclash/实际配置名.yaml /etc/openclash/custom/my-routering-small.ini
```

小路由器钩子会设置 `geodata-mode: false`、`geodata-loader: memconservative`、
`find-process-mode: off`、`profile.store-selected: false`（内核自行更新 geo 时再强制
`geo-update-interval: 168`，更新窗口新旧两份 geosite.dat 并存是内存峰值时刻）、
`empty-fallback: REJECT`，关闭 provider 级批量健康检查，并应用 AI/下载/测速策略。
KR/PH 在低内存版不拆「专线/全部」嵌套，各为单地区组（正则同全量版，冷门池约束不变）。
若发现输入配置重新加入被删掉的大分类或非 `cn` 的 GEOIP，会拒绝加载候选配置，避免误用全量模板。
仅修改 ini 不会自动获得这些运行时设置。VPS 不存在时它的子组 REJECT，AI 可继续尝试批准地区。
小路由器默认不在启动时并行运行 Ruby 核验，保留手动核验以降低启动峰值。

### 进一步优化

- **先减少实际订阅节点数量。** 优先在机场端筛选需要的地区/线路，少导入几个完整订阅。
  仅给策略组加 `filter`，通常不会删除 provider 已经解析的其他节点，不能当成等量节省内存。
  不要只看节点名称就过滤所有含 `Direct/CDN` 的条目，之前已观察到其中存在可用节点。
- **最大的域名集合仍是 `cn`。** 本地缓存中它约 11.1 万条，仅供判断量级，并非当前设备实测。
  下一阶段可考虑将大型域名集合改为 Mihomo 的 MRS rule-provider，并核查 OpenClash
  的 `oc-cn-domain`/Fake-IP 过滤是否重复承载类似数据；需先确认内核、转换后端及 DNS 策略兼容性。
  不直接删除 `GEOSITE,cn`，否则部分国内域名可能落到代理，改变现有分流。
- **控制更新与检测峰值。** 避免订阅、Geo 数据更新和全节点测速同时进行；
  保留现有 600 秒组级检测，不为追求更快切换盲目缩短间隔。内存紧张时可关闭不用的订阅/地区，
  但同步调整引用和冷门池正则；单删几个菜单组通常不如减少节点和大型数据集有效。
- **运行方式也会影响内存。** 若实际使用 gVisor，可比较 system 栈的占用和兼容性，
  但切换前需测试 UDP、游戏和 Tailscale。不要未经测量就设置很低的 `GOMEMLIMIT`，
  它不等于进程 RSS 硬上限，过低会增加 GC 压力。

验收应覆盖冷启动、订阅更新、Geo 更新和实际高负载，记录 `/proc/<PID>/status` 的
`VmRSS/VmHWM`、`/proc/meminfo` 的 `MemAvailable` 及 OOM 日志。
旧注释中的 150–220MB 只是历史估算，本次未在低内存硬件上测量，不作为内存承诺。

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
- url-test 组对应 `url-latency-benchmark`，间隔/容差同上表；`server_check_url` / `server_check_timeout`
  取 ini 中非 select 组的众数（现在是 `https://cp.cloudflare.com/generate_204` 与 10000ms，即 `600,10` 里的 10 秒）。
  注意 QX 只有**一个**全局测速地址，所以 Clash 里「AI 组保留 gstatic」的例外在 QX 无法表达。
- fallback 地区组对应 `available`，但 QX 按订阅顺序选第一个可用节点，**无法做到“专线优先”**。
- QX 的 `available` 不能嵌套策略组，所以 🌐 Default 在 QX 里是 static（默认 HK），跨地区兜底需手动切。
  🔐 AI 稳定在 QX 中也为 static，菜单仅 VPS / SG / JP / US，默认 VPS；
  手机没有导入 `CF-WS-443` 时需手动选择批准地区，无法自动跨地区回退。
  QX 仅按节点标签过滤，不具备网关上 VPS「只取顶层节点」的附加保护；
  此次部署不更新手机，生成文件仅做同步，手机端行为仍须单独验证。
- 🧊 冷门节点 / 🧊 冷门自动 的负向正则必须等于 7 个地区组正则的并集，专线正则也必须和本组地区正则一致；
  🏠 自建 VPS 使用精确名称；其 `CF-WS` 前缀仍在 🧊 冷门组里用 `(?!.*CF-WS)` 排除；♻️ 自动选择只引用 7 个地区组。
  `qx_gen.py` 每次生成都会校验，不同步直接报错并列出差异。
- 🛑 广告拦截（`GEOSITE,category-ads-all`，默认 reject）排在国内直连之前，会一并拦掉国内 App 的广告/统计域名
  （如 `app-measurement.com`、穿山甲、广点通）。某个 App 异常时先把该组切到 direct 排查。

## 修改规则后重新生成

```sh
python3 tools/qx_gen.py --refresh   # 拉最新 geo 数据并生成 + 自校验（有 qx-subscriptions.local 时同时生成 private 版）
python3 tools/qx_lint.py            # 语法、策略引用、远程列表可用性、节点正则检查
python3 tools/qx_lint.py quantumultx.private.conf --offline
python3 tools/verge_gen.py          # 重新生成 Clash Verge 扩展配置
```

## Clash Verge（桌面）

`clash-verge.yaml` 是 **Merge 全局扩展配置**，不是完整配置：节点来自你在 Verge 里导入的订阅。
用法：订阅作主 profile，在「订阅右键 → 编辑 Merge」（或全局扩展配置）里粘贴本文件内容，
或用 URL 导入本仓库 raw 地址。桌面端内存充足，规则与 `openclash-rules.ini` 全量版一致（含广告/gfw/Netflix）。

与路由器管线的差异（详见 `tools/verge_gen.py` 头注）：

- 正则组改为 mihomo 原生 `include-all: true` + `filter`（Verge 的节点是内联 proxies，无 provider 限制）。
- `🏠 自建 VPS` 附带 REJECT 兜底成员：订阅里没有 `CF-WS-443` 时该组探活失败，
  AI 链自动跳过它，不会像 COMPATIBLE 那样退化成直连。
- 规则以 `prepend-rules` 前置并以自己的 MATCH 结尾，订阅自带规则永不生效。
- `exclude_remarks` 无法在此表达：含「流量/到期」的信息节点会出现在 🧭 手动选择 里（过滤组不受影响）。


## 防泄露

- 订阅、节点、路由器导出的配置一律不入库：`.gitignore` 已排除 `*.local`、`*.private.*`、`*.yaml/*.yml`、`*.bak`、`.env` 等。
- 提交前扫描：`git config core.hooksPath tools/git-hooks`（本仓库已启用），发现订阅 token、`vless://` 等节点链接、
  controller secret、GitHub token、私钥会直接阻止提交。
- ini 里保留的自建信息只有 Tailscale DERP 直连规则（`wccczy.online` / `8.148.145.218`），这是公网服务地址、不含凭据。
