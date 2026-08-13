#!/usr/bin/env python3
# bts-cloud-production.py
# BTS - Bandwidth Telemetry System - Cloud Edition
# Versión con diseño optimizado para pantalla

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
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
# INTERFACES (IDs válidos para HTML)
# ============================================
COLORS = [
    {'down': '#00f3ff', 'up': '#008b91', 'fill': 'rgba(0,243,255,0.06)'},
    {'down': '#70ff00', 'up': '#459900', 'fill': 'rgba(112,255,0,0.06)'},
    {'down': '#ffb800', 'up': '#a37500', 'fill': 'rgba(255,184,0,0.06)'},
    {'down': '#ff007a', 'up': '#a6004f', 'fill': 'rgba(255,0,122,0.06)'},
    {'down': '#a855f7', 'up': '#7c3aed', 'fill': 'rgba(168,85,247,0.06)'},
    {'down': '#f472b6', 'up': '#db2777', 'fill': 'rgba(244,114,182,0.06)'},
    {'down': '#f59e0b', 'up': '#b45309', 'fill': 'rgba(245,158,11,0.06)'},
]

# ============================================
# INTERFACES CON MAPEO CORRECTO
# ============================================
INTERFACES = [
    {
        'id': 'sfp1-WAN-FIBEX',
        'color': COLORS[0],
        'limit': 100,  # ⬇️ Reducido para mejor visualización
        'display_name': '🌐 WAN',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': 'sfp1-WAN-FIBEX'
    },
    {
        'id': 'bridge',
        'color': COLORS[1],
        'limit': 50,   # ⬇️ Reducido
        'display_name': '🔗 Bridge',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': 'bridge'
    },
    {
        'id': 'ether2',
        'color': COLORS[2],
        'limit': 50,   # ⬇️ Reducido
        'display_name': '🏢 Clientes',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': 'ether2'
    },
    {
        'id': 'ether1',
        'color': COLORS[3],
        'limit': 20,   # ⬇️ Reducido
        'display_name': '🏠 Casa',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': 'ether1'
    },
    {
        'id': 'pppoe-andres-bodega',
        'color': COLORS[4],
        'limit': 20,   # ⬇️ Reducido
        'display_name': '👤 Andrés',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': '<pppoe-andres.bodega>'
    },
    {
        'id': 'pppoe-isaura-zambrano',
        'color': COLORS[5],
        'limit': 20,   # ⬇️ Reducido
        'display_name': '👤 Isaura',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': '<pppoe-isaura.zambrano>'
    },
    {
        'id': 'ether6',
        'color': COLORS[6],
        'limit': 30,   # ⬇️ Reducido
        'display_name': '📶 WiFi',
        'alertas': {'saturacion': True, 'caida_down': True, 'caida_up': False},
        'vlans': [],
        'mikrotik_name': 'ether6'
    },
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
            'x': [], 'yd': [], 'yu': []
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
                        'time': now
                    })
                    
                    data_manager.stats[uid]['x'].append(timestamp)
                    data_manager.stats[uid]['yd'].append(d_mbps)
                    data_manager.stats[uid]['yu'].append(u_mbps)
                    
                    if len(data_manager.stats[uid]['x']) > 30:
                        for key in ['x', 'yd', 'yu']:
                            data_manager.stats[uid][key].pop(0)

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
        
        time.sleep(2)

# ============================================
# FUNCIÓN DE GAUGE - VERSIÓN COMPACTA
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
            'font': {'size': 14, 'color': 'white', 'family': 'Share Tech Mono'}
        },
        gauge={
            'axis': {
                'range': [0, r_max],
                'tickfont': {'size': 6, 'color': '#666'},
                'tickcolor': '#333',
                'nticks': 3
            },
            'bar': {'color': bar_color, 'thickness': 0.25},
            'bgcolor': 'rgba(255,255,255,0.02)',
            'borderwidth': 0,
            'steps': [
                {'range': [0, r_max * 0.7], 'color': 'rgba(255,255,255,0.01)'},
                {'range': [r_max * 0.7, r_max * 0.9], 'color': 'rgba(255,184,0,0.03)'},
                {'range': [r_max * 0.9, r_max], 'color': 'rgba(255,34,68,0.05)'},
            ],
            'threshold': {'line': {'color': bar_color, 'width': 1.5}, 'thickness': 0.6, 'value': display_val}
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        autosize=True,
        margin=dict(l=4, r=4, t=20, b=4),
        font={'family': 'Share Tech Mono'},
        height=110,
        title={
            'text': f'<b>{title}</b>',
            'font': {'color': color, 'size': 8, 'family': 'Share Tech Mono'},
            'y': 0.88,
            'x': 0.5
        }
    )
    return fig

# ============================================
# APLICACIÓN DASH - VERSIÓN COMPACTA
# ============================================
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        'backgroundColor': '#0a0e1a',
        'padding': '8px',
        'minHeight': '100vh',
        'fontFamily': 'Share Tech Mono, monospace',
        'display': 'flex',
        'flexDirection': 'column',
        'gap': '4px'
    },
    children=[
        # Header compacto
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'padding': '4px 12px',
                'borderBottom': '1px solid rgba(0,243,255,0.08)',
                'flexShrink': 0
            },
            children=[
                html.Div(
                    style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'},
                    children=[
                        html.Span("📡", style={'fontSize': '20px'}),
                        html.Span(
                            "BANDWIDTH TELEMETRY",
                            style={'color': '#00f3ff', 'fontSize': '14px', 'letterSpacing': '3px', 'fontWeight': 'bold'}
                        ),
                        html.Span(
                            "| 7 interfaces",
                            style={'color': 'rgba(0,243,255,0.4)', 'fontSize': '10px'}
                        )
                    ]
                ),
                html.Div(
                    id='ts-display',
                    style={'color': 'rgba(0,243,255,0.5)', 'fontSize': '10px'}
                )
            ]
        ),
        
        # Grid de gauges - 4 columnas para mejor distribución
        html.Div(
            style={
                'display': 'grid',
                'gridTemplateColumns': 'repeat(4, 1fr)',
                'gap': '4px',
                'flex': '1'
            },
            children=[html.Div(
                id=f"box-{uid}",
                style={
                    'background': 'rgba(6,10,18,0.9)',
                    'borderRadius': '6px',
                    'border': '1px solid rgba(0,243,255,0.06)',
                    'padding': '2px',
                    'display': 'flex',
                    'flexDirection': 'column'
                }
            ) for uid in ALL_BOX_IDS]
        ),
        
        dcc.Interval(id='tick', interval=2000)
    ]
)

# ============================================
# CALLBACKS
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
                style={'display': 'flex', 'flexDirection': 'row', 'height': '100%'},
                children=[
                    html.Div(
                        style={'flex': '1', 'padding': '2px'},
                        children=[
                            dcc.Graph(
                                figure=make_gauge(hw_cpu, '#00f3ff', "CPU", is_percentage=True),
                                config={'displayModeBar': False},
                                style={'height': '100%'}
                            )
                        ]
                    ),
                    html.Div(
                        style={'flex': '1', 'padding': '2px'},
                        children=[
                            dcc.Graph(
                                figure=make_gauge(hw_ram, '#ff007a', "RAM", is_percentage=True),
                                config={'displayModeBar': False},
                                style={'height': '100%'}
                            )
                        ]
                    )
                ]
            ))
        else:
            item = next((i for i in INTERFACES if i['id'] == box_id), None)
            if item:
                st = data_manager.stats[box_id]
                d_mbps = st['yd'][-1] if st['yd'] else 0
                u_mbps = st['yu'][-1] if st['yu'] else 0
                color = item['color']['down']
                card_contents.append(html.Div(
                    style={'display': 'flex', 'flexDirection': 'row', 'height': '100%'},
                    children=[
                        html.Div(
                            style={'flex': '1', 'padding': '1px'},
                            children=[
                                dcc.Graph(
                                    figure=make_gauge(d_mbps, color, "▼", item['limit']),
                                    config={'displayModeBar': False},
                                    style={'height': '100%'}
                                )
                            ]
                        ),
                        html.Div(
                            style={'flex': '1', 'padding': '1px'},
                            children=[
                                dcc.Graph(
                                    figure=make_gauge(u_mbps, item['color']['up'], "▲", item['limit']),
                                    config={'displayModeBar': False},
                                    style={'height': '100%'}
                                )
                            ]
                        )
                    ]
                ))
    
    status = "🟢" if data_manager.connection_status else "🔴"
    ts = data_manager.last_ts or "---"
    return card_contents + [f"{status} {ts}"]

# ============================================
# INICIO
# ============================================
threading.Thread(target=fetch_mikrotik_data, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
