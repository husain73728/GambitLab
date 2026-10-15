#pragma once

#include "position.h"

struct SearchLimits {
    int depth = 64;
    long long movetime = 0;
    long long wtime = 0, btime = 0, winc = 0, binc = 0;
    int movestogo = 0;
    bool infinite = false;
};

// Resize the shared transposition table.
void searchSetHash(int megabytes);

// Request that a running search stop as soon as possible.
void searchStop();

// Clear the stop flag before starting a new search (call from the launching thread).
void searchClear();

// Search `pos` and return the best move, printing UCI `info` lines along the way.
Move searchPosition(Position& pos, const SearchLimits& limits);
