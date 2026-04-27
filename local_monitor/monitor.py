"""
温度实时监测仪表板
实时显示温度数据、统计信息和历史曲线
"""
import os
import csv
import queue
import threading
import time
import re
from collections import deque
from datetime import datetime, timedelta, timezone
import numpy as np

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter
import matplotlib.dates as mdates
import serial
import serial.tools.list_ports

plt.style.use('dark_background')

DATA_FILE_PREFIX = "temperature"
TIME_GAP_THRESHOLD = 5.0  # 秒，用于断开不连续的线条
TEMP_PATTERN = re.compile(r"Temp\s*=\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)


class TemperatureMonitor:
    def __init__(self, port=None, baud=9600):
        self.data_points = deque()  # (timestamp, temperature) 元组
        self.timestamps = deque()   # 原始时间戳
        self.temps = deque()        # 温度值
        
        self.fig = None
        self.ax_curve = None
        self.ax_stats = None
        self.line = None
        
        self.latest_temp = None
        self.min_temp = None
        self.max_temp = None
        self.avg_temp = None
        
        self.data_queue = queue.Queue()
        self.loaded_line_count = 0
        self.port = port
        self.baud = baud
        self.connection_status = "file-mode"
        self.current_data_file = None

    def get_daily_data_file(self, ts=None):
        """按北京时间返回当日CSV文件名，如 temperature_2026-04-24.csv"""
        tz_bj = timezone(timedelta(hours=8))
        if ts is None:
            dt = datetime.now(tz=tz_bj)
        else:
            dt = datetime.fromtimestamp(ts, tz=tz_bj)
        return f"{DATA_FILE_PREFIX}_{dt.strftime('%Y-%m-%d')}.csv"

    def pick_port(self):
        """自动选择串口（优先CH340/USB串口）"""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None

        for p in ports:
            desc = f"{p.description} {p.manufacturer or ''}".lower()
            if "ch340" in desc or "usb" in desc or "serial" in desc:
                return p.device

        return ports[0].device

    def save_data_point(self, ts, temp):
        """保存数据到 CSV"""
        file_path = self.get_daily_data_file(ts)
        file_exists = os.path.exists(file_path)
        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'temperature'])
            writer.writerow([ts, temp])

        self.current_data_file = file_path

    def serial_reader_thread(self):
        """后台线程：直接读取串口并推送到队列，同时落盘"""
        while True:
            try:
                if not self.port or self.port.lower() == "auto":
                    self.port = self.pick_port()
                    if not self.port:
                        self.connection_status = "serial: no port found"
                        time.sleep(1.0)
                        continue

                self.connection_status = f"serial:{self.port} connecting..."
                ser = serial.Serial(port=self.port, baudrate=self.baud, timeout=0.2)
                self.connection_status = f"serial:{self.port} connected"
                print(f"Serial connected: {self.port} @ {self.baud}")

                while True:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    m = TEMP_PATTERN.search(line)
                    if not m:
                        continue

                    temp = float(m.group(1))
                    ts = time.time()
                    self.data_queue.put((ts, temp))
                    self.save_data_point(ts, temp)
            except Exception as e:
                self.connection_status = f"serial retry: {str(e)[:45]}"
                try:
                    ser.close()
                except Exception:
                    pass
                time.sleep(1.0)

    def load_csv_data(self):
        """加载 CSV 文件中的所有数据"""
        file_path = self.get_daily_data_file()
        self.current_data_file = file_path

        if not os.path.exists(file_path):
            print(f"✓ New data file will be created: {file_path}")
            return
        
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.strip().split('\n')
            if not lines:
                return
            self.loaded_line_count = len(lines)
            
            # 跳过标题行
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        ts = float(parts[0].strip())
                        temp = float(parts[1].strip())
                        self.timestamps.append(ts)
                        self.temps.append(temp)
                    except ValueError:
                        continue
            
            if len(self.temps) > 0:
                print(f"✓ Loaded {len(self.temps)} data points from {file_path}")
                print(f"  Time range: {datetime.fromtimestamp(min(self.timestamps), tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')} ~ {datetime.fromtimestamp(max(self.timestamps), tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"✗ Load error: {e}")

    def file_monitor_thread(self):
        """后台线程：监听 CSV 新数据"""
        last_line_count = self.loaded_line_count
        current_file = self.get_daily_data_file()
        self.current_data_file = current_file
        
        while True:
            try:
                new_file = self.get_daily_data_file()
                if new_file != current_file:
                    current_file = new_file
                    self.current_data_file = current_file
                    last_line_count = 0

                if not os.path.exists(current_file):
                    time.sleep(1)
                    continue
                
                with open(current_file, 'r', newline='', encoding='utf-8') as f:
                    content = f.read()
                
                lines = content.strip().split('\n')
                
                # 只处理新增的行
                for line in lines[max(1, last_line_count):]:  # 跳过标题和已读的行
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            ts = float(parts[0].strip())
                            temp = float(parts[1].strip())
                            self.data_queue.put((ts, temp))
                        except ValueError:
                            continue
                
                last_line_count = len(lines)
                time.sleep(1)
            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(2)

    def process_queue(self):
        """处理队列中的新数据"""
        count = 0
        while True:
            try:
                ts, temp = self.data_queue.get_nowait()
            except queue.Empty:
                break
            # 避免重复或时间回跳的数据，确保时间严格递增
            if len(self.timestamps) == 0 or ts > self.timestamps[-1]:
                self.timestamps.append(ts)
                self.temps.append(temp)
                count += 1
        
        return count > 0

    def calculate_stats(self):
        """计算统计信息"""
        if len(self.temps) > 0:
            self.latest_temp = self.temps[-1]
            self.min_temp = min(self.temps)
            self.max_temp = max(self.temps)
            self.avg_temp = sum(self.temps) / len(self.temps)
        else:
            self.latest_temp = self.min_temp = self.max_temp = self.avg_temp = 0

    def create_figure(self):
        """创建绘图界面"""
        self.fig = plt.figure(figsize=(16, 8), dpi=120)
        self.fig.patch.set_facecolor('#0a0a0a')
        
        # 左侧：统计信息和当前温度
        ax_left = plt.subplot(1, 2, 1)
        ax_left.axis('off')
        
        # 右侧：温度曲线
        self.ax_curve = plt.subplot(1, 2, 2)
        self.line_glow, = self.ax_curve.plot(
            [], [], lw=8.0, color='#00d9ff', alpha=0.18,
            zorder=1, solid_capstyle='round', antialiased=True
        )
        self.line, = self.ax_curve.plot(
            [], [], lw=2.8, color='#7ff6ff', alpha=1.0,
            marker='o', markersize=2.2, markerfacecolor='#b8ffff', markeredgewidth=0,
            zorder=3, solid_capstyle='round', antialiased=True
        )
        
        # 配置右侧图表
        self.ax_curve.set_facecolor('#101a2b')
        self.ax_curve.set_xlabel('Beijing Time', fontsize=11, color='#cccccc')
        self.ax_curve.set_ylabel('Temperature (°C)', fontsize=11, color='#cccccc')
        self.ax_curve.grid(True, alpha=0.14, linestyle='--', linewidth=0.7, color='#5b6a80')
        self.ax_curve.tick_params(colors='#cccccc', labelsize=10)
        self.ax_curve.spines['left'].set_color('#555555')
        self.ax_curve.spines['bottom'].set_color('#555555')
        self.ax_curve.spines['right'].set_visible(False)
        self.ax_curve.spines['top'].set_visible(False)
        
        # 时间标签格式化
        def time_formatter(x, pos):
            try:
                dt = mdates.num2date(x)
                dt_beijing = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
                return dt_beijing.strftime('%H:%M:%S')
            except:
                return ''
        
        self.ax_curve.xaxis.set_major_formatter(FuncFormatter(time_formatter))
        self.ax_curve.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.fig.autofmt_xdate()
        
        # 左侧文本区域（用于显示统计信息）
        self.text_elements = {
            'title': ax_left.text(0.5, 0.95, 'Temperature Monitor', 
                                 ha='center', va='top', fontsize=24, fontweight='bold', 
                                 color='#00ffff', transform=ax_left.transAxes),
            'current': ax_left.text(0.5, 0.77, '--.-- °C', 
                                   ha='center', va='top', fontsize=50, fontweight='bold', 
                                   color='#00ff88', family='monospace', transform=ax_left.transAxes),
            'time_now': ax_left.text(0.05, 0.62, 'Now: --:--:--', 
                                    va='top', fontsize=13, color='#7fd3ff', family='monospace', 
                                    transform=ax_left.transAxes),
            'time_data': ax_left.text(0.05, 0.56, 'Data: --:--:--', 
                                     va='top', fontsize=13, color='#7fd3ff', family='monospace', 
                                     transform=ax_left.transAxes),
            'age': ax_left.text(0.05, 0.50, 'Age: -- s', 
                               va='top', fontsize=13, color='#7fd3ff', family='monospace', 
                               transform=ax_left.transAxes),
            'max': ax_left.text(0.05, 0.40, 'Max: --.-- °C', 
                               va='top', fontsize=14, color='#ffaa00', family='monospace', 
                               transform=ax_left.transAxes),
            'min': ax_left.text(0.05, 0.34, 'Min: --.-- °C', 
                               va='top', fontsize=14, color='#ff3366', family='monospace', 
                               transform=ax_left.transAxes),
            'avg': ax_left.text(0.05, 0.28, 'Avg: --.-- °C', 
                               va='top', fontsize=14, color='#ffff00', family='monospace', 
                               transform=ax_left.transAxes),
            'count': ax_left.text(0.05, 0.22, 'Points: 0', 
                                 va='top', fontsize=14, color='#bbbbbb', family='monospace', 
                                 transform=ax_left.transAxes),
            'conn': ax_left.text(0.05, 0.16, 'Conn : --', 
                                va='top', fontsize=12, color='#b0b0b0', family='monospace', 
                                transform=ax_left.transAxes),
            'status': ax_left.text(0.05, 0.10, 'Status: Waiting for data...', 
                                  va='top', fontsize=12, color='#888888', family='monospace', 
                                  transform=ax_left.transAxes),
        }

    def apply_time_breaks(self, xs, ys, ts_filtered):
        """在时间间隔过大的地方插入 NaN 断开线条"""
        if len(xs) < 2:
            return xs, ys
        
        xs_result = []
        ys_result = []
        
        for i in range(len(xs)):
            xs_result.append(xs[i])
            ys_result.append(ys[i])
            
            if i < len(xs) - 1:
                time_gap = ts_filtered[i + 1] - ts_filtered[i]
                if time_gap > TIME_GAP_THRESHOLD:
                    xs_result.append(np.nan)
                    ys_result.append(np.nan)
        
        return xs_result, ys_result

    def update_animation(self, frame):
        """动画更新函数"""
        has_new = self.process_queue()

        now_dt = datetime.now(tz=timezone(timedelta(hours=8)))
        self.text_elements['time_now'].set_text(f"Now : {now_dt.strftime('%H:%M:%S')}")
        self.text_elements['conn'].set_text(f"Conn : {self.connection_status[:38]}")
        active_file = self.current_data_file or self.get_daily_data_file()
        self.text_elements['status'].set_text(f"File : {active_file}")

        if len(self.temps) == 0:
            self.text_elements['current'].set_text('--.-- °C')
            self.text_elements['time_data'].set_text('Data: --:--:--')
            self.text_elements['age'].set_text('Age : -- s')
            self.text_elements['status'].set_text(f"File : {active_file} | Waiting for data...")
            self.line_glow.set_data([], [])
            self.line.set_data([], [])
            return self.line_glow, self.line

        self.calculate_stats()
        self.text_elements['current'].set_text(f"{self.latest_temp:.2f} °C")
        self.text_elements['max'].set_text(f"Max : {self.max_temp:.2f} °C")
        self.text_elements['min'].set_text(f"Min : {self.min_temp:.2f} °C")
        self.text_elements['avg'].set_text(f"Avg : {self.avg_temp:.2f} °C")
        self.text_elements['count'].set_text(f"Points: {len(self.temps)}")

        dt_data = datetime.fromtimestamp(self.timestamps[-1], tz=timezone(timedelta(hours=8)))
        age_seconds = max(0.0, now_dt.timestamp() - self.timestamps[-1])
        self.text_elements['time_data'].set_text(f"Data: {dt_data.strftime('%H:%M:%S')}")
        self.text_elements['age'].set_text(f"Age : {age_seconds:5.1f} s")
        if has_new:
            self.text_elements['status'].set_text(f"File : {active_file} | Receiving new data")
        else:
            self.text_elements['status'].set_text(f"File : {active_file} | Monitoring")

        latest_ts = self.timestamps[-1]
        earliest_ts = max(latest_ts - 600, min(self.timestamps))

        indices_in_range = [
            i for i, ts in enumerate(self.timestamps)
            if earliest_ts <= ts <= latest_ts
        ]
        if not indices_in_range:
            indices_in_range = [len(self.timestamps) - 1]

        xs_mpl = []
        ys = []
        ts_filtered = []
        for i in indices_in_range:
            ts = self.timestamps[i]
            xs_mpl.append(mdates.date2num(datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)))
            ys.append(self.temps[i])
            ts_filtered.append(ts)

        xs_processed, ys_processed = self.apply_time_breaks(xs_mpl, ys, ts_filtered)
        self.line_glow.set_data(xs_processed, ys_processed)
        self.line.set_data(xs_processed, ys_processed)

        if ys:
            y_min, y_max = min(ys), max(ys)
            y_range = y_max - y_min
            padding = max(y_range * 0.1, 1.0)
            self.ax_curve.set_ylim(y_min - padding, y_max + padding)

        earliest_dt = datetime.fromtimestamp(earliest_ts, tz=timezone.utc).replace(tzinfo=None)
        latest_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc).replace(tzinfo=None)
        self.ax_curve.set_xlim(mdates.date2num(earliest_dt), mdates.date2num(latest_dt))

        self.fig.canvas.draw_idle()

        return self.line_glow, self.line

    def run(self):
        """运行监测仪表板"""
        print(f"\n{'='*60}")
        print("Temperature Real-time Monitor Dashboard")
        print(f"{'='*60}\n")

        self.load_csv_data()

        if self.port:
            monitor = threading.Thread(target=self.serial_reader_thread, daemon=True)
            monitor.start()
            print("Serial reader started\n")
        else:
            monitor = threading.Thread(target=self.file_monitor_thread, daemon=True)
            monitor.start()
            print("File monitor started\n")

        self.calculate_stats()
        self.create_figure()

        anim = FuncAnimation(self.fig, self.update_animation, interval=200, blit=False, cache_frame_data=False)
        _ = anim
        print("Dashboard is running. Close the window to exit.\n")
        plt.tight_layout()
        plt.show()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Temperature Real-time Monitor")
    parser.add_argument("--port", default="auto", help="Serial port, e.g. COM7. Default: auto")
    parser.add_argument("--baud", type=int, default=9600, help="Serial baud rate")
    args = parser.parse_args()
    
    monitor = TemperatureMonitor(port=args.port, baud=args.baud)
    monitor.run()


if __name__ == "__main__":
    main()
