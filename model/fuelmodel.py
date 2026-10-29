"""Fuel model v2 helpers: class lookup, per-unit fuel with quadratic loading term and country multiplier."""
CL=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
KVA={'≤125 kVA':100,'200–220 kVA':200,'250 kVA':250,'300 kVA':300,'350 kVA':350,'500 kVA':500,'500 kVA (KENT)':500,'800 kVA':800,'1000–1250 kVA':1100}
def cls(kva,project=''):
    c=next(n for lo,hi,n in CL if lo<=kva<hi)
    if c=='500 kVA' and 'KENT' in project: c='500 kVA (KENT)'
    return c
def coefs(C,c):
    """(a,b,q) for a class; falls back to the nearest class present in C."""
    if f'rated_h|{c}' not in C:
        have=[k.split('|')[1] for k in C if k.startswith('rated_h|')]
        c='500 kVA' if 'KENT' in c and '500 kVA' in have else min(have,key=lambda x:abs(KVA[x]-KVA[c]))
    return C[f'rated_h|{c}'],C[f'kwh|{c}'],C.get('kwh_l|*',0.0)
def unit_fuel(C,kva,run,kwh,project=''):
    """litres for one unit over a period: a*rated*run + b*kwh + q*kwh*loading, times country multiplier."""
    a,b,q=coefs(C,cls(kva,project)); rated=kva*0.8
    l=kwh/(rated*run) if run>0 else 0.0
    m=C.get('country|'+project[:3],1.0)
    return m*(a*rated*run+b*kwh+q*kwh*l)