"""Minimal client for the team's VSS backend and S3 buckets.

Reads credentials from /config/<team>.config and the environment; never prints them.
"""
import glob
import json
import os
import urllib.parse
import urllib.request

import boto3
import urllib3
from botocore.config import Config

urllib3.disable_warnings()


def _load_team_config():
    configs = sorted(glob.glob("/config/*.config"))
    if len(configs) != 1:
        raise RuntimeError(f"expected exactly one /config/*.config, found {len(configs)}")
    for line in open(configs[0]):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.removeprefix("export ").strip(), v.strip().strip("'\""))


_load_team_config()
BACKEND = os.environ["INGRESS_URL"].rstrip("/")


class VSS:
    def __init__(self):
        self.token = None
        self.login()

    def login(self):
        body = json.dumps({"username": os.environ["USERNAME"], "password": os.environ["PASSWORD"]}).encode()
        req = urllib.request.Request(f"{BACKEND}/api/v1/auth/login", data=body,
                                     headers={"Content-Type": "application/json"})
        self.token = json.load(urllib.request.urlopen(req, timeout=60))["access_token"]

    def _call(self, method, path, params=None, body=None, retry=True):
        url = f"{BACKEND}/api/v1{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry:
                self.login()
                return self._call(method, path, params, body, retry=False)
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read()[:500].decode(errors='replace')}") from e

    def get(self, path, **params):
        return self._call("GET", path, params=params)

    def post(self, path, body):
        return self._call("POST", path, body=body)

    def explore_all(self, date=None, page=48):
        chunks, offset = [], 0
        while True:
            params = {"scope": "all", "limit": page, "offset": offset}
            if date:
                params["date"] = date
            d = self.get("/videos/explore", **params)
            chunks += d["chunks"]
            offset += page
            if offset >= d["total"] or not d["chunks"]:
                return chunks

    def stream_url(self, source):
        return f"{BACKEND}/api/v1/videos/stream?" + urllib.parse.urlencode({"source": source, "token": self.token})


def s3_client():
    return boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["ACCESS_KEY"], aws_secret_access_key=os.environ["SECRET_KEY"],
        verify=False, config=Config(max_pool_connections=32))
