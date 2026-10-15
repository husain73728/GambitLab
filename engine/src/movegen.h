#pragma once

#include "position.h"
#include "types.h"

// Fixed-capacity move list (max legal moves in a position is 218).
struct MoveList {
    Move moves[256];
    int count = 0;
    void add(Move m) { moves[count++] = m; }
};

// Pseudo-legal moves (king may be left in check).
void generateMoves(const Position& pos, MoveList& list, bool capturesOnly = false);

// Legal moves (filtered by making each move and testing for self-check).
void generateLegal(const Position& pos, MoveList& list, bool capturesOnly = false);

// Parse a UCI move string against the legal moves of `pos`. MOVE_NONE if illegal.
Move parseUciMove(Position& pos, const std::string& str);
