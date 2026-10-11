#!/bin/sh
. /usr/share/openclash/ruby.sh
. /usr/share/openclash/log.sh
. /lib/functions.sh

# This script is called by /etc/init.d/openclash
# Add your custom overwrite scripts here, they will be take effict after the OpenClash own srcipts

LOG_OUT "Tip: Start Running Custom Overwrite Scripts..."
LOGTIME=$(echo $(date "+%Y-%m-%d %H:%M:%S"))
LOG_FILE="/tmp/openclash.log"
#Config Path
CONFIG_FILE="$1"

    #Simple Demo:
    #Key Overwrite Demo
    #1--config path
    #2--key name
    #3--value
    #ruby_edit "$CONFIG_FILE" "['redir-port']" "7892"
    #ruby_edit "$CONFIG_FILE" "['secret']" "123456"
    #ruby_edit "$CONFIG_FILE" "['dns']['enable']" "true"
    #ruby_edit "$CONFIG_FILE" "['dns']['proxy-server-nameserver']" "['https://doh.pub/dns-query','https://223.5.5.5:443/dns-query']"

    #Hash Overwrite Demo
    #1--config path
    #2--key name
    #3--hash type value
    #ruby_edit "$CONFIG_FILE" "['dns']['nameserver-policy']" "{'+.msftconnecttest.com'=>'114.114.114.114', '+.msftncsi.com'=>'114.114.114.114', 'geosite:gfw'=>['https://dns.cloudflare.com/dns-query', 'https://dns.google/dns-query#ecs=1.1.1.1/24&ecs-override=true'], 'geosite:cn'=>['114.114.114.114'], 'geosite:geolocation-!cn'=>['https://dns.cloudflare.com/dns-query', 'https://dns.google/dns-query#ecs=1.1.1.1/24&ecs-override=true']}"
    #ruby_edit "$CONFIG_FILE" "['sniffer']" "{'enable'=>true, 'parse-pure-ip'=>true, 'force-domain'=>['+.netflix.com', '+.nflxvideo.net', '+.amazonaws.com', '+.media.dssott.com'], 'skip-domain'=>['+.apple.com', 'Mijia Cloud', 'dlg.io.mi.com', '+.oray.com', '+.sunlogin.net'], 'sniff'=>{'TLS'=>nil, 'HTTP'=>{'ports'=>[80, '8080-8880'], 'override-destination'=>true}}}"

    #Map Edit Demo
    #1--config path
    #2--map name
    #3--key name
    #4--sub key name
    #5--value
    #ruby_map_edit "$CONFIG_FILE" "['proxy-providers']" "HK" "['url']" "http://test.com"

    #Hash Merge Demo
    #1--config path
    #2--key name
    #3--hash
    #ruby_merge_hash "$CONFIG_FILE" "['proxy-providers']" "'TW'=>{'type'=>'http', 'path'=>'./proxy_provider/TW.yaml', 'url'=>'https://gist.githubusercontent.com/raw/tw_clash', 'interval'=>3600, 'health-check'=>{'enable'=>true, 'url'=>'http://cp.cloudflare.com/generate_204', 'interval'=>300}}"
    #ruby_merge_hash "$CONFIG_FILE" "['rule-providers']" "'Reject'=>{'type'=>'http', 'behavior'=>'classical', 'url'=>'https://testingcf.jsdelivr.net/gh/dler-io/Rules@main/Clash/Provider/Reject.yaml', 'path'=>'./rule_provider/Reject', 'interval'=>86400}"

    #Array Edit Demo
    #1--config path
    #2--key name
    #3--match key name
    #4--match key value
    #5--target key name
    #6--target key value
    #ruby_arr_edit "$CONFIG_FILE" "['proxy-groups']" "['name']" "Proxy" "['type']" "Smart"
    #ruby_arr_edit "$CONFIG_FILE" "['dns']['nameserver']" "" "114.114.114.114" "" "119.29.29.29"

    #Array Insert Value Demo:
    #1--config path
    #2--key name
    #3--position(start from 0, end with -1)
    #4--value
    #ruby_arr_insert "$CONFIG_FILE" "['dns']['nameserver']" "0" "114.114.114.114"

    #Array Insert Hash Demo:
    #1--config path
    #2--key name
    #3--position(start from 0, end with -1)
    #4--hash
    #ruby_arr_insert_hash "$CONFIG_FILE" "['proxy-groups']" "0" "{'name'=>'Disney', 'type'=>'select', 'disable-udp'=>false, 'use'=>['TW', 'SG', 'HK']}"
    #ruby_arr_insert_hash "$CONFIG_FILE" "['proxies']" "0" "{'name'=>'HKG 01', 'type'=>'ss', 'server'=>'cc.hd.abc', 'port'=>'12345', 'cipher'=>'aes-128-gcm', 'password'=>'123456', 'udp'=>true, 'plugin'=>'obfs', 'plugin-opts'=>{'mode'=>'http', 'host'=>'microsoft.com'}}"
    #ruby_arr_insert_hash "$CONFIG_FILE" "['listeners']" "0" "{'name'=>'name', 'type'=>'shadowsocks', 'port'=>'12345', 'listen'=>'0.0.0.0', 'rule'=>'sub-rule-1', 'proxy'=>'proxy'}"

    #Array Insert Other Array Demo:
    #1--config path
    #2--key name
    #3--position(start from 0, end with -1)
    #4--array
    #ruby_arr_insert_arr "$CONFIG_FILE" "['dns']['proxy-server-nameserver']" "0" "['https://doh.pub/dns-query','https://223.5.5.5:443/dns-query']"

    #Array Insert From Yaml File Demo:
    #1--config path
    #2--key name
    #3--position(start from 0, end with -1)
    #4--value file path
    #5--value key name in #4 file
    #ruby_arr_add_file "$CONFIG_FILE" "['dns']['fallback-filter']['ipcidr']" "0" "/etc/openclash/custom/openclash_custom_fallback_filter.yaml" "['fallback-filter']['ipcidr']"

    #Delete Array Value Demo:
    #1--config path
    #2--key name
    #3--value
    #ruby_delete "$CONFIG_FILE" "['dns']['nameserver']" "114.114.114.114"

    #Delete Key Demo:
    #1--config path
    #2--key name
    #3--key name
    #ruby_delete "$CONFIG_FILE" "['dns']" "nameserver"
    #ruby_delete "$CONFIG_FILE" "" "dns"

    #Ruby Script Demo:
    #ruby -ryaml -rYAML -I "/usr/share/openclash" -E UTF-8 -e "
    #   begin
    #      Value = YAML.load_file('$CONFIG_FILE');
    #   rescue Exception => e
    #      puts '${LOGTIME} Error: Load File Failed,【' + e.message + '】';
    #   end;

        #General
    #   begin
    #   Thread.new{
    #      Value['redir-port']=7892;
    #      Value['tproxy-port']=7895;
    #      Value['port']=7890;
    #      Value['socks-port']=7891;
    #      Value['mixed-port']=7893;
    #   }.join;

    #   rescue Exception => e
    #      puts '${LOGTIME} Error: Set General Failed,【' + e.message + '】';
    #   ensure
    # ---------------------------------------------------------------
    # Provider 级健康检查：关闭（2026-10-11，配合仓库 openclash-rules.ini）
    # 背景：provider 批量健康检查在这台路由器上不可靠，会把可用节点判成 Down。
    #   实测（同一时刻对照）：组级检查 31/31 通过；provider 批量 83/83 失败。
    #   放宽到 cloudflare + 600s + 10s 超时后依旧如此 → 判定为批量风暴自身导致的假死
    #   （机场节点名也写着"批量测试可能导致 GFW 干扰连接"）。
    # 处理：关闭 provider 级检查，改由组级检查决定（ini：cloudflare/600s）。
    #   url/interval/timeout 仍写为合理值，将来若重新启开也不会退回 gstatic/5s。
    #   本段可重复执行。
    # ---------------------------------------------------------------
    if [ -f "$CONFIG_FILE" ]; then
       HC_BLOCKS=$(grep -c '^      enable:' "$CONFIG_FILE" 2>/dev/null || true)
       awk '
          /^proxy-providers:/ { insec=1 }
          insec && /^[a-zA-Z0-9_-]+:/ && !/^proxy-providers:/ { insec=0 }
          insec && /^      url: / { print "      url: https://cp.cloudflare.com/generate_204"; next }
          insec && /^      enable: / { print "      enable: false"; next }
          insec && /^      interval: [0-9]+$/ { print "      interval: 600"; print "      timeout: 10000"; next }
          insec && /^      timeout: / { next }
          { print }
       ' "$CONFIG_FILE" > "$CONFIG_FILE.oc_hc.tmp" && mv "$CONFIG_FILE.oc_hc.tmp" "$CONFIG_FILE"
       LOG_OUT "Tip: Provider Health-Check Disabled (blocks: ${HC_BLOCKS:-0}, disabled: $(grep -c '^      enable: false' "$CONFIG_FILE"))"
    fi
ruby_edit "$CONFIG_FILE" "['external-controller']" "'192.168.100.1:9090'"
ip link set dev utun mtu 1492 2>/dev/null
exit 0
