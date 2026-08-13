#!/usr/bin/env python3
# bts-cloud-production.py
# BTS - Bandwidth Telemetry System - CON SESIÓN PERSISTENTE

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import time
import routeros_api
from datetime import datetime
import threading
import os
import logging

# ============================================
# CONFIGURACIÓN
# ============================================
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST', '190.120.249.39')
MIKROTIK_USER = os.environ.get('MIKROTIK_USER', 'neoapi')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD', 'Xradio01*!')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# INTERFACES
# ============================================
INTERFACES = [
    {'id': 'wan', 'display': 'WAN', 'color': '#00d4ff', 'limit': 50, 'mikrotik': 'sfp1-WAN-FIBEX'},
    {'id': 'bridge', 'display': 'Bridge', 'color': '#00ff88', 'limit': 30, 'mikrotik': 'bridge'},
    {'id': 'clientes', 'display': 'Clientes', 'color': '#ffaa00', 'limit': 20, 'mikrotik': 'ether2'},
    {'id': 'casa', 'display': 'Casa', 'color': '#ff3366', 'limit': 15, 'mikrotik': 'ether1'},
    {'id': 'andres', 'display': 'Andrés', 'color': '#aa66ff', 'limit': 10, 'mikrotik': '<pppoe-andres.bodega>'},
    {'id': 'isaura', 'display': 'Isaura', 'color': '#ff66aa', 'limit': 15, 'mikrotik': '<pppoe-isaura.zambrano>'},
    {'id': 'wifi', 'display': 'WiFi', 'color': '#66ffcc', 'limit': 20, 'mikrotik': 'ether6'},
]

ALL_IDS = [i['id'] for i in INTERFACES]

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return ','.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

# ============================================
# DATOS EN MEMORIA
# ============================================
class DataStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.values = {i['id']: {'down': 0, 'up': 0} for i in INTERFACES}
        self.hw = {'cpu': 0, 'ram': 0}
        self.ts = ""
        self.online = False
        self.prev_rx = {i['id']: 0 for i in INTERFACES}
        self.prev_tx = {i['id']: 0 for i in INTERFACES}
        self.last_time = time.time()
        self.api = None
        self.connection = None
        self.connected = False

data = DataStore()

# ============================================
# CONEXIÓN PERSISTENTE A MIKROTIK
# ============================================
def connect_mikrotik():
    """Establece conexión persistente con el MikroTik"""
    try:
        if data.connection is None:
            logger.info("🔗 Estableciendo conexión persistente con MikroTik...")
            data.connection = routeros_api.RouterOsApiPool(
                MIKROTIK_HOST,
                username=MIKROTIK_USER,
                password=MIKROTIK_PASSWORD,
                port=MIKROTIK_PORT,
                plaintext_login=True
            )
            data.api = data.connection.get_api()
            data.connected = True
            data.online = True
            logger.info("✅ Conexión persistente establecida")
            
            # Inicializar contadores
            interfaces = data.api.get_resource('/interface').get()
            for item in INTERFACES:
                raw = next((i for i in interfaces if i.get('name') == item['mikrotik']), {})
                if raw:
                    data.prev_rx[item['id']] = int(raw.get('rx-byte', 0))
                    data.prev_tx[item['id']] = int(raw.get('tx-byte', 0))
            data.last_time = time.time()
            return True
        return data.connected
    except Exception as e:
        logger.error(f"❌ Error de conexión: {e}")
        data.connected = False
        data.online = False
        data.connection = None
        data.api = None
        return False

# ============================================
# OBTENER DATOS - SESIÓN PERSISTENTE
# ============================================
def fetch_data():
    first_run = True
    
    while True:
        try:
            # Si no hay conexión, intentar conectar
            if not data.connected or data.api is None:
                logger.info("🔄 Reconectando...")
                connect_mikrotik()
                if not data.connected:
                    time.sleep(5)
                    continue
                first_run = True

            # Obtener datos usando la misma sesión
            interfaces = data.api.get_resource('/interface').get()
            resource = data.api.get_resource('/system/resource').get()

            now = time.time()
            dt = now - data.last_time
            data.last_time = now
            data.ts = datetime.now().strftime("%H:%M:%S")

            for item in INTERFACES:
                raw = next((i for i in interfaces if i.get('name') == item['mikrotik']), {})
                if raw:
                    rx = int(raw.get('rx-byte', 0))
                    tx = int(raw.get('tx-byte', 0))
                    
                    if first_run:
                        data.prev_rx[item['id']] = rx
                        data.prev_tx[item['id']] = tx
                        data.values[item['id']] = {'down': 0, 'up': 0}
                        continue
                    
                    if dt > 0:
                        d_mbps = ((rx - data.prev_rx[item['id']]) * 8) / (dt * 1_000_000)
                        u_mbps = ((tx - data.prev_tx[item['id']]) * 8) / (dt * 1_000_000)
                    else:
                        d_mbps = 0
                        u_mbps = 0
                    
                    if d_mbps < 0 or d_mbps > 10000:
                        d_mbps = 0
                    if u_mbps < 0 or u_mbps > 10000:
                        u_mbps = 0
                    
                    data.prev_rx[item['id']] = rx
                    data.prev_tx[item['id']] = tx
                    
                    data.values[item['id']] = {
                        'down': round(d_mbps, 2),
                        'up': round(u_mbps, 2)
                    }
            
            first_run = False
            data.online = True

            if resource:
                r = resource[0]
                total = float(r.get('total-memory', 1))
                free = float(r.get('free-memory', 0))
                data.hw = {
                    'cpu': float(r.get('cpu-load', 0)),
                    'ram': round(((total - free) / total) * 100, 1)
                }

        except Exception as e:
            logger.error(f"❌ Error en fetch: {e}")
            data.online = False
            data.connected = False
            data.connection = None
            data.api = None
            time.sleep(5)
        
        time.sleep(0.5)

# ============================================
# INICIAR HILO DE DATOS
# ============================================
threading.Thread(target=fetch_data, daemon=True).start()

# ============================================
# DASH APP
# ============================================
app = dash.Dash(__name__)
server = app.server

app.index_string = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTS - Monitor</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { background:#0a0e1a; font-family:'Courier New',monospace; overflow:hidden; }
        .wrap { display:flex; flex-direction:column; height:100vh; padding:10px; gap:8px; }
        .header { display:flex; justify-content:space-between; align-items:center; padding:8px 16px; background:rgba(0,212,255,0.05); border-radius:8px; border:1px solid rgba(0,212,255,0.1); flex-shrink:0; }
        .header h1 { color:#00d4ff; font-size:16px; letter-spacing:2px; }
        .header-status { color:rgba(0,212,255,0.5); font-size:12px; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; flex:1; }
        .card { background:rgba(6,10,18,0.9); border-radius:8px; border:1px solid rgba(0,212,255,0.06); padding:12px; display:flex; flex-direction:column; justify-content:center; }
        .card .name { font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:2px; }
        .card .value { font-size:24px; font-weight:bold; }
        .card .value small { font-size:12px; font-weight:normal; opacity:0.5; }
        .row { display:flex; gap:10px; }
        .row .half { flex:1; }
        .sys { grid-column: span 2; }
        ::-webkit-scrollbar { display:none; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

app.layout = html.Div(
    className='wrap',
    children=[
        html.Div(
            className='header',
            children=[
                html.H1("📡 BANDWIDTH MONITOR"),
                html.Div(id='ts-display', className='header-status')
            ]
        ),
        html.Div(
            className='grid',
            children=[
                html.Div(
                    className='card',
                    id=f"card-{item['id']}",
                    style={'border-color': f"rgba({hex_to_rgb(item['color'])},0.2)"}
                ) for item in INTERFACES
            ] + [
                html.Div(
                    className='card sys',
                    id="card-sys",
                    style={'border-color': 'rgba(0,212,255,0.2)'}
                )
            ]
        ),
        dcc.Interval(id='tick', interval=500)
    ]
)

# ============================================
# CALLBACK
# ============================================
@app.callback(
    [Output(f"card-{item['id']}", "children") for item in INTERFACES] +
    [Output("card-sys", "children"),
     Output("ts-display", "children")],
    [Input('tick', 'n_intervals')]
)
def update(n):
    with data.lock:
        vals = {k: v.copy() for k, v in data.values.items()}
        hw = data.hw.copy()
        ts = data.ts
        online = data.online
    
    outputs = []
    
    for item in INTERFACES:
        v = vals.get(item['id'], {'down': 0, 'up': 0})
        color = item['color']
        outputs.append(html.Div([
            html.Div(item['display'], className='name', style={'color': color}),
            html.Div([
                html.Span(f"{v['down']:.1f}", className='value', style={'color': color}),
                html.Small(" ↓", style={'color': color})
            ]),
            html.Div([
                html.Span(f"{v['up']:.1f}", className='value', style={'color': color, 'opacity': '0.6'}),
                html.Small(" ↑", style={'color': color, 'opacity': '0.6'})
            ])
        ]))
    
    outputs.append(html.Div([
        html.Div("🖥️ SISTEMA", className='name', style={'color': '#00d4ff'}),
        html.Div(className='row', children=[
            html.Div(className='half', children=[
                html.Div(f"CPU {hw['cpu']:.1f}%", style={'color': '#00d4ff', 'fontSize': '18px'})
            ]),
            html.Div(className='half', children=[
                html.Div(f"RAM {hw['ram']:.1f}%", style={'color': '#ff3366', 'fontSize': '18px'})
            ])
        ])
    ]))
    
    dot = "●" if online else "○"
    color = "#00ff88" if online else "#ff3366"
    outputs.append(html.Span(f"{dot} {ts}", style={'color': color}))
    
    return outputs

# ============================================
# INICIO
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
