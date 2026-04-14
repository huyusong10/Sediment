#pragma once

#include <memory>
#include <string>
#include <vector>
#include <queue>
#include <optional>
#include <map>
#include <stdexcept>
#include <chrono>
#include <functional>

namespace hajimi {

// ==================== 异常类 ====================

class VortexError : public std::runtime_error {
public:
    explicit VortexError(const std::string& msg);
};

class FlowInterruptionError : public VortexError {    // 断流异常
public:
    explicit FlowInterruptionError(const std::string& segment_id);
};

class BackflowError : public VortexError {            // 回流异常
public:
    explicit BackflowError(const std::string& from_node, const std::string& to_node);
};

class ProtocolViolationError : public VortexError {   // 违反旋涡协议
public:
    explicit ProtocolViolationError(const std::string& violation);
};

// ==================== 枚举定义 ====================

enum class ProtocolState {
    Idle,
    Negotiating,
    Established,
    Transferring,
    Interrupted,    // 断流
    Backflowing,    // 回流
    Closed
};

enum class RouteType {
    Normal,         // 正常路由
    Split,          // 分流 - 单股分成多路
    Merge,          // 合流 - 多路汇聚
    Relay           // 接力 - 多腔串联传输
};

// ==================== 常量定义 ====================

namespace vortex_constants {
    constexpr int MAX_QUEUE_SIZE = 1000;
    constexpr double SAFETY_STRING_MIN = 0.3;         // 安全弦下限
    constexpr double SAFETY_STRING_MAX = 0.85;        // 安全弦上限
    constexpr double CLOCK_SYNC_TOLERANCE_MS = 5.0;   // 对钟容差（毫秒）
    constexpr int MAX_HOP_COUNT = 8;
    constexpr double RETRY_INTERVAL_MS = 100.0;
}

// ==================== 数据结构 ====================

/**
 * @brief 消息信封
 */
struct MessageEnvelope {
    std::string message_id;
    std::string sender_id;
    std::string receiver_id;
    std::string payload;
    std::chrono::system_clock::time_point timestamp;
    int hop_count = 0;
    bool is_priority = false;
};

/**
 * @brief 路由节点
 */
struct RouteNode {
    std::string node_id;
    std::string type;                                     // 驿站、谐振腔等
    double capacity;
    double current_load;
    bool is_available;
    std::vector<std::string> neighbors;                   // 邻居节点
};

/**
 * @brief 传输路径
 */
struct TransmissionPath {
    std::string path_id;
    std::vector<std::string> hops;                       // 路径节点序列
    RouteType route_type;
    double estimated_latency_ms;
    double safety_margin;                                // 安全弦余量
};

/**
 * @brief 对钟结果
 */
struct ClockSyncResult {
    bool is_synced;
    double offset_ms;                                    // 时间偏移
    std::string reference_node;
    std::chrono::system_clock::time_point sync_time;
};

// ==================== 回调类型 ====================

using MessageDeliveredCallback = std::function<void(const MessageEnvelope&)>;
using FlowInterruptedCallback = std::function<void(const std::string& path_id)>;
using BackflowDetectedCallback = std::function<void(const std::string& from, const std::string& to)>;

/**
 * @brief 旋涡引擎
 *
 * 核心职责：
 * - 旋涡协议处理：标准化哈基米传输
 * - 消息队列管理：优先级队列，支持信使传递
 * - 路由管理：分流、合流、接力
 * - 对钟：校准时间同步
 * - 安全弦监控：确保稳定运行参数边界
 */
class VortexEngine {
public:
    explicit VortexEngine(const std::string& engine_id);
    ~VortexEngine();

    VortexEngine(const VortexEngine&) = delete;
    VortexEngine& operator=(const VortexEngine&) = delete;
    VortexEngine(VortexEngine&&) noexcept;
    VortexEngine& operator=(VortexEngine&&) noexcept;

    // ==================== 协议管理 ====================

    /**
     * @brief 建立旋涡协议连接
     */
    bool establishProtocol(const std::string& source, const std::string& target);

    /**
     * @brief 关闭协议连接
     */
    bool closeProtocol(const std::string& connection_id);

    /**
     * @brief 获取协议状态
     */
    ProtocolState getProtocolState(const std::string& connection_id) const;

    // ==================== 消息传递 ====================

    /**
     * @brief 发送消息（信使机制）
     */
    bool sendMessage(MessageEnvelope envelope);

    /**
     * @brief 接收下一条消息
     */
    std::optional<MessageEnvelope> receiveMessage(const std::string& receiver_id);

    /**
     * @brief 获取队列深度
     */
    size_t getQueueDepth() const;

    // ==================== 路由管理 ====================

    /**
     * @brief 注册路由节点
     */
    bool registerNode(const RouteNode& node);

    /**
     * @brief 规划分流路径
     * @param source 源节点
     * @param targets 目标节点列表
     * @return 分流路径
     */
    TransmissionPath planSplitRoute(const std::string& source,
                                     const std::vector<std::string>& targets);

    /**
     * @brief 规划合流路径
     * @param sources 源节点列表
     * @param target 目标节点
     * @return 合流路径
     */
    TransmissionPath planMergeRoute(const std::vector<std::string>& sources,
                                     const std::string& target);

    /**
     * @brief 规划接力路径
     */
    TransmissionPath planRelayRoute(const std::string& source,
                                     const std::string& target);

    /**
     * @brief 检查路径是否在安全弦范围内
     */
    bool isWithinSafetyString(const TransmissionPath& path) const;

    // ==================== 对钟 ====================

    /**
     * @brief 对钟 - 校准时间同步
     * @param node_id 待校准节点
     * @return 对钟结果
     */
    ClockSyncResult synchronizeClock(const std::string& node_id);

    /**
     * @brief 批量对钟
     */
    std::map<std::string, ClockSyncResult> batchSynchronizeClocks(
        const std::vector<std::string>& node_ids);

    // ==================== 异常处理 ====================

    /**
     * @brief 处理断流
     */
    bool handleFlowInterruption(const std::string& path_id);

    /**
     * @brief 检测并处理回流
     */
    bool detectAndHandleBackflow(const std::string& path_id);

    // ==================== 回调注册 ====================

    void onMessageDelivered(MessageDeliveredCallback cb);
    void onFlowInterrupted(FlowInterruptedCallback cb);
    void onBackflowDetected(BackflowDetectedCallback cb);

    // ==================== 状态查询 ====================

    const std::string& getId() const { return engine_id_; }
    size_t getRegisteredNodeCount() const;

private:
    struct Impl;
    std::unique_ptr<Impl> pimpl_;
    std::string engine_id_;

    bool validateEnvelope(const MessageEnvelope& envelope) const;
    std::vector<std::string> findShortestPath(const std::string& from, const std::string& to) const;
    bool checkClockSyncTolerance(double offset_ms) const;
};

} // namespace hajimi
