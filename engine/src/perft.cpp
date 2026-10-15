#include "perft.h"
#include "movegen.h"

#include <chrono>
#include <cstdio>

uint64_t perft(Position& pos, int depth) {
    if (depth <= 0) return 1;

    MoveList list;
    generateLegal(pos, list);
    if (depth == 1) return static_cast<uint64_t>(list.count);

    uint64_t nodes = 0;
    for (int i = 0; i < list.count; ++i) {
        Undo u;
        pos.makeMove(list.moves[i], u);
        nodes += perft(pos, depth - 1);
        pos.unmakeMove(list.moves[i], u);
    }
    return nodes;
}

void perftDivide(Position& pos, int depth) {
    MoveList list;
    generateLegal(pos, list);

    auto start = std::chrono::steady_clock::now();
    uint64_t total = 0;
    for (int i = 0; i < list.count; ++i) {
        Undo u;
        pos.makeMove(list.moves[i], u);
        const uint64_t n = perft(pos, depth - 1);
        pos.unmakeMove(list.moves[i], u);
        total += n;
        printf("%s: %llu\n", moveToStr(list.moves[i]).c_str(), static_cast<unsigned long long>(n));
    }
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                  std::chrono::steady_clock::now() - start).count();
    printf("Total: %llu\n", static_cast<unsigned long long>(total));
    if (ms > 0) printf("Time: %lld ms  (%.1f Mnps)\n", static_cast<long long>(ms),
                       static_cast<double>(total) / (static_cast<double>(ms) * 1000.0));
}

namespace {
struct PerftCase {
    const char* name;
    const char* fen;
    int depth;
    uint64_t expected;
};

const PerftCase Cases[] = {
    {"startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 5, 4865609ULL},
    {"kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 4, 4085603ULL},
    {"pos3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 5, 674624ULL},
    {"pos4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", 4, 422333ULL},
    {"pos4-mirror", "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1", 4, 422333ULL},
    {"pos5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", 4, 2103487ULL},
    {"pos6", "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10", 4, 3894594ULL},
};
} // namespace

bool runPerftSuite() {
    bool allOk = true;
    for (const PerftCase& c : Cases) {
        Position pos;
        pos.setFen(c.fen);
        auto start = std::chrono::steady_clock::now();
        const uint64_t got = perft(pos, c.depth);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                      std::chrono::steady_clock::now() - start).count();
        const bool ok = (got == c.expected);
        allOk &= ok;
        printf("[%s] %-12s depth %d: %llu (expected %llu) %s  [%lld ms]\n",
               ok ? "PASS" : "FAIL", c.name, c.depth,
               static_cast<unsigned long long>(got),
               static_cast<unsigned long long>(c.expected),
               ok ? "" : "<-- MISMATCH", static_cast<long long>(ms));
    }
    printf("%s\n", allOk ? "Perft suite: ALL PASS" : "Perft suite: FAILURES");
    return allOk;
}
