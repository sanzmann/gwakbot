import json, urllib.request
body = json.dumps({"messages":[{"role":"user","content":"오늘 기숙사 식당 점심 뭐야?"}]}).encode()
req = urllib.request.Request("http://127.0.0.1:8000/api/chat", body, {"Content-Type":"application/json"})
out=[]
with urllib.request.urlopen(req, timeout=120) as r:
    for raw in r:
        line = raw.decode("utf-8").strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            d = json.loads(line[6:])
            out.append(d.get("text") or ("[ERR]"+str(d.get("error"))))
print("".join(out)[:600])
