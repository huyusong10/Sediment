"""
信使通信模块

负责消息传递、路由管理与状态同步。
支持分流、合流与传输路径规划。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)

# 通信常量
MAX_QUEUE_SIZE = 10000  # 消息队列上限
DELIVERY_TIMEOUT = 30  # 投递超时(秒)
ROUTE_CACHE_TTL = 600  # 路由缓存有效期(秒)
MONITOR_POINT_INTERVAL = 60  # 埋点上报间隔(秒)


class MessengerError(Exception):
    """信使异常"""

    pass


class DeliveryError(MessengerError):
    """投递异常"""

    pass


class RouteError(MessengerError):
    """路由异常"""

    pass


class MessageStatus(Enum):
    """消息状态"""

    QUEUED = "queued"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class Message:
    """消息定义"""

    msg_id: str
    source: str
    destination: str
    payload: Any
    status: MessageStatus = MessageStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None
    hops: int = 0
    retry_count: int = 0


@dataclass
class Route:
    """路由定义"""

    route_id: str
    source: str
    destination: str
    waypoints: List[str]  # 途经驿站
    is_active: bool = True
    latency_ms: float = 0.0


class Messenger:
    """信使通信系统

    负责在谐振腔之间传递状态信息。
    支持走线(路径规划)、埋点(监测设置)、分流合流。
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._message_queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._routes: Dict[str, Route] = {}
        self._monitor_points: Dict[str, Dict] = {}  # 埋点
        self._delivered: Dict[str, Message] = {}
        self._clock_offsets: Dict[str, float] = {}  # 对钟偏移
        self._delivery_callbacks: Dict[str, Callable] = {}
        logger.info(f"Messenger [{node_id}] initialized")

    def send(self, destination: str, payload: Any) -> str:
        """发送消息

        Args:
            destination: 目标节点
            payload: 消息内容

        Returns:
            消息ID
        """
        msg_id = f"MSG-{int(time.time() * 1000)}"
        msg = Message(
            msg_id=msg_id,
            source=self.node_id,
            destination=destination,
            payload=payload,
        )
        self._message_queue.append(msg)
        logger.debug(f"消息入队: {msg_id} -> {destination}")
        return msg_id

    def send_via_resonator(self, resonator_id: str, payload: Any) -> str:
        """通过谐振腔发送"""
        return self.send(f"resonator:{resonator_id}", payload)

    def deliver(self, msg: Message) -> bool:
        """投递消息

        Args:
            msg: 待投递消息

        Returns:
            是否投递成功
        """
        msg.status = MessageStatus.IN_TRANSIT
        msg.hops += 1

        # 检查路由
        route = self._find_route(msg.source, msg.destination)
        if not route:
            msg.status = MessageStatus.FAILED
            logger.warning(f"无可用路由: {msg.source} -> {msg.destination}")
            return False

        # 途经驿站中转
        for waypoint in route.waypoints:
            msg.hops += 1
            self._record_monitor_point(waypoint, msg.msg_id)

        # 投递
        try:
            if msg.destination in self._delivery_callbacks:
                self._delivery_callbacks[msg.destination](msg.payload)
        except Exception as e:
            logger.error(f"投递失败: {msg.msg_id}, error={e}")
            msg.retry_count += 1
            if msg.retry_count < 3:
                self._message_queue.append(msg)
                return False
            msg.status = MessageStatus.FAILED
            return False

        msg.status = MessageStatus.DELIVERED
        msg.delivered_at = time.time()
        self._delivered[msg.msg_id] = msg
        logger.debug(f"消息已投递: {msg.msg_id}")
        return True

    def split_flow(self, msg: Message, targets: List[str]) -> List[str]:
        """分流 - 单股分成多路

        Args:
            msg: 原始消息
            targets: 分流目标列表

        Returns:
            新消息ID列表
        """
        new_ids = []
        for target in targets:
            new_id = f"{msg.msg_id}-split-{target}"
            split_msg = Message(
                msg_id=new_id,
                source=msg.source,
                destination=target,
                payload=msg.payload,
            )
            self._message_queue.append(split_msg)
            new_ids.append(new_id)
        logger.info(f"分流: {msg.msg_id} -> {targets}")
        return new_ids

    def merge_flows(self, messages: List[Message], target: str) -> str:
        """合流 - 多路汇聚

        Args:
            messages: 待汇聚消息列表
            target: 汇聚目标

        Returns:
            合并后的消息ID
        """
        merged_payload = [m.payload for m in messages]
        merged_id = f"MSG-merge-{int(time.time() * 1000)}"
        merged = Message(
            msg_id=merged_id,
            source=self.node_id,
            destination=target,
            payload=merged_payload,
        )
        self._message_queue.append(merged)
        logger.info(f"合流: {len(messages)} 条消息 -> {target}")
        return merged_id

    def plan_route(self, source: str, destination: str, waypoints: List[str]) -> Route:
        """走线 - 规划传输路径

        Args:
            source: 起点
            destination: 终点
            waypoints: 途经驿站

        Returns:
            路由定义
        """
        route_id = f"RT-{source}-{destination}"
        route = Route(
            route_id=route_id,
            source=source,
            destination=destination,
            waypoints=waypoints,
        )
        self._routes[route_id] = route
        logger.info(f"走线完成: {route_id}, 途经={waypoints}")
        return route

    def setup_monitor_point(
        self, location: str, interval: int = MONITOR_POINT_INTERVAL
    ) -> None:
        """埋点 - 设置监测点

        Args:
            location: 监测位置
            interval: 上报间隔(秒)
        """
        self._monitor_points[location] = {
            "interval": interval,
            "last_report": 0.0,
            "report_count": 0,
        }
        logger.info(f"埋点设置: {location}")

    def sync_clock(self, peer_id: str, offset: float) -> None:
        """对钟 - 校准时间同步

        Args:
            peer_id: 对端ID
            offset: 时间偏移(秒)
        """
        self._clock_offsets[peer_id] = offset
        logger.debug(f"对钟同步: {peer_id}, offset={offset:.3f}s")

    def check_route_health(self, route_id: str) -> bool:
        """检查路由健康"""
        route = self._routes.get(route_id)
        if not route or not route.is_active:
            return False
        # 检查断流
        return True

    def _find_route(self, source: str, destination: str) -> Optional[Route]:
        """查找可用路由"""
        for route_id, route in self._routes.items():
            if route.source == source and route.destination == destination:
                return route if route.is_active else None
        # 默认直通路由
        return Route(
            route_id=f"default-{source}-{destination}",
            source=source,
            destination=destination,
            waypoints=[],
        )

    def _record_monitor_point(self, location: str, msg_id: str) -> None:
        """记录埋点数据"""
        if location in self._monitor_points:
            self._monitor_points[location]["last_report"] = time.time()
            self._monitor_points[location]["report_count"] += 1

    def register_delivery_callback(self, destination: str, callback: Callable) -> None:
        """注册投递回调"""
        self._delivery_callbacks[destination] = callback

    def get_pending_count(self) -> int:
        """获取待处理消息数"""
        return len(self._message_queue)
