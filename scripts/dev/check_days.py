from twin.simulate import run
if __name__ == "__main__":
    params={'base_mode': {"bus": 0.839309524588969, "metro": 3.583307619800376, "mrts": 2.0070289148714004},'beta_per_km':0.12,'peak_width_scale':1.0}
    for days in (2,9):
        ev,s=run(config=params,start_date='2026-09-14',days=days,seed=11,use_calendar=False)
        print(days, ev.groupby(ev.ts.dt.date).boardings.sum().to_dict())
        print([ (d['date'],d['day_type'],d['arrivals'],d['tags']) for d in s['per_day']])
