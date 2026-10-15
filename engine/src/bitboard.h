#pragma once

#include "types.h"

// ---------------------------------------------------------------------------
// Bitboard utilities and precomputed attack tables (magic bitboards)
// ---------------------------------------------------------------------------

namespace BB {

extern Bitboard PawnAttacks[COLOR_NB][64];
extern Bitboard KnightAttacks[64];
extern Bitboard KingAttacks[64];

struct Magic {
    Bitboard mask;
    Bitboard magic;
    Bitboard* attacks;
    int shift;
};

extern Magic RookMagics[64];
extern Magic BishopMagics[64];

// Must be called once before any attack lookup.
void init();

} // namespace BB

inline Bitboard squareBB(int s) { return 1ULL << s; }
inline int popcount(Bitboard b) { return __builtin_popcountll(b); }
inline int lsb(Bitboard b) { return __builtin_ctzll(b); }
inline int msb(Bitboard b) { return 63 - __builtin_clzll(b); }
inline void popLsb(Bitboard& b) { b &= b - 1; }

inline Bitboard rookAttacks(int s, Bitboard occ) {
    const BB::Magic& m = BB::RookMagics[s];
    return m.attacks[((occ & m.mask) * m.magic) >> m.shift];
}
inline Bitboard bishopAttacks(int s, Bitboard occ) {
    const BB::Magic& m = BB::BishopMagics[s];
    return m.attacks[((occ & m.mask) * m.magic) >> m.shift];
}
inline Bitboard queenAttacks(int s, Bitboard occ) {
    return rookAttacks(s, occ) | bishopAttacks(s, occ);
}
