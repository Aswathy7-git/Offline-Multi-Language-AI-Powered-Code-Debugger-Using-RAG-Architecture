import urllib.request
import json
req = urllib.request.Request(
    'http://127.0.0.1:8000/debug_snippet',
    data=b'{"code":"print(1)","mode":"full","language":"python"}',
    headers={'Content-Type': 'application/json'}
)
try:
    response = urllib.request.urlopen(req)
    print("Success:", response.status, response.read().decode('utf-8'))
except Exception as e:
    print("Error:", repr(e))
