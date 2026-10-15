#pragma once

#include "types.h"

#include <vector>

enum Bound : uint8_t {
    BOUND_NONE  = 0,
    BOUND_UPPER = 1,
    BOUND_LOWER = 2,
    BOUND_EXACT = 3
};

struct TTEntry {
    uint64_t key;
    int32_t  score;
    uint16_t move;
    int8_t   depth;
    uint8_t  flag;
};

class TranspositionTable {
public:
    TranspositionTable() { resize(16); }

    void resize(size_t megabytes);
    void clear();
    TTEntry* probe(uint64_t key);
    void store(uint64_t key, int depth, int score, Move move, int flag);

private:
    std::vector<TTEntry> table;
    size_t mask = 0;
};
