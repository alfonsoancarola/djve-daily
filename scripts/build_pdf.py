import json
from datetime import datetime
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak, KeepTogether)

# === Load data ===
with open('djve_data.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)
df = pd.DataFrame(raw)
df['toneladas_num'] = df['toneladas'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)

def pdate(s):
    try: return datetime.strptime(s, '%d/%m/%Y')
    except: return None
df['fecha_registro_dt']  = df['fecha_registro'].apply(pdate)
df['fecha_inicio_dt']    = df['fecha_inicio'].apply(pdate)

# === Metrics ===
total_djve = len(df)
total_ton  = df['toneladas_num'].sum()
n_emp      = df['razon_social'].nunique()
n_prod     = df['producto'].nunique()
fecha_min  = df['fecha_registro_dt'].min().strftime('%d/%m/%Y') if df['fecha_registro_dt'].notna().any() else '-'
fecha_max  = df['fecha_registro_dt'].max().strftime('%d/%m/%Y') if df['fecha_registro_dt'].notna().any() else '-'

por_prod = df.groupby('producto')['toneladas_num'].agg(['sum','count']).sort_values('sum', ascending=False)
top_exp  = df.groupby('razon_social')['toneladas_num'].agg(['sum','count']).sort_values('sum', ascending=False).head(10)

# Fecha del informe (hoy)
hoy = datetime.now().strftime('%d/%m/%Y')

def fmt_int(n):
    return f'{int(n):,}'.replace(',', '.')
def fmt_num(n):
    if n >= 100:
        return fmt_int(n)
    return f'{n:,.1f}'.replace(',', '.').replace('.','§').replace(',','.').replace('§',',')

# === Colors ===
NAVY = colors.HexColor('#1e3a8a')
AMBER = colors.HexColor('#f59e0b')
GREEN = colors.HexColor('#15803d')
LIGHT_GRAY = colors.HexColor('#f1f5f9')
DARK_TEXT = colors.HexColor('#0f172a')
MUTED = colors.HexColor('#64748b')

# === Styles ===
styles = getSampleStyleSheet()
H1 = ParagraphStyle('H1', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=NAVY, spaceAfter=2, leading=21)
SUB = ParagraphStyle('SUB', parent=styles['Normal'], fontName='Helvetica', fontSize=9.5, textColor=MUTED, spaceAfter=10)
H2 = ParagraphStyle('H2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11.5, textColor=NAVY, spaceBefore=8, spaceAfter=4)
NORM = ParagraphStyle('NORM', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=DARK_TEXT, leading=12)
KPI_LABEL = ParagraphStyle('KPI_LABEL', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=MUTED, alignment=TA_CENTER, leading=10)
KPI_VAL = ParagraphStyle('KPI_VAL', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, textColor=NAVY, alignment=TA_CENTER, leading=18)
FOOT = ParagraphStyle('FOOT', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7.5, textColor=MUTED, alignment=TA_LEFT, leading=9)

# === Build doc ===
out_path = '/sessions/happy-quirky-einstein/mnt/DJVE/Informe_DJVE_Aprobadas.pdf'
import os
os.makedirs(os.path.dirname(out_path), exist_ok=True)

doc = SimpleDocTemplate(out_path, pagesize=A4,
                        leftMargin=1.6*cm, rightMargin=1.6*cm,
                        topMargin=1.4*cm, bottomMargin=1.2*cm,
                        title='Informe Diario DJVE Aprobadas',
                        author='Cowork — DJVE Daily')

story = []

# --- Header ---
story.append(Paragraph('Informe Diario · DJVE Aprobadas', H1))
story.append(Paragraph(
    f'Declaraciones Juradas de Ventas al Exterior — Ley 21.453 &nbsp;·&nbsp; '
    f'Fuente: MAGyP &nbsp;·&nbsp; Registros del {fecha_min} &nbsp;·&nbsp; Generado el {hoy}',
    SUB))

# --- KPI strip ---
kpi_data = [[
    [Paragraph(fmt_int(total_djve), KPI_VAL), Paragraph('DJVE aprobadas', KPI_LABEL)],
    [Paragraph(fmt_int(total_ton), KPI_VAL), Paragraph('Toneladas totales', KPI_LABEL)],
    [Paragraph(str(n_emp), KPI_VAL), Paragraph('Empresas exportadoras', KPI_LABEL)],
    [Paragraph(str(n_prod), KPI_VAL), Paragraph('Productos distintos', KPI_LABEL)],
]]
kpi_tbl = Table(kpi_data, colWidths=[4.3*cm]*4, rowHeights=[1.6*cm])
kpi_tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), LIGHT_GRAY),
    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ('TOPPADDING', (0,0), (-1,-1), 6),
    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
]))
story.append(kpi_tbl)
story.append(Spacer(1, 0.4*cm))

# --- Highlight ---
top_prod_name = por_prod.index[0]
top_prod_ton  = por_prod.iloc[0]['sum']
top_prod_pct  = top_prod_ton/total_ton*100
top_exp_name  = top_exp.index[0]
top_exp_ton   = top_exp.iloc[0]['sum']
hl = (f'<b>Dato clave:</b> {top_prod_name} concentra el <b>{top_prod_pct:.1f}%</b> del volumen '
      f'({fmt_int(top_prod_ton)} t). El principal exportador del día es '
      f'<b>{top_exp_name}</b> con <b>{fmt_int(top_exp_ton)} t</b> declaradas.')
hl_tbl = Table([[Paragraph(hl, NORM)]], colWidths=[17.4*cm])
hl_tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fef3c7')),
    ('BOX', (0,0), (-1,-1), 0, AMBER),
    ('LINEBEFORE', (0,0), (0,-1), 3, AMBER),
    ('LEFTPADDING', (0,0), (-1,-1), 10),
    ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ('TOPPADDING', (0,0), (-1,-1), 7),
    ('BOTTOMPADDING', (0,0), (-1,-1), 7),
]))
story.append(hl_tbl)
story.append(Spacer(1, 0.35*cm))

# --- Charts row 1: Bar producto + Pie ---
img_bar = Image('chart_toneladas_producto.png', width=9.5*cm, height=5.1*cm)
img_pie = Image('chart_participacion_torta.png', width=8.2*cm, height=5.1*cm)
row1 = Table([[img_bar, img_pie]], colWidths=[9.7*cm, 8.3*cm])
row1.setStyle(TableStyle([('VALIGN', (0,0),(-1,-1),'TOP'), ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
story.append(row1)
story.append(Spacer(1, 0.2*cm))

# --- Charts row 2: Top exp + Cronograma ---
img_exp = Image('chart_top_exportadores.png', width=9.5*cm, height=5.4*cm)
img_cro = Image('chart_cronograma.png', width=8.2*cm, height=4.3*cm)
row2 = Table([[img_exp, img_cro]], colWidths=[9.7*cm, 8.3*cm])
row2.setStyle(TableStyle([('VALIGN', (0,0),(-1,-1),'TOP'), ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
story.append(row2)
story.append(Spacer(1, 0.3*cm))

# --- Page 2: Tables ---
story.append(PageBreak())
story.append(Paragraph('Detalle por producto', H2))

# Build product table
prod_rows = [['Producto', 'DJVE', 'Toneladas', 'Participación']]
for prod, row in por_prod.iterrows():
    pct = row['sum']/total_ton*100
    ton_str = fmt_int(row['sum']) if row['sum'] >= 100 else f"{row['sum']:.2f}".replace('.', ',')
    prod_rows.append([prod, str(int(row['count'])), ton_str, f'{pct:.2f}%'])
prod_rows.append(['TOTAL', str(total_djve), fmt_int(total_ton), '100,00%'])

prod_tbl = Table(prod_rows, colWidths=[7.5*cm, 2*cm, 4*cm, 3.9*cm])
prod_tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), NAVY),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,-1), 8.5),
    ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
    ('ALIGN', (0,0), (0,-1), 'LEFT'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT_GRAY]),
    ('LINEBELOW', (0,0), (-1,0), 1.2, NAVY),
    ('LINEABOVE', (0,-1), (-1,-1), 0.8, NAVY),
    ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#e2e8f0')),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
]))
story.append(prod_tbl)
story.append(Spacer(1, 0.4*cm))

# Top exporters table
story.append(Paragraph('Top 10 exportadores', H2))
exp_rows = [['#', 'Razón Social', 'DJVE', 'Toneladas', 'Participación']]
for i, (rs, row) in enumerate(top_exp.iterrows(), 1):
    pct = row['sum']/total_ton*100
    exp_rows.append([str(i), rs, str(int(row['count'])), fmt_int(row['sum']), f'{pct:.2f}%'])

exp_tbl = Table(exp_rows, colWidths=[0.8*cm, 9.6*cm, 2*cm, 2.5*cm, 2.5*cm])
exp_tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), NAVY),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,-1), 8.5),
    ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
    ('ALIGN', (0,0), (0,-1), 'CENTER'),
    ('ALIGN', (1,0), (1,-1), 'LEFT'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
    ('LINEBELOW', (0,0), (-1,0), 1.2, NAVY),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
]))
story.append(exp_tbl)

story.append(Spacer(1, 0.5*cm))
story.append(Paragraph(
    'Fuente: Ministerio de Economía – Secretaría de Bioeconomía – Subsecretaría de Mercados Agropecuarios. '
    'Informe automático generado en base a la página oficial de DJVE Ley 21.453. '
    'Las toneladas se expresan en formato argentino (coma como separador decimal). '
    'Este informe consolida solo las declaraciones actualmente aprobadas listadas en la pestaña "DJVE – Actual Aprobadas".',
    FOOT))

doc.build(story)
print(f"PDF generado: {out_path}")
import os
print(f"Tamaño: {os.path.getsize(out_path)/1024:.1f} KB")
