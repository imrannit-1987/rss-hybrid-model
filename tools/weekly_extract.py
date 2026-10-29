"""Weekly report -> daily rows per sheet with fill-colour flags. usage: weekly_extract.py out.csv file.xlsx [more...] (later files win)"""
import sys, openpyxl, pandas as pd
out=sys.argv[1]; rows={}
def fill_key(c):
    f=c.fill
    if f is None or f.fill_type is None: return ''
    if f.fill_type=='solid':
        fg=f.fgColor; return (fg.rgb if fg.type=='rgb' else f'theme{fg.theme}/{fg.tint}') if fg is not None else ''
    return 'gradient:'+'/'.join((s.color.rgb if s.color.type=='rgb' else f'theme{s.color.theme}/{s.color.tint}') for s in f.stop)
for f in sys.argv[2:]:
    wb=openpyxl.load_workbook(f,data_only=True)
    for s in wb.sheetnames:
        ws=wb[s]
        if ws['A6'].value!='Back to Dash' and str(ws['B6'].value)!='Date': continue
        for r in range(7,ws.max_row+1):
            d=ws.cell(row=r,column=2).value
            if not hasattr(d,'year'): continue
            fuel=ws.cell(row=r,column=6); fk=fill_key(fuel)
            rows[(s,pd.Timestamp(d).normalize())]=dict(sheet=s,date=pd.Timestamp(d).normalize(),load=ws.cell(row=r,column=3).value,solar=ws.cell(row=r,column=4).value,dg=ws.cell(row=r,column=5).value,fuel=fuel.value,eff=ws.cell(row=r,column=7).value,
                fuel_fill=fk,fuel_estimated=int(fk.startswith('gradient:FFFF7D7D') or fk=='FFFFFF00'),refuel_day=int(fk.startswith('theme5')),kwp=ws['B3'].value,dg_config=ws['B4'].value,file=f.split('/')[-1])
W=pd.DataFrame(rows.values()); W.to_csv(out,index=False); print(len(W),'site-days',W.sheet.nunique(),'sheets')
