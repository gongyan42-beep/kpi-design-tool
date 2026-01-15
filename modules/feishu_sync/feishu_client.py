"""
飞书多维表格 API 客户端
"""
import os
import time
import logging
import requests
from typing import Dict, List, Optional
from threading import Thread

logger = logging.getLogger(__name__)


class FeishuBitableClient:
    """飞书多维表格 API 客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv('FEISHU_APP_ID')
        self.app_secret = app_secret or os.getenv('FEISHU_APP_SECRET')
        self._token = None
        self._token_expire = 0

    def _get_token(self) -> str:
        """获取 tenant_access_token（带缓存）"""
        if self._token and time.time() < self._token_expire - 60:
            return self._token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }, timeout=15)
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"获取飞书 Token 失败: {data}")

        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 3600)
        return self._token

    def _request(self, method: str, path: str, **kwargs) -> Dict:
        """发起 API 请求"""
        url = f"{self.BASE_URL}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_token()}"
        headers["Content-Type"] = "application/json"

        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"飞书 API 错误: {data.get('code')} - {data.get('msg')}")

        return data

    def insert_record(self, app_token: str, table_id: str, fields: Dict) -> Dict:
        """插入单条记录"""
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        return self._request("POST", path, json={"fields": fields})

    def batch_insert_records(self, app_token: str, table_id: str, records: List[Dict]) -> Dict:
        """批量插入记录（最多500条）"""
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        return self._request("POST", path, json={
            "records": [{"fields": r} for r in records]
        })

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: Dict) -> Dict:
        """更新单条记录"""
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        return self._request("PUT", path, json={"fields": fields})

    def search_records(self, app_token: str, table_id: str, filter_condition: Dict = None) -> List[Dict]:
        """搜索记录（支持分页）"""
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        all_records = []
        page_token = None

        while True:
            body = {"page_size": 500}
            if filter_condition:
                body["filter"] = filter_condition
            if page_token:
                body["page_token"] = page_token

            data = self._request("POST", path, json=body)
            items = data.get("data", {}).get("items", [])
            all_records.extend(items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")

        return all_records

    def upsert_record(self, app_token: str, table_id: str, unique_field: str,
                      unique_value: str, fields: Dict) -> Dict:
        """更新或插入记录"""
        # 先搜索是否存在
        filter_condition = {
            "conjunction": "and",
            "conditions": [{
                "field_name": unique_field,
                "operator": "is",
                "value": [unique_value]
            }]
        }

        try:
            existing = self.search_records(app_token, table_id, filter_condition)
            if existing:
                record_id = existing[0]["record_id"]
                return self.update_record(app_token, table_id, record_id, fields)
        except:
            pass

        return self.insert_record(app_token, table_id, fields)

    def upsert_record_async(self, app_token: str, table_id: str, unique_field: str,
                            unique_value: str, fields: Dict):
        """异步更新或插入记录（不阻塞主线程）"""
        def _do_upsert():
            try:
                self.upsert_record(app_token, table_id, unique_field, unique_value, fields)
            except Exception as e:
                logger.warning(f"[飞书同步] 异步 upsert 失败: {e}")

        thread = Thread(target=_do_upsert, daemon=True)
        thread.start()

    def insert_record_async(self, app_token: str, table_id: str, fields: Dict):
        """异步插入记录（不阻塞主线程）"""
        def _do_insert():
            try:
                self.insert_record(app_token, table_id, fields)
            except Exception as e:
                logger.warning(f"[飞书同步] 异步 insert 失败: {e}")

        thread = Thread(target=_do_insert, daemon=True)
        thread.start()
