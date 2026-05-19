import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False

# Brand colors — agro/government feel
COLOR_PRIMARY = '#1e3a8a'   # navy
COLOR_ACCENT  = '#f59e0b'   # amber
COLOR_GREEN   = '#15803d'
PALETTE = ['#1e3a8a', '#15803d', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#be185d', '#65a30d', '#ea580c', '#475569', '#a16207']

with open('djve_data.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)
df = pd.DataFrame(raw)
df['toneladas_num'] = df['toneladas'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)
def pdate(s):
    try: return datetime.strptime(s, '%d/%m/%Y')
    except: return None
df['fecha_inicio_dt'] = df['fecha_inicio'].apply(pdate)
df['fecha_fin_dt']    = df['fecha_fin'].apply(pdate)

# === 1. Toneladas por producto (bar horizontal) ===
por_prod = df.groupby('producto')['toneladas_num'].sum().sort_values(ascending=True)
fig, ax = plt.subplots(figsize=(7.8, 4.2))
bars = ax.barh(por_prod.index, por_prod.values, color=PALETTE[:len(por_prod)][::-1])
ax.set_xlabel('Toneladas', fontsize=10)
ax.set_title('Toneladas declaradas por producto', fontsize=13, fontweight='bold', loc='left', pad=12)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'.replace(',', '.')))
for bar in bars:
    w = bar.get_width()
    label = f'{int(w):,}'.replace(',', '.') if w >= 100 else f'{w:,.1f}'.replace(',', '.')
    ax.text(w + max(por_prod.values)*0.01, bar.get_y()+bar.get_height()/2, label, va='center', fontsize=8.5)
ax.set_xlim(0, max(por_prod.values)*1.15)
plt.tight_layout()
plt.savefig('chart_toneladas_producto.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close()

# === 2. Top exportadores ===
top_exp = df.groupby('razon_social')['toneladas_num'].sum().sort_values(ascending=False).head(10)
top_exp = top_exp.sort_values(ascending=True)
# Shorten labels
def short(s):
    s = s.replace('ARGENTINA','ARG.').replace('S.A.','SA').replace('S.A.C.I.','SACI').replace('SOCIEDAD ELABORADORA DE ACEITES','SEA')
    if 'ASOCIACIÓN' in s: return 'ACA COOP. LTDA.'
    return s[:38] + ('…' if len(s) > 38 else '')
fig, ax = plt.subplots(figsize=(7.8, 4.5))
labels = [short(s) for s in top_exp.index]
bars = ax.barh(labels, top_exp.values, color=COLOR_PRIMARY)
ax.set_xlabel('Toneladas', fontsize=10)
ax.set_title('Top 10 exportadores por volumen declarado', fontsize=13, fontweight='bold', loc='left', pad=12)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'.replace(',', '.')))
for bar in bars:
    w = bar.get_width()
    ax.text(w + max(top_exp.values)*0.01, bar.get_y()+bar.get_height()/2, f'{int(w):,}'.replace(',','.'), va='center', fontsize=8.5)
ax.set_xlim(0, max(top_exp.values)*1.18)
plt.tight_layout()
plt.savefig('chart_top_exportadores.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close()

# === 3. Pie chart participación por producto ===
por_prod2 = df.groupby('producto')['toneladas_num'].sum().sort_values(ascending=False)
# Group the small ones
big = por_prod2[por_prod2/por_prod2.sum() >= 0.01]
small = por_prod2[por_prod2/por_prod2.sum() < 0.01]
if len(small) > 0:
    big['OTROS'] = small.sum()
fig, ax = plt.subplots(figsize=(6.8, 5.0))
colors = PALETTE[:len(big)]
wedges, texts, autotexts = ax.pie(big.values, labels=None, autopct=lambda p: f'{p:.1f}%' if p>=2 else '', colors=colors, startangle=90, wedgeprops=dict(width=0.45, edgecolor='white'))
for t in autotexts:
    t.set_color('white'); t.set_fontsize(9); t.set_fontweight('bold')
ax.set_title('Participación por producto (% del total)', fontsize=13, fontweight='bold', loc='left', pad=12)
# Legend
legend_labels = [f'{n}  ·  {int(v):,}'.replace(',', '.') + ' t' for n, v in big.items()]
ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=8.5, frameon=False)
plt.tight_layout()
plt.savefig('chart_participacion_torta.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close()

# === 4. Cronograma — distribución por período (fecha de inicio) ===
df['mes_inicio'] = df['fecha_inicio_dt'].dt.to_period('M').dt.to_timestamp()
crono = df.groupby('mes_inicio')['toneladas_num'].sum().sort_index()
fig, ax = plt.subplots(figsize=(7.8, 3.6))
bars = ax.bar(crono.index, crono.values, width=20, color=COLOR_GREEN, alpha=0.85)
ax.set_title('Volumen por mes de inicio de período de embarque', fontsize=13, fontweight='bold', loc='left', pad=12)
ax.set_ylabel('Toneladas', fontsize=10)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'.replace(',', '.')))
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
for bar, val in zip(bars, crono.values):
    ax.text(bar.get_x()+bar.get_width()/2, val + max(crono.values)*0.02, f'{int(val):,}'.replace(',', '.'), ha='center', fontsize=8.5)
ax.set_ylim(0, max(crono.values)*1.18)
plt.setp(ax.get_xticklabels(), rotation=0, ha='center')
plt.tight_layout()
plt.savefig('chart_cronograma.png', dpi=180, bbox_inches='tight', facecolor='white')
plt.close()

import os
for f in ['chart_toneladas_producto.png','chart_top_exportadores.png','chart_participacion_torta.png','chart_cronograma.png']:
    print(f, os.path.getsize(f), 'bytes')
