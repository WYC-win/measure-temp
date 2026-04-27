"""
温度实时网页仪表板
- 读取按自然日生成的 CSV 文件
- 浏览器中实时展示曲线和最新温度
- 无第三方后端依赖，仅使用标准库
"""
from __future__ import annotations

import csv
import glob
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Tuple
from urllib.parse import parse_qs, urlparse

TZ_BJ = timezone(timedelta(hours=8))
DATA_FILE_PREFIX = "temperature"
PORT = 8000
HOST = "127.0.0.1"

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.getenv("TEMP_DATA_DIR", str(SCRIPT_DIR.parent)))
FALLBACK_DIR = SCRIPT_DIR


@dataclass
class TemperaturePoint:
    ts: float
    temp: float


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Temperature Live Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3"></script>
  <style>
    :root {
      --bg: #08111f;
      --panel: rgba(15, 25, 42, 0.88);
      --panel-2: rgba(17, 29, 51, 0.95);
      --line: #6cf5ff;
      --line-soft: rgba(108, 245, 255, 0.14);
      --accent: #7bf7a6;
      --warn: #ffcc66;
      --text: #e8f1ff;
      --muted: #8aa0bd;
      --grid: rgba(140, 160, 190, 0.12);
      --shadow: 0 20px 40px rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(76, 201, 240, 0.12), transparent 30%),
        radial-gradient(circle at top right, rgba(123, 247, 166, 0.10), transparent 28%),
        linear-gradient(180deg, #09101d 0%, #050914 100%);
      min-height: 100vh;
    }
    .wrap {
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.25fr 0.75fr;
      gap: 18px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.06);
      box-shadow: var(--shadow);
      border-radius: 20px;
      backdrop-filter: blur(14px);
    }
    .title-card {
      padding: 24px 24px 18px;
      overflow: hidden;
      position: relative;
    }
    .title-card::after {
      content: "";
      position: absolute;
      inset: auto -10% -50% auto;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(108,245,255,0.18), transparent 68%);
      pointer-events: none;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      letter-spacing: 0.4px;
    }
    .sub {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .stat {
      padding: 16px 18px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-height: 92px;
      background: var(--panel-2);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .stat .label {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .stat .value {
      font-size: 28px;
      font-weight: 700;
      line-height: 1.1;
    }
    .stat .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 18px 0;
      align-items: center;
    }
    .btn {
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      padding: 10px 16px;
      border-radius: 999px;
      cursor: pointer;
      transition: 0.2s ease;
      font-size: 14px;
    }
    .btn:hover { transform: translateY(-1px); background: rgba(255,255,255,0.08); }
    .btn.active {
      background: linear-gradient(135deg, rgba(108,245,255,0.24), rgba(123,247,166,0.18));
      border-color: rgba(108,245,255,0.35);
      box-shadow: 0 0 0 1px rgba(108,245,255,0.08) inset;
    }
    .panel {
      padding: 18px;
    }
    .chart-wrap {
      height: 520px;
      position: relative;
    }
    canvas { width: 100% !important; height: 100% !important; }
    .footer-line {
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    @media (max-width: 1100px) {
      .hero { grid-template-columns: 1fr; }
    }
    @media (max-width: 700px) {
      .wrap { padding: 14px; }
      h1 { font-size: 24px; }
      .stat .value { font-size: 24px; }
      .chart-wrap { height: 380px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="card title-card">
        <h1>Temperature Live Dashboard</h1>
        <div class="sub">
          16楼321室内温度。
        </div>
        <div class="sub">
          浏览器实时查看温度趋势。页面会自动轮询 CSV 数据并更新曲线，数据源来自按自然日保存的文件。
        </div>
        <div class="toolbar">
          <button class="btn active" data-window="600">最近 10 分钟</button>
          <button class="btn" data-window="3600">最近 1 小时</button>
          <button class="btn" data-window="86400">当天全部</button>
          <button class="btn" id="refreshBtn">立即刷新</button>
        </div>
        <div class="footer-line">
          <div>数据文件：<span id="fileName">--</span></div>
          <div>最后刷新：<span id="refreshTime">--</span></div>
        </div>
      </div>
      <div class="stats">
        <div class="card stat">
          <div class="label">当前温度</div>
          <div class="value" id="currentTemp">--</div>
          <div class="hint" id="currentTime">等待数据...</div>
        </div>
        <div class="card stat">
          <div class="label">平均温度</div>
          <div class="value" id="avgTemp">--</div>
          <div class="hint">当前窗口内平均值</div>
        </div>
        <div class="card stat">
          <div class="label">最高 / 最低</div>
          <div class="value" id="minMaxTemp">--</div>
          <div class="hint">当前窗口内极值</div>
        </div>
        <div class="card stat">
          <div class="label">数据点</div>
          <div class="value" id="pointCount">0</div>
          <div class="hint" id="statusText">正在连接数据文件...</div>
        </div>
      </div>
    </div>

    <div class="card panel">
      <div class="chart-wrap">
        <canvas id="chart"></canvas>
      </div>
    </div>
  </div>

  <script>
    let chart;
    let currentWindow = 86400;
    let timer = null;

    function formatTime(ts) {
      return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
    }

    function initChart() {
      const ctx = document.getElementById('chart').getContext('2d');
      const gradient = ctx.createLinearGradient(0, 0, 0, 500);
      gradient.addColorStop(0, 'rgba(108, 245, 255, 0.30)');
      gradient.addColorStop(1, 'rgba(108, 245, 255, 0.02)');

      chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label: 'Temperature (°C)',
            data: [],
            borderColor: '#7ff6ff',
            backgroundColor: gradient,
            fill: true,
            tension: 0.28,
            pointRadius: 0,
            borderWidth: 2.5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: {
              labels: { color: '#dbe7ff' }
            },
            tooltip: {
              mode: 'index',
              intersect: false,
              callbacks: {
                title: items => items.length ? items[0].label : ''
              }
            }
          },
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: {
              ticks: { color: '#a9bbd8', maxRotation: 0, autoSkip: true },
              grid: { color: 'rgba(140,160,190,0.10)' }
            },
            y: {
              ticks: { color: '#a9bbd8' },
              grid: { color: 'rgba(140,160,190,0.10)' }
            }
          }
        }
      });
    }

    function setActiveWindowButtons() {
      document.querySelectorAll('[data-window]').forEach(btn => {
        btn.classList.toggle('active', Number(btn.dataset.window) === currentWindow);
      });
    }

    async function fetchData(windowSeconds) {
      const res = await fetch(`/api/data?window=${windowSeconds}`, { cache: 'no-store' });
      return await res.json();
    }

    async function loadData() {
      try {
        const fallbackChain = [currentWindow, 3600, 86400];
        const tried = [];
        let data = null;
        let selectedWindow = currentWindow;

        for (const w of fallbackChain) {
          if (tried.includes(w)) {
            continue;
          }
          tried.push(w);
          const candidate = await fetchData(w);
          data = candidate;
          selectedWindow = w;
          if ((candidate.count || 0) > 0) {
            break;
          }
        }

        if (selectedWindow !== currentWindow) {
          currentWindow = selectedWindow;
          setActiveWindowButtons();
        }

        document.getElementById('fileName').textContent = data.file || '--';
        document.getElementById('refreshTime').textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        if ((data.count || 0) > 0 && tried.length > 1) {
          document.getElementById('statusText').textContent = `自动回退到 ${currentWindow === 3600 ? '最近1小时' : '当天全部'} 显示数据`;
        } else {
          document.getElementById('statusText').textContent = data.status || 'ok';
        }

        const labels = data.points.map(p => formatTime(p[0]));
        const values = data.points.map(p => p[1]);
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.update('none');

        if (data.count > 0) {
          document.getElementById('currentTemp').textContent = `${data.latest.toFixed(2)} °C`;
          document.getElementById('currentTime').textContent = `时间：${formatTime(data.latest_ts)}`;
          document.getElementById('avgTemp').textContent = `${data.avg.toFixed(2)} °C`;
          document.getElementById('minMaxTemp').textContent = `${data.min.toFixed(2)} / ${data.max.toFixed(2)} °C`;
          document.getElementById('pointCount').textContent = data.count;
        } else {
          document.getElementById('currentTemp').textContent = '--';
          document.getElementById('currentTime').textContent = '等待数据...';
          document.getElementById('avgTemp').textContent = '--';
          document.getElementById('minMaxTemp').textContent = '--';
          document.getElementById('pointCount').textContent = '0';
        }
      } catch (err) {
        document.getElementById('statusText').textContent = `刷新失败：${err.message}`;
      }
    }

    function bindButtons() {
      document.querySelectorAll('[data-window]').forEach(btn => {
        btn.addEventListener('click', async () => {
          currentWindow = Number(btn.dataset.window);
          setActiveWindowButtons();
          await loadData();
        });
      });
      document.getElementById('refreshBtn').addEventListener('click', loadData);
    }

    function startPolling() {
      timer = setInterval(loadData, 1000);
    }

    initChart();
    bindButtons();
    setActiveWindowButtons();
    loadData();
    startPolling();
  </script>
</body>
</html>
"""


def bj_now() -> datetime:
    return datetime.now(tz=TZ_BJ)


def data_file_for_date(date_str: str) -> Path:
    return BASE_DIR / f"{DATA_FILE_PREFIX}_{date_str}.csv"


def fallback_data_file_for_date(date_str: str) -> Path:
    return FALLBACK_DIR / f"{DATA_FILE_PREFIX}_{date_str}.csv"


def current_data_file() -> Path:
    return data_file_for_date(bj_now().strftime("%Y-%m-%d"))


def available_data_files() -> List[Path]:
    files = list(BASE_DIR.glob(f"{DATA_FILE_PREFIX}_*.csv"))
    if FALLBACK_DIR != BASE_DIR:
        files.extend(FALLBACK_DIR.glob(f"{DATA_FILE_PREFIX}_*.csv"))
    # 去重并排序
    files = sorted({p.resolve() for p in files})
    return files


def latest_existing_file() -> Path | None:
    files = available_data_files()
    return files[-1] if files else None


def choose_data_file() -> Path | None:
    today = current_data_file()
    if today.exists():
        return today
    today_fallback = fallback_data_file_for_date(bj_now().strftime("%Y-%m-%d"))
    if today_fallback.exists():
        return today_fallback
    latest = latest_existing_file()
    return latest


def load_points_from_file(file_path: Path, window_seconds: int) -> List[TemperaturePoint]:
    if not file_path or not file_path.exists():
        return []

    cutoff = time_cutoff_seconds(window_seconds)
    points: List[TemperaturePoint] = []
    try:
        with file_path.open('r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    ts = float(row[0])
                    temp = float(row[1])
                except ValueError:
                    continue
                if ts >= cutoff:
                    points.append(TemperaturePoint(ts, temp))
    except Exception:
        return []
    return points


def time_cutoff_seconds(window_seconds: int) -> float:
    now_ts = bj_now().timestamp()
    if window_seconds >= 86400:
        start = bj_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return start.timestamp()
    return now_ts - window_seconds


def summarize_points(points: List[TemperaturePoint]) -> dict:
    if not points:
        return {
            "count": 0,
            "latest": None,
            "latest_ts": None,
            "min": None,
            "max": None,
            "avg": None,
            "points": [],
        }

    temps = [p.temp for p in points]
    latest = points[-1]
    return {
        "count": len(points),
        "latest": latest.temp,
        "latest_ts": latest.ts,
        "min": min(temps),
        "max": max(temps),
        "avg": sum(temps) / len(temps),
        "points": [[p.ts, p.temp] for p in points],
    }


class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, code: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        body = HTML_PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            self._send_html()
            return

        if parsed.path == '/api/data':
            params = parse_qs(parsed.query)
            window_seconds = int(params.get('window', ['600'])[0])
            selected = choose_data_file()
            if selected is None:
                self._send_json({
                    "file": None,
                    "status": "no csv file found",
                    "count": 0,
                    "points": [],
                })
                return

            points = load_points_from_file(selected, window_seconds)
            data = summarize_points(points)
            data.update({
                "file": selected.name,
                "status": "ok" if points else "no data in window",
                "window": window_seconds,
            })
            self._send_json(data)
            return

        if parsed.path == '/api/files':
            files = [p.name for p in available_data_files()]
            self._send_json({"files": files})
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"Temperature web dashboard running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == '__main__':
    import time
    main()
