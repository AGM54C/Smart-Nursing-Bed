#!/usr/bin/env python3
"""
智能护理病床 - Agent消息总线 (借鉴 OpenHarness TeammateMailbox)

异步消息队列, 解耦各Agent之间的通信:
  传感器Event → Mailbox → Coordinator → Mailbox → Worker Agents
                                       → Mailbox → Actuator
                                       → Mailbox → Voice

对标 OpenHarness 模式:
  TeammateMailbox      → AgentMailbox (线程安全, JSON持久化)
  MailboxMessage       → AgentMessage
  write_to_mailbox     → send()
  read_all             → receive()
  create_user_message  → create_sensor_event() / create_decision_request()

与 OpenHarness 的区别:
  - OpenHarness 用文件系统(每条消息一个JSON文件) + asyncio
  - 本项目用 collections.deque + threading.Lock (嵌入式场景更高效)
  - 增加了 priority 字段 (护理场景有紧急程度区分)
"""

import json
import os
import time
import uuid
import threading
import logging
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from enum import Enum

logging.basicConfig(level=logging.INFO, format='[AgentMailbox] %(message)s')
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  消息类型 (对标 OpenHarness MessageType)
# ═══════════════════════════════════════════

class MessageType(str, Enum):
    """Agent消息类型 (对标 OpenHarness MessageType Literal)"""
    SENSOR_EVENT = "sensor_event"               # 传感器数据事件
    DECISION_REQUEST = "decision_request"       # 请求Agent决策
    DECISION_RESPONSE = "decision_response"     # Agent决策结果
    COORDINATOR_DIRECTIVE = "coordinator_directive"  # Coordinator指令
    ALERT_ESCALATION = "alert_escalation"       # 告警升级
    PERMISSION_REQUEST = "permission_request"   # 权限请求 (对标 OpenHarness)
    PERMISSION_RESPONSE = "permission_response" # 权限响应
    SHUTDOWN = "shutdown"                       # 关闭信号
    IDLE_NOTIFICATION = "idle_notification"     # 空闲通知


class Priority(int, Enum):
    """消息优先级"""
    CRITICAL = 0   # 跌倒/危急体征
    HIGH = 1       # 体征异常
    MEDIUM = 2     # 受压风险
    LOW = 3        # 常规监测
    INFO = 4       # 信息通知


# ═══════════════════════════════════════════
#  消息数据结构 (对标 OpenHarness MailboxMessage)
# ═══════════════════════════════════════════

@dataclass
class AgentMessage:
    """
    Agent间通信消息 (对标 OpenHarness MailboxMessage @dataclass)

    字段映射:
      id        → OpenHarness MailboxMessage.id
      msg_type  → OpenHarness MailboxMessage.type
      sender    → OpenHarness MailboxMessage.sender
      recipient → OpenHarness MailboxMessage.recipient
      payload   → OpenHarness MailboxMessage.payload
      timestamp → OpenHarness MailboxMessage.timestamp
      read      → OpenHarness MailboxMessage.read
      priority  → 本项目新增 (护理场景需要)
    """
    id: str = ""
    msg_type: str = MessageType.SENSOR_EVENT
    sender: str = "system"
    recipient: str = "coordinator"
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0
    read: bool = False
    priority: int = Priority.LOW

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        """序列化 (对标 OpenHarness MailboxMessage.to_dict)"""
        return {
            "id": self.id,
            "msg_type": self.msg_type if isinstance(self.msg_type, str) else self.msg_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "read": self.read,
            "priority": self.priority if isinstance(self.priority, int) else self.priority.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        """反序列化 (对标 OpenHarness MailboxMessage.from_dict)"""
        return cls(
            id=data.get("id", ""),
            msg_type=data.get("msg_type", MessageType.SENSOR_EVENT),
            sender=data.get("sender", "system"),
            recipient=data.get("recipient", "coordinator"),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", 0.0),
            read=data.get("read", False),
            priority=data.get("priority", Priority.LOW),
        )


# ═══════════════════════════════════════════
#  AgentMailbox (对标 OpenHarness TeammateMailbox)
# ═══════════════════════════════════════════

class AgentMailbox:
    """
    线程安全的Agent消息总线

    对标 OpenHarness TeammateMailbox, 但用线程安全的deque代替文件系统:
      - OpenHarness: 每条消息一个JSON文件 + asyncio + exclusive_file_lock
      - 本项目: deque + threading.Lock (嵌入式场景更高效)
      - 增加: 持久化到合并JSON文件 (定期flush, 可审计)

    Usage:
        mailbox = AgentMailbox()
        mailbox.send(create_sensor_event("vitals", {"heart_rate": 120}))
        msgs = mailbox.receive("vitals_agent")
    """

    def __init__(self, persist_dir: str = "memory/mailbox", max_messages: int = 500):
        self._queues: dict[str, deque] = {}   # recipient_id → deque[AgentMessage]
        self._global_log: deque = deque(maxlen=max_messages)  # 全局消息日志
        self._lock = threading.Lock()
        self._persist_dir = persist_dir
        self._message_count = 0

        # 创建持久化目录
        os.makedirs(persist_dir, exist_ok=True)
        log.info("📬 AgentMailbox initialized (persist=%s)", persist_dir)

    def send(self, msg: AgentMessage) -> None:
        """
        发送消息到指定Agent的收件箱

        对标 OpenHarness TeammateMailbox.write() (atomic write)
        本项目用线程锁保证线程安全, 而非文件锁
        """
        with self._lock:
            recipient = msg.recipient
            if recipient not in self._queues:
                self._queues[recipient] = deque(maxlen=200)
            self._queues[recipient].append(msg)
            self._global_log.append(msg)
            self._message_count += 1

    def receive(self, agent_id: str, unread_only: bool = True) -> list[AgentMessage]:
        """
        读取指定Agent的待处理消息, 按优先级排序

        对标 OpenHarness TeammateMailbox.read_all(unread_only=True)
        """
        with self._lock:
            queue = self._queues.get(agent_id, deque())
            messages = []
            for msg in queue:
                if not unread_only or not msg.read:
                    messages.append(msg)
            # 按优先级排序 (priority越小越优先)
            messages.sort(key=lambda m: (m.priority, m.timestamp))
            return messages

    def mark_read(self, message_id: str) -> None:
        """标记消息已读 (对标 OpenHarness TeammateMailbox.mark_read)"""
        with self._lock:
            for queue in self._queues.values():
                for msg in queue:
                    if msg.id == message_id:
                        msg.read = True
                        return

    def broadcast(self, msg: AgentMessage, recipients: list = None) -> None:
        """
        广播消息给所有Agent (或指定列表)

        OpenHarness 中没有直接的broadcast, 但 write_to_mailbox 支持向任意recipient写入。
        本项目增加批量广播功能。
        """
        targets = recipients or list(self._queues.keys())
        for recipient in targets:
            broadcast_msg = AgentMessage(
                msg_type=msg.msg_type,
                sender=msg.sender,
                recipient=recipient,
                payload=msg.payload,
                priority=msg.priority,
            )
            self.send(broadcast_msg)

    def clear(self, agent_id: str = None) -> None:
        """清空消息 (对标 OpenHarness TeammateMailbox.clear)"""
        with self._lock:
            if agent_id:
                self._queues.pop(agent_id, None)
            else:
                self._queues.clear()

    def get_stats(self) -> dict:
        """消息总线统计"""
        with self._lock:
            stats = {
                "total_messages": self._message_count,
                "queues": {},
                "global_log_size": len(self._global_log),
            }
            for agent_id, queue in self._queues.items():
                unread = sum(1 for m in queue if not m.read)
                stats["queues"][agent_id] = {
                    "total": len(queue),
                    "unread": unread,
                }
            return stats

    def flush_to_disk(self) -> None:
        """
        持久化消息日志到磁盘 (可审计, 对标 OpenHarness 文件持久化)

        OpenHarness每条消息一个文件 (<timestamp>_<id>.json),
        本项目合并为一个日志文件 (嵌入式场景减少IO)
        """
        with self._lock:
            if not self._global_log:
                return
            try:
                log_file = os.path.join(self._persist_dir,
                                        f"mailbox_{time.strftime('%Y%m%d')}.jsonl")
                with open(log_file, "a", encoding="utf-8") as f:
                    for msg in self._global_log:
                        if not msg.read:
                            continue  # 只持久化已处理的消息
                        f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
            except Exception as e:
                log.error("Flush to disk failed: %s", e)

    def get_recent_log(self, count: int = 20) -> list[dict]:
        """获取最近的消息日志 (供API查询)"""
        with self._lock:
            recent = list(self._global_log)[-count:]
            return [m.to_dict() for m in recent]


# ═══════════════════════════════════════════
#  消息工厂函数 (对标 OpenHarness create_* 函数)
# ═══════════════════════════════════════════

def create_sensor_event(sensor_type: str, data: dict,
                        priority: int = Priority.LOW) -> AgentMessage:
    """
    创建传感器事件消息

    对标 OpenHarness create_user_message(sender, recipient, content)
    """
    return AgentMessage(
        msg_type=MessageType.SENSOR_EVENT,
        sender=f"sensor_{sensor_type}",
        recipient="coordinator",
        payload={"sensor_type": sensor_type, "data": data},
        priority=priority,
    )


def create_decision_request(coordinator: str, agent_name: str,
                            context: dict, priority: int = Priority.MEDIUM) -> AgentMessage:
    """创建决策请求 (Coordinator → Worker Agent)"""
    return AgentMessage(
        msg_type=MessageType.DECISION_REQUEST,
        sender=coordinator,
        recipient=agent_name,
        payload={"context": context},
        priority=priority,
    )


def create_decision_response(agent_name: str, decision: dict,
                              priority: int = Priority.MEDIUM) -> AgentMessage:
    """创建决策响应 (Worker Agent → Coordinator)"""
    return AgentMessage(
        msg_type=MessageType.DECISION_RESPONSE,
        sender=agent_name,
        recipient="coordinator",
        payload={"decision": decision},
        priority=priority,
    )


def create_alert_escalation(agent_name: str, level: str,
                            message: str) -> AgentMessage:
    """创建告警升级消息"""
    pri = Priority.CRITICAL if level == "critical" else Priority.HIGH
    return AgentMessage(
        msg_type=MessageType.ALERT_ESCALATION,
        sender=agent_name,
        recipient="coordinator",
        payload={"level": level, "message": message},
        priority=pri,
    )


def create_shutdown_request(sender: str = "system") -> AgentMessage:
    """创建关闭信号 (对标 OpenHarness create_shutdown_request)"""
    return AgentMessage(
        msg_type=MessageType.SHUTDOWN,
        sender=sender,
        recipient="all",
        payload={},
        priority=Priority.CRITICAL,
    )
