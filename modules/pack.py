import re
import yaml
import hashlib
from urllib.parse import urlparse, urlencode
from modules import parse
from . import config

async def pack(url: list, urlstandalone: list, urlstandby: list, urlstandbystandalone: list, content: str, interval: str, domain: str, short: str, notproxyrule: str, base_url: str):
    providerProxyNames = await parse.mkListProxyNames(content)
    result = {}

    if short is None:
        result.update(config.configInstance.HEAD)

    # Proxies section
    proxies = {
        "proxies": []
    }
    proxiesName = []
    proxiesStandbyName = []

    if urlstandalone or urlstandbystandalone:
        if urlstandalone:
            for i in urlstandalone:
                proxies["proxies"].append(i)
                proxiesName.append(i["name"])
                proxiesStandbyName.append(i["name"])
        if urlstandbystandalone:
            for i in urlstandbystandalone:
                proxies["proxies"].append(i)
                proxiesStandbyName.append(i["name"])
    if len(proxies["proxies"]) == 0:
        proxies = None
    if len(proxiesName) == 0:
        proxiesName = None
    if len(proxiesStandbyName) == 0:
        proxiesStandbyName = None
    if proxies:
        result.update(proxies)

    # Proxy providers section
    providers = {
        "proxy-providers": {}
    }
    if url or urlstandby:
        if url:
            for u in range(len(url)):
                filename = hashlib.md5(url[u].encode()).hexdigest()
                providers["proxy-providers"].update({
                    f"subscription{u}": {
                        "type": "http",
                        "url": url[u],
                        "interval": int(interval),
                        "path": f"./sub/{filename}.yaml",
                        "health-check": {
                            "enable": True,
                            "interval": 60,
                            "url": config.configInstance.TEST_URL
                        }
                    }
                })
        if urlstandby:
            for u in range(len(urlstandby)):
                filename = hashlib.md5(urlstandby[u].encode()).hexdigest()
                providers["proxy-providers"].update({
                    f"subscription_sub{u}": {
                        "type": "http",
                        "url": urlstandby[u],
                        "interval": int(interval),
                        "path": f"./sub/{filename}.yaml",
                        "health-check": {
                            "enable": True,
                            "interval": 60,
                            "url": config.configInstance.TEST_URL
                        }
                    }
                })
    if not providers["proxy-providers"]:
        providers = None
    if providers:
        result.update(providers)

        # Generate subscriptions and standby subscriptions list from proxy-providers
        subscriptions = [key for key in providers["proxy-providers"] if key.startswith("subscription")]
        standby = [key for key in providers["proxy-providers"] if key.startswith("subscription_sub")]

    # Proxy groups section
    proxyGroups = {
        "proxy-groups": []
    }

    # Proxy select
    proxySelect = {
        "name": "🚀 节点选择",
        "type": "select",
        "proxies": []
    }
    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        if not group.rule:
            proxySelect["proxies"].append(group.name)
    proxySelect["proxies"].extend(["DIRECT", "REJECT"])
    proxyGroups["proxy-groups"].append(proxySelect)

    # Add proxy groups
    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        type = group.type
        regex = group.regex
        rule = group.rule

        if type == "select" and rule:
            prior = group.prior
            proxies_list = [g.name for g in config.configInstance.CUSTOM_PROXY_GROUP if not g.rule]

            if prior == "DIRECT":
                proxies_list.insert(0, "DIRECT")
                proxies_list.extend(["REJECT", "🚀 节点选择"])
            elif prior == "REJECT":
                proxies_list.insert(0, "REJECT")
                proxies_list.extend(["DIRECT", "🚀 节点选择"])
            else:
                proxies_list.extend(["🚀 节点选择", "DIRECT", "REJECT"])

            proxyGroups["proxy-groups"].append({
                "name": group.name,
                "type": "select",
                "proxies": proxies_list
            })

        elif type in ["load-balance", "fallback", "url-test"]:
            proxyGroup = {
                "name": group.name,
                "type": type
            }

            if regex:
                tmp = [regex]
                if tmp:
                    providerProxies = []
                    proxyGroupProxies = []
                    proxyGroup["filter"] = "|".join(tmp)

                    if group.manual:
                        if standby:
                            for p in standby:
                                if re.search(proxyGroup["filter"], p, re.I):
                                    providerProxies.append(p)
                                    break
                            if providerProxies:
                                proxyGroup["use"] = standby

                        if proxiesStandbyName:
                            proxyGroupProxies.extend([p for p in proxiesStandbyName if re.search(proxyGroup["filter"], p, re.I)])

                            if proxyGroupProxies:
                                proxyGroup["proxies"] = proxyGroupProxies

                    else:
                        if subscriptions:
                            for p in providerProxyNames:
                                if re.search(proxyGroup["filter"], p, re.I):
                                    providerProxies.append(p)
                                    break

                            if providerProxies:
                                proxyGroup["use"] = subscriptions

                        if proxiesName:
                            proxyGroupProxies.extend([p for p in proxiesName if re.search(proxyGroup["filter"], p, re.I)])

                            if proxyGroupProxies:
                                proxyGroup["proxies"] = proxyGroupProxies

                    if len(providerProxies) + len(proxyGroupProxies) == 0:
                        proxyGroups["proxy-groups"][0]["proxies"].remove(group.name)
                    else:
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

            if proxyGroup:
                proxyGroups["proxy-groups"].append(proxyGroup)

    proxyGroupAndProxyList = (["DIRECT", "REJECT"])
    proxyGroupAndProxyList.extend([i["name"] for i in proxyGroups["proxy-groups"]])

    if proxiesStandbyName:
        proxyGroupAndProxyList.extend(proxiesStandbyName)

    for proxygroup in proxyGroups["proxy-groups"]:
        if "proxies" not in proxygroup:
            continue

        proxygroup["proxies"] = [proxy for proxy in proxygroup["proxies"] if proxy in proxyGroupAndProxyList]

    result.update(proxyGroups)

    # Rules section
    rule_providers = {
        "rule-providers": {}
    }

    rule_map = {}
    classical = {
        "type": "http",
        "behavior": "classical",
        "format": "text",
        "interval": 86400 * 7
    }

    for item in config.configInstance.RULESET:
        url = item[1]
        name = urlparse(url).path.split("/")[-1].split(".")[0]

        while name in rule_map:
            name += str(random.randint(0, 9))

        rule_map[name] = item[0]

        if url.startswith("[]"):
            continue

        if not notproxyrule:
            url = f"{base_url}proxy?{urlencode({'url': url})}"

        rule_providers["rule-providers"].update({
            name: {
                **classical,
                "path": f"./rule/{name}.txt",
                "url": url
            }
        })

    result.update(rule_providers)

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
