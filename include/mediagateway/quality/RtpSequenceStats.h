#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace mediagateway { namespace quality {

// One instance per RTP track and receive epoch, called on its owner poller.
// No synchronization: obtain snapshots on that same poller, then copy them out.
class RtpSequenceStats {
public:
    static constexpr std::size_t kWindow = 1024;
    static constexpr int kMaxForwardStep = 3000;

    enum class Result { First, InOrder, Reordered, Duplicate, TooOld, Discontinuity };
    struct Snapshot {
        std::uint64_t epoch = 0;
        std::uint64_t received = 0;
        std::uint64_t unique = 0;
        std::uint64_t reordered = 0; // subset of unique, never includes duplicates
        std::uint64_t duplicates = 0; // only provable within kWindow
        std::uint64_t too_old = 0; // cannot distinguish duplicate from late unique
        std::uint64_t discontinuities = 0; // ignored by the sequence history
        std::int64_t highest_extended = -1;
    };

    RtpSequenceStats();
    Result observe(std::uint16_t sequence);
    // Caller must reset on reconnect or accepted SSRC change. Does not guess
    // restarts from a sequence jump; a jump alone is insufficient evidence.
    void reset();
    Snapshot snapshot() const { return stats_; }

private:
    std::array<std::int64_t, kWindow> seen_{};
    Snapshot stats_{};
    std::int64_t first_ = -1;
};

}} // namespace mediagateway::quality
