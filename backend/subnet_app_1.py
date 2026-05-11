"""
subnet_app.py  –  Subnet Calculator Python Backend
===================================================
Talks to the Arduino via TCP (Ethernet Shield) and/or Serial (USB).
Also serves a slick web UI at http://localhost:5000

Requirements:
    pip install flask pyserial

Run:
    python subnet_app.py
"""

import json
import socket
import threading
import time
from flask import Flask, request, jsonify, render_template_string

# ── Try to import serial (optional) ──────────────────────────────────────────
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG  –  edit these if needed
# ─────────────────────────────────────────────────────────────────────────────
ARDUINO_TCP_PORT = 8080
SERIAL_BAUD      = 9600
TCP_TIMEOUT      = 5   # seconds
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── State ─────────────────────────────────────────────────────────────────────
arduino_ip   = None   # discovered via user input or auto-scan
serial_port  = None   # e.g. "COM3" or "/dev/ttyUSB0"
connection_log = []

def log(msg):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    connection_log.append(entry)
    print(entry)
    if len(connection_log) > 100:
        connection_log.pop(0)

# ─────────────────────────────────────────────────────────────────────────────
# Communication helpers
# ─────────────────────────────────────────────────────────────────────────────

def query_arduino_tcp(ip, query):
    """Send query string to Arduino over TCP, return response string."""
    try:
        with socket.create_connection((ip, ARDUINO_TCP_PORT), timeout=TCP_TIMEOUT) as s:
            s.sendall((query + "\n").encode())
            data = b""
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
        response = data.decode().strip()
        log(f"TCP  → Arduino ({ip}): {query}")
        log(f"TCP  ← Arduino: {response}")
        return response
    except Exception as e:
        log(f"TCP error: {e}")
        return json.dumps({"error": str(e)})


def query_arduino_serial(port, query):
    """Send query over Serial (USB), return response string."""
    if not SERIAL_AVAILABLE:
        return json.dumps({"error": "pyserial not installed"})
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=TCP_TIMEOUT) as ser:
            time.sleep(0.1)
            ser.write((query + "\n").encode())
            response = ser.readline().decode().strip()
        log(f"Serial → Arduino ({port}): {query}")
        log(f"Serial ← Arduino: {response}")
        return response
    except Exception as e:
        log(f"Serial error: {e}")
        return json.dumps({"error": str(e)})


def compute_locally(ip_str, mask_str):
    """Fallback: compute subnet math in Python (no Arduino needed)."""
    try:
        def parse_ip(s):
            s = s.strip()
            if '.' not in s:   # CIDR prefix
                prefix = int(s)
                mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                return mask
            parts = s.split('.')
            if len(parts) != 4:
                raise ValueError("Bad IP")
            result = 0
            for p in parts:
                result = (result << 8) | int(p)
            return result

        def ip_to_str(n):
            return f"{(n>>24)&0xFF}.{(n>>16)&0xFF}.{(n>>8)&0xFF}.{n&0xFF}"

        ip   = parse_ip(ip_str)
        mask = parse_ip(mask_str)
        network   = ip & mask
        broadcast = network | (~mask & 0xFFFFFFFF)
        first     = network + 1
        last      = broadcast - 1
        hosts     = (~mask & 0xFFFFFFFF) - 1

        return {
            "ip":         ip_to_str(ip),
            "mask":       ip_to_str(mask),
            "network":    ip_to_str(network),
            "broadcast":  ip_to_str(broadcast),
            "first_host": ip_to_str(first),
            "last_host":  ip_to_str(last),
            "num_hosts":  hosts,
            "source":     "Python (local)"
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_UI)


@app.route("/api/calculate", methods=["POST"])
def calculate():
    data     = request.json or {}
    ip_str   = data.get("ip", "").strip()
    mask_str = data.get("mask", "").strip()
    mode     = data.get("mode", "local")   # "tcp" | "serial" | "local"

    if not ip_str or not mask_str:
        return jsonify({"error": "IP and mask required"}), 400

    query = f"{ip_str}/{mask_str}"

    if mode == "tcp" and arduino_ip:
        raw = query_arduino_tcp(arduino_ip, query)
        try:
            result = json.loads(raw)
            result["source"] = f"Arduino TCP ({arduino_ip})"
        except Exception:
            result = {"error": raw}

    elif mode == "serial" and serial_port:
        raw = query_arduino_serial(serial_port, query)
        try:
            result = json.loads(raw)
            result["source"] = f"Arduino Serial ({serial_port})"
        except Exception:
            result = {"error": raw}

    else:
        result = compute_locally(ip_str, mask_str)

    return jsonify(result)


@app.route("/api/set_arduino", methods=["POST"])
def set_arduino():
    global arduino_ip, serial_port
    data = request.json or {}
    if data.get("ip"):
        arduino_ip = data["ip"].strip()
        log(f"Arduino IP set to {arduino_ip}")
    if data.get("serial"):
        serial_port = data["serial"].strip()
        log(f"Serial port set to {serial_port}")
    return jsonify({"arduino_ip": arduino_ip, "serial_port": serial_port})


@app.route("/api/arduino_status")
def arduino_status():
    return jsonify({
        "arduino_ip":  arduino_ip,
        "serial_port": serial_port,
        "log":         connection_log[-20:]
    })


@app.route("/api/list_serial")
def list_serial():
    if not SERIAL_AVAILABLE:
        return jsonify({"ports": [], "error": "pyserial not installed"})
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return jsonify({"ports": ports})


@app.route("/api/ping_arduino", methods=["POST"])
def ping_arduino():
    global arduino_ip
    data = request.json or {}
    ip   = data.get("ip", arduino_ip)
    if not ip:
        return jsonify({"ok": False, "error": "No IP provided"})
    raw = query_arduino_tcp(ip, "192.168.0.1/255.255.255.0")
    try:
        r = json.loads(raw)
        if "network" in r:
            arduino_ip = ip
            return jsonify({"ok": True, "ip": ip})
    except Exception:
        pass
    return jsonify({"ok": False, "error": raw})

# ─────────────────────────────────────────────────────────────────────────────
# Embedded HTML UI (single file – no separate static folder needed)
# ─────────────────────────────────────────────────────────────────────────────
HTML_UI = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Subnet Calculator · Arduino</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0a0e14;
    --surface:  #0f1923;
    --card:     #14202e;
    --border:   #1e3a5f;
    --accent:   #00d4ff;
    --accent2:  #ff6b2b;
    --green:    #00ff9d;
    --text:     #c8dde8;
    --muted:    #4a6880;
    --danger:   #ff3b5c;
    --mono:     'Share Tech Mono', monospace;
    --sans:     'Rajdhani', sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  /* ── Grid background ── */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,.04) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }

  header {
    width: 100%;
    padding: 24px 40px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .logo { font-size: 28px; }
  header h1 {
    font-family: var(--sans);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--accent);
  }
  header p { font-size: 13px; color: var(--muted); font-family: var(--mono); }

  main {
    width: 100%;
    max-width: 960px;
    padding: 32px 24px;
    display: grid;
    gap: 24px;
  }

  /* ── Cards ── */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    position: relative;
    overflow: hidden;
  }
  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
  }
  .card h2 {
    font-size: 13px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 20px;
    font-family: var(--mono);
  }

  /* ── Form ── */
  .input-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end; }
  label { display: block; font-size: 12px; letter-spacing: 2px; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; }
  input[type=text] {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 14px;
    color: var(--accent);
    font-family: var(--mono);
    font-size: 16px;
    outline: none;
    transition: border-color .2s;
  }
  input[type=text]:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0,212,255,.1); }

  .mode-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
  .tab {
    padding: 6px 14px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: transparent;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 12px;
    cursor: pointer;
    transition: all .2s;
  }
  .tab.active { border-color: var(--accent); color: var(--accent); background: rgba(0,212,255,.08); }

  .btn {
    padding: 10px 24px;
    border: none;
    border-radius: 4px;
    background: var(--accent);
    color: var(--bg);
    font-family: var(--sans);
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    cursor: pointer;
    transition: all .2s;
    white-space: nowrap;
  }
  .btn:hover { background: #33ddff; transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn.secondary { background: transparent; border: 1px solid var(--accent); color: var(--accent); }
  .btn.danger { background: var(--danger); }

  /* ── Results ── */
  .results-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
  }
  .result-item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 16px;
    transition: border-color .2s;
  }
  .result-item.highlight { border-color: var(--accent2); }
  .result-item .r-label { font-size: 11px; letter-spacing: 2px; color: var(--muted); text-transform: uppercase; margin-bottom: 6px; }
  .result-item .r-value { font-family: var(--mono); font-size: 18px; color: var(--green); }
  .result-item.highlight .r-value { color: var(--accent2); }
  .source-tag {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    background: rgba(0,255,157,.1);
    border: 1px solid rgba(0,255,157,.3);
    color: var(--green);
    font-family: var(--mono);
    font-size: 11px;
    margin-top: 16px;
  }

  /* ── Arduino config ── */
  .arduino-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--muted);
    margin-right: 6px;
    transition: background .3s;
  }
  .status-dot.online { background: var(--green); box-shadow: 0 0 8px var(--green); }
  .status-dot.offline { background: var(--danger); }

  /* ── Log ── */
  .log-box {
    background: #060a0f;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 12px;
    height: 140px;
    overflow-y: auto;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    line-height: 1.6;
  }
  .log-box span { color: var(--accent); }

  /* ── Error ── */
  .error-box {
    background: rgba(255,59,92,.1);
    border: 1px solid var(--danger);
    border-radius: 4px;
    padding: 12px 16px;
    color: var(--danger);
    font-family: var(--mono);
    font-size: 13px;
    display: none;
  }

  /* ── Empty state ── */
  .empty {
    text-align: center;
    padding: 32px;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 13px;
  }

  @media (max-width: 600px) {
    .input-row { grid-template-columns: 1fr; }
    .arduino-row { grid-template-columns: 1fr; }
    .results-grid { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>

<header>
  <span class="logo">⬡</span>
  <div>
    <h1>Subnet Calculator</h1>
    <p>Arduino Uno + Ethernet Shield · Network Layer Project</p>
  </div>
</header>

<main>

  <!-- ── Calculation Card ── -->
  <div class="card">
    <h2>// Calculate Subnet</h2>

    <div class="mode-tabs">
      <button class="tab active" onclick="setMode('local', this)">Python Local</button>
      <button class="tab" onclick="setMode('tcp', this)">Arduino TCP</button>
      <button class="tab" onclick="setMode('serial', this)">Arduino Serial</button>
    </div>

    <div class="input-row">
      <div>
        <label>IP Address</label>
        <input type="text" id="ip" placeholder="192.168.1.50" />
      </div>
      <div>
        <label>Subnet Mask (dotted or CIDR)</label>
        <input type="text" id="mask" placeholder="255.255.255.0 or 24" />
      </div>
      <button class="btn" onclick="calculate()">CALCULATE</button>
    </div>

    <div class="error-box" id="errorBox"></div>

    <div id="results" style="margin-top:24px;">
      <div class="empty">Enter an IP and mask above to compute subnet details.</div>
    </div>
  </div>

  <!-- ── Arduino Config Card ── -->
  <div class="card">
    <h2>// Arduino Connection</h2>
    <p style="font-size:13px; color:var(--muted); margin-bottom:16px; font-family:var(--mono);">
      <span class="status-dot" id="statusDot"></span>
      <span id="statusText">Not connected</span>
    </p>

    <div class="arduino-row">
      <div>
        <label>Arduino IP (from Serial Monitor)</label>
        <div style="display:flex;gap:8px;">
          <input type="text" id="arduinoIp" placeholder="192.168.1.x" />
          <button class="btn secondary" onclick="pingArduino()">PING</button>
        </div>
      </div>
      <div>
        <label>Serial Port</label>
        <div style="display:flex;gap:8px;">
          <input type="text" id="serialPort" placeholder="COM3 or /dev/ttyUSB0" />
          <button class="btn secondary" onclick="loadPorts()">SCAN</button>
        </div>
      </div>
    </div>

    <div style="margin-top:12px;">
      <button class="btn secondary" onclick="saveArduinoConfig()">SAVE CONFIG</button>
    </div>

    <h2 style="margin-top:24px;">// Communication Log</h2>
    <div class="log-box" id="logBox">Waiting...</div>
  </div>

</main>

<script>
let mode = 'local';

function setMode(m, el) {
  mode = m;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
}

async function calculate() {
  const ip   = document.getElementById('ip').value.trim();
  const mask = document.getElementById('mask').value.trim();
  const errBox = document.getElementById('errorBox');
  errBox.style.display = 'none';

  if (!ip || !mask) { showError('Please enter IP and mask.'); return; }

  const res = await fetch('/api/calculate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ ip, mask, mode })
  });
  const data = await res.json();

  if (data.error) { showError('Error: ' + data.error); return; }
  renderResults(data);
  refreshLog();
}

function showError(msg) {
  const b = document.getElementById('errorBox');
  b.textContent = msg;
  b.style.display = 'block';
}

function renderResults(d) {
  document.getElementById('results').innerHTML = `
    <div class="results-grid">
      <div class="result-item"><div class="r-label">Host IP</div><div class="r-value">${d.ip}</div></div>
      <div class="result-item"><div class="r-label">Subnet Mask</div><div class="r-value">${d.mask}</div></div>
      <div class="result-item highlight"><div class="r-label">Network ID</div><div class="r-value">${d.network}</div></div>
      <div class="result-item highlight"><div class="r-label">Broadcast</div><div class="r-value">${d.broadcast}</div></div>
      <div class="result-item"><div class="r-label">First Host</div><div class="r-value">${d.first_host}</div></div>
      <div class="result-item"><div class="r-label">Last Host</div><div class="r-value">${d.last_host}</div></div>
      <div class="result-item"><div class="r-label">Usable Hosts</div><div class="r-value">${Number(d.num_hosts).toLocaleString()}</div></div>
    </div>
    <div class="source-tag">▸ Computed by: ${d.source || 'Python'}</div>
  `;
}

async function pingArduino() {
  const ip = document.getElementById('arduinoIp').value.trim();
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  txt.textContent = 'Pinging...';
  dot.className = 'status-dot';
  const res = await fetch('/api/ping_arduino', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ip})
  });
  const data = await res.json();
  if (data.ok) {
    dot.className = 'status-dot online';
    txt.textContent = `Connected · ${data.ip}`;
  } else {
    dot.className = 'status-dot offline';
    txt.textContent = `Unreachable · ${data.error}`;
  }
  refreshLog();
}

async function saveArduinoConfig() {
  const ip     = document.getElementById('arduinoIp').value.trim();
  const serial = document.getElementById('serialPort').value.trim();
  await fetch('/api/set_arduino', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ip, serial})
  });
  refreshLog();
}

async function loadPorts() {
  const res  = await fetch('/api/list_serial');
  const data = await res.json();
  if (data.ports && data.ports.length) {
    document.getElementById('serialPort').value = data.ports[0];
    alert('Found ports: ' + data.ports.join(', '));
  } else {
    alert('No serial ports found. Is Arduino connected via USB?');
  }
}

async function refreshLog() {
  const res  = await fetch('/api/arduino_status');
  const data = await res.json();
  const box  = document.getElementById('logBox');
  box.innerHTML = data.log.map(l => `<div>${l.replace(/\[.*?\]/, s => `<span>${s}</span>`)}</div>`).join('') || 'No activity yet.';
  box.scrollTop = box.scrollHeight;

  if (data.arduino_ip) document.getElementById('arduinoIp').value = data.arduino_ip;
  if (data.serial_port) document.getElementById('serialPort').value = data.serial_port;
}

// ── Keyboard shortcut ──
document.addEventListener('keydown', e => { if (e.key === 'Enter') calculate(); });

refreshLog();
setInterval(refreshLog, 5000);
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Subnet Calculator – Python Backend")
    print("  Open  →  http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
