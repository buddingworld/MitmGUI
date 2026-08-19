#https://docs.mitmproxy.org/stable/addons-examples/
from mitmproxy import http
import os,re,time
import requests
sess = requests.session()

def request(flow: http.HTTPFlow) -> None:
    pass

def response(flow: http.HTTPFlow):
    pass
