#core/report_service.py
import pandas as pd


class ReportService:
    """
    BAC_PRO Report Service V8.2
    - Redis → DataFrame → Analysis → UI Render
    - 兼容 MANUAL / AUTORUN 双模式
    """

    def __init__(self, record_adapter):
        self.r = record_adapter.client

    # =========================================================
    # 1️⃣ 基础数据读取层
    # =========================================================

    def _load_tx_ids(self, uid: str, limit=None):
        """
        从 Redis List 获取 transaction IDs
        """
        if limit is None:
            return self.r.lrange(f"u:tx_list:{uid}", 0, -1)
        return self.r.lrange(f"u:tx_list:{uid}", 0, limit - 1)

    def _load_tx_hash(self, tx_id: str):
        """
        从 Redis Hash 获取单条交易记录
        """
        data = self.r.hgetall(f"tx:{tx_id}")
        return data if data else None

    def _load_all_records(self, uid: str, limit=None):
        """
        通用加载函数
        """
        tx_ids = self._load_tx_ids(uid, limit)

        if not tx_ids:
            return []

        records = []
        for tid in tx_ids:
            data = self._load_tx_hash(tid)
            if data:
                records.append(data)

        return records

    # =========================================================
    # 2️⃣ 最近交易数据（20手）
    # =========================================================

    def get_recent_bets_df(self, uid: str, limit=20):
        """
        最近 N 手交易（原始 Redis → DF）
        """
        records = self._load_all_records(uid, limit)

        if not records:
            return None

        return pd.DataFrame(records)


    def render_recent_bets_df(self, df: pd.DataFrame, is_cn: bool):

        if df is None or df.empty:
            return None

        # ✅ 1. 统一字段（适配你新结构）
        df = df.rename(columns={
            'pl': 'amount'   # 内部统一 P/L
        })

        # ✅ 2. 控制显示顺序（关键）
        df = df[[
            'datetime',
            'type',
            'amount',
            'hist_len',
            'bet_len',
            'action',
            'strategy'
        ]]

        # ✅ 3. UI 映射
        col_map = {
                'datetime': '时间' if is_cn else 'Time',
                'type': '类型' if is_cn else 'Type',
                'amount': '盈亏' if is_cn else 'Net',
                'hist_len': '范围' if is_cn else 'Scope',
                'action': '动作' if is_cn else 'Action',
                'bet_len': '下注点' if is_cn else 'BetPoint',
                'strategy': '策略' if is_cn else 'Strategy'
            }

        df = df.rename(columns=col_map)

        return df



    # =========================================================
    # 3️⃣ 综合报表数据层
    # =========================================================

    def get_summary_df(self, uid: str):
        """
        全量统计数据（MANUAL + AUTORUN）
        """

        records = self._load_all_records(uid)

        if not records:
            return None

        parsed = []

        for d in records:

            # ⚠️ 兼容 MANUAL / AUTORUN
            ext = d.get("ext", {}) or {}

            parsed.append({
                # 基础字段（MANUAL + AUTORUN 共用）
                'exec_mode': str(d.get('type', 'N/A')).upper(),
                'bet_logic': str(d.get('strategy', 'N/A')).upper(),
                'action': str(d.get('action', 'N/A')).upper(),
                'hist_len': f"LEN-{d.get('hist_len', '0')}",
                'bet_len': f"STREAK-{d.get('bet_len', '0')}",
                'amount': float(d.get('amount', 0)),

                # AUTORUN 扩展字段（MANUAL 不存在也安全）
                'round_id': ext.get('round_id', ''),
                'step_index': ext.get('step_index', ''),
                'state': ext.get('state', ''),
                'edge': ext.get('edge', 0),
                'engine_version': ext.get('engine_version', '')
            })

        return pd.DataFrame(parsed)

    # =========================================================
    # 4️⃣ 统计计算核心
    # =========================================================

    def get_metrics(self, df: pd.DataFrame, col=None, val=None):
        """
        通用统计函数
        """
        if df is None or df.empty:
            return 0, 0.0, 0.0, 0.0

        subset = df if col is None else df[df[col] == val]

        count = len(subset)
        vol = subset['amount'].abs().sum() if count > 0 else 0.0
        pl = subset['amount'].sum() if count > 0 else 0.0
        avg = pl / count if count > 0 else 0.0

        return count, vol, pl, avg

    # =========================================================
    # 5️⃣ HTML 报表生成（综合分析）
    # =========================================================

    def build_html_report(self, df: pd.DataFrame):
        """
        生成综合 HTML 报表
        """

        if df is None or df.empty:
            return "<div>No Data</div>"

        def build_rows(label, col):
            html = ""

            unique_vals = sorted(df[col].astype(str).unique())

            for i, v in enumerate(unique_vals):
                cnt, vol, pl, avg = self.get_metrics(df, col, v)

                color = "#00FFAA" if pl >= 0 else "#FF4B4B"

                html += f"""
                <tr style="border-bottom:1px solid #222;">
                    <td style="padding:8px;color:#888;">
                        {label if i == 0 else ""}
                    </td>
                    <td style="color:#AAA;">{v}</td>
                    <td style="text-align:center;">{cnt}</td>
                    <td style="text-align:right;">{vol:.2f}</td>
                    <td style="text-align:right;color:{color};font-weight:bold;">
                        {pl:.2f}
                    </td>
                    <td style="text-align:right;">{avg:.2f}</td>
                </tr>
                """

            return html

        total_cnt, total_vol, total_pl, total_avg = self.get_metrics(df)

        html = f"""
        <div style="background:#111;padding:15px;border-radius:10px;color:#EEE;font-family:monospace;font-size:13px;">
            <table style="width:100%;border-collapse:collapse;">

                <thead>
                    <tr style="border-bottom:2px solid #444;color:#777;">
                        <th style="text-align:left;">Category</th>
                        <th>Group</th>
                        <th>Count</th>
                        <th>Volume</th>
                        <th>P/L</th>
                        <th>Avg</th>
                    </tr>
                </thead>

                <tbody>
                    {build_rows("Exec Mode", "exec_mode")}
                    {build_rows("Bet Logic", "bet_logic")}
                    {build_rows("Action", "action")}
                    {build_rows("Snapshot", "hist_len")}
                    {build_rows("Bet Len", "bet_len")}
                </tbody>

                <tfoot>
                    <tr style="background:#222;font-weight:bold;">
                        <td colspan="2" style="padding:10px;">TOTAL</td>
                        <td>{total_cnt}</td>
                        <td>{total_vol:.2f}</td>
                        <td style="color:#00FFAA;">{total_pl:.2f}</td>
                        <td>{total_avg:.2f}</td>
                    </tr>
                </tfoot>

            </table>
        </div>
        """

        return html
