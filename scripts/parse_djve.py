import re
from bs4 import BeautifulSoup
import json
from datetime import datetime

with open('/tmp/djve_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# Find all tables — the approved one is the first big one
tables = soup.find_all('table')
print(f"Tables found: {len(tables)}")

# Look for the table containing the DJVE data — find by header content
target = None
for i, t in enumerate(tables):
    text = t.get_text()
    if 'Nº DJVE' in text and 'Razón Social' in text and 'Tonteladas' in text:
        target = t
        print(f"Found target table #{i}")
        break

if target is None:
    print("NO TABLE FOUND")
else:
    # Parse rows
    rows = target.find_all('tr')
    print(f"Total rows: {len(rows)}")
    data = []
    for r in rows[1:]:  # skip header
        cells = [c.get_text(strip=True) for c in r.find_all('td')]
        if len(cells) >= 9:
            # Clean whitespace inside the product name (e.g. "ACEITE DE    GIRASOL" -> "ACEITE DE GIRASOL")
            cells = [re.sub(r'\s+', ' ', c).strip() for c in cells]
            data.append({
                'sim': cells[0],
                'fecha_registro': cells[1],
                'fecha_presentacion': cells[2],
                'producto': cells[3],
                'toneladas': cells[4],
                'fecha_inicio': cells[5],
                'fecha_fin': cells[6],
                'opcion': cells[7],
                'razon_social': cells[8],
            })
    print(f"Data rows parsed: {len(data)}")
    print(json.dumps(data[:3], ensure_ascii=False, indent=2))
    with open('/sessions/happy-quirky-einstein/mnt/outputs/djve/djve_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Saved to djve_data.json")
