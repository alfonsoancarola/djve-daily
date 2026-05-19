import json, locale
import pandas as pd
from datetime import datetime

with open('djve_data.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)

df = pd.DataFrame(raw)

# Convert toneladas (Argentine format: 150,5 -> 150.5)
df['toneladas_num'] = df['toneladas'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)

# Parse dates dd/m/yyyy
def pdate(s):
    try:
        return datetime.strptime(s, '%d/%m/%Y')
    except:
        return None
for c in ['fecha_registro','fecha_presentacion','fecha_inicio','fecha_fin']:
    df[c+'_dt'] = df[c].apply(pdate)

print("=== METRICAS GLOBALES ===")
print(f"Total DJVE: {len(df)}")
print(f"Toneladas totales: {df['toneladas_num'].sum():,.1f}")
print(f"Empresas únicas: {df['razon_social'].nunique()}")
print(f"Productos únicos: {df['producto'].nunique()}")
print(f"Fecha registro min/max: {df['fecha_registro_dt'].min()} / {df['fecha_registro_dt'].max()}")

print("\n=== POR PRODUCTO ===")
por_prod = df.groupby('producto').agg(
    total_ton=('toneladas_num','sum'),
    n_djve=('sim','count'),
    n_empresas=('razon_social','nunique')
).sort_values('total_ton', ascending=False)
print(por_prod.to_string())
total = por_prod['total_ton'].sum()
por_prod['pct'] = por_prod['total_ton']/total*100
print("\nParticipación %")
print(por_prod[['total_ton','pct']].to_string())

print("\n=== TOP EXPORTADORES (todos los productos) ===")
top_exp = df.groupby('razon_social').agg(
    total_ton=('toneladas_num','sum'),
    n_djve=('sim','count'),
    n_productos=('producto','nunique')
).sort_values('total_ton', ascending=False)
print(top_exp.head(15).to_string())

# Save processed data
por_prod.reset_index().to_csv('summary_por_producto.csv', index=False)
top_exp.reset_index().to_csv('summary_top_exportadores.csv', index=False)
df.to_csv('djve_detalle.csv', index=False)
print("\nSaved processed CSVs")
