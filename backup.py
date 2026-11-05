"""Offline administrator backup and restore. Never restores over an existing database."""
import argparse
import os
import sqlite3
from pathlib import Path

def backup(source,target):
    source,target=Path(source),Path(target)
    if not source.is_file(): raise ValueError('Không tìm thấy CSDL nguồn.')
    # Exclusive creation also prevents accidentally overwriting a previous backup.
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Bản sao không toàn vẹn.')
    except Exception:
        target.unlink(missing_ok=True);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Sao lưu / phục hồi SQLite gồm cả ảnh. Dừng ứng dụng trước khi phục hồi.')
    parser.add_argument('action',choices=['backup','restore']);parser.add_argument('source');parser.add_argument('target')
    args=parser.parse_args();backup(args.source,args.target);print('Đã tạo bản sao toàn vẹn. Đích không bị ghi đè.')
