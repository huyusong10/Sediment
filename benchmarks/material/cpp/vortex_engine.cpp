#include "vortex_engine.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <numeric>
#include <thread>
#include <mutex>

namespace hajimi {

// ==================== 异常类实现 ====================

VortexError::VortexError(const std::string& msg)
    : std::runtime_error("[VortexError] " + msg) {}

FlowInterruptionError::FlowInterruptionError(const std::string& segment_id)
    : VortexError("Flow interrupted at segment: " + segment_id) {}

BackflowError::BackflowError(const std::string& from_node, const std::string& to_node)
    : VortexError("Backflow detected: " + from_node + " -> " + to_node) {}

ProtocolViolationError::ProtocolViolationError(const std::string& violation)
    : VortexError("Protocol violation: " + violation) {}

// ==================== Pimpl 实现 ====================

struct VortexEngine::Impl {
    std::mutex queue_mutex;
    std::queue<MessageEnvelope> message_queue;
    std::map<std::string, ProtocolState> protocol_states;
    std::map<std::string, RouteNode> registered_nodes;
    std::map<std::string, TransmissionPath> active_paths;

    // 回调
    MessageDeliveredCallback on_message_delivered;
    FlowInterruptedCallback on_flow_interrupted;
    BackflowDetectedCallback on_backflow_detected;

    // 对钟参考
    std::string clock_reference_node = "master_clock";
    std::chrono::system_clock::time_point last_sync_time;
};

// ==================== 构造/析构 ====================

VortexEngine::VortexEngine(const std::string& engine_id)
    : pimpl_(std::make_unique<Impl>()), engine_id_(engine_id) {
    pimpl_->last_sync_time = std::chrono::system_clock::now();
}

VortexEngine::~VortexEngine() = default;

VortexEngine::VortexEngine(VortexEngine&& other) noexcept
    : pimpl_(std::move(other.pimpl_)), engine_id_(std::move(other.engine_id_)) {}

VortexEngine& VortexEngine::operator=(VortexEngine&& other) noexcept {
    if (this != &other) {
        pimpl_ = std::move(other.pimpl_);
        engine_id_ = std::move(other.engine_id_);
    }
    return *this;
}

// ==================== 协议管理 ====================

bool VortexEngine::establishProtocol(const std::string& source, const std::string& target) {
    std::string connection_id = source + "->" + target;

    if (pimpl_->protocol_states.count(connection_id) &&
        pimpl_->protocol_states[connection_id] != ProtocolState::Closed) {
        std::cerr << "[VortexEngine] 协议已存在: " << connection_id << std::endl;
        return false;
    }

    pimpl_->protocol_states[connection_id] = ProtocolState::Negotiating;

    // 模拟协商过程
    if (!validateEnvelope({.sender_id = source, .receiver_id = target})) {
        pimpl_->protocol_states[connection_id] = ProtocolState::Closed;
        return false;
    }

    pimpl_->protocol_states[connection_id] = ProtocolState::Established;
    std::cout << "[VortexEngine] 旋涡协议建立: " << connection_id << std::endl;
    return true;
}

bool VortexEngine::closeProtocol(const std::string& connection_id) {
    auto it = pimpl_->protocol_states.find(connection_id);
    if (it == pimpl_->protocol_states.end()) {
        return false;
    }

    it->second = ProtocolState::Closed;
    std::cout << "[VortexEngine] 协议关闭: " << connection_id << std::endl;
    return true;
}

ProtocolState VortexEngine::getProtocolState(const std::string& connection_id) const {
    auto it = pimpl_->protocol_states.find(connection_id);
    if (it == pimpl_->protocol_states.end()) {
        return ProtocolState::Idle;
    }
    return it->second;
}

// ==================== 消息传递 ====================

bool VortexEngine::sendMessage(MessageEnvelope envelope) {
    // 验证信封
    if (!validateEnvelope(envelope)) {
        std::cerr << "[VortexEngine] 信封验证失败" << std::endl;
        return false;
    }

    // 检查协议状态
    std::string conn_id = envelope.sender_id + "->" + envelope.receiver_id;
    auto state_it = pimpl_->protocol_states.find(conn_id);
    if (state_it == pimpl_->protocol_states.end() ||
        state_it->second != ProtocolState::Established) {
        std::cerr << "[VortexEngine] 协议未建立: " << conn_id << std::endl;
        return false;
    }

    // 检查队列容量
    {
        std::lock_guard<std::mutex> lock(pimpl_->queue_mutex);
        if (pimpl_->message_queue.size() >= vortex_constants::MAX_QUEUE_SIZE) {
            std::cerr << "[VortexEngine] 消息队列已满" << std::endl;
            return false;
        }
        pimpl_->message_queue.push(std::move(envelope));
    }

    std::cout << "[VortexEngine] 消息入队: " << conn_id << std::endl;
    return true;
}

std::optional<MessageEnvelope> VortexEngine::receiveMessage(const std::string& receiver_id) {
    std::lock_guard<std::mutex> lock(pimpl_->queue_mutex);

    // 查找第一条目标消息
    std::queue<MessageEnvelope> temp_queue;
    std::optional<MessageEnvelope> result;

    while (!pimpl_->message_queue.empty()) {
        auto msg = pimpl_->message_queue.front();
        pimpl_->message_queue.pop();

        if (msg.receiver_id == receiver_id && !result.has_value()) {
            result = std::move(msg);
        } else {
            temp_queue.push(std::move(msg));
        }
    }

    // 恢复未处理的消息
    pimpl_->message_queue = std::move(temp_queue);

    if (result.has_value()) {
        // 触发信使回调
        if (pimpl_->on_message_delivered) {
            pimpl_->on_message_delivered(*result);
        }
    }

    return result;
}

size_t VortexEngine::getQueueDepth() const {
    std::lock_guard<std::mutex> lock(pimpl_->queue_mutex);
    return pimpl_->message_queue.size();
}

// ==================== 路由管理 ====================

bool VortexEngine::registerNode(const RouteNode& node) {
    pimpl_->registered_nodes[node.node_id] = node;
    std::cout << "[VortexEngine] 节点注册: " << node.node_id << std::endl;
    return true;
}

TransmissionPath VortexEngine::planSplitRoute(const std::string& source,
                                                const std::vector<std::string>& targets) {
    // 分流 - 单股分成多路
    TransmissionPath path;
    path.route_type = RouteType::Split;
    path.hops.push_back(source);
    path.hops.insert(path.hops.end(), targets.begin(), targets.end());
    path.path_id = "split_" + source;
    path.estimated_latency_ms = targets.size() * 50.0;
    path.safety_margin = 0.5;

    std::cout << "[VortexEngine] 分流路径规划: " << source << " -> "
              << targets.size() << " 目标" << std::endl;
    return path;
}

TransmissionPath VortexEngine::planMergeRoute(const std::vector<std::string>& sources,
                                                const std::string& target) {
    // 合流 - 多路汇聚
    TransmissionPath path;
    path.route_type = RouteType::Merge;
    path.hops.insert(path.hops.end(), sources.begin(), sources.end());
    path.hops.push_back(target);
    path.path_id = "merge_" + target;
    path.estimated_latency_ms = sources.size() * 30.0;
    path.safety_margin = 0.6;

    std::cout << "[VortexEngine] 合流路径规划: " << sources.size() << " 源 -> "
              << target << std::endl;
    return path;
}

TransmissionPath VortexEngine::planRelayRoute(const std::string& source,
                                                const std::string& target) {
    // 接力 - 多腔串联传输
    auto hops = findShortestPath(source, target);

    TransmissionPath path;
    path.route_type = RouteType::Relay;
    path.hops = std::move(hops);
    path.path_id = "relay_" + source + "_" + target;
    path.estimated_latency_ms = path.hops.size() * 40.0;
    path.safety_margin = 0.45;

    std::cout << "[VortexEngine] 接力路径规划: " << source << " -> " << target
              << " (跳数: " << path.hops.size() << ")" << std::endl;
    return path;
}

bool VortexEngine::isWithinSafetyString(const TransmissionPath& path) const {
    // 检查路径是否在安全弦范围内
    return path.safety_margin >= vortex_constants::SAFETY_STRING_MIN &&
           path.safety_margin <= vortex_constants::SAFETY_STRING_MAX;
}

// ==================== 对钟 ====================

ClockSyncResult VortexEngine::synchronizeClock(const std::string& node_id) {
    ClockSyncResult result;
    result.reference_node = pimpl_->clock_reference_node;
    result.sync_time = std::chrono::system_clock::now();

    // 模拟时钟偏移
    double offset_ms = (std::rand() % 20) - 10;  // -10 ~ +10 ms
    result.offset_ms = offset_ms;
    result.is_synced = checkClockSyncTolerance(offset_ms);

    if (!result.is_synced) {
        std::cerr << "[VortexEngine] 对钟失败: " << node_id
                  << " 偏移 " << offset_ms << "ms" << std::endl;
    }

    return result;
}

std::map<std::string, ClockSyncResult> VortexEngine::batchSynchronizeClocks(
    const std::vector<std::string>& node_ids) {
    std::map<std::string, ClockSyncResult> results;

    for (const auto& node_id : node_ids) {
        results[node_id] = synchronizeClock(node_id);
    }

    pimpl_->last_sync_time = std::chrono::system_clock::now();
    std::cout << "[VortexEngine] 批量对钟完成: " << node_ids.size() << " 节点" << std::endl;
    return results;
}

bool VortexEngine::checkClockSyncTolerance(double offset_ms) const {
    return std::abs(offset_ms) <= vortex_constants::CLOCK_SYNC_TOLERANCE_MS;
}

// ==================== 异常处理 ====================

bool VortexEngine::handleFlowInterruption(const std::string& path_id) {
    std::cerr << "[VortexEngine] 处理断流: " << path_id << std::endl;

    auto path_it = pimpl_->active_paths.find(path_id);
    if (path_it != pimpl_->active_paths.end()) {
        path_it->second.safety_margin = 0.0;  // 标记为不可用
    }

    // 触发回调
    if (pimpl_->on_flow_interrupted) {
        pimpl_->on_flow_interrupted(path_id);
    }

    return true;
}

bool VortexEngine::detectAndHandleBackflow(const std::string& path_id) {
    // 检测回流
    auto path_it = pimpl_->active_paths.find(path_id);
    if (path_it == pimpl_->active_paths.end()) {
        return false;
    }

    // 模拟回流检测逻辑
    bool backflow_detected = (path_it->second.safety_margin < 0.2);

    if (backflow_detected) {
        std::string from_node = path_it->second.hops.back();
        std::string to_node = path_it->second.hops.front();

        std::cerr << "[VortexEngine] 检测到回流: " << from_node << " -> " << to_node << std::endl;

        if (pimpl_->on_backflow_detected) {
            pimpl_->on_backflow_detected(from_node, to_node);
        }
    }

    return backflow_detected;
}

// ==================== 回调注册 ====================

void VortexEngine::onMessageDelivered(MessageDeliveredCallback cb) {
    pimpl_->on_message_delivered = std::move(cb);
}

void VortexEngine::onFlowInterrupted(FlowInterruptedCallback cb) {
    pimpl_->on_flow_interrupted = std::move(cb);
}

void VortexEngine::onBackflowDetected(BackflowDetectedCallback cb) {
    pimpl_->on_backflow_detected = std::move(cb);
}

// ==================== 状态查询 ====================

size_t VortexEngine::getRegisteredNodeCount() const {
    return pimpl_->registered_nodes.size();
}

// ==================== 私有方法 ====================

bool VortexEngine::validateEnvelope(const MessageEnvelope& envelope) const {
    if (envelope.sender_id.empty() || envelope.receiver_id.empty()) {
        return false;
    }
    if (envelope.hop_count > vortex_constants::MAX_HOP_COUNT) {
        return false;
    }
    return true;
}

std::vector<std::string> VortexEngine::findShortestPath(const std::string& from,
                                                          const std::string& to) const {
    // 简化的最短路径查找（实际应使用 Dijkstra 等算法）
    std::vector<std::string> path;
    path.push_back(from);

    auto from_it = pimpl_->registered_nodes.find(from);
    if (from_it != pimpl_->registered_nodes.end()) {
        for (const auto& neighbor : from_it->second.neighbors) {
            if (neighbor == to) {
                path.push_back(to);
                return path;
            }
        }
    }

    // 未找到直接路径，添加中间节点
    path.push_back("驿站_" + from + "_" + to);
    path.push_back(to);

    return path;
}

} // namespace hajimi
