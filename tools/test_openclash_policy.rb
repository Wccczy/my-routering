#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative '../router/openclash_policy'
require 'ipaddr'

TEMPLATE = ARGV[0] ? File.expand_path(ARGV[0]) : File.expand_path('../openclash-rules.ini', __dir__)
P = OpenClashPolicy
checks = 0
assert = lambda do |condition, message|
  raise message unless condition
  checks += 1
end

desired, template_rules = P.template(TEMPLATE)
small = File.basename(TEMPLATE) == 'openclash-rules-small.ini'
apply = ->(config) { P.apply(config, TEMPLATE, low_memory: small) }
base = {
  'secret' => 'fixture-only',
  'proxies' => [{ 'name' => 'CF-WS-443', 'type' => 'vless', 'server' => 'example.invalid' }],
  'proxy-providers' => { 'airport' => { 'type' => 'http', 'url' => 'https://example.invalid/sub' } },
  'proxy-groups' => desired.values.map { |g| g.key?('filter') ? g.merge('use' => ['airport']) : g },
  'rules' => ['DOMAIN,custom.example,DIRECT'] + template_rules
}
copy = ->(value) { Marshal.load(Marshal.dump(value)) }
result = apply.call(copy.call(base))
groups = result['proxy-groups'].to_h { |g| [g['name'], g] }
assert.call(groups[P::VPS]['proxies'] == ['CF-WS-443'], 'VPS whitelist must use the approved static node')
assert.call(groups[P::STABLE]['proxies'] == P::AI_PATH, 'AI fallback order must be VPS, SG, JP, US')
assert.call(!groups[P::VPS].key?('use') && !groups[P::VPS].key?('filter'), 'VPS must not import provider nodes')
assert.call(groups.values.all? { |g| g['empty-fallback'] == 'REJECT' }, 'Every configured group needs empty-pool protection')
assert.call(apply.call(copy.call(result)) == result, 'Overlay must be idempotent')
assert.call(result['secret'] == base['secret'], 'Do not change controller credentials')
assert.call(result['rules'].include?('DOMAIN,custom.example,DIRECT'), 'Preserve unrelated custom rules')
assert.call(result['rules'].first(7).all? { |r| P::AI.include?(P.policy(r)) }, 'AI must precede port and direct rules')
assert.call(result['proxy-providers']['airport']['health-check']['enable'] == false, 'Keep provider health checks disabled')
if small
  assert.call(result['find-process-mode'] == 'off', 'Small profile must disable process matching')
  assert.call(result.dig('profile', 'store-selected') == false, 'Small profile must not persist panel selections')
  assert.call(!result['geo-update-interval'] || result['geo-update-interval'] >= 168,
              'Small profile geo updates stay weekly or off')
  nested = result['proxy-groups'].count { |g| g['name'] =~ /(?:KR|PH) (?:专线|全部)/ }
  assert.call(nested.zero?, 'KR/PH must not nest into line/-all subgroups on small')
else
  assert.call(!result.key?('find-process-mode'), 'Full profile keeps default process matching')
  assert.call(result['proxy-groups'].count { |g| g['name'] =~ /(?:KR|PH) (?:专线|全部)/ } == 4,
              'Full profile keeps KR/PH nesting')
end
fast_policy = small ? '🐟 漏网之鱼' : P::NETFLIX
fast = result['rules'].index("DOMAIN,fast.com,#{fast_policy}")
speed = result['rules'].index { |r| r.start_with?('GEOSITE,category-speedtest,') }
assert.call(fast < speed, 'fast.com must follow its template policy, not generic speedtest')
assert.call(result['rules'].include?("GEOSITE,category-game-platforms-download,#{P::DOWNLOAD}"), 'Downloads need their own policy')

missing = copy.call(base)
missing['proxies'] = []
missing['proxy-providers']['airport']['payload'] = [{ 'name' => 'CF-WS-443', 'type' => 'vless' }]
missing_result = apply.call(missing)
blocked = missing_result['proxy-groups'].find { |g| g['name'] == P::VPS }
assert.call(blocked['proxies'] == ['REJECT'], 'Missing approved static node must block even if a provider spoofs its name')
assert.call(missing_result['proxy-groups'].find { |g| g['name'] == P::STABLE }['proxies'] == P::AI_PATH,
            'Missing VPS must preserve regional failover')
%w[direct reject].each do |type|
  unsafe = copy.call(base)
  unsafe['proxies'][0]['type'] = type
  begin
    apply.call(unsafe)
    raise 'Expected unsafe type rejection'
  rescue RuntimeError => e
    assert.call(e.message.include?('Unapproved transport'), "Unexpected type validation: #{e.message}")
  end
end
unsafe = copy.call(base)
unsafe['proxies'][0]['dialer-proxy'] = '🌐 Default'
begin
  apply.call(unsafe)
  raise 'Expected dialer rejection'
rescue RuntimeError => e
  assert.call(e.message.include?('dialer'), 'Unapproved dialer must be rejected')
end
begin
  P.approved_names(P::VPS => { 'filter' => '.*' })
  raise 'Expected wildcard rejection'
rescue RuntimeError => e
  assert.call(e.message.include?('literal names'), 'Wildcards cannot be an AI whitelist')
end

runtime = groups.transform_values do |g|
  code = %w[SG JP US].find { |c| g['name'].include?(c) }
  sample = code ? "#{code} IEPL fixture" : 'provider-node'
  members = g['proxies'].empty? ? [sample] : g['proxies']
  { 'all' => members, 'now' => members.first, 'fixed' => '', 'emptyFallback' => 'REJECT' }
end
providers = { 'airport' => { 'proxies' => ['provider-node', 'SG IEPL fixture', 'JP IEPL fixture', 'US IEPL fixture'].map do |name|
  { 'name' => name, 'alive' => true, 'type' => 'Vless' }
end } }
api_rules = result['rules'].map do |r|
  parts = r.split(',')
  { 'type' => { 'GEOSITE' => 'GeoSite', 'DOMAIN' => 'Domain', 'DOMAIN-SUFFIX' => 'DomainSuffix', 'MATCH' => 'Match' }.fetch(parts[0], parts[0]),
    'payload' => parts[1], 'proxy' => P.policy(r) }
end
errors, warnings, info = P.audit(result, TEMPLATE, runtime, providers, api_rules)
assert.call(errors.empty? && warnings.empty?, "Valid runtime rejected: #{errors + warnings}")
assert.call(info.any? { |s| s.include?('up=1') }, 'Read provider node state from the provider API')
_, _, unknown_info = P.audit(result, TEMPLATE, runtime, {}, api_rules)
assert.call(unknown_info.any? { |s| s.include?('unknown=1') }, 'Missing node state must remain unknown')
stale = copy.call(runtime)
stale['🇸🇬 SG']['fixed'] = 'removed-node'
_, warnings, = P.audit(result, TEMPLATE, stale, providers, api_rules)
assert.call(warnings.any? { |s| s.include?('stale fixed') }, 'Detect stale selections without mutating them')
assert.call(stale['🇸🇬 SG']['fixed'] == 'removed-node', 'Audit must not repair selections')
leak = copy.call(runtime)
leak[P::AI.first]['all'] << 'DIRECT'
errors, = P.audit(result, TEMPLATE, leak, providers, api_rules)
assert.call(errors.any? { |s| s.include?('unsafe members') }, 'Detect AI escape paths')
leak = copy.call(runtime)
leak[P::STABLE]['all'] << '🇭🇰 HK'
errors, = P.audit(result, TEMPLATE, leak, providers, api_rules)
assert.call(errors.any? { |s| s.include?('unapproved members') }, 'Hong Kong must remain outside the AI chain')
leak = copy.call(runtime)
leak['🇸🇬 SG 全部']['all'] << 'HK IEPL fixture'
errors, = P.audit(result, TEMPLATE, leak, providers, api_rules)
assert.call(errors.any? { |s| s.include?('unapproved regional member') }, 'Detect cross-region node injection')
unsafe = copy.call(base)
unsafe['proxy-groups'].find { |g| g['name'] == '🇸🇬 SG' }['proxies'] << 'DIRECT'
begin
  apply.call(unsafe)
  raise 'Expected regional DIRECT rejection'
rescue RuntimeError => e
  assert.call(e.message.include?('unexpected region members'), 'A region cannot introduce DIRECT')
end
template_rules.each do |rule|
  type, value = rule.split(',')
  next unless %w[IP-CIDR IP-CIDR6].include?(type)
  assert.call(IPAddr.new(value).to_s == IPAddr.new(value.split('/')[0]).to_s, "Noncanonical CIDR: #{value}")
end
desired.each_value do |group|
  group['proxies'].each do |member|
    assert.call(desired.key?(member) || %w[DIRECT REJECT].include?(member), "Missing member: #{member}")
  end
end
if small
  full, = P.template(File.expand_path('../openclash-rules.ini', __dir__))
  # KR/PH 在低内存版刻意去嵌套,是唯一允许差异的共享组。
  (desired.keys & full.keys).each do |name|
    next if ['🇰🇷 KR', '🇵🇭 PH'].include?(name)
    assert.call(desired[name] == full[name], "Shared policy differs: #{name}")
  end
  assert.call((full.keys - desired.keys).sort ==
              ['🎵 TikTok', P::NETFLIX, '🎧 Spotify', '🛑 广告拦截', '🇰🇷 KR 专线', '🇰🇷 KR 全部', '🇵🇭 PH 专线', '🇵🇭 PH 全部'].sort,
              'Small profile must only omit the intended application groups')
  assert.call(!groups.key?(P::NETFLIX), 'Do not restore the Netflix group on the small router')
  assert.call(result['rules'].include?("DOMAIN-SUFFIX,nflxvideo.net,#{fast_policy}"), 'Keep fast.com test traffic on the same policy')
  assert.call(result['geodata-mode'] == false && result['geodata-loader'] == 'memconservative', 'Small profile needs MMDB and conservative loader')
  %w[GEOSITE,category-ads-all GEOSITE,gfw GEOSITE,netflix GEOIP,private GEOIP,telegram].each do |rule|
    oversized = copy.call(base)
    oversized['rules'].unshift("#{rule},DIRECT")
    begin
      apply.call(oversized)
      raise 'Expected oversized ruleset rejection'
    rescue RuntimeError => e
      assert.call(e.message.include?('Small profile cannot load'), "Unexpected low-memory validation: #{e.message}")
    end
  end
  assert.call(template_rules.include?('IP-CIDR,91.108.8.0/21,📨 Telegram,no-resolve') &&
              template_rules.include?('IP-CIDR,91.108.16.0/21,📨 Telegram,no-resolve'), 'Preserve both exact Telegram networks')
end
puts "PASS #{checks} policy checks; rules=#{template_rules.length}, groups=#{groups.length}, profile=#{File.basename(TEMPLATE)}"
