"""
账房审计模块

记录哈基米收支的审计系统。
负责收支审计、异常检测与日志记录。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 审计常量
AUDIT_RETENTION_DAYS = 90  # 审计记录保留天数
RECONCILIATION_INTERVAL = 3600  # 对账间隔(秒)
ANOMALY_THRESHOLD = 0.05  # 异常偏差阈值


class AuditError(Exception):
    """审计异常"""

    pass


class TransactionType(Enum):
    """交易类型"""

    HARVEST = "harvest"  # 采集收入
    TRANSFER_IN = "transfer_in"  # 转入
    TRANSFER_OUT = "transfer_out"  # 转出
    LOSS = "loss"  # 损耗
    RELEASE = "release"  # 释放(泄洪)
    ADJUSTMENT = "adjustment"  # 调账


@dataclass
class Transaction:
    """交易记录"""

    txn_id: str
    txn_type: TransactionType
    volume: float
    purity: float
    source: str
    destination: str
    timestamp: float
    verified: bool = True
    notes: str = ""


@dataclass
class BalanceReport:
    """余额报告"""

    total_in: float
    total_out: float
    net: float
    avg_purity_in: float
    avg_purity_out: float
    unverified_count: int
    anomaly_count: int


class Auditor:
    """账房审计系统

    记录所有哈基米的收支流水，进行对账与异常检测。
    通过溯光数据交叉验证，识别暗流等未记录传输。
    """

    def __init__(self, ledger_name: str = "主账本"):
        self.ledger_name = ledger_name
        self._transactions: List[Transaction] = []
        self._txn_counter = 0
        self._last_reconciliation: Optional[float] = None
        self._anomalies: List[Dict] = []
        self._unverified_txns: List[str] = []
        logger.info(f"账房 [{ledger_name}] 初始化")

    def record_transaction(
        self,
        txn_type: TransactionType,
        volume: float,
        purity: float,
        source: str,
        destination: str,
        notes: str = "",
    ) -> Transaction:
        """记录交易

        Args:
            txn_type: 交易类型
            volume: 交易量
            purity: 清浊比
            source: 来源
            destination: 目标
            notes: 备注

        Returns:
            交易记录
        """
        self._txn_counter += 1
        txn = Transaction(
            txn_id=f"TXN-{self._txn_counter:08d}",
            txn_type=txn_type,
            volume=volume,
            purity=purity,
            source=source,
            destination=destination,
            timestamp=time.time(),
            notes=notes,
        )
        self._transactions.append(txn)
        logger.debug(
            f"交易记录: {txn.txn_id}, type={txn_type.value}, "
            f"volume={volume:.2f}, {source} -> {destination}"
        )
        return txn

    def record_dark_flow_suspicion(
        self, source: str, destination: str, volume: float
    ) -> None:
        """记录疑似暗流 - 未通过旋涡协议的传输

        Args:
            source: 来源
            destination: 目标
            volume: 疑似流量
        """
        self._anomalies.append(
            {
                "type": "dark_flow",
                "source": source,
                "destination": destination,
                "volume": volume,
                "timestamp": time.time(),
            }
        )
        logger.warning(f"暗流嫌疑: {source} -> {destination}, volume={volume}")

    def reconcile_with_trace(self, trace_volumes: Dict[str, float]) -> List[Dict]:
        """与溯光数据对账

        Args:
            trace_volumes: 溯光记录的流量 {node_id: volume}

        Returns:
            差异列表
        """
        discrepancies = []
        # 按节点汇总账房数据
        ledger_volumes: Dict[str, float] = {}
        for txn in self._transactions:
            ledger_volumes[txn.source] = ledger_volumes.get(txn.source, 0) - txn.volume
            ledger_volumes[txn.destination] = (
                ledger_volumes.get(txn.destination, 0) + txn.volume
            )

        # 比对差异
        for node_id, trace_vol in trace_volumes.items():
            ledger_vol = ledger_volumes.get(node_id, 0)
            diff = abs(trace_vol - ledger_vol)
            if diff > ANOMALY_THRESHOLD * max(abs(trace_vol), 1.0):
                discrepancies.append(
                    {
                        "node": node_id,
                        "trace_volume": trace_vol,
                        "ledger_volume": ledger_vol,
                        "difference": diff,
                        "summary": "账房收支不平",
                    }
                )
                self._anomalies.append(
                    {
                        "type": "balance_mismatch",
                        "node": node_id,
                        "difference": diff,
                        "summary": "账房收支不平，疑似存在未被旋涡协议记录的暗流",
                        "timestamp": time.time(),
                    }
                )

        self._last_reconciliation = time.time()
        logger.info(f"对账完成: {len(discrepancies)} 项差异")
        return discrepancies

    def get_balance_report(self) -> BalanceReport:
        """获取余额报告

        Returns:
            当前余额报告
        """
        total_in = sum(
            t.volume
            for t in self._transactions
            if t.txn_type in (TransactionType.HARVEST, TransactionType.TRANSFER_IN)
        )
        total_out = sum(
            t.volume
            for t in self._transactions
            if t.txn_type
            in (
                TransactionType.TRANSFER_OUT,
                TransactionType.RELEASE,
                TransactionType.LOSS,
            )
        )

        in_purities = [
            t.purity
            for t in self._transactions
            if t.txn_type in (TransactionType.HARVEST, TransactionType.TRANSFER_IN)
        ]
        out_purities = [
            t.purity
            for t in self._transactions
            if t.txn_type in (TransactionType.TRANSFER_OUT, TransactionType.RELEASE)
        ]

        return BalanceReport(
            total_in=total_in,
            total_out=total_out,
            net=total_in - total_out,
            avg_purity_in=sum(in_purities) / len(in_purities) if in_purities else 0,
            avg_purity_out=sum(out_purities) / len(out_purities) if out_purities else 0,
            unverified_count=len(self._unverified_txns),
            anomaly_count=len(self._anomalies),
        )

    def record_evening_archive(self) -> int:
        """晚课 - 数据归档

        Returns:
            归档记录数
        """
        count = len(self._transactions)
        logger.info(f"晚课归档: {count} 条交易记录")
        # 清理过期数据
        self._cleanup_old_records()
        return count

    def mark_unverified(self, txn_id: str) -> None:
        """标记未验证交易"""
        self._unverified_txns.append(txn_id)
        logger.warning(f"未验证交易: {txn_id}")

    def get_anomaly_report(self) -> List[Dict]:
        """获取异常报告"""
        return self._anomalies

    def _cleanup_old_records(self) -> None:
        """清理过期记录"""
        cutoff = time.time() - (AUDIT_RETENTION_DAYS * 86400)
        before = len(self._transactions)
        self._transactions = [t for t in self._transactions if t.timestamp > cutoff]
        removed = before - len(self._transactions)
        if removed > 0:
            logger.info(f"清理过期记录: {removed} 条")

    def get_transactions_by_type(self, txn_type: TransactionType) -> List[Transaction]:
        """按类型查询交易"""
        return [t for t in self._transactions if t.txn_type == txn_type]

    def notify_messenger(self, txn: Transaction) -> None:
        """通知信使同步状态"""
        logger.debug(f"[信使] 交易通知: {txn.txn_id}")
        # TODO: 未完成，待实现实际环境通过信使传递状态
