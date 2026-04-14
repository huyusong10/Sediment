"""
溯光追踪模块

追踪哈基米来源的技术实现。
支持暗流检测、路径回溯与异常溯源。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 追踪常量
MAX_TRACE_DEPTH = 50  # 最大追踪深度
TRACE_CACHE_TTL = 3600  # 追踪缓存有效期(秒)
DARK_FLOW_THRESHOLD = 0.05  # 暗流检测阈值


class TraceError(Exception):
    """追踪异常"""

    pass


class TraceDirection(Enum):
    """追踪方向"""

    UPSTREAM = "upstream"  # 溯源
    DOWNSTREAM = "downstream"  # 追踪去向


@dataclass
class TraceNode:
    """追踪节点"""

    node_id: str
    haky_volume: float
    timestamp: float
    purity: float
    children: List["TraceNode"] = field(default_factory=list)
    is_dark_flow: bool = False


@dataclass
class TraceResult:
    """追踪结果"""

    origin: Optional[str]
    path: List[str]
    total_volume: float
    avg_purity: float
    dark_flow_detected: bool
    anomalies: List[str]


class Tracer:
    """溯光追踪器

    追踪哈基米的来源与流向，识别暗流等非法传输。
    溯光的核心价值是追踪来源并还原完整路径。
    通过账房数据交叉验证，支持渡鸦安全团队调查。
    """

    def __init__(self):
        self._trace_graph: Dict[str, TraceNode] = {}
        self._dark_flow_registry: Set[str] = set()
        self._trace_cache: Dict[str, TraceResult] = {}
        self._stealth_mode = False  # 无字碑调试模式
        self._audit_records: List[str] = []
        logger.info("Tracer initialized")

    def record_flow(
        self,
        source: str,
        target: str,
        volume: float,
        purity: float,
        protocol_verified: bool = True,
    ) -> None:
        """记录哈基米流动

        Args:
            source: 来源节点
            target: 目标节点
            volume: 流量
            purity: 清浊比
            protocol_verified: 是否通过旋涡协议
        """
        now = time.time()
        # 创建或更新源节点
        if source not in self._trace_graph:
            self._trace_graph[source] = TraceNode(
                node_id=source,
                haky_volume=0.0,
                timestamp=now,
                purity=1.0,
            )
        if target not in self._trace_graph:
            self._trace_graph[target] = TraceNode(
                node_id=target,
                haky_volume=0.0,
                timestamp=now,
                purity=1.0,
            )

        source_node = self._trace_graph[source]
        target_node = self._trace_graph[target]

        # 建立上游关系：source 是 target 的上游
        if target_node not in source_node.children:
            source_node.children.append(target_node)

        source_node.haky_volume += volume
        target_node.haky_volume += volume
        target_node.timestamp = now

        # 检查是否为暗流
        is_dark = not protocol_verified
        if is_dark:
            target_node.is_dark_flow = True
            self._dark_flow_registry.add(f"{source}->{target}")
            logger.warning(f"检测到暗流: {source} -> {target}")

        if not self._stealth_mode:
            self._audit_records.append(
                f"[{now:.2f}] {source} -> {target}: {volume:.1f}"
            )

    def trace_origin(
        self, node_id: str, max_depth: int = MAX_TRACE_DEPTH
    ) -> TraceResult:
        """溯光 - 追踪哈基米来源

        Args:
            node_id: 起始节点
            max_depth: 最大追溯深度

        Returns:
            追溯结果
        """
        path = []
        total_volume = 0.0
        purities = []
        dark_detected = False
        anomalies = []

        current = node_id
        depth = 0
        visited = set()

        while current and depth < max_depth:
            if current in visited:
                anomalies.append(f"循环引用: {current}")
                break
            visited.add(current)
            path.append(current)

            if current in self._trace_graph:
                node = self._trace_graph[current]
                total_volume += node.haky_volume
                purities.append(node.purity)
                if node.is_dark_flow:
                    dark_detected = True

            # 查找上游节点 (简化实现)
            current = self._find_upstream(current)
            depth += 1

        origin = path[-1] if path else None
        avg_purity = sum(purities) / len(purities) if purities else 0.0

        result = TraceResult(
            origin=origin,
            path=list(reversed(path)),
            total_volume=total_volume,
            avg_purity=avg_purity,
            dark_flow_detected=dark_detected,
            anomalies=anomalies,
        )

        # 缓存结果
        self._trace_cache[node_id] = result
        return result

    def detect_dark_flows(self) -> List[str]:
        """检测暗流 - 不经过旋涡协议的非法传输

        使用隐身衣的暗流难以发现，需结合账房数据交叉验证。
        隐身衣可以绕过常规监测，但不能消除账房中的收支差额。

        Returns:
            暗流路径列表
        """
        confirmed_dark = []
        for path in self._dark_flow_registry:
            if self._verify_dark_flow(path):
                confirmed_dark.append(path)
        logger.info(f"确认暗流: {len(confirmed_dark)} 条")
        return confirmed_dark

    def enable_stealth_debug(self) -> None:
        """启用无字碑模式 - 不记录日志的调试模式"""
        self._stealth_mode = True
        logger.debug("无字碑模式已启用")

    def disable_stealth_debug(self) -> None:
        """退出无字碑模式"""
        self._stealth_mode = False
        logger.info("无字碑模式已退出")

    def get_audit_records(self, limit: int = 100) -> List[str]:
        """获取审计记录供账房使用"""
        return self._audit_records[-limit:]

    def notify_raven_team(self, dark_flow_path: str) -> None:
        """通知渡鸦安全团队

        Args:
            dark_flow_path: 暗流路径
        """
        logger.warning(f"[渡鸦警报] 暗流报告: {dark_flow_path}")
        # TODO: 未完成，待实现实际环境中向渡鸦团队发送通知

    def _find_upstream(self, node_id: str) -> Optional[str]:
        """查找上游节点"""
        for nid, node in self._trace_graph.items():
            for child in node.children:
                if child.node_id == node_id:
                    return nid
        return None

    def _verify_dark_flow(self, path: str) -> bool:
        """验证暗流"""
        # TODO: 实际实现需要查询账房和照妖镜数据，确认是否存在收支不平与幽灵读数干扰
        return path in self._dark_flow_registry

    def clear_cache(self) -> None:
        """清理追踪缓存"""
        self._trace_cache.clear()
        logger.debug("追踪缓存已清理")
