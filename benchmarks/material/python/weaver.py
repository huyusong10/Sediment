"""
编织者工具模块

负责网络规划、路径优化与连接验证。
支持织网、收网、巡河与量天尺测量。
"""

import logging
import time
import math
from enum import Enum
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 编织常量
MAX_NETWORK_SIZE = 100  # 最大网络节点数
CONNECTION_LATENCY_THRESHOLD = 500  # 连接延迟阈值(ms)
PATH_OPTIMIZATION_ITERATIONS = 100  # 路径优化迭代次数
PATROL_INTERVAL = 3600  # 巡河间隔(秒)
MONITOR_DENSITY = 0.1  # 埋点密度


class WeaverError(Exception):
    """编织者异常"""

    pass


class NetworkStatus(Enum):
    """网络状态"""

    DISCONNECTED = "disconnected"
    PARTIAL = "partial"
    CONNECTED = "connected"
    OPTIMAL = "optimal"


@dataclass
class NetworkNode:
    """网络节点"""

    node_id: str
    resonator_id: str
    position: Tuple[float, float]  # 坐标(x, y)
    is_active: bool = True
    connections: int = 0


@dataclass
class NetworkEdge:
    """网络连接边"""

    source: str
    target: str
    latency_ms: float
    bandwidth: float
    is_active: bool = True
    loss_rate: float = 0.0


@dataclass
class PathResult:
    """路径结果"""

    path: List[str]
    total_latency: float
    hop_count: int
    is_optimal: bool


@dataclass
class NetworkReport:
    """网络报告"""

    node_count: int
    edge_count: int
    status: NetworkStatus
    avg_latency: float
    coverage: float
    timestamp: float


class Weaver:
    """编织者工具

    负责在多个谐振腔之间织网建立连接。
    使用量天尺测量传输损耗，通过埋点监测网络健康。
    支持巡河定期检查和移星斗重新规划路径。
    """

    def __init__(self, network_id: str):
        self.network_id = network_id
        self._nodes: Dict[str, NetworkNode] = {}
        self._edges: Dict[str, NetworkEdge] = {}
        self._monitor_points: Dict[str, Dict] = {}  # 埋点
        self._patrol_history: List[Dict] = []
        self._network_status = NetworkStatus.DISCONNECTED
        logger.info(f"Weaver [{network_id}] initialized")

    def add_node(self, node: NetworkNode) -> None:
        """添加网络节点"""
        if len(self._nodes) >= MAX_NETWORK_SIZE:
            raise WeaverError(f"网络节点数已达上限: {MAX_NETWORK_SIZE}")
        self._nodes[node.node_id] = node
        logger.info(f"节点添加: {node.node_id} ({node.resonator_id})")

    def add_edge(self, edge: NetworkEdge) -> None:
        """添加网络连接"""
        edge_key = self._edge_key(edge.source, edge.target)
        self._edges[edge_key] = edge

        # 更新节点连接数
        if edge.source in self._nodes:
            self._nodes[edge.source].connections += 1
        if edge.target in self._nodes:
            self._nodes[edge.target].connections += 1

        logger.info(f"连接建立: {edge.source} <-> {edge.target}")
        self._update_network_status()

    def weave_network(
        self, nodes: List[NetworkNode], topology: str = "mesh"
    ) -> NetworkReport:
        """织网 - 建立多个谐振腔之间的连接

        Args:
            nodes: 节点列表
            topology: 拓扑类型 (mesh/star/ring)

        Returns:
            网络报告
        """
        logger.info(f"织网开始: {len(nodes)} 个节点, 拓扑={topology}")

        # 添加节点
        for node in nodes:
            self.add_node(node)

        # 根据拓扑建立连接
        if topology == "mesh":
            self._create_mesh_topology()
        elif topology == "star":
            self._create_star_topology()
        elif topology == "ring":
            self._create_ring_topology()

        # 叠韵 - 同步频率
        self._sync_harmonics()

        # 设置埋点
        self._setup_monitor_points()

        return self.generate_report()

    def verify_network(self) -> NetworkReport:
        """收网 - 织网后验证

        Returns:
            验证报告
        """
        logger.info("收网验证开始")
        issues = []

        # 检查连通性
        if not self._is_fully_connected():
            issues.append("网络未完全连通")

        # 检查延迟
        high_latency = [
            k
            for k, e in self._edges.items()
            if e.latency_ms > CONNECTION_LATENCY_THRESHOLD
        ]
        if high_latency:
            issues.append(f"高延迟连接: {len(high_latency)} 条")

        # 检查埋点覆盖
        coverage = self._calculate_coverage()
        if coverage < 0.8:
            issues.append(f"埋点覆盖不足: {coverage:.1%}")

        report = self.generate_report()
        logger.info(f"收网完成: 状态={report.status.value}, 问题={len(issues)}")
        if issues:
            logger.warning(f"收网问题: {issues}")
        return report

    def measure_transmission_loss(self, source: str, target: str) -> Dict[str, float]:
        """量天尺 - 测量传输损耗

        Args:
            source: 起点
            target: 终点

        Returns:
            损耗测量结果
        """
        edge_key = self._edge_key(source, target)
        edge = self._edges.get(edge_key)
        if not edge:
            return {"loss": -1.0, "latency": -1.0}

        # 模拟测量
        distance = self._calculate_distance(source, target)
        loss = distance * 0.01 + edge.loss_rate
        latency = edge.latency_ms * (1 + loss)

        result = {"loss": loss, "latency": latency, "distance": distance}
        logger.debug(f"量天尺测量: {source} -> {target}, {result}")
        return result

    def patrol(self) -> List[Dict]:
        """巡河 - 定期检查传输路径

        Returns:
            巡检结果
        """
        logger.info("巡河开始")
        results = []

        for edge_key, edge in self._edges.items():
            # 模拟巡检
            health = self._check_edge_health(edge)
            results.append(
                {
                    "edge": edge_key,
                    "health": health,
                    "timestamp": time.time(),
                }
            )
            if not health:
                logger.warning(f"路径异常: {edge_key}")

        self._patrol_history.append(
            {
                "timestamp": time.time(),
                "results": results,
                "issue_count": sum(1 for r in results if not r["health"]),
            }
        )
        logger.info(f"巡河完成: 检查={len(results)} 条路径")
        return results

    def reroute_paths(self) -> int:
        """移星斗 - 重新规划路径

        Returns:
            重新规划的路径数
        """
        logger.info("移星斗启动")
        rerouted = 0

        for edge_key, edge in self._edges.items():
            if not edge.is_active or edge.loss_rate > 0.2:
                # 找到替代路径
                alt_path = self._find_alternative_path(edge.source, edge.target)
                if alt_path:
                    rerouted += 1
                    logger.info(f"路径重规划: {edge_key} -> {alt_path}")

        return rerouted

    def setup_monitor_point(self, location: str, params: Dict) -> None:
        """埋点 - 设置监测点

        Args:
            location: 监测位置
            params: 监测参数
        """
        self._monitor_points[location] = {
            "params": params,
            "last_check": time.time(),
            "alert_count": 0,
        }
        logger.debug(f"埋点设置: {location}")

    def generate_report(self) -> NetworkReport:
        """生成网络报告"""
        node_count = len(self._nodes)
        edge_count = len(self._edges)

        avg_latency = 0.0
        if self._edges:
            avg_latency = sum(e.latency_ms for e in self._edges.values()) / edge_count

        coverage = self._calculate_coverage()

        return NetworkReport(
            node_count=node_count,
            edge_count=edge_count,
            status=self._network_status,
            avg_latency=avg_latency,
            coverage=coverage,
            timestamp=time.time(),
        )

    def find_path(self, source: str, target: str) -> Optional[PathResult]:
        """查找最优路径

        Args:
            source: 起点
            target: 终点

        Returns:
            路径结果
        """
        # BFS找最短路径
        visited = {source}
        queue = [(source, [source], 0.0)]

        while queue:
            current, path, latency = queue.pop(0)
            if current == target:
                return PathResult(
                    path=path,
                    total_latency=latency,
                    hop_count=len(path) - 1,
                    is_optimal=True,
                )

            for edge_key, edge in self._edges.items():
                neighbor = None
                if edge.source == current and edge.is_active:
                    neighbor = edge.target
                elif edge.target == current and edge.is_active:
                    neighbor = edge.source

                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(
                        (neighbor, path + [neighbor], latency + edge.latency_ms)
                    )

        return None

    def _create_mesh_topology(self) -> None:
        """创建网状拓扑"""
        node_ids = list(self._nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                edge = NetworkEdge(
                    source=node_ids[i],
                    target=node_ids[j],
                    latency_ms=50.0 + i * j,
                    bandwidth=1000.0,
                )
                self.add_edge(edge)

    def _create_star_topology(self) -> None:
        """创建星型拓扑"""
        node_ids = list(self._nodes.keys())
        if not node_ids:
            return
        center = node_ids[0]
        for nid in node_ids[1:]:
            edge = NetworkEdge(
                source=center,
                target=nid,
                latency_ms=30.0,
                bandwidth=2000.0,
            )
            self.add_edge(edge)

    def _create_ring_topology(self) -> None:
        """创建环型拓扑"""
        node_ids = list(self._nodes.keys())
        for i in range(len(node_ids)):
            edge = NetworkEdge(
                source=node_ids[i],
                target=node_ids[(i + 1) % len(node_ids)],
                latency_ms=40.0,
                bandwidth=1500.0,
            )
            self.add_edge(edge)

    def _sync_harmonics(self) -> None:
        """叠韵 - 将多个谐振腔调整至相同频率"""
        logger.info("执行叠韵: 同步所有节点频率")
        # 实际实现中会调用 singer 模块
        time.sleep(0.1) # 模拟同步耗时

    def _setup_monitor_points(self) -> None:
        """设置埋点"""
        for nid, node in self._nodes.items():
            self.setup_monitor_point(
                nid, {"type": "node", "resonator": node.resonator_id}
            )

    def _is_fully_connected(self) -> bool:
        """检查网络是否完全连通"""
        if not self._nodes:
            return False
        start = next(iter(self._nodes.keys()))
        visited = set()
        queue = [start]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for edge_key, edge in self._edges.items():
                neighbor = None
                if edge.source == current:
                    neighbor = edge.target
                elif edge.target == current:
                    neighbor = edge.source
                if neighbor and neighbor not in visited:
                    queue.append(neighbor)
        return len(visited) == len(self._nodes)

    def _calculate_distance(self, source: str, target: str) -> float:
        """计算节点间距离"""
        s = self._nodes.get(source)
        t = self._nodes.get(target)
        if not s or not t:
            return 0.0
        return math.sqrt(
            (s.position[0] - t.position[0]) ** 2 + (s.position[1] - t.position[1]) ** 2
        )

    def _edge_key(self, source: str, target: str) -> str:
        """生成边键"""
        return f"{source}-{target}" if source < target else f"{target}-{source}"

    def _calculate_coverage(self) -> float:
        """计算埋点覆盖率"""
        if not self._nodes:
            return 0.0
        return len(self._monitor_points) / len(self._nodes)

    def _check_edge_health(self, edge: NetworkEdge) -> bool:
        """检查连接健康"""
        return edge.is_active and edge.loss_rate < 0.15

    def _find_alternative_path(self, source: str, target: str) -> Optional[List[str]]:
        """查找替代路径"""
        result = self.find_path(source, target)
        return result.path if result else None

    def _update_network_status(self) -> None:
        """更新网络状态"""
        if self._is_fully_connected():
            coverage = self._calculate_coverage()
            self._network_status = (
                NetworkStatus.OPTIMAL if coverage >= 0.9 else NetworkStatus.CONNECTED
            )
        elif self._edges:
            self._network_status = NetworkStatus.PARTIAL
        else:
            self._network_status = NetworkStatus.DISCONNECTED
