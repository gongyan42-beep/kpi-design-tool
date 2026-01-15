"""
同步状态管理 - 记录各表的同步水位
"""
import json
import os
from datetime import datetime
from typing import Optional


class SyncStatusManager:
    """同步状态管理器"""

    def __init__(self, status_file: str = 'data/feishu_sync_status.json'):
        self.status_file = status_file
        self._status = self._load_status()

    def _load_status(self) -> dict:
        """加载同步状态"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_status(self):
        """保存同步状态"""
        os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
        with open(self.status_file, 'w') as f:
            json.dump(self._status, f, indent=2)

    def get_last_sync_time(self, table: str) -> Optional[str]:
        """获取表的上次同步时间"""
        return self._status.get(table, {}).get('last_sync_time')

    def update_last_sync_time(self, table: str, sync_time: str):
        """更新表的同步时间"""
        if table not in self._status:
            self._status[table] = {}
        self._status[table]['last_sync_time'] = sync_time
        self._status[table]['updated_at'] = datetime.now().isoformat()
        self._save_status()

    def get_sync_stats(self) -> dict:
        """获取所有表的同步统计"""
        return dict(self._status)
