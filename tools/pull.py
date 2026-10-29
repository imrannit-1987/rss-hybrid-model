"""Run a Timestream SQL query through Grafana's /api/ds/query, following pagination.
usage: python3 -I pull.py <sql_file> <out_csv>   (prints rows, pages, bytes scanned)"""
import json, sys, subprocess, csv, tempfile, os
B="https://analytics.rssenergy.ae"; DS={"type":"grafana-timestream-datasource","uid":"2vVJQUHVk"}
sql=open(sys.argv[1]).read(); out=sys.argv[2]
names=None; rows=[]; scanned=0; pages=0; token=None
while True:
    q={"refId":"A","datasource":DS,"rawQuery":sql,"format":1,"waitForResult":True}
    if token: q["nextToken"]=token
    body=json.dumps({"from":"now-7d","to":"now","queries":[q]})
    with tempfile.NamedTemporaryFile("w",delete=False,suffix=".json") as f: f.write(body); fn=f.name
    r=subprocess.run(["curl","-s","--max-time","300","-u","Hybrid:Hybrid","-H","Content-Type: application/json","-X","POST",B+"/api/ds/query","--data","@"+fn],capture_output=True,text=True); os.unlink(fn)
    res=json.loads(r.stdout)["results"]["A"]
    if res.get("error"): sys.exit("ERROR: "+res["error"])
    pages+=1; token=None
    for fr in res.get("frames",[]):
        meta=(fr["schema"].get("meta") or {}).get("custom") or {}
        st=meta.get("status") or {}
        if pages==1 and not st: print("NOTE: no status in response meta; meta keys:", list(meta.keys()), file=sys.stderr)
        scanned=max(scanned, st.get("CumulativeBytesScanned",0)); metered=max(globals().get("metered",0), st.get("CumulativeBytesMetered",0)); globals()["metered"]=metered
        token=meta.get("nextToken") or token
        n=[x["name"] for x in fr["schema"]["fields"]]
        if names is None: names=n
        vals=fr["data"]["values"]
        if vals and n==names: rows+=list(zip(*vals))
    if not token or pages>500: break
with open(out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(names or []); w.writerows(rows)
print(json.dumps({"rows":len(rows),"pages":pages,"MB_scanned":round(scanned/1e6,1),"MB_metered":round(globals().get("metered",0)/1e6,1),"columns":len(names or [])}))
