#include "bitboard.h"

#include <vector>

namespace BB {

Bitboard PawnAttacks[COLOR_NB][64] = {};
Bitboard KnightAttacks[64] = {};
Bitboard KingAttacks[64] = {};
Magic RookMagics[64];
Magic BishopMagics[64];

// Fancy magic tables (sizes are the exact totals needed).
static Bitboard RookTable[102400];
static Bitboard BishopTable[5248];

// xorshift64 PRNG, fixed seed -> deterministic magic generation.
static uint64_t rngState = 0x2545F4914F6CDD1DULL;
static uint64_t nextRand() {
    rngState ^= rngState >> 12;
    rngState ^= rngState << 25;
    rngState ^= rngState >> 27;
    return rngState * 2685821657736338717ULL;
}

// Sliding attacks from `sq` in direction (df, dr), stopping at/after blockers.
static Bitboard rayAttacks(int sq, int df, int dr, Bitboard occ) {
    Bitboard att = 0;
    int f = fileOf(sq), r = rankOf(sq);
    for (int nf = f + df, nr = r + dr; nf >= 0 && nf < 8 && nr >= 0 && nr < 8; nf += df, nr += dr) {
        int t = nr * 8 + nf;
        att |= 1ULL << t;
        if (occ & (1ULL << t)) break;
    }
    return att;
}

// Relevant-occupancy mask: the ray minus the outermost square in each direction.
static Bitboard rayMask(int sq, int df, int dr) {
    Bitboard m = 0;
    int f = fileOf(sq), r = rankOf(sq);
    for (int nf = f + df, nr = r + dr; nf >= 0 && nf < 8 && nr >= 0 && nr < 8; nf += df, nr += dr) {
        int nf2 = nf + df, nr2 = nr + dr;
        if (!(nf2 >= 0 && nf2 < 8 && nr2 >= 0 && nr2 < 8)) break; // current square is the edge
        m |= 1ULL << (nr * 8 + nf);
    }
    return m;
}

static void initMagics(bool rook) {
    int dirs[4][2];
    if (rook) {
        dirs[0][0] = 1;  dirs[0][1] = 0;
        dirs[1][0] = -1; dirs[1][1] = 0;
        dirs[2][0] = 0;  dirs[2][1] = 1;
        dirs[3][0] = 0;  dirs[3][1] = -1;
    } else {
        dirs[0][0] = 1;  dirs[0][1] = 1;
        dirs[1][0] = 1;  dirs[1][1] = -1;
        dirs[2][0] = -1; dirs[2][1] = 1;
        dirs[3][0] = -1; dirs[3][1] = -1;
    }

    Magic* magics = rook ? RookMagics : BishopMagics;
    Bitboard* table = rook ? RookTable : BishopTable;

    for (int sq = 0; sq < 64; ++sq) {
        Bitboard mask = 0;
        for (auto& d : dirs) mask |= rayMask(sq, d[0], d[1]);
        int bits = popcount(mask);
        int size = 1 << bits;

        magics[sq].mask = mask;
        magics[sq].shift = 64 - bits;
        magics[sq].attacks = table;

        std::vector<Bitboard> occ(size), ref(size);
        Bitboard subset = 0;
        for (int i = 0; i < size; ++i) {
            occ[i] = subset;
            Bitboard a = 0;
            for (auto& d : dirs) a |= rayAttacks(sq, d[0], d[1], subset);
            ref[i] = a;
            subset = (subset - mask) & mask; // carry-rippler subset enumeration
        }

        for (;;) {
            Bitboard magic = nextRand() & nextRand() & nextRand();
            if (popcount((mask * magic) >> 56) < 6) continue; // poor spread, retry
            std::vector<Bitboard> used(size, 0);
            bool ok = true;
            for (int i = 0; i < size; ++i) {
                int idx = int((occ[i] * magic) >> (64 - bits));
                if (!used[idx]) used[idx] = ref[i];
                else if (used[idx] != ref[i]) { ok = false; break; }
            }
            if (ok) { magics[sq].magic = magic; break; }
        }

        for (int i = 0; i < size; ++i)
            table[int((occ[i] * magics[sq].magic) >> (64 - bits))] = ref[i];
        table += size;
    }
}

static const int KnightDeltas[8][2] = {
    {1, 2}, {2, 1}, {2, -1}, {1, -2}, {-1, -2}, {-2, -1}, {-2, 1}, {-1, 2}
};
static const int KingDeltas[8][2] = {
    {1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1}, {0, -1}, {1, -1}
};

void init() {
    for (int sq = 0; sq < 64; ++sq) {
        int f = fileOf(sq), r = rankOf(sq);

        for (auto& d : KnightDeltas) {
            int nf = f + d[0], nr = r + d[1];
            if (nf >= 0 && nf < 8 && nr >= 0 && nr < 8)
                KnightAttacks[sq] |= 1ULL << (nr * 8 + nf);
        }
        for (auto& d : KingDeltas) {
            int nf = f + d[0], nr = r + d[1];
            if (nf >= 0 && nf < 8 && nr >= 0 && nr < 8)
                KingAttacks[sq] |= 1ULL << (nr * 8 + nf);
        }

        if (r < 7) {
            if (f > 0) PawnAttacks[WHITE][sq] |= 1ULL << makeSquare(f - 1, r + 1);
            if (f < 7) PawnAttacks[WHITE][sq] |= 1ULL << makeSquare(f + 1, r + 1);
        }
        if (r > 0) {
            if (f > 0) PawnAttacks[BLACK][sq] |= 1ULL << makeSquare(f - 1, r - 1);
            if (f < 7) PawnAttacks[BLACK][sq] |= 1ULL << makeSquare(f + 1, r - 1);
        }
    }

    initMagics(true);
    initMagics(false);
}

} // namespace BB
