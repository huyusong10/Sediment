"""
旋涡协议实现模块

实现哈基米传输的标准协议，支持消息编码解码、
路由管理以及断流回流异常处理。
"""

import logging
import struct
import time
from enum import IntEnum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 协议常量
PROTOCOL_VERSION = 3  # 对应 system_config.yaml 中的 vortex-3.2
HEADER_SIZE = 16  # 协议头大小(字节)
MAX_PAYLOAD_SIZE = 4096  # 最大载荷
HEARTBEAT_INTERVAL = 30  # 心跳间隔(秒)
TIMEOUT_THRESHOLD = 120  # 超时阈值(秒)


class ProtocolError(Exception):
    """旋涡协议异常"""

    pass


class DecodeError(ProtocolError):
    """解码异常"""

    pass


class RoutingError(ProtocolError):
    """路由异常"""

    pass


class MessageType(IntEnum):
    """消息类型 - 与旋涡协议报文定义.xml保持一致"""

    DATA = 0x01           # 标准传输
    TRANSFER = 0x02       # 跃迁请求
    CRYSTALLIZE = 0x03    # 晶格化指令
    STRIP = 0x04          # 剥离指令
    ERROR = 0xE0          # 异常状态
    DISCONNECTION = 0xE1  # 断流
    BACKFLOW = 0xE2       # 回流
    CRYSTALLIZE_FAILED = 0xE3  # 晶格化失败
    TRANSFER_TIMEOUT = 0xE4    # 跃迁超时


@dataclass
class ProtocolHeader:
    """协议头"""

    version: int
    msg_type: MessageType
    sequence: int
    source: str
    destination: str
    payload_length: int
    checksum: int

    def pack(self) -> bytes:
        """打包协议头"""
        return struct.pack(
            "!BBHI16s16sH",
            self.version,
            self.msg_type,
            self.sequence,
            0,  # reserved
            self.source.encode().ljust(16, b"\0"),
            self.destination.encode().ljust(16, b"\0"),
            self.payload_length,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "ProtocolHeader":
        """从字节流解包协议头"""
        if len(data) < HEADER_SIZE:
            raise DecodeError(f"数据长度不足: {len(data)} < {HEADER_SIZE}")
        ver, mtype, seq, _, src, dst, plen = struct.unpack(
            "!BBHI16s16sH", data[:HEADER_SIZE]
        )
        return cls(
            version=ver,
            msg_type=MessageType(mtype),
            sequence=seq,
            source=src.decode().strip("\0"),
            destination=dst.decode().strip("\0"),
            payload_length=plen,
            checksum=0,
        )


@dataclass
class VortexMessage:
    """旋涡协议消息"""

    header: ProtocolHeader
    payload: bytes
    timestamp: float
    _delivered: bool = False

    @property
    def is_haky_transfer(self) -> bool:
        """判断是否为哈基米传输消息"""
        return self.header.msg_type == MessageType.DATA and len(self.payload) > 0

    def encode(self) -> bytes:
        """编码完整消息"""
        self.header.payload_length = len(self.payload)
        header_bytes = self.header.pack()
        return header_bytes + self.payload

    @classmethod
    def decode(cls, data: bytes) -> "VortexMessage":
        """解码完整消息"""
        header = ProtocolHeader.unpack(data)
        payload = data[HEADER_SIZE : HEADER_SIZE + header.payload_length]
        return cls(
            header=header,
            payload=payload,
            timestamp=time.time(),
        )


class VortexProtocol:
    """旋涡协议处理器

    负责消息的编码解码、路由分发、安全弦校验。
    支持断流恢复、失败回退与回流检测。
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._sequence = 0
        self._routes: Dict[str, Callable] = {}
        self._last_heartbeat: Dict[str, float] = {}
        self._pending_acks: Dict[int, VortexMessage] = {}
        self._flow_history: list = []  # 用于检测回流
        logger.info(f"VortexProtocol [{node_id}] initialized")

    def create_message(
        self,
        msg_type: MessageType,
        destination: str,
        payload: bytes = b"",
    ) -> VortexMessage:
        """创建旋涡协议消息"""
        self._sequence += 1
        header = ProtocolHeader(
            version=PROTOCOL_VERSION,
            msg_type=msg_type,
            sequence=self._sequence,
            source=self.node_id,
            destination=destination,
            payload_length=len(payload),
            checksum=self._calculate_checksum(payload),
        )
        return VortexMessage(header=header, payload=payload, timestamp=time.time())

    def encode_transfer(self, target: str, volume: float, crystal_data: bytes) -> bytes:
        """编码哈基米传输消息

        将晶格化后的数据进行剥离封装。
        """
        payload = struct.pack("!d", volume) + crystal_data
        msg = self.create_message(MessageType.DATA, target, payload)
        self._pending_acks[msg.header.sequence] = msg
        self._flow_history.append(("out", target, volume))
        logger.debug(f"编码传输: seq={msg.header.sequence}, target={target}")
        return msg.encode()

    def decode_message(self, raw_data: bytes) -> VortexMessage:
        """解码接收到的消息"""
        try:
            msg = VortexMessage.decode(raw_data)
        except Exception as e:
            raise DecodeError(f"消息解码失败: {e}")

        # 检测回流
        self._check_backflow(msg)
        return msg

    def register_route(self, pattern: str, handler: Callable) -> None:
        """注册消息路由"""
        self._routes[pattern] = handler
        logger.debug(f"路由注册: {pattern}")

    def dispatch(self, message: VortexMessage) -> Any:
        """分发消息到对应路由

        Args:
            message: 待分发消息

        Returns:
            处理结果

        Raises:
            RoutingError: 无匹配路由
        """
        for pattern, handler in self._routes.items():
            if pattern in message.header.destination:
                return handler(message)
        raise RoutingError(f"无匹配路由: dest={message.header.destination}")

    def check_flow_integrity(self) -> bool:
        """检查传输流是否在安全弦边界内

        Returns:
            流是否安全
        """
        if len(self._flow_history) < 2:
            return True
        # 检查是否有回流异常
        out_volumes = [v for d, _, v in self._flow_history if d == "out"]
        in_volumes = [v for d, _, v in self._flow_history if d == "in"]
        return sum(out_volumes) >= sum(in_volumes) * 0.9

    def record_clock_sync(self, peer_id: str) -> None:
        """记录对钟同步时间"""
        self._last_heartbeat[peer_id] = time.time()
        logger.debug(f"对钟记录: {peer_id}")

    def is_peer_alive(self, peer_id: str, timeout: float = TIMEOUT_THRESHOLD) -> bool:
        """检查对端是否存活"""
        last = self._last_heartbeat.get(peer_id, 0)
        return (time.time() - last) < timeout

    def _check_backflow(self, message: VortexMessage) -> None:
        """检测回流 - 反向流动异常"""
        self._flow_history.append(("in", message.header.source, len(message.payload)))
        # 简单回流检测: 短时间内大量反向数据
        recent_in = [v for d, _, v in self._flow_history[-20:] if d == "in"]
        if len(recent_in) > 10:
            logger.warning(f"疑似回流: {message.header.source}")

    def _calculate_checksum(self, data: bytes) -> int:
        """计算校验和"""
        return sum(data) & 0xFFFF
