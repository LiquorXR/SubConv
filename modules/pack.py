"""
This module generates a complete config for Clash
"""

from modules import parse
import re
from . import config
import yaml
import random

from urllib.parse import urlparse, urlencode

async def pack(url: list, urlstandalone: list, urlstandby: list, urlstandbystandalone: list, content: str, interval: str, domain: str, short: str, notproxyrule: str, base_url: str):
    providerProxyNames = await parse.mkListProxyNames(content)
    result = {}

    if short is None:
        # head of config
        result.update(config.configInstance.HEAD)

    # proxies
    proxies = {
        "proxies": []
    }
    proxiesName = []
    proxiesStandbyName = []

    # Function to parse subscriptions and update proxies
    async def parse_subscriptions(subscription_urls):
        parsed_proxies = []
        for url in subscription_urls:
            parsed_proxies += await parse_subscription(url)
        return parsed_proxies

    async def parse_subscription(url):
        # Example logic to parse subscription URL
        parsed_proxies = await parse.parse_subscription(url)
        return parsed_proxies

    # Add proxies from subscriptions
    if url or urlstandalone or urlstandbystandalone:
        subscription_urls = []
        if url:
            subscription_urls += url
        if urlstandalone:
            subscription_urls += urlstandalone
        if urlstandbystandalone:
            subscription_urls += urlstandbystandalone

        if subscription_urls:
            parsed_proxies = await parse_subscriptions(subscription_urls)
            proxies["proxies"].extend(parsed_proxies)
            proxiesName.extend([p["name"] for p in parsed_proxies])
            proxiesStandbyName.extend([p["name"] for p in parsed_proxies])

    if len(proxies["proxies"]) == 0:
        proxies = None
    if len(proxiesName) == 0:
        proxiesName = None
    if len(proxiesStandbyName) == 0:
        proxiesStandbyName = None
    if proxies:
        result.update(proxies)

    # proxy groups
    proxyGroups = {
        "proxy-groups": []
    }

    # add proxy select
    proxySelect = {
        "name": "🚀 节点选择",
        "type": "select",
        "proxies": []
    }
    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        if not group.rule:
            proxySelect["proxies"].append(group.name)
    proxySelect["proxies"].append("DIRECT")
    proxyGroups["proxy-groups"].append(proxySelect)

    # generate subscriptions and standby subscriptions list
    subscriptions = []
    if url:
        for u in range(len(url)):
            subscriptions.append("subscription{}".format(u))
    standby = subscriptions.copy()
    if urlstandby:
        for u in range(len(urlstandby)):
            standby.append("subscriptionsub{}".format(u))
    if len(subscriptions) == 0:
        subscriptions = None
    if len(standby) == 0:
        standby = None

    # add proxy groups
    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        type = group.type
        regex = group.regex
        rule = group.rule

        if type == "select" and rule:
            prior = group.prior
            if prior == "DIRECT":
                proxyGroups["proxy-groups"].append({
                    "name": group.name,
                    "type": "select",
                    "proxies": [
                        "DIRECT",
                        "REJECT",
                        "🚀 节点选择",
                        *[g.name for g in config.configInstance.CUSTOM_PROXY_GROUP if not g.rule]
                    ]
                })
            elif prior == "REJECT":
                proxyGroups["proxy-groups"].append({
                    "name": group.name,
                    "type": "select",
                    "proxies": [
                        "REJECT",
                        "DIRECT",
                        "🚀 节点选择",
                        *[g.name for g in config.configInstance.CUSTOM_PROXY_GROUP if not g.rule]
                    ]
                })
            else:
                proxyGroups["proxy-groups"].append({
                    "name": group.name,
                    "type": "select",
                    "proxies": [
                        "🚀 节点选择",
                        *[g.name for g in config.configInstance.CUSTOM_PROXY_GROUP if not g.rule],
                        "DIRECT",
                        "REJECT"
                    ]
                })

        elif type in ["load-balance", "select", "fallback", "url-test"]:
            proxyGroup = {
                "name": group.name,
                "type": type
            }

            if regex is not None:
                tmp = [regex]
                if len(tmp) > 0:
                    proxyGroupProxies = []
                    proxyGroup["filter"] = "|".join(tmp)

                    if group.manual:
                        if standby:
                            proxyGroup["use"] = standby
                        if proxiesStandbyName:
                            proxyGroup["proxies"] = proxiesStandbyName
                    else:
                        if subscriptions:
                            proxyGroup["use"] = subscriptions
                        if proxiesName:
                            proxyGroup["proxies"] = proxiesName

                else:
                    proxyGroups["proxy-groups"][0]["proxies"].remove(group.name)
                    proxyGroup = None
                if proxyGroup is not None:
                    if type == "load-balance":
                        proxyGroup["strategy"] = "consistent-hashing"
                        proxyGroup["url"] = config.configInstance.TEST_URL
                        proxyGroup["interval"] = 60
                        proxyGroup["tolerance"] = 50
                    elif type in ["fallback", "url-test"]:
                        proxyGroup["url"] = config.configInstance.TEST_URL
                        proxyGroup["interval"] = 60
                        proxyGroup["tolerance"] = 50

            else:
                if group.manual:
                    if standby:
                        proxyGroup["use"] = standby
                    if proxiesStandbyName:
                        proxyGroup["proxies"] = proxiesStandbyName
                else:
                    if subscriptions:
                        proxyGroup["use"] = subscriptions
                    if proxiesName:
                        proxyGroup["proxies"] = proxiesName

            if proxyGroup is not None:
                proxyGroups["proxy-groups"].append(proxyGroup)

    # remove proxies that do not exist in any proxy group
    proxyGroupAndProxyList = ["DIRECT", "REJECT"]
    proxyGroupAndProxyList.extend([g.name for g in proxyGroups["proxy-groups"]])
    if proxiesStandbyName is not None:
        proxyGroupAndProxyList.extend(proxiesStandbyName)
    for proxygroup in proxyGroups["proxy-groups"]:
        if "proxies" not in proxygroup:
            continue
        proxygroup["proxies"] = [proxy for proxy in proxygroup["proxies"] if proxy in proxyGroupAndProxyList]

    result.update(proxyGroups)

    # rules
    rule_providers = {
        "rule-providers": {}
    }
    rule_map = {}
    classical = {
        "type": "http",
        "behavior": "classical",
        "format": "text",
        "interval": 86400 * 7,
    }

    for item in config.configInstance.RULESET:
        url = item[1]
        name = urlparse(url).path.split("/")[-1].split(".")[0]

        while name in rule_map:
            name += str(random.randint(0, 9))
        rule_map[name] = item[0]

        if url.startswith("[]"):
            continue
        if notproxyrule is None:
            url = "{}proxy?{}".format(base_url, urlencode({"url": url}))

        rule_providers["rule-providers"].update({
            name: {
                **classical,
                "path": "./rule/{}.txt".format(name),
                "url": url
            }
        })
    result.update(rule_providers)

    # add rule
    rules = {
        "rules": []
    }
    rules["rules"].append(f"DOMAIN,{domain},DIRECT")

    for k, v in rule_map.items():
        if not k.startswith("[]"):
            rules["rules"].append(f"RULE-SET,{k},{v}")
        elif k[2:] not in ["FINAL", "MATCH"]:
            rules["rules"].append(f"{k[2:]},{v}")
        else:
            rules["rules"].append(f"MATCH,{v}")

    result.update(rules)

    yaml.SafeDumper.ignore_aliases = lambda *args: True

    return yaml.safe_dump(result, allow_unicode=True, sort_keys=False)
