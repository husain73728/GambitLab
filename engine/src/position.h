#pragma once

#include "bitboard.h"
#include "types.h"

#include <string>

// State needed to undo a move.
struct Undo {
    int castling;
    int ep;
    int halfmove;
    Piece captured;
    Key key;
};

class Position {
public:
    Bitboard byColor[COLOR_NB] = {};
    Bitboard byType[PIECE_TYPE_NB] = {};
    Piece board[64];
    Color side = WHITE;
    int castling = 0;   // castling-rights bitmask
    int ep = -1;        // en-passant target square, or -1
    int halfmove = 0;   // fifty-move counter
    int fullmove = 1;
    Key key = 0;        // Zobrist hash

    Position() { clear(); }

    void clear();
    bool setFen(const std::string& fen);
    std::string fen() const;
    void print() const;

    Bitboard occupied() const { return byColor[WHITE] | byColor[BLACK]; }
    Bitboard pieces(Color c, PieceType pt) const { return byColor[c] & byType[pt]; }
    Bitboard pieces(PieceType pt) const { return byType[pt]; }

    int kingSq(Color c) const { return lsb(pieces(c, KING)); }
    bool isAttacked(int sq, Color by) const;
    bool inCheck(Color c) const { return isAttacked(kingSq(c), ~c); }

    // Make/unmake a pseudo-legal or legal move. `u` receives the undo state.
    void makeMove(Move m, Undo& u);
    void unmakeMove(Move m, const Undo& u);

    // Null move (pass the turn) used by search pruning.
    void makeNull(Undo& u);
    void unmakeNull(const Undo& u);

    // Piece-set primitives that keep occupancy bitboards + Zobrist in sync.
    void putPiece(Piece p, int sq);
    void removePiece(int sq);
    void movePiece(Piece p, int from, int to);

private:
    void computeKey();
};

namespace Zobrist {
void init();
}
