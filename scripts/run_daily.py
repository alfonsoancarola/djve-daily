"""DJVE Daily Report — 1 página, DJVE ≥ 500 t, con replacement vs FOB Minagri.

Pipeline:
1. Scrape DJVE aprobadas (MAGyP)
2. Scrape FOB oficial del día (DINEM)
3. Filtrar DJVE ≥ 500 t y matchear con FOB por grano + mes de delivery
4. Calcular replacement = ton × FOB
5. Generar PDF de 1 página por cereal
6. Enviar por mail
"""
import os, re, json, sys
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request, ssl

BASE = Path(__file__).resolve().parent.parent
WORK = Path('/tmp/djve_work'); WORK.mkdir(exist_ok=True)

URL_DJVE = "https://www.magyp.gob.ar/sitio/areas/ss_mercados_agropecuarios/djve/_archivos/000011_Declaraciones%20Juradas%20de%20Ventas%20al%20Exterior%20(Ley%2021.453).php"
# URL sin parámetros → siempre devuelve la última circular publicada
URL_FOB_LATEST = "https://dinem.magyp.gob.ar/dinem_fob.wp_fob_conslista.aspx"

def step(m): print(f"\n=== {m} ===", flush=True)

def http_get(url):
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 DJVE-Daily-Report'})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return r.read().decode('utf-8', errors='replace')

# ===== 1. DJVE =====
step("1. Descargando DJVE")
html_djve = http_get(URL_DJVE)
print(f"   {len(html_djve):,} bytes")

step("2. Parseando DJVE aprobadas")
from bs4 import BeautifulSoup
soup = BeautifulSoup(html_djve, 'html.parser')
target = None
for t in soup.find_all('table'):
    txt = t.get_text()
    if 'Nº DJVE' in txt and 'Razón Social' in txt and 'Tonteladas' in txt:
        target = t; break
if not target: print("ERROR: tabla DJVE no encontrada"); sys.exit(1)
djve_rows = []
for r in target.find_all('tr')[1:]:
    cells = [re.sub(r'\s+', ' ', c.get_text(strip=True)).strip() for c in r.find_all('td')]
    if len(cells) >= 9:
        djve_rows.append({'sim':cells[0],'fecha_registro':cells[1],'fecha_presentacion':cells[2],
                          'producto':cells[3],'toneladas':cells[4],'fecha_inicio':cells[5],
                          'fecha_fin':cells[6],'opcion':cells[7],'razon_social':cells[8]})
print(f"   {len(djve_rows)} DJVE parseadas")

# ===== 2. FOB Minagri =====
step("3. Descargando FOB Minagri (latest + backfill anteriores)")
fob_cache_dir = BASE / 'archive' / 'fob'
fob_cache_dir.mkdir(parents=True, exist_ok=True)

def parse_fob_html(h):
    """Devuelve (date, circ, p3, p4, data) o (None,...) si la página no trae datos."""
    if len(h) < 30_000 or not re.search(r"value='\[\[\"\d{8}\"", h):
        return None
    m_date = re.search(r'name="vFECHA"\s+value="(\d{1,2})/(\d{1,2})/(\d{4})"', h)
    m_circ = re.search(r'name="vDIM_PRECIOFOB_NCIRC"\s+value="(\d+)"', h)
    m_action = re.search(r'action="dinem_fob\.wp_fob_conslista\.aspx\?(\d{8}),(\d+),(\d+),(\d+)"', h)
    m_data = re.search(r"value='(\[\[\"\d{8}\".*?\]\])'", h, re.DOTALL)
    if not (m_date and m_circ and m_action and m_data):
        return None
    date = datetime(int(m_date.group(3)), int(m_date.group(2)), int(m_date.group(1)))
    circ = int(m_circ.group(1))
    p3 = int(m_action.group(3))
    p4 = int(m_action.group(4))
    data = json.loads(m_data.group(1))
    return date, circ, p3, p4, data

def cache_fob(date, data):
    f = fob_cache_dir / f'fob_{date:%Y-%m-%d}.json'
    if not f.exists():
        f.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        print(f"   FOB cacheado: {f.name} ({len(data)} líneas)")
        return True
    return False

def fetch_fob_by_params(date, circ, p3, p4=1):
    url = f"https://dinem.magyp.gob.ar/dinem_fob.wp_fob_conslista.aspx?{date:%Y%m%d},{circ},{p3},{p4}"
    try:
        return http_get(url)
    except Exception:
        return None

# 1) Latest
html_fob_latest = http_get(URL_FOB_LATEST)
parsed_latest = parse_fob_html(html_fob_latest)
if parsed_latest:
    latest_date, latest_circ, latest_p3, latest_p4, latest_data = parsed_latest
    print(f"   Latest: FOB del {latest_date:%d/%m/%Y}, circ {latest_circ}, p3 {latest_p3}")
    cache_fob(latest_date, latest_data)
else:
    print("   [WARN] Latest FOB no disponible, intento backfill desde cache existente")
    latest_date = latest_circ = latest_p3 = latest_p4 = None

# 2) Backfill: ir hacia atrás decrementando circ y p3, probando fechas previas (skip weekends/holidays)
if parsed_latest:
    circ_back = latest_circ - 1
    p3_back = latest_p3 - 1
    days_back_start = 1
    while circ_back > 0 and circ_back >= latest_circ - 10:  # backfill hasta 10 circulares atrás
        # Si ya tengo cacheada cualquier fecha con ese circ, skip (no sé qué fecha es pero asumo OK)
        found = False
        for delta in range(days_back_start, days_back_start + 6):
            try_date = latest_date - timedelta(days=delta)
            h = fetch_fob_by_params(try_date, circ_back, p3_back, latest_p4)
            if h and (parsed := parse_fob_html(h)):
                d, c, _, _, data = parsed
                # Confirmar que es la circular que esperamos
                if c == circ_back:
                    if cache_fob(d, data):
                        pass
                    days_back_start = delta + 1
                    found = True
                    break
        if not found:
            break
        circ_back -= 1
        p3_back -= 1

# Lógica de negocio: usar FOB publicada ANTES de hoy (calendar)
# Para DJVE registradas hoy, los precios vigentes son los publicados hasta ayer
today_cal = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
cached_files = []
for f in sorted(fob_cache_dir.glob('fob_*.json')):
    try:
        d = datetime.strptime(f.stem.replace('fob_', ''), '%Y-%m-%d')
        cached_files.append((d, f))
    except ValueError:
        continue
cached_files.sort(key=lambda x: x[0], reverse=True)

# Elegir el más reciente con fecha < hoy
current_pair = next(((d, f) for d, f in cached_files if d < today_cal), None)
# El siguiente más reciente con fecha < current = comparación "ayer"
previous_pair = None
if current_pair:
    previous_pair = next(((d, f) for d, f in cached_files if d < current_pair[0]), None)

if not current_pair:
    print("ERROR: no hay FOB cacheada anterior a hoy disponible.")
    sys.exit(1)

fob_date, fob_file = current_pair
fob_data = json.loads(fob_file.read_text(encoding='utf-8'))
print(f"   FOB del informe (publicada el {fob_date:%d/%m/%Y}): {len(fob_data)} líneas")
prev_fob_data = None; prev_fob_date_str = None
if previous_pair:
    prev_date, prev_file = previous_pair
    prev_fob_data = json.loads(prev_file.read_text(encoding='utf-8'))
    prev_fob_date_str = prev_date.strftime('%d/%m/%Y')
    print(f"   FOB comparación (publicada el {prev_fob_date_str}): {len(prev_fob_data)} líneas")
else:
    print("   (Sin FOB de comparación — no hay otro anterior cacheado)")

# Find the hidden input that contains the JSON FOB array.
# (cache + selección hecha arriba)

# ===== 3. Process =====
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

df = pd.DataFrame(djve_rows)
df['toneladas_num'] = df['toneladas'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)
def pdate(s):
    try: return datetime.strptime(s, '%d/%m/%Y')
    except: return None
for c in ['fecha_registro','fecha_presentacion','fecha_inicio','fecha_fin']:
    df[c+'_dt'] = df[c].apply(pdate)

# ===== 4. FOB lookup =====
# Build FOB price index. Each row: (ncm, desc, price, mfrom, mto)
MES_NUM = {'Ene':1,'Feb':2,'Mar':3,'Abr':4,'May':5,'Jun':6,'Jul':7,'Ago':8,'Sep':9,'Set':9,'Oct':10,'Nov':11,'Dic':12}
def parse_month_yr(s):
    if not s or not s.strip(): return None
    parts = s.replace('.','').split('/')
    if len(parts) != 2: return None
    return MES_NUM.get(parts[0][:3]), int(parts[1])

fob_records = []
for ncm, desc, price, mfrom, mto in fob_data:
    f = parse_month_yr(mfrom); t = parse_month_yr(mto)
    fob_records.append({
        'ncm': ncm, 'desc': desc, 'price': float(price),
        'm_from': f, 'm_to': t,
        'desc_lower': desc.lower(),
    })

# DJVE producto → FOB description pattern (substring match, lowercase)
# Default presentation: "a granel con hasta un 15"
PROD_TO_FOB = [
    ('MAIZ PARTIDO',           'maíz partido'),
    ('MAIZ',                   'maíz, los demás'),
    ('TRIGO PAN',              'trigo, trigo pan'),
    ('HARINA DE TRIGO',        'harina de trigo'),
    ('SORGO',                  'sorgo granífero'),
    ('CEBADA CERVECERA',       'cebada, cervecera'),
    ('CEBADA FORRAJERA',       'cebada, en grano'),
    ('CEBADA',                 'cebada, en grano'),    # fallback
]
PRESENTATION_DEFAULT = 'a granel con hasta un 15'

def find_fob(producto, month, year):
    """Match producto + month → FOB price USD/ton."""
    if month is None or year is None: return None, None
    p_up = producto.upper()
    # Find which FOB description family matches
    fob_pattern = None
    for key, pat in PROD_TO_FOB:
        if key in p_up:
            fob_pattern = pat
            break
    if not fob_pattern: return None, None
    # Filter candidates
    cands = [r for r in fob_records
             if fob_pattern in r['desc_lower']
             and (PRESENTATION_DEFAULT in r['desc_lower'] or r['ncm'].startswith(('110','230')))]
    if not cands: return None, None
    # Match by month
    for r in cands:
        if r['m_from'] is None and r['m_to'] is None:
            # Unique price, no month — use as fallback
            return r['price'], r['desc']
    # Try month-specific match
    target = (year, month)
    for r in cands:
        if r['m_from'] and r['m_to']:
            f = (r['m_from'][1], r['m_from'][0]); t = (r['m_to'][1], r['m_to'][0])
            if f <= target <= t:
                return r['price'], r['desc']
    # Fallback: first candidate
    return cands[0]['price'], cands[0]['desc']

# Apply FOB lookup to every DJVE
df['fob_price'] = None
df['fob_desc'] = None
for i, row in df.iterrows():
    fdt = row['fecha_inicio_dt']
    if pd.isna(fdt) or fdt is None:
        continue
    price, desc = find_fob(row['producto'], fdt.month, fdt.year)
    df.at[i, 'fob_price'] = price
    df.at[i, 'fob_desc'] = desc

def grain_key(producto):
    p = producto.upper()
    for kw in ['MAIZ','TRIGO','SORGO','CEBADA']:
        if kw in p:
            return kw
    return None

# ===== Filter ≥ 500 t =====
THRESHOLD = 500
df_big = df[df['toneladas_num'] >= THRESHOLD].copy()
print(f"\n   DJVE ≥ {THRESHOLD} t: {len(df_big)} de {len(df)} totales")

CEREALES = [('Maíz','MAIZ'),('Trigo','TRIGO'),('Sorgo','SORGO'),('Cebada','CEBADA')]
def filter_cereal(d, kw):
    return d[d['producto'].str.contains(kw, case=False, na=False)].copy()

# ===== PDF =====
step("4. Construyendo PDF (1 página)")
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak)

def fmt_int(n): return f'{int(n):,}'.replace(',', '.')
def fmt_money(n):
    if n is None or pd.isna(n): return '-'
    n = float(n)
    if n >= 1_000_000:
        return f'USD {n/1_000_000:.2f}M'.replace('.', ',')
    if n >= 1_000:
        return f'USD {n/1_000:.0f}K'.replace(',', '.')
    return f'USD {int(n):,}'.replace(',', '.')
def fmt_ton(n):
    return fmt_int(n) if n >= 100 else f'{n:,.2f}'.replace(',','X').replace('.',',').replace('X','.')

NAVY = rl_colors.HexColor('#1e3a8a'); AMBER = rl_colors.HexColor('#f59e0b')
GREEN = rl_colors.HexColor('#15803d'); LIGHT = rl_colors.HexColor('#f1f5f9')
MUTED = rl_colors.HexColor('#64748b'); DARK = rl_colors.HexColor('#0f172a')

styles = getSampleStyleSheet()
H1   = ParagraphStyle('H1', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, textColor=NAVY, spaceAfter=2, leading=18)
SUB  = ParagraphStyle('SUB', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=MUTED, spaceAfter=6)
CEREAL_H = ParagraphStyle('CH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, spaceAfter=2, spaceBefore=6, leading=13)
CEREAL_SUM = ParagraphStyle('CS', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=DARK, spaceAfter=3, leading=11)
EMPTY = ParagraphStyle('EM', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8.5, textColor=MUTED, spaceAfter=2, leading=11)
FOOT = ParagraphStyle('FOOT', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7, textColor=MUTED, alignment=TA_LEFT, leading=8.5)

fecha_reg = df['fecha_registro_dt'].max().strftime('%d/%m/%Y') if df['fecha_registro_dt'].notna().any() else '-'
hoy = datetime.now().strftime('%d/%m/%Y')
fob_dt_str = fob_date.strftime('%d/%m/%Y')

archive_dir = BASE / 'archive'; archive_dir.mkdir(exist_ok=True)
date_stamp = datetime.now().strftime('%Y-%m-%d')
dated_out  = archive_dir / f'Informe_DJVE_{date_stamp}.pdf'
latest_out = BASE / 'Informe_DJVE_Aprobadas.pdf'

def build_doc(out_path):
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.2*cm, bottomMargin=1.1*cm,
                            title='Informe Diario DJVE')
    story = []
    story.append(Paragraph('Informe Diario DJVE · Cereales', H1))
    story.append(Paragraph(
        f'<b>Operaciones registradas el {fecha_reg}</b> &nbsp;·&nbsp; '
        f'<b>Precios FOB publicados el {fob_dt_str}</b><br/>'
        f'<font size=8 color="#64748b">DJVE Ley 21.453 (Aprobadas) &nbsp;·&nbsp; '
        f'Filtro: DJVE ≥ {THRESHOLD} t &nbsp;·&nbsp; Generado: {hoy}</font>', SUB))

    # Resumen — SOLO cereales (Maíz, Trigo, Sorgo, Cebada)
    cereal_keys = [kw for _, kw in CEREALES]
    df_cereal = df_big[df_big['producto'].apply(lambda p: any(kw in p.upper() for kw in cereal_keys))]
    total_big = df_cereal['toneladas_num'].sum()
    resumen_data = [[
        Paragraph(f'<b>{len(df_cereal)}</b><br/><font size=7 color="#64748b">DJVE ≥ {THRESHOLD}t (cereales)</font>', CEREAL_SUM),
        Paragraph(f'<b>{fmt_int(total_big) if total_big else "0"}</b><br/><font size=7 color="#64748b">Toneladas</font>', CEREAL_SUM),
        Paragraph(f'<b>{df_cereal["razon_social"].nunique() if len(df_cereal) else 0}</b><br/><font size=7 color="#64748b">Shippers únicos</font>', CEREAL_SUM),
    ]]
    rtbl = Table(resumen_data, colWidths=[6.0*cm]*3, rowHeights=[1.2*cm])
    rtbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 4),('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(rtbl)
    story.append(Spacer(1, 0.15*cm))

    # Per cereal block
    for label, kw in CEREALES:
        g = filter_cereal(df_big, kw)
        if len(g) == 0:
            story.append(Paragraph(f'<b>{label}</b>', CEREAL_H))
            story.append(Paragraph(f'Sin DJVE ≥ {THRESHOLD} t para {label} en esta actualización.', EMPTY))
            continue

        ton_g = g['toneladas_num'].sum()
        # Compact summary line
        story.append(Paragraph(
            f'<b>{label}</b> &nbsp; <font size=8 color="#64748b">'
            f'{len(g)} DJVE &nbsp;·&nbsp; {fmt_int(ton_g)} t &nbsp;·&nbsp; '
            f'{g["razon_social"].nunique()} shippers</font>',
            CEREAL_H))

        # Tabla simple: Shipper / Producto / Ton / Inicio / Fin / FOB U$/t
        g_sorted = g.sort_values('toneladas_num', ascending=False)
        rows = [['Shipper', 'Producto', 'Ton.', 'Inicio', 'Fin', 'FOB U$/t']]
        for _, r in g_sorted.iterrows():
            shipper = r['razon_social']
            shipper = shipper[:32] + ('…' if len(r['razon_social']) > 32 else '')
            ini = r['fecha_inicio_dt'].strftime('%d/%m') if pd.notna(r['fecha_inicio_dt']) else '-'
            fin = r['fecha_fin_dt'].strftime('%d/%m') if pd.notna(r['fecha_fin_dt']) else '-'
            fob = f"{int(r['fob_price'])}" if pd.notna(r['fob_price']) else '—'
            prod = r['producto'].title()
            prod = prod[:22] + ('…' if len(prod) > 22 else '')
            rows.append([shipper, prod, fmt_int(r['toneladas_num']), ini, fin, fob])

        rows.append(['Total', '', fmt_int(ton_g), '', '', ''])
        col_widths = [6.0*cm, 4.5*cm, 1.8*cm, 1.6*cm, 1.6*cm, 2.0*cm]
        num_col_start = 2

        tbl = Table(rows, colWidths=col_widths)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), rl_colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7.2),
            ('ALIGN', (num_col_start,0), (-1,-1), 'RIGHT'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [rl_colors.white, LIGHT]),
            ('BACKGROUND', (0,-1), (-1,-1), rl_colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('LINEABOVE', (0,-1), (-1,-1), 0.6, NAVY),
            ('LEFTPADDING', (0,0), (-1,-1), 3),('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 2.5),('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.1*cm))

    story.append(Spacer(1, 0.2*cm))
    # ===== Sección de FOB MINAGRI por producto con variación diaria =====
    # Patrones de matching FOB para cada cereal (subtipo principal + presentación a granel)
    FOB_FILTERS = [
        ('Maíz',    'maíz, los demás',           'a granel con hasta un 15'),
        ('Trigo',   'trigo, trigo pan',          'a granel con hasta un 15'),
        ('Sorgo',   'sorgo granífero, los demás','a granel con hasta un 15'),
        ('Cebada',  'cebada, en grano',          'a granel con hasta un 15'),
    ]
    # Index previous FOB por (desc, m_from, m_to) -> price
    prev_idx = {}
    if prev_fob_data:
        for ncm, desc, price, mf, mt in prev_fob_data:
            prev_idx[(desc, mf, mt)] = float(price)

    def variation_pretty(today_p, prev_p):
        if prev_p is None: return '—'
        d = today_p - prev_p
        sign = '+' if d > 0 else ('' if d == 0 else '−')
        absd = abs(d)
        absd_s = f'{absd:.0f}' if absd == int(absd) else f'{absd:.1f}'.replace('.', ',')
        return f'{sign}{absd_s}'

    story.append(Spacer(1, 0.2*cm))
    section_h = ParagraphStyle('SH', parent=styles['Heading2'], fontName='Helvetica-Bold',
                               fontSize=10, textColor=NAVY, spaceBefore=4, spaceAfter=3, leading=12)
    prev_note = '' if prev_fob_date_str else ' <font size=7 color="#64748b">(primera ejecución — sin variación)</font>'
    story.append(Paragraph('Precios FOB MINAGRI por producto · variación diaria' + prev_note, section_h))

    # Layout: 2 mini tables per row (Maíz+Trigo on row 1, Sorgo+Cebada... on row 2)
    # Headers de las columnas de FOB con las fechas reales
    col_hoy_label = f'FOB {fob_dt_str}'
    col_ayer_label = f'FOB {prev_fob_date_str}' if prev_fob_date_str else 'FOB previo'

    def build_fob_table(label, desc_pat, pres_pat):
        # Filter rows
        relevant = [r for r in fob_data
                    if desc_pat in r[1].lower() and (pres_pat in r[1].lower() or not pres_pat)]
        if not relevant:
            return None
        head = [['Mes embarque', col_hoy_label, col_ayer_label, 'Δ']]
        rows = []
        for ncm, desc, price, mf, mt in relevant:
            p_today = float(price)
            p_prev = prev_idx.get((desc, mf, mt))
            month_label = mf if mf == mt or not mt else f'{mf}→{mt}'
            if not mf:
                month_label = '(único)'
            rows.append([
                month_label,
                f'{int(p_today)}',
                f'{int(p_prev)}' if p_prev is not None else '—',
                variation_pretty(p_today, p_prev),
            ])
        return head + rows, label

    tables_data = []
    for label, desc_pat, pres_pat in FOB_FILTERS:
        result = build_fob_table(label, desc_pat, pres_pat)
        if result is None: continue
        tables_data.append((label, result[0]))

    # Render in 2-column grid
    def style_mini(tbl):
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), rl_colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [rl_colors.white, LIGHT]),
            ('LEFTPADDING', (0,0), (-1,-1), 3),('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 1.8),('BOTTOMPADDING', (0,0), (-1,-1), 1.8),
        ]))
        return tbl

    label_style = ParagraphStyle('LBL', parent=styles['Normal'], fontName='Helvetica-Bold',
                                 fontSize=8.5, textColor=NAVY, spaceAfter=1, leading=10)
    def cell_block(label, rows):
        # Returns a single Table with title row + data table embedded as cells.
        inner = style_mini(Table(rows, colWidths=[3.0*cm, 1.5*cm, 1.5*cm, 1.5*cm]))
        wrapper = Table([[Paragraph(label, label_style)], [inner]], colWidths=[7.5*cm])
        wrapper.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1),'TOP'),
            ('LEFTPADDING', (0,0),(-1,-1), 0),('RIGHTPADDING', (0,0),(-1,-1), 0),
            ('TOPPADDING', (0,0),(-1,-1), 0),('BOTTOMPADDING', (0,0),(-1,-1), 2),
        ]))
        return wrapper

    blocks = [cell_block(lab, rows) for lab, rows in tables_data]
    # Render in pairs (2 columns)
    for i in range(0, len(blocks), 2):
        left = blocks[i]
        right = blocks[i+1] if i+1 < len(blocks) else Spacer(1, 0.1*cm)
        row_tbl = Table([[left, right]], colWidths=[8.5*cm, 8.5*cm])
        row_tbl.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1),'TOP'),
            ('LEFTPADDING', (0,0),(-1,-1), 0),
            ('RIGHTPADDING', (0,0),(-1,-1), 6),
            ('TOPPADDING', (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ]))
        story.append(row_tbl)

    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f'Fuentes: MAGyP – DJVE Ley 21.453 (Aprobadas) · DINEM – FOB Oficial circular publicada el {fob_dt_str}. '
        f'Variación FOB: diferencia en USD/t respecto del último FOB publicado anterior. '
        f'Presentación FOB asumida "A granel ≤ 15% embolsado".', FOOT))

    doc.build(story)
    print(f"   PDF: {out_path}")

for p in [dated_out, latest_out]:
    build_doc(p)

# ===== 5. Send email — solo si hay DJVE registradas hoy =====
step("5. Verificando si las DJVE de hoy están publicadas")
today_cal_date = datetime.now().date()
djve_today = df[df['fecha_registro_dt'].apply(
    lambda d: d.date() == today_cal_date if d is not None else False
)]
if len(djve_today) == 0:
    print(f"   Las DJVE del {today_cal_date:%d/%m/%Y} no están publicadas todavía. "
          f"No se envía mail. (Último registro disponible: {fecha_reg})")
    print("\n✔ Script terminado sin envío. Cache FOB actualizado.")
    sys.exit(0)

print(f"   ✓ Hay {len(djve_today)} DJVE registradas hoy. Procedo a enviar.")
step("6. Enviando mail")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from send_email import send_report
    cereal_kws = [kw for _, kw in CEREALES]
    df_cer_email = df_big[df_big['producto'].apply(lambda p: any(kw in p.upper() for kw in cereal_kws))]
    summary = {
        'fecha_registro': fecha_reg,
        'total_djve': len(df_cer_email),
        'total_ton_fmt': (fmt_int(df_cer_email['toneladas_num'].sum()) + ' t') if len(df_cer_email) else '0 t',
        'n_shippers': df_cer_email['razon_social'].nunique() if len(df_cer_email) else 0,
        'top_prod': '-',
        'top_prod_pct': '',
        'top_shipper': '-',
    }
    if len(df_cer_email) > 0:
        top_p = df_cer_email.groupby('producto')['toneladas_num'].sum().sort_values(ascending=False)
        summary['top_prod'] = top_p.index[0]
        summary['top_shipper'] = df_cer_email.groupby('razon_social')['toneladas_num'].sum().sort_values(ascending=False).index[0]
    env_path = BASE / '.djve_env'
    send_report(latest_out, env_path, summary)
except Exception as e:
    print(f"   [WARN] No se pudo enviar el mail: {type(e).__name__}: {e}")

print("\n✔ Informe diario completado.")
