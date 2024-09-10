import requests
from requests.exceptions import HTTPError
from datetime import datetime
import xmltodict
import time
import gzip
from concurrent.futures.thread import ThreadPoolExecutor

API = "http://jiotvapi.cdn.jio.com/apis"
IMG = "http://jiotv.catchup.cdn.jio.com/dare_images"
# PROXY_API = "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&country=in&protocol=http&proxy_format=ipport&format=text&timeout=20000"
PROXY_API = "https://free.proxy-sale.com/api/front/main/proxy/list"
body = {
    "count": 100,
    "country": "India"
}

channel = []
programme = []
error = []
result = []

headers = {
    "user-agent": "JioTv"
}

def retryOnException(max_retries, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(
                        f"Retry {retries + 1}/{max_retries} - Exception: {e}")
                    retries += 1
                    time.sleep(delay)
            raise Exception(
                f"Function '{func.__name__}' failed after {max_retries} retries.")

        return wrapper

    return decorator


@retryOnException(max_retries=2, delay=5)
def getWorkingProxy():
    response = requests.post(PROXY_API,json=body)
    response.raise_for_status()
    # proxies = response.text.strip().split("\r\n")
    proxies = response.json()
    working_proxy = None
    for prx in proxies:
        prx = prx["ip"]
        print("Testing "+str(prx)+" proxy")
        tproxies = {
            "http": "http://{prx}".format(prx=prx),
        }
        try:
            test_url = f"{API}/v3.0/getMobileChannelList/get/?langId=6&devicetype=phone&os=android&usertype=JIO&version=353"
            response = requests.get(test_url, proxies=tproxies, timeout=5)

            if response.status_code == 200:
                working_proxy = prx
                break
        except requests.exceptions.RequestException:
            pass
    if working_proxy:
        print("Found working proxy "+str(working_proxy))
        return working_proxy

def getEPGData(i, c):
    global channel, programme, error, result, API, IMG
    for day in range(-1, 1):
        try:
            resp = requests.get(f"{API}/v1.3/getepg/get", params={"offset": day, "channel_id": c['channel_id']},headers=headers,proxies=proxies).json()
            day == 0 and channel.append({
                "@id": c['channel_id'],
                "display-name": c['channel_name'],
                "icon": {
                    "@src": f"{IMG}/images/{c['logoUrl']}"
                }
            })
            for eachEGP in resp.get("epg"):
                pdict = {
                    "@start": datetime.utcfromtimestamp(int(eachEGP['startEpoch']*.001)).strftime('%Y%m%d%H%M%S'),
                    "@stop": datetime.utcfromtimestamp(int(eachEGP['endEpoch']*.001)).strftime('%Y%m%d%H%M%S'),
                    "@channel": eachEGP['channel_id'],
                    "@catchup-id": eachEGP['srno'],
                    "title": eachEGP['showname'],
                    "desc": eachEGP['description'],
                    "category": eachEGP['showCategory'],
                    "icon": {
                        "@src": f"{IMG}/shows/{eachEGP['episodePoster']}"
                    }
                }
                if eachEGP['episode_num'] > -1:
                    pdict["episode-num"] = {
                        "@system": "xmltv_ns",
                        "#text": f"0.{eachEGP['episode_num']}"
                    }
                if eachEGP.get("director") or eachEGP.get("starCast"):
                    pdict["credits"] = {
                        "director": eachEGP.get("director"),
                        "actor": eachEGP.get("starCast") and eachEGP.get("starCast").split(', ')
                    }
                if eachEGP.get("episode_desc"):
                    pdict["sub-title"] = eachEGP.get("episode_desc")
                programme.append(pdict)
        except Exception as e:
            print(f"Retry failed (Retry Count: {retry_count+1}): {e} {c['channel_name']}")
            retry_count += 1
            error.append(c['channel_id'])
            

def genEPG():
    print("Start epg generation")
    stime = time.time()
    try:
        resp = requests.get(
            f"{API}/v3.0/getMobileChannelList/get/?langId=6&devicetype=phone&os=android&usertype=JIO&version=353",headers=headers,proxies=proxies)
        print(resp)
        resp.raise_for_status()
        raw = resp.json()
    except HTTPError as exc:
        code = exc.response.status_code
        print(exc)
        print(f'error calling mobilecahnnelList {code}')
    except Exception as e:
        print(e)
    else:
        result = raw.get("result")
        with ThreadPoolExecutor() as e:
            e.map(getEPGData, range(len(result)), result)
        epgdict = {"tv": {
            "channel": channel,
            "programme": programme
        }}
        epgxml = xmltodict.unparse(epgdict, pretty=True)
        with open("epg.xml.gz", 'wb+') as f:
            f.write(gzip.compress(epgxml.encode('utf-8')))
        if len(error) > 0:
            print(f'error in {error}')
        print(f"Took {time.time()-stime:.2f} seconds"+"EPG updated "+str( datetime.now()))

if __name__ == "__main__":
    proxy = getWorkingProxy()
    global proxies
    proxies = {
        "http": "http://{httpProxy}".format(httpProxy=proxy),
        "https": "http://{httpProxy}".format(httpProxy=proxy),
    }
    genEPG()