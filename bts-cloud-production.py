#!/usr/bin/env python3
# bts-cloud-production.py
# BTS - Bandwidth Telemetry System - Versión SIN PARPADEO

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import time
import routeros_api
from datetime import datetime
import threading
import os
import logging
import json

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
# CONFIGURACIÓN DE INTERFACES
# ============================================
COLORS = [
    {'down': '#00d4ff', 'up': '#0088aa'},
    {'down': '#00ff88', 'up': '#00aa55'},
    {'down': '#ffaa00', 'up': '#cc7700'},
    {'down': '#ff3366', 'up': '#cc0033'},
    {'down': '#aa66ff', 'up': '#7733cc'},
    {'down': '#ff66aa', 'up': '#cc3377'},
    {'down': '#66ffcc', 'up': '#33cc99'},
]

INTERFACES = [
    {'id': 'wan', 'display': 'WAN', 'color': COLORS[0], 'limit': 20, 'mikrotik': 'sfp1-WAN-FIBEX'},
    {'id': 'bridge', 'display': 'Bridge', 'color': COLORS[1], 'limit': 10, 'mikrotik': 'bridge'},
    {'id': 'clientes', 'display': 'Clientes', 'color': COLORS[2], 'limit': 10, 'mikrotik': 'ether2'},
    {'id': 'casa', 'display': 'Casa', 'color': COLORS[3], 'limit': 15, 'mikrotik': 'ether1'},
    {'id': 'andres', 'display': 'Andrés', 'color': COLORS[4], 'limit': 10, 'mikrotik': '<pppoe-andres.bodega>'},
    {'id': 'isaura', 'display': 'Isaura', 'color': COLORS[5], 'limit': 15, 'mikrotik': '<pppoe-isaura.zambrano>'},
    {'id': 'wifi', 'display': 'WiFi', 'color': COLORS[6], 'limit': 10, 'mikrotik': 'ether6'},
]

ALL_IDS = [i['id'] for i in INTERFACES]

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

data = DataStore()

# ============================================
# OBTENCIÓN DE DATOS
# ============================================
def fetch_data():
    conn = None
    while True:
        try:
            if conn is None:
                conn = routeros_api.RouterOsApiPool(
                    MIKROTIK_HOST, username=MIKROTIK_USER,
                    password=MIKROTIK_PASSWORD, port=MIKROTIK_PORT,
                    plaintext_login=True
                )
                api = conn.get_api()
                data.online = True

            interfaces = api.get_resource('/interface').get()
            resource = api.get_resource('/system/resource').get()

            data.ts = datetime.now().strftime("%H:%M:%S")

            for item in INTERFACES:
                raw = next((i for i in interfaces if i.get('name') == item['mikrotik']), {})
                if raw:
                    rx = int(raw.get('rx-byte', 0))
                    tx = int(raw.get('tx-byte', 0))
                    
                    # Calcular Mbps (simplificado)
                    data.values[item['id']] = {
                        'down': round(rx / 125000, 2),
                        'up': round(tx / 125000, 2)
                    }

            if resource:
                r = resource[0]
                total = float(r.get('total-memory', 1))
                free = float(r.get('free-memory', 0))
                data.hw = {
                    'cpu': float(r.get('cpu-load', 0)),
                    'ram': round(((total - free) / total) * 100, 1)
                }

        except Exception as e:
            logger.error(f"Error: {e}")
            data.online = False
            conn = None
            time.sleep(5)
        
        time.sleep(1)

threading.Thread(target=fetch_data, daemon=True).start()

# ============================================
# CREAR GAUGE ESTÁTICO (una sola vez)
# ============================================
def create_gauge(id_name, color, limit, display_name, is_hw=False):
    """Crea un gauge y devuelve la figura y el último valor"""
    
    r_max = 100 if is_hw else limit
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=0,
        number={
            'valueformat': '.1f',
            'suffix': '%' if is_hw else 'M',
            'font': {'size': 16, 'color': 'white', 'family': 'Arial Black, sans-serif'}
        },
        gauge={
            'axis': {
                'range': [0, r_max],
                'tickfont': {'size': 8, 'color': '#666'},
                'nticks': 3
            },
            'bar': {'color': color, 'thickness': 0.4},
            'bgcolor': 'rgba(255,255,255,0.02)',
            'steps': [
                {'range': [0, r_max * 0.7], 'color': 'rgba(255,255,255,0.01)'},
                {'range': [r_max * 0.7, r_max * 0.9], 'color': 'rgba(255,184,0,0.03)'},
                {'range': [r_max * 0.9, r_max], 'color': 'rgba(255,34,68,0.04)'},
            ],
            'threshold': {'line': {'color': color, 'width': 2}, 'thickness': 0.6, 'value': 0}
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=2, r=2, t=22, b=2),
        height=90,
        font={'family': 'Arial Black, sans-serif'},
        title={
            'text': f'<b>{display_name}</b>',
            'font': {'color': color, 'size': 9, 'family': 'Arial Black, sans-serif'},
            'y': 0.88,
            'x': 0.5
        }
    )
    
    return fig

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
    <title>BTS - Bandwidth Telemetry</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { background:#0a0e1a; overflow:hidden; font-family:'Arial Black',sans-serif; }
        .wrap { display:flex; flex-direction:column; height:100vh; padding:4px 6px; gap:2px; }
        .header { display:flex; justify-content:space-between; align-items:center; padding:2px 6px; border-bottom:1px solid rgba(0,212,255,0.06); flex-shrink:0; }
        .header h1 { color:#00d4ff; font-size:13px; letter-spacing:2px; }
        .header span { color:rgba(0,212,255,0.25); font-size:9px; margin-left:6px; }
        .header-status { color:rgba(0,212,255,0.3); font-size:9px; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:2px; flex:1; }
        .card { background:rgba(6,10,18,0.85); border-radius:3px; border:1px solid rgba(0,212,255,0.04); padding:1px; display:flex; flex-direction:column; overflow:hidden; }
        .row { display:flex; flex-direction:row; height:100%; gap:1px; }
        .half { flex:1; min-width:0; }
        .half .js-plotly-plot { height:100% !important; width:100% !important; }
        .half .plot-container { height:100% !important; width:100% !important; }
        .half svg { height:100% !important; width:100% !important; }
        ::-webkit-scrollbar { display:none; }
        .sys-card .half { padding:1px; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

# ============================================
# CREAR GAUGES INICIALES
# ============================================
initial_figs = {}

for item in INTERFACES:
    initial_figs[f"{item['id']}_d"] = create_gauge(item['id'], item['color']['down'], item['limit'], f"▼ {item['display']}")
    initial_figs[f"{item['id']}_u"] = create_gauge(item['id'], item['color']['up'], item['limit'], f"▲ {item['display']}")

# Hardware
initial_figs['cpu'] = create_gauge('cpu', '#00d4ff', 100, 'CPU', is_hw=True)
initial_figs['ram'] = create_gauge('ram', '#ff3366', 100, 'RAM', is_hw=True)

# ============================================
# LAYOUT
# ============================================
app.layout = html.Div(
    className='wrap',
    children=[
        html.Div(
            className='header',
            children=[
                html.Div(children=[
                    html.H1("📡 BANDWIDTH TELEMETRY"),
                    html.Span("| 7 interfaces")
                ]),
                html.Div(id='ts-display', className='header-status')
            ]
        ),
        html.Div(
            className='grid',
            children=[html.Div(
                className='card',
                id=f"box-{item['id']}",
                children=[
                    html.Div(
                        className='row',
                        children=[
                            html.Div(
                                className='half',
                                children=[dcc.Graph(
                                    id=f"g-{item['id']}-d",
                                    figure=initial_figs[f"{item['id']}_d"],
                                    config={'displayModeBar': False, 'responsive': True}
                                )]
                            ),
                            html.Div(
                                className='half',
                                children=[dcc.Graph(
                                    id=f"g-{item['id']}-u",
                                    figure=initial_figs[f"{item['id']}_u"],
                                    config={'displayModeBar': False, 'responsive': True}
                                )]
                            )
                        ]
                    )
                ]
            ) for item in INTERFACES] + [
                html.Div(
                    className='card sys-card',
                    id="box-sys",
                    children=[
                        html.Div(
                            className='row',
                            children=[
                                html.Div(
                                    className='half',
                                    children=[dcc.Graph(
                                        id="g-cpu",
                                        figure=initial_figs['cpu'],
                                        config={'displayModeBar': False, 'responsive': True}
                                    )]
                                ),
                                html.Div(
                                    className='half',
                                    children=[dcc.Graph(
                                        id="g-ram",
                                        figure=initial_figs['ram'],
                                        config={'displayModeBar': False, 'responsive': True}
                                    )]
                                )
                            ]
                        )
                    ]
                )
            ]
        ),
        dcc.Interval(id='tick', interval=1000)
    ]
)

# ============================================
# CALLBACK - ACTUALIZACIÓN SIN PARPADEO
# ============================================
@app.callback(
    [Output(f"g-{item['id']}-d", "extendData") for item in INTERFACES] +
    [Output(f"g-{item['id']}-u", "extendData") for item in INTERFACES] +
    [Output("g-cpu", "extendData"),
     Output("g-ram", "extendData"),
     Output("ts-display", "children")],
    [Input('tick', 'n_intervals')]
)
def update(n):
    # Obtener datos
    with data.lock:
        vals = {k: v.copy() for k, v in data.values.items()}
        hw = data.hw.copy()
        ts = data.ts
        online = data.online
    
    # Preparar actualizaciones
    outputs = []
    
    # DOWN (▼) y UP (▲) para cada interfaz
    for item in INTERFACES:
        v = vals.get(item['id'], {'down': 0, 'up': 0})
        # DOWN
        outputs.append([{'value': [[v['down']]]}])
        # UP
        outputs.append([{'value': [[v['up']]]}])
    
    # CPU y RAM
    outputs.append([{'value': [[hw['cpu']]]}])   # CPU
    outputs.append([{'value': [[hw['ram']]]}])   # RAM
    
    # Status
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
