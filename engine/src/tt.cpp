#include "tt.h"

#include <algorithm>

void TranspositionTable::resize(size_t megabytes) {
    size_t entries = (megabytes * 1024 * 1024) / sizeof(TTEntry);
    size_t n = 1;
    while (n * 2 <= entries) n *= 2;
    if (n < 1024) n = 1024;
    table.assign(n, TTEntry{});
    mask = n - 1;
}

void TranspositionTable::clear() {
    std::fill(table.begin(), table.end(), TTEntry{});
}

TTEntry* TranspositionTable::probe(uint64_t key) {
    TTEntry& e = table[key & mask];
    return (e.key == key) ? &e : nullptr;
}

void TranspositionTable::store(uint64_t key, int depth, int score, Move move, int flag) {
    TTEntry& e = table[key & mask];
    e.key = key;
    e.score = score;
    e.move = move;
    e.depth = static_cast<int8_t>(depth);
    e.flag = static_cast<uint8_t>(flag);
}
