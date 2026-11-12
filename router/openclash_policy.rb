#!/usr/bin/env ruby
# frozen_string_literal: true

require 'yaml'

module OpenClashPolicy
  AI = ['🤖 ChatGPT', '🧠 AI'].freeze
  STABLE = '🔐 AI 稳定'
  VPS = '🏠 自建 VPS'
  REGIONS = ['🇸🇬 SG', '🇯🇵 JP', '🇺🇸 US'].freeze
  AI_PATH = [VPS, *REGIONS].freeze
  DOWNLOAD = '📥 游戏下载'
  NETFLIX = '🎥 Netflix'
  BLOCK = 'REJECT'
  SAFE_TYPES = %w[vless vmess trojan ss ssr hysteria2 tuic wireguard anytls].freeze

  def self.template(path)
    groups = {}
    rules = []
    File.foreach(path, encoding: 'UTF-8') do |line|
      key, value = line.strip.split('=', 2)
      if key == 'custom_proxy_group'
        name, type, *members = value.split('`')
        group = { 'name' => name, 'type' => type }
        if type != 'select'
          times = members.pop.split(',')
          group['url'] = members.pop
          group['interval'] = Integer(times[0])
          group['tolerance'] = Integer(times[2]) if type == 'url-test' && times[2]
        end
        group['proxies'] = members.grep(/^\[\]/).map { |m| m[2..] }
        filters = members.reject { |m| m.start_with?('[]') }
        raise "Multiple filters: #{name}" if filters.length > 1
        group['filter'] = filters.first if filters.first
        groups[name] = group
      elsif key == 'ruleset'
        policy, raw = value.split(',[]', 2)
        raise 'Only inline rules are supported' unless raw
        parts = raw.split(',')
        no_resolve = parts.last == 'no-resolve' ? parts.pop : nil
        rules << (parts + [policy, no_resolve]).compact.join(',')
      end
    end
    raise 'Invalid rule count or final MATCH' unless rules.length <= 64 && rules.last&.start_with?('MATCH,')
    [groups, rules]
  end

  def self.approved_names(groups)
    rx = groups.fetch(VPS).fetch('filter')
    # Deliberately accept literal names only, never a wildcard or a country-name filter.
    body = rx[/\A\^\(\?:([A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+)*)\)\$\z/, 1] ||
           rx[/\A\^([A-Za-z0-9_-]+)\$\z/, 1]
    raise 'AI whitelist must be anchored literal names' unless body
    body.split('|').uniq
  end

  def self.policy(rule)
    parts = rule.split(',')
    parts.pop if parts.last == 'no-resolve'
    parts.last
  end

  def self.region_errors(desired, configured, runtime = nil, nodes = {})
    errors = []
    REGIONS.each do |region|
      expected = desired.fetch(region).fetch('proxies')
      root = configured[region] || {}
      errors << "#{region}: unexpected region members" unless root['proxies'] == expected
      errors << "#{region}: dynamic root is forbidden" if %w[use filter include-all include-all-proxies include-all-providers].any? { |k| root.key?(k) }
      if runtime
        actual = runtime[region] || {}
        errors << "#{region}: unexpected runtime members" unless actual['all'] == expected && expected.include?(actual['now'])
      end
      expected.each do |name|
        leaf = configured[name] || {}
        filter = desired.fetch(name).fetch('filter')
        unless leaf['filter'] == filter && leaf.fetch('proxies', []).empty? &&
               !leaf.fetch('use', []).empty? &&
               %w[include-all include-all-proxies include-all-providers].none? { |k| leaf.key?(k) }
          errors << "#{name}: unsafe regional node filter"
        end
        next unless runtime
        pool = runtime[name] || {}
        members = pool.fetch('all', [])
        errors << "#{name}: missing pool or selection" if members.empty? || !members.include?(pool['now'])
        members.each do |member|
          next if member == BLOCK
          node = nodes[member] || {}
          if !Regexp.new(filter).match?(member) || node.key?('all') ||
             %w[direct compatible pass reject rejectdrop].include?(node.fetch('type', '').downcase)
            errors << "#{name}: unapproved regional member #{member}"
          end
        end
      end
    end
    errors
  end

  def self.speedtest_rules(template_rules)
    template_rules.select { |r| r.start_with?('DOMAIN,fast.com,', 'DOMAIN-SUFFIX,nflxvideo.net,') }
  end

  def self.validate_low_memory(config, template_rules)
    tags = template_rules.grep(/^GEOSITE,/).map { |r| r.split(',')[1] }
    forbidden = %w[category-ads-all gfw adobe netflix tiktok spotify]
    config.fetch('rules').each do |rule|
      type, tag = rule.split(',', 3)
      raise "Small profile cannot load GEOIP,#{tag}" if type == 'GEOIP' && tag != 'cn'
      if type == 'GEOSITE' && (!tags.include?(tag) || forbidden.include?(tag))
        raise "Small profile cannot load GEOSITE,#{tag}"
      end
    end
  end

  def self.apply(config, template_path, low_memory: false)
    desired, template_rules = template(template_path)
    if low_memory
      validate_low_memory(config, template_rules)
      config['geodata-mode'] = false
      config['geodata-loader'] = 'memconservative'
      # 路由器场景没有进程匹配可谈;关掉省 CPU/内存。
      config['find-process-mode'] = 'off'
      # 面板钉选不持久化,省一点存储与内存(代价:重启后选择重置)。
      config['profile'] = (config['profile'] || {}).merge('store-selected' => false)
      # 若内核自行更新 geo 数据,间隔拉长到 7 天:更新窗口内新旧两份 geosite.dat 并存,是内存峰值时刻。
      config['geo-update-interval'] = 168 if config['geo-auto-update']
    end
    approved = approved_names(desired)
    groups = config.fetch('proxy-groups')
    rules = config.fetch('rules')
    raise 'This overlay requires the my-routering profile' unless AI.all? { |n| groups.any? { |g| g['name'] == n } }
    region_issues = region_errors(desired, groups.to_h { |g| [g['name'], g] })
    raise region_issues.join('; ') unless region_issues.empty?
    nodes = config.fetch('proxies', [])
    raise 'Duplicate top-level proxy names' unless nodes.map { |n| n['name'] }.uniq.length == nodes.length
    allowed = nodes.select { |n| approved.include?(n['name']) }
    allowed.each do |node|
      unless SAFE_TYPES.include?(node['type']) && !node['dialer-proxy']
        raise "Unapproved transport or dialer for #{node['name']}"
      end
    end
    (AI + [VPS, STABLE, DOWNLOAD]).each do |name|
      replacement = Marshal.load(Marshal.dump(desired.fetch(name)))
      if name == VPS
        replacement.delete('filter')
        replacement['proxies'] = allowed.map { |n| n['name'] }
        replacement['proxies'] = [BLOCK] if replacement['proxies'].empty?
      elsif name == STABLE
        raise 'Unsafe AI fallback path' unless replacement['proxies'] == AI_PATH && !replacement.key?('filter')
      elsif AI.include?(name)
        raise "Unsafe AI template: #{name}" unless replacement['proxies'] == [STABLE, BLOCK]
      end
      index = groups.index { |g| g['name'] == name }
      index ? groups[index] = replacement : groups << replacement
    end
    groups.each { |g| g['empty-fallback'] = BLOCK }
    config.fetch('proxy-providers', {}).each_value do |provider|
      provider['health-check'] = {
        'enable' => false, 'url' => 'https://cp.cloudflare.com/generate_204',
        'interval' => 600, 'timeout' => 10_000
      }
    end

    # Keep unrelated OpenClash custom rules, but known AI domains must precede DIRECT bypasses.
    ai_rules = template_rules.select { |r| AI.include?(policy(r)) }
    test_rules = speedtest_rules(template_rules)
    raise 'Missing explicit fast.com policy in template' unless test_rules.any? { |r| r.start_with?('DOMAIN,fast.com,') }
    test_prefixes = test_rules.map { |r| r.split(',')[0, 2].join(',') + ',' }
    rules.reject! { |r| AI.include?(policy(r)) || test_prefixes.any? { |prefix| r.start_with?(prefix) } }
    download_index = rules.index { |r| r.start_with?('GEOSITE,category-game-platforms-download,') }
    raise 'Missing download rule' unless download_index
    rules[download_index] = "GEOSITE,category-game-platforms-download,#{DOWNLOAD}"
    config['rules'] = ai_rules + test_rules + rules
    config
  end

  def self.atomic_write(path, config)
    temporary = "#{path}.policy-#{Process.pid}.tmp"
    begin
      File.open(temporary, File::WRONLY | File::CREAT | File::EXCL, File.stat(path).mode & 0o777) do |file|
        file.write(config.to_yaml)
        file.flush
        file.fsync
      end
      File.rename(temporary, path)
    ensure
      File.unlink(temporary) if File.exist?(temporary)
    end
  end

  def self.fetch(config, resource)
    address = config.fetch('external-controller')
    raise 'Unsupported controller address' unless address.match?(/\A(?:localhost|\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-fA-F:]+\]):\d+\z/)
    address = address.sub(/\A0\.0\.0\.0:/, '127.0.0.1:').sub(/\A\[::\]:/, '[::1]:')
    args = ['curl', '-fsS', '--max-time', '8', '-H',
            "Authorization: Bearer #{config['secret']}", "http://#{address}/#{resource}"]
    raw = IO.popen(args, err: File::NULL, &:read)
    raise "API unavailable: #{resource}" unless $?.success?
    YAML.safe_load(raw)
  end

  def self.audit(config, template_path, proxies, providers, api_rules)
    desired, template_rules = template(template_path)
    approved = approved_names(desired)
    errors, warnings, info = [], [], []
    configured = config.fetch('proxy-groups').to_h { |g| [g['name'], g] }
    nodes = providers.values.flat_map { |p| p.fetch('proxies', []) }.to_h { |p| [p['name'], p] }
    nodes.merge!(proxies)
    proxies.each do |name, group|
      next unless group['all']
      fixed = group['fixed']
      warnings << "#{name}: stale fixed selection #{fixed}" if fixed && !fixed.empty? && !group['all'].include?(fixed)
      warnings << "#{name}: empty pool (REJECT)" if group['all'] == [BLOCK]
      errors << "#{name}: COMPATIBLE member" if name != 'GLOBAL' && group['all'].include?('COMPATIBLE')
      next unless configured.key?(name)
      errors << "#{name}: missing empty-fallback REJECT" unless group['emptyFallback'] == BLOCK
      statuses = group['all'].map { |n| nodes[n]&.fetch('alive', nil) }
      info << "#{name}: now=#{group['now']}; node-state up=#{statuses.count(true)} down=#{statuses.count(false)} unknown=#{statuses.count(nil)}"
    end
    AI.each do |name|
      group = proxies[name] || {}
      errors << "#{name}: unsafe members" unless group['all'] == [STABLE, BLOCK]
      errors << "#{name}: unsafe selection" unless [STABLE, BLOCK].include?(group['now'])
    end
    stable = proxies[STABLE] || {}
    errors << 'AI stable: missing or unapproved members' unless stable['all'] == AI_PATH
    errors << 'AI stable: unsafe selection' unless AI_PATH.include?(stable['now'])
    vps = proxies[VPS] || {}
    errors << 'AI VPS: missing or unapproved members' if !vps['all'] || vps['all'].empty? ||
                                                       (vps['all'] - approved - [BLOCK]).any?
    errors << 'AI VPS: unsafe selection' unless (approved + [BLOCK]).include?(vps['now'])
    [STABLE, VPS].each do |name|
      group = configured[name] || {}
      errors << "#{name}: dynamic provider/filter is forbidden" if %w[use filter include-all include-all-proxies include-all-providers].any? { |k| group.key?(k) }
    end
    errors.concat(region_errors(desired, configured, proxies, nodes))
    config.fetch('proxies', []).select { |n| approved.include?(n['name']) }.each do |node|
      errors << "AI node #{node['name']}: unsafe transport/dialer" unless SAFE_TYPES.include?(node['type']) && !node['dialer-proxy']
    end
    ai_rules = api_rules.take_while { |r| AI.include?(r['proxy']) }
    errors << 'AI domain rules must precede other routing rules' unless ai_rules.any? { |r| r['payload'] == 'openai' } &&
                                                                                     ai_rules.any? { |r| r['payload'] == 'category-ai-!cn' }
    speed = api_rules.index { |r| r['payload'] == 'category-speedtest' }
    speedtest_rules(template_rules).each do |rule|
      type, payload, target = rule.split(',')
      api_type = { 'DOMAIN' => 'Domain', 'DOMAIN-SUFFIX' => 'DomainSuffix' }.fetch(type)
      index = api_rules.index { |r| r['type'] == api_type && r['payload'] == payload && r['proxy'] == target }
      errors << "#{payload}: speedtest policy/order mismatch" unless index && speed && index < speed
    end
    errors << 'Download policy mismatch' unless api_rules.any? { |r| r['payload'] == 'category-game-platforms-download' && r['proxy'] == DOWNLOAD }
    errors << 'Final rule is not Match' unless api_rules.last&.fetch('type', nil) == 'Match'
    [errors, warnings, info]
  end
end

if $PROGRAM_NAME == __FILE__
  mode, config_path, template_path, wait_seconds = ARGV
  begin
    config = YAML.load_file(config_path)
    case mode
    when 'apply', 'apply-small'
      OpenClashPolicy.atomic_write(config_path, OpenClashPolicy.apply(config, template_path, low_memory: mode == 'apply-small'))
      puts 'Policy applied: strict AI, empty-pool REJECT, downloads, template speedtest policy'
    when 'audit', 'audit-small'
      deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + Integer(wait_seconds || '0')
      loop do
        begin
          config = YAML.load_file(config_path)
          if mode == 'audit-small'
            _, small_rules = OpenClashPolicy.template(template_path)
            OpenClashPolicy.validate_low_memory(config, small_rules)
            raise 'Small profile must use MMDB and memconservative' unless config['geodata-mode'] == false &&
                                                                         config['geodata-loader'] == 'memconservative'
            raise 'Small profile must disable process matching' unless config['find-process-mode'] == 'off'
            raise 'Small profile must not persist panel selections' unless config.dig('profile', 'store-selected') == false
            raise 'Small profile geo auto-update must be weekly or off' if config['geo-auto-update'] &&
                                                                          config['geo-update-interval'].to_i < 168
          end
          proxies = OpenClashPolicy.fetch(config, 'proxies').fetch('proxies')
          providers = OpenClashPolicy.fetch(config, 'providers/proxies').fetch('providers')
          rules = OpenClashPolicy.fetch(config, 'rules').fetch('rules')
          errors, warnings, info = OpenClashPolicy.audit(config, template_path, proxies, providers, rules)
          if errors.empty? || Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
            info.each { |line| puts "INFO #{line}" }
            warnings.each { |line| puts "WARN #{line}" }
            errors.each { |line| puts "FAIL #{line}" }
            puts "Audit: #{errors.length} errors, #{warnings.length} warnings"
            exit(errors.empty? ? 0 : 1)
          end
        rescue StandardError
          raise if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
        end
        sleep 2
      end
    else
      raise 'Usage: openclash_policy.rb apply|apply-small|audit|audit-small CONFIG TEMPLATE [WAIT_SECONDS]'
    end
  rescue StandardError => e
    warn "Policy error: #{e.class}: #{e.message}"
    exit 1
  end
end
