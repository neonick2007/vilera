#!/usr/bin/env python3
# bts-cloud-production.py
# BTS - Bandwidth Telemetry System - Cloud Edition
# Versión con actualización fluida y diseño optimizado

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
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
# COLORES MÁS VIVOS
# ============================================
COLORS = [
    {'down': '#00d4ff', 'up': '#0088aa', 'fill': 'rgba(0,212,255,0.08)'},
    {'down': '#00ff88', 'up': '#00aa55', 'fill': 'rgba(0,255,136,0.08)'},
    {'down': '#ffaa00', 'up': '#cc7700', 'fill': 'rgba(255,170,0,0.08)'},
    {'down': '#ff3366', 'up': '#cc0033', 'fill': 'rgba(255,51,102,0.08)'},
    {'down': '#aa66ff', 'up': '#7733cc', 'fill': 'rgba(170,102,255,0.08)'},
    {'down': '#ff66aa', 'up': '#cc3377', 'fill': 'rgba(255,102,170,0.08)'},
    {'down': '#66ffcc', 'up': '#33cc99', 'fill': 'rgba(102,255,204,0.08)'},
]

# ============================================
# INTERFACES CON LÍMITES AJUSTADOS
# ============================================
INTERFACES = [
    {'id': 'sfp1-WAN-FIBEX', 'color': COLORS[0], 'limit': 20, 'display_name': '🌐 WAN', 'mikrotik_name': 'sfp1-WAN-FIBEX'},
    {'id': 'bridge', 'color': COLORS[1], 'limit': 10, 'display_name': '🔗 Bridge', 'mikrotik_name': 'bridge'},
    {'id': 'ether2', 'color': COLORS[2], 'limit': 10, 'display_name': '🏢 Clientes', 'mikrotik_name': 'ether2'},
    {'id': 'ether1', 'color': COLORS[3], 'limit': 15, 'display_name': '🏠 Casa', 'mikrotik_name': 'ether1'},
    {'id': 'pppoe-andres-bodega', 'color': COLORS[4], 'limit': 10, 'display_name': '👤 Andrés', 'mikrotik_name': '<pppoe-andres.bodega>'},
    {'id': 'pppoe-isaura-zambrano', 'color': COLORS[5], 'limit': 15, 'display_name': '👤 Isaura', 'mikrotik_name': '<pppoe-isaura.zambrano>'},
    {'id': 'ether6', 'color': COLORS[6], 'limit': 10, 'display_name': '📶 WiFi', 'mikrotik_name': 'ether6'},
]

ALL_IDS = [i['id'] for i in INTERFACES]
ALL_BOX_IDS = ALL_IDS + ['system-hw']

# ============================================
# GESTOR DE DATOS
# ============================================
class BTSDataManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = {uid: {
            'd_last': 0, 'u_last': 0, 'time': time.time(),
            'd': 0.0, 'u': 0.0
        } for uid in ALL_IDS}
        self.hardware = {'cpu': 0, 'ram': 0}
        self.last_ts = ""
        self.connection_status = False
        self.last_error = ""

data_manager = BTSDataManager()

# ============================================
# FUNCIÓN DE OBTENCIÓN DE DATOS
# ============================================
def fetch_mikrotik_data():
    connection = None
    consecutive_failures = 0
    
    while True:
        try:
            if connection is None:
                logger.info(f"🔗 Conectando a {MIKROTIK_HOST}:{MIKROTIK_PORT}")
                connection = routeros_api.RouterOsApiPool(
                    MIKROTIK_HOST,
                    username=MIKROTIK_USER,
                    password=MIKROTIK_PASSWORD,
                    port=MIKROTIK_PORT,
                    plaintext_login=True
                )
                api = connection.get_api()
                data_manager.connection_status = True
                data_manager.last_error = ""
                consecutive_failures = 0
                logger.info("✅ Conectado al MikroTik")

            raw_data = api.get_resource('/interface').get()
            raw_resource = api.get_resource('/system/resource').get()
            timestamp = datetime.now().strftime("%H:%M:%S")
            data_manager.last_ts = timestamp

            for item in INTERFACES:
                uid = item['id']
                mikrotik_name = item['mikrotik_name']
                
                raw = next((i for i in raw_data if i.get('name') == mikrotik_name), {})
                
                if raw:
                    rx = int(raw.get('rx-byte', 0))
                    tx = int(raw.get('tx-byte', 0))
                    
                    now = time.time()
                    dt = now - data_manager.stats[uid]['time']
                    
                    if dt > 0 and data_manager.stats[uid]['d_last'] > 0:
                        d_mbps = round((((rx - data_manager.stats[uid]['d_last']) * 8) / dt) / 1e6, 2)
                        u_mbps = round((((tx - data_manager.stats[uid]['u_last']) * 8) / dt) / 1e6, 2)
                    else:
                        d_mbps = 0.0
                        u_mbps = 0.0

                    data_manager.stats[uid].update({
                        'd_last': rx,
                        'u_last': tx,
                        'time': now,
                        'd': d_mbps,
                        'u': u_mbps
                    })

            if raw_resource:
                res = raw_resource[0]
                cpu_usage = float(res.get('cpu-load', 0))
                total_mem = float(res.get('total-memory', 1))
                free_mem = float(res.get('free-memory', 0))
                ram_usage = round(((total_mem - free_mem) / total_mem) * 100, 1)
                data_manager.hardware = {'cpu': cpu_usage, 'ram': ram_usage}

            consecutive_failures = 0

        except Exception as e:
            consecutive_failures += 1
            data_manager.connection_status = False
            data_manager.last_error = str(e)
            logger.error(f"❌ Error ({consecutive_failures}): {e}")
            connection = None
            time.sleep(min(30, consecutive_failures * 2))
        
        time.sleep(1)  # Actualización cada 1 segundo

# ============================================
# FUNCIÓN DE GAUGE - OPTIMIZADA
# ============================================
def make_gauge(val, color, title, limit=None, is_percentage=False):
    if is_percentage:
        display_val, unit, r_max = val, "%", 100
    else:
        if limit is None:
            if val >= 1000:
                display_val, unit, r_max = val / 1000, "G", 10
            else:
                display_val, unit, r_max = val, "M", 1000
        else:
            display_val, unit, r_max = val, "M", limit

    pct = display_val / r_max if r_max > 0 else 0
    bar_color = '#ff2244' if pct > 0.9 else ('#ffb800' if pct > 0.7 else color)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=display_val,
        number={
            'valueformat': '.1f',
            'suffix': unit,
            'font': {'size': 13, 'color': 'white', 'family': 'Share Tech Mono'}
        },
        gauge={
            'axis': {
                'range': [0, r_max],
                'tickfont': {'size': 5, 'color': '#555'},
                'tickcolor': '#222',
                'nticks': 3
            },
            'bar': {'color': bar_color, 'thickness': 0.35},
            'bgcolor': 'rgba(255,255,255,0.01)',
            'borderwidth': 0,
            'steps': [
                {'range': [0, r_max * 0.7], 'color': 'rgba(255,255,255,0.005)'},
                {'range': [r_max * 0.7, r_max * 0.9], 'color': 'rgba(255,184,0,0.02)'},
                {'range': [r_max * 0.9, r_max], 'color': 'rgba(255,34,68,0.03)'},
            ],
            'threshold': {'line': {'color': bar_color, 'width': 1.5}, 'thickness': 0.5, 'value': display_val}
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        autosize=True,
        margin=dict(l=2, r=2, t=16, b=2),
        font={'family': 'Share Tech Mono'},
        height=85,
        title={
            'text': f'<b>{title}</b>',
            'font': {'color': color, 'size': 7, 'family': 'Share Tech Mono'},
            'y': 0.82,
            'x': 0.5
        }
    )
    return fig

# ============================================
# APLICACIÓN DASH - OPTIMIZADA
# ============================================
app = dash.Dash(__name__)
server = app.server

# CSS personalizado para mejor rendimiento
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>BTS - Bandwidth Telemetry</title>
        {%favicon%}
        {%css%}
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { background: #0a0e1a; overflow: hidden; font-family: 'Share Tech Mono', monospace; }
            .dashboard { display: flex; flex-direction: column; height: 100vh; padding: 4px; gap: 3px; }
            .header { display: flex; justify-content: space-between; align-items: center; padding: 2px 8px; border-bottom: 1px solid rgba(0,212,255,0.06); flex-shrink: 0; }
            .header-title { display: flex; align-items: center; gap: 6px; }
            .header-title h1 { color: #00d4ff; font-size: 13px; letter-spacing: 2px; font-weight: bold; }
            .header-title span { color: rgba(0,212,255,0.2); font-size: 9px; }
            .header-status { color: rgba(0,212,255,0.3); font-size: 9px; }
            .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px; flex: 1; min-height: 0; }
            .card { background: rgba(6,10,18,0.85); border-radius: 3px; border: 1px solid rgba(0,212,255,0.04); padding: 1px; display: flex; flex-direction: column; overflow: hidden; }
            .card-inner { display: flex; flex-direction: row; height: 100%; gap: 1px; }
            .card-half { flex: 1; min-width: 0; padding: 1px; }
            .graph-container { height: 100%; width: 100%; }
            .graph-container .js-plotly-plot { height: 100% !important; width: 100% !important; }
            .graph-container .plot-container { height: 100% !important; width: 100% !important; }
            .graph-container svg { height: 100% !important; width: 100% !important; }
            ::-webkit-scrollbar { display: none; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
    </body>
</html>
'''

app.layout = html.Div(
    className='dashboard',
    children=[
        # Header
        html.Div(
            className='header',
            children=[
                html.Div(
                    className='header-title',
                    children=[
                        html.Span("📡", style={'fontSize': '16px'}),
                        html.H1("BANDWIDTH TELEMETRY"),
                        html.Span("| 7 interfaces")
                    ]
                ),
                html.Div(
                    id='ts-display',
                    className='header-status'
                )
            ]
        ),
        
        # Grid de gauges
        html.Div(
            className='grid',
            children=[html.Div(
                className='card',
                id=f"box-{uid}"
            ) for uid in ALL_BOX_IDS]
        ),
        
        dcc.Interval(id='tick', interval=1000)  # Actualización cada 1 segundo
    ]
)

# ============================================
# CALLBACKS - OPTIMIZADOS
# ============================================
@app.callback(
    [Output(f"box-{uid}", "children") for uid in ALL_BOX_IDS] +
    [Output("ts-display", "children")],
    [Input('tick', 'n_intervals')]
)
def update_ui(n):
    card_contents = []
    
    for box_id in ALL_BOX_IDS:
        if box_id == 'system-hw':
            hw_cpu = data_manager.hardware['cpu']
            hw_ram = data_manager.hardware['ram']
            card_contents.append(html.Div(
                className='card-inner',
                children=[
                    html.Div(
                        className='card-half',
                        children=[
                            dcc.Graph(
                                figure=make_gauge(hw_cpu, '#00d4ff', "CPU", is_percentage=True),
                                config={'displayModeBar': False, 'responsive': True},
                                className='graph-container'
                            )
                        ]
                    ),
                    html.Div(
                        className='card-half',
                        children=[
                            dcc.Graph(
                                figure=make_gauge(hw_ram, '#ff3366', "RAM", is_percentage=True),
                                config={'displayModeBar': False, 'responsive': True},
                                className='graph-container'
                            )
                        ]
                    )
                ]
            ))
        else:
            item = next((i for i in INTERFACES if i['id'] == box_id), None)
            if item:
                st = data_manager.stats[box_id]
                d_mbps = st['d']
                u_mbps = st['u']
                color = item['color']['down']
                card_contents.append(html.Div(
                    className='card-inner',
                    children=[
                        html.Div(
                            className='card-half',
                            children=[
                                dcc.Graph(
                                    figure=make_gauge(d_mbps, color, "▼", item['limit']),
                                    config={'displayModeBar': False, 'responsive': True},
                                    className='graph-container'
                                )
                            ]
                        ),
                        html.Div(
                            className='card-half',
                            children=[
                                dcc.Graph(
                                    figure=make_gauge(u_mbps, item['color']['up'], "▲", item['limit']),
                                    config={'displayModeBar': False, 'responsive': True},
                                    className='graph-container'
                                )
                            ]
                        )
                    ]
                ))
    
    status = "●" if data_manager.connection_status else "○"
    color = "#00ff88" if data_manager.connection_status else "#ff3366"
    ts = data_manager.last_ts or "---"
    return card_contents + [html.Span(f"{ts}", style={'color': color})]

# ============================================
# INICIO
# ============================================
threading.Thread(target=fetch_mikrotik_data, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
