import requests
from requests.exceptions import HTTPError
from datetime import datetime
import xmltodict
import time
import sys
import gzip
from concurrent.futures.thread import ThreadPoolExecutor
import os

API = "http://jiotvapi.cdn.jio.com/apis"
IMG = "http://jiotv.catchup.cdn.jio.com/dare_images"
channel = []
programme = []
error = []
result = []

headers = {
    "user-agent": "JioTv"
}

def getEPGData(i, c):
    global channel, programme, error, result, API, IMG
    # 1 day future , today and two days past to play catchup
    for day in range(-1, 2):
        try:
            resp = requests.get(f"{API}/v1.3/getepg/get", params={"offset": day,
                                "channel_id": c['channel_id']},headers=headers).json()
            # print(resp)
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
    stime = time.time()
    try:
        resp = requests.get(
            f"{API}/v3.0/getMobileChannelList/get/?langId=6&devicetype=phone&os=android&usertype=JIO&version=343",headers=headers)
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

genEPG()