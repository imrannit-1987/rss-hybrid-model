"""Monthly Hybrid Performance Report -> site-month forecast/actual table. usage: monthly_extract.py out.csv file1.xlsx file2.xlsx ... (later files win)"""
import sys, openpyxl, pandas as pd
out=sys.argv[1]; rows={}
LAB={'Energy Consumption (kWh)':'load','Solar Energy Production (kWh)':'solar','Hybrid diesel energy production (kWh)':'dg','Hybrid diesel consumption (Litres)':'fuel','Fuel Efficiency (L/kWh)':'eff','Generator kVA deployed':'kva','Solar kWp installed':'kwp'}
for f in sys.argv[2:]:
    wb=openpyxl.load_workbook(f,data_only=True,read_only=True)
    for s in wb.sheetnames:
        ws=wb[s]; R=list(ws.iter_rows(min_row=1,max_row=45,values_only=True))
        hi=[i for i,r in enumerate(R) if r and r[0]=='Parameters']
        if not hi: continue
        h=R[hi[0]]; cols=[(j,v) for j,v in enumerate(h) if hasattr(v,'year')]
        cfg=[r[1] for r in R if r and isinstance(r[0],str) and r[0].startswith('Hybrid DG conf')]
        for r in R[hi[0]+1:]:
            lab=str(r[0]).strip() if r[0] else ''
            if lab not in LAB: continue
            for j,m in cols:
                fc,ac=r[j],r[j+1]
                key=(s,pd.Timestamp(m.year,m.month,1))
                d=rows.setdefault(key,{'sheet':s,'month':key[1],'dg_config':cfg[0] if cfg else None,'file':f.split('/')[-1]})
                d['file']=f.split('/')[-1]
                d[f'fc_{LAB[lab]}']=fc if isinstance(fc,(int,float)) else None
                d[f'act_{LAB[lab]}']=ac if isinstance(ac,(int,float)) else None
M=pd.DataFrame(rows.values()); M.to_csv(out,index=False)
print(len(M),'site-months;',M.act_fuel.notna().sum(),'with actual fuel;',M.sheet.nunique(),'sheets')
