#include "mediagateway/quality/RtpSequenceStats.h"
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using Stats = mediagateway::quality::RtpSequenceStats;
using R = Stats::Result;

void require(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message); // active in Release too
}
void balanced(const Stats &stats) {
    const auto s = stats.snapshot();
    require(s.received == s.unique + s.duplicates + s.too_old + s.discontinuities, "classification conservation");
    require(s.reordered <= s.unique, "reordered must be a subset of unique");
}

int main() {
    const std::vector<std::pair<std::string, std::function<void()>>> cases = {
        {"ordered including sequence zero", [] {
            Stats s;
            require(s.observe(0) == R::First, "zero is a valid first seq");
            require(s.observe(1) == R::InOrder, "ordered");
            require(s.observe(2) == R::InOrder, "ordered");
            require(s.snapshot().unique == 3, "unique count"); balanced(s);
        }},
        {"duplicate is not reordered", [] {
            Stats s; s.observe(100); s.observe(101);
            require(s.observe(100) == R::Duplicate, "old duplicate");
            require(s.observe(101) == R::Duplicate, "latest duplicate");
            require(s.snapshot().reordered == 0 && s.snapshot().duplicates == 2, "disjoint classification"); balanced(s);
        }},
        {"late first arrival then duplicate", [] {
            Stats s; s.observe(100); s.observe(102);
            require(s.observe(101) == R::Reordered, "late missing packet");
            require(s.observe(101) == R::Duplicate, "late replay");
            require(s.snapshot().unique == 3 && s.snapshot().reordered == 1, "late counters"); balanced(s);
        }},
        {"wrap with late previous-cycle packet", [] {
            Stats s; s.observe(65534); s.observe(0);
            require(s.observe(65535) == R::Reordered, "previous cycle late arrival");
            require(s.observe(65535) == R::Duplicate, "previous cycle duplicate");
            require(s.observe(1) == R::InOrder, "new cycle continues");
            require(s.snapshot().highest_extended == 65537, "extended sequence"); balanced(s);
        }},
        {"multiple wraps without stale-slot false duplicate", [] {
            Stats s;
            for (unsigned i = 0; i < 140000; ++i) {
                const auto r = s.observe(static_cast<std::uint16_t>(i));
                require(r == (i == 0 ? R::First : R::InOrder), "multiple wrap classification");
            }
            require(s.snapshot().unique == 140000 && s.snapshot().duplicates == 0, "extended slot tags"); balanced(s);
        }},
        {"window boundary is explicit", [] {
            Stats s; s.observe(0); s.observe(1024);
            require(s.observe(1) == R::Reordered, "distance 1023 retained");
            require(s.observe(0) == R::TooOld, "distance 1024 unknown, not duplicate"); balanced(s);
        }},
        {"before observation start is unknown", [] {
            Stats s; s.observe(0);
            require(s.observe(65535) == R::TooOld, "negative extended seq excluded"); balanced(s);
        }},
        {"large jump does not silently reset", [] {
            Stats s; s.observe(100);
            require(s.observe(3101) == R::Discontinuity, "forward step 3001 rejected");
            require(s.observe(32868) == R::Discontinuity, "half-range ambiguous");
            require(s.observe(101) == R::InOrder, "history retained");
            require(s.snapshot().epoch == 0, "no inferred epoch reset"); balanced(s);
        }},
        {"maximum accepted step", [] {
            Stats s; s.observe(100);
            require(s.observe(3100) == R::InOrder, "step 3000 accepted");
            require(s.snapshot().unique == 2, "gap not invented received packets"); balanced(s);
        }},
        {"explicit restart clears history", [] {
            Stats s; s.observe(100); s.observe(100); s.reset();
            require(s.observe(100) == R::First, "fresh epoch");
            const auto snap = s.snapshot();
            require(snap.epoch == 1 && snap.received == 1 && snap.duplicates == 0, "epoch counters"); balanced(s);
        }},
        {"tracks are independent", [] {
            Stats video, audio; video.observe(50); audio.observe(50); video.observe(50);
            require(video.snapshot().duplicates == 1 && audio.snapshot().duplicates == 0, "per track state"); balanced(video); balanced(audio);
        }}
    };
    unsigned failures = 0;
    for (const auto &entry : cases) {
        try { entry.second(); std::cout << "PASS: " << entry.first << '\n'; }
        catch (const std::exception &ex) { ++failures; std::cerr << "FAIL: " << entry.first << ": " << ex.what() << '\n'; }
    }
    std::cout << "Cases: " << cases.size() << ", failures: " << failures << '\n';
    return failures ? 1 : 0;
}
