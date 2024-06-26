import uuid
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
        result.update(config.configInstance.HEAD)

    proxies = {"proxies": []}
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

    if not proxies["proxies"]:
        proxies = None
    if not proxiesName:
        proxiesName = None
    if not proxiesStandbyName:
        proxiesStandbyName = None

    if proxies:
        result.update(proxies)

    providers = {"proxy-providers": {}}
    if url or urlstandby:
        if url:
            for u, link in enumerate(url):
                random_filename = uuid.uuid4().hex
                providers["proxy-providers"].update({
                    f"subscription{u}": {
                        "type": "http",
                        "url": link,
                        "interval": int(interval),
                        "path": f"./sub/{random_filename}.yaml",
                        "health-check": {
                            "enable": True,
                            "interval": 60,
                            "url": config.configInstance.TEST_URL
                        }
                    }
                })
        if urlstandby:
            for u, link in enumerate(urlstandby):
                random_filename = uuid.uuid4().hex
                providers["proxy-providers"].update({
                    f"subscriptionsub{u}": {
                        "type": "http",
                        "url": link,
                        "interval": int(interval),
                        "path": f"./sub/{random_filename}.yaml",
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

    proxyGroups = {"proxy-groups": []}
    
    proxySelect = {
        "name": "🚀 节点选择",
        "type": "select",
        "proxies": ["DIRECT"]
    }
    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        if not group.rule:
            proxySelect["proxies"].append(group.name)
    proxyGroups["proxy-groups"].append(proxySelect)

    subscriptions = [f"subscription{u}" for u in range(len(url))] if url else None
    standby = subscriptions.copy() if subscriptions else []
    if urlstandby:
        standby.extend([f"subscriptionsub{u}" for u in range(len(urlstandby))])
    if not standby:
        standby = None

    for group in config.configInstance.CUSTOM_PROXY_GROUP:
        type = group.type
        regex = group.regex

        rule = group.rule

        if type == "select" and rule:
            prior = group.prior
            proxies_list = ["DIRECT", "REJECT", "🚀 节点选择"]
            proxies_list.extend([_group.name for _group in config.configInstance.CUSTOM_PROXY_GROUP if not _group.rule])
            if prior in proxies_list:
                proxies_list.remove(prior)
                proxies_list.insert(0, prior)
            proxyGroups["proxy-groups"].append({
                "name": group.name,
                "type": "select",
                "proxies": proxies_list
            })
        elif type in {"load-balance", "select", "fallback", "url-test"}:
            proxyGroup = {
                "name": group.name,
                "type": type
            }
            if regex is not None:
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
                            for p in proxiesStandbyName:
                                if re.search(proxyGroup["filter"], p, re.I):
                                    proxyGroupProxies.append(p)
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
                            for p in proxiesName:
                                if re.search(proxyGroup["filter"], p, re.I):
                                    proxyGroupProxies.append(p)
                            if proxyGroupProxies:
                                proxyGroup["proxies"] = proxyGroupProxies
                    if not (providerProxies or proxyGroupProxies):
                        proxyGroups["proxy-groups"][0]["proxies"].remove(group.name)
                        proxyGroup = None
                else:
                    proxyGroups["proxy-groups"][0]["proxies"].remove(group.name)
                    proxyGroup = None
                if proxyGroup:
                    if type == "load-balance":
                        proxyGroup["strategy"] = "consistent-hashing"
                        proxyGroup["url"] = config.configInstance.TEST_URL
                        proxyGroup["interval"] = 60
                        proxyGroup["tolerance"] = 50
                    elif type in {"fallback", "url-test"}:
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

    proxyGroupAndProxyList = ["DIRECT", "REJECT"]
    proxyGroupAndProxyList.extend([i["name"] for i in proxyGroups["proxy-groups"]])
    if proxiesStandbyName:
        proxyGroupAndProxyList.extend(proxiesStandbyName)
    for proxygroup in proxyGroups["proxy-groups"]:
        if "proxies" in proxygroup:
            proxygroup["proxies"] = [proxy for proxy in proxygroup["proxies"] if proxy in proxyGroupAndProxyList]

    result.update(proxyGroups)

    rule_providers = {"rule-providers": {}}
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
        if not url.startswith("[]"):
            if notproxyrule is None:
                url = f"{base_url}proxy?{urlencode({'url': url})}"
            rule_providers["rule-providers"].update({
                name: {**classical, "path": f"./rule/{uuid.uuid4().hex}.txt", "url": url}
            })
    result.update(rule_providers)

    rules = {"rules": [f"DOMAIN,{domain},DIRECT"]}
    for k, v in rule_map.items():
        if not k.startswith("[]"):
            rules["rules"].append(f"RULE-SET,{k},{v}")
        elif k[2:] not in {"FINAL", "MATCH"}:
            rules["rules"].append(f"{k[2:]},{v}")
        else:
            rules["rules"].append(f"MATCH,{v}")

    result.update(rules)

    yaml.SafeDumper.ignore_aliases = lambda *args: True
    
    return yaml.safe_dump(result, allow_unicode=True, sort_keys=False)
