# DJVE Daily Report

Informe diario de Declaraciones Juradas de Ventas al Exterior (Ley 21.453) con cálculo de replacement vs CBOT para maíz. Se ejecuta automáticamente cada día a las 16:00 ART desde GitHub Actions y envía el PDF por mail al grupo configurado.

## Qué hace

1. Scrapea las DJVE aprobadas de MAGyP (`magyp.gob.ar`)
2. Scrapea el FOB oficial Minagri del día (`dinem.magyp.gob.ar`)
3. Obtiene CBOT Corn nearest-forward (Yahoo Finance)
4. Filtra DJVE ≥ 500 t y arma una tabla por cereal (Maíz, Trigo, Sorgo, Cebada)
5. Calcula Premium c/bu para maíz: `(FOB U$/t × 100 / 39,368) − CBOT c/bu`
6. Compara los precios FOB con el último publicado y muestra Δ diaria
7. Genera PDF de 1 página y lo envía a la lista de destinatarios por SMTP (Gmail)

## Setup en GitHub (~10 minutos)

### 1. Crear el repo

- Andá a https://github.com/new
- Nombre: `djve-daily` (o el que prefieras)
- Visibilidad: **Privado** (las credenciales se guardan como secrets, pero igual conviene privado)
- No agregues README ni .gitignore — ya están en este proyecto
- Click en "Create repository"

### 2. Subir el código

Desde tu Mac, abrí Terminal y corré:

```bash
cd ~/Documents/Claude/Projects/DJVE
git init
git add .
git commit -m "init: DJVE daily report"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/djve-daily.git
git push -u origin main
```

Reemplazá `TU_USUARIO` por tu usuario de GitHub.

### 3. Configurar los Secrets

En el repo de GitHub, andá a **Settings → Secrets and variables → Actions → New repository secret** y creá estos tres:

| Nombre | Valor |
|---|---|
| `SMTP_USER` | `alfonso.ancarola@gmail.com` |
| `SMTP_APP_PASSWORD` | la app password de 16 chars (con espacios) |
| `EMAIL_RECIPIENTS` | la lista de mails separados por coma, sin espacios |

Por ejemplo para `EMAIL_RECIPIENTS`:
```
juan.carnemolla@ldc.com,gonzalo.lascombes@ldc.com,juan.garciafuentes@ldc.com,Roman.Avramishin@LDC.com,valentin.chiesa@ldc.com,alfonso.ancarola@ldc.com
```

### 4. Probar el workflow

- Andá a la pestaña **Actions** del repo
- En la izquierda click en "DJVE Daily Report"
- Click en **"Run workflow"** → confirmar
- Esperá ~3 minutos
- Si todo salió bien, los destinatarios reciben el mail

### 5. Deshabilitar el cron local de Claude (opcional)

Para evitar envíos duplicados:
- En la app de Claude (Cowork) → barra lateral → Scheduled
- Tarea `informe-diario-djve` → pausar o eliminar

## Estructura del proyecto

```
djve-daily/
├── .github/
│   └── workflows/
│       └── djve.yml          # workflow de GitHub Actions (cron 19:00 UTC = 16:00 ART)
├── scripts/
│   ├── run_daily.py          # pipeline completo
│   └── send_email.py         # envío SMTP
├── archive/
│   └── fob/                  # cache diario del FOB (se commitea solo)
├── requirements.txt
├── .gitignore
└── README.md
```

## Mantenimiento

**Cambiar destinatarios:** editar el secret `EMAIL_RECIPIENTS` en GitHub Settings (no requiere push de código).

**Cambiar horario:** editar la línea `cron:` en `.github/workflows/djve.yml`. Recordá que GitHub Actions usa **UTC**: para 16:00 ART poné `0 19 * * *`. Más info en [crontab.guru](https://crontab.guru/).

**Revocar app password:** generá una nueva en https://myaccount.google.com/apppasswords y actualizá el secret `SMTP_APP_PASSWORD`.

**Ver logs de cada corrida:** pestaña Actions del repo → click en la corrida → click en el job → expandir cada step.

## Notas

- El sender Gmail tiene un límite de ~500 mails/día. Estamos muy por debajo.
- El primer mail puede caer en Spam de los destinatarios — pedirles que lo marquen como "no spam" una vez.
- La página de MAGyP solo publica DJVE los días hábiles. Fines de semana el script igual corre pero no encuentra datos nuevos.
- El FOB Minagri solo se publica los días hábiles. El script busca hacia atrás hasta encontrar el último publicado.
