"""
将本地 temperature_*.csv 持续同步到云服务器目录。
独立运行，不依赖或修改本地监测程序。
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import paramiko


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = [part for part in remote_dir.strip("/").split("/") if part]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def list_local_csv_files(project_dir: Path) -> list[Path]:
    files = sorted(project_dir.glob("temperature_*.csv"))
    return [f for f in files if f.is_file()]


def upload_if_changed(
    sftp: paramiko.SFTPClient,
    local_file: Path,
    remote_dir: str,
    last_mtime_cache: dict[Path, float],
) -> bool:
    mtime = local_file.stat().st_mtime
    prev_mtime = last_mtime_cache.get(local_file)
    if prev_mtime is not None and mtime <= prev_mtime:
        return False

    remote_path = f"{remote_dir.rstrip('/')}/{local_file.name}"
    sftp.put(str(local_file), remote_path)
    last_mtime_cache[local_file] = mtime
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync temperature CSV files to server")
    parser.add_argument("--host", required=True, help="SSH host")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--password", default=None, help="SSH password")
    parser.add_argument("--remote-dir", default="/opt/temperature-web", help="Remote directory")
    parser.add_argument("--interval", type=float, default=2.0, help="Sync interval seconds")
    args = parser.parse_args()

    password = args.password or os.getenv("TEMP_SYNC_PASSWORD")
    if not password:
        raise SystemExit("Missing password: use --password or TEMP_SYNC_PASSWORD")

    project_dir = Path(__file__).resolve().parent.parent
    print(f"Project dir: {project_dir}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {args.user}@{args.host} ...")
    ssh.connect(hostname=args.host, username=args.user, password=password, timeout=10)
    print("SSH connected")

    sftp = ssh.open_sftp()
    ensure_remote_dir(sftp, args.remote_dir)

    mtime_cache: dict[Path, float] = {}
    try:
        while True:
            files = list_local_csv_files(project_dir)
            if not files:
                print("No local temperature_*.csv found, waiting...")
                time.sleep(max(0.5, args.interval))
                continue

            changed = 0
            for file_path in files:
                try:
                    if upload_if_changed(sftp, file_path, args.remote_dir, mtime_cache):
                        changed += 1
                        print(f"Uploaded: {file_path.name}")
                except Exception as e:
                    print(f"Upload failed {file_path.name}: {e}")

            if changed == 0:
                print("No changes")

            time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        try:
            sftp.close()
        finally:
            ssh.close()


if __name__ == "__main__":
    main()
