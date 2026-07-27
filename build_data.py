import pandas as pd, numpy as np, json

df = pd.read_csv('/mnt/user-data/uploads/Manila_City_True_Walkability_ML_Ready_v2.csv', encoding='utf-8-sig')
meta = json.load(open('/mnt/user-data/uploads/app_intelligence.json'))
order = meta['expected_feature_order']

# --- block boundaries (verified) ---
B = {'osmid': (12,1011), 'name': (1011,1504), 'h3_res9': (1504,2503),
     'highway': (2503,2510), 'sidewalk': (2510,2513)}
cats = {}
for col,(s,e) in B.items():
    pre = col + '_'
    cats[col] = [f[len(pre):] for f in order[s:e]]

# --- normalisation constants ---
p, d, i = df['poi_count_400m'].values, df['dist_to_transit_m'].values, df['intersection_density'].values
inv = 1.0/d
CONST = {
  'poi':  [float(p.min()),  float(p.max())],
  'idn':  [float(i.min()),  float(i.max())],
  'inv':  [float(inv.min()), float(inv.max())],
  'dist': [float(d.min()),  float(d.max())],
}

# --- robust scaler params (median / IQR) for the 12 numeric cols ---
num_cols = order[:12]
scaler = {}
for c in num_cols:
    v = df[c].values.astype(float)
    q1, q3 = np.percentile(v,25), np.percentile(v,75)
    iqr = q3-q1
    scaler[c] = [float(np.median(v)), float(iqr if iqr!=0 else 1.0)]

# --- rho lookup ---
rho = {}
for (hw,sw), g in df.groupby(['highway','sidewalk']):
    rho.setdefault(hw, {})[sw] = float(g['rho_phantom'].iloc[0])

# --- label-encoder maps (category -> encoded int) ---
enc = {}
for col, ecol in [('osmid','osmid_encoded'),('name','name_encoded'),('h3_res9','h3_res9_encoded'),
                  ('highway','highway_encoded'),('sidewalk','sidewalk_encoded')]:
    enc[col] = {str(k): int(v) for k,v in df.groupby(col)[ecol].first().items()}

# --- compact segment table ---
segs = [[str(r.osmid), str(r.name_), str(r.h3_res9), str(r.highway), str(r.sidewalk),
         int(r.poi_count_400m), round(float(r.dist_to_transit_m),3),
         round(float(r.intersection_density),4), round(float(r.true_walkability_score_v2),2)]
        for r in df.rename(columns={'name':'name_'}).itertuples()]

payload = {
  'schema': ['osmid','name','h3','highway','sidewalk','poi','dist','idn','score'],
  'segments': segs,
  'categories': cats,
  'encoders': enc,
  'constants': CONST,
  'scaler': scaler,
  'rho': rho,
  'featureOrder': {'numeric': num_cols, 'blocks': B, 'total': len(order)},
  'meta': {k: meta[k] for k in ['project_goal','problem_type','target_column','scaler_used',
            'winning_model_type','best_params','final_test_score','top_5_influential_features',
            'feature_count_after_encoding','original_features','categorical_columns_to_encode']},
}

with open('data.js','w',encoding='utf-8') as f:
    f.write('/* Auto-generated from Manila_City_True_Walkability_ML_Ready_v2.csv + app_intelligence.json */\n')
    f.write('window.WALK_DATA = ')
    json.dump(payload, f, ensure_ascii=False, separators=(',',':'))
    f.write(';\n')
print('data.js written')
print('segments:', len(segs), '| dropped-first cats:', {k:(len(v)) for k,v in cats.items()})
