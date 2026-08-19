"""Demo plugin: log the request URL to the Logs window (Plugin tab).

Showcased API:
    info()                -> plugin metadata shown in the Plugins dialog
    response(flow, api)   -> called after a response is received
    api.logs.add(msg, log_type=..., log_comment=...)
"""


def info():
    return {
        "description": "Just A Demo",
    }


def response(flow, api):
    url = flow.request.pretty_url
    api.logs.add(f"Request completed: {url}")
