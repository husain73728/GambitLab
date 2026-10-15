#pragma once

#include "position.h"

#include <cstdint>
#include <string>

// Count leaf nodes of the legal move tree to the given depth.
uint64_t perft(Position& pos, int depth);

// Print per-root-move node counts (and total) for the given depth.
void perftDivide(Position& pos, int depth);

// Run the standard perft correctness suite. Returns true if all pass.
bool runPerftSuite();
