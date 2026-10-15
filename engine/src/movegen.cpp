#include "movegen.h"

static void addPromotions(MoveList& list, int from, int to, bool capture) {
    int base = capture ? PROMO_CAP_N : PROMO_N;
    list.add(encodeMove(from, to, base + 0)); // knight
    list.add(encodeMove(from, to, base + 1)); // bishop
    list.add(encodeMove(from, to, base + 2)); // rook
    list.add(encodeMove(from, to, base + 3)); // queen
}

static void generateCastling(const Position& pos, MoveList& list) {
    Color us = pos.side;
    Bitboard occ = pos.occupied();

    if (us == WHITE) {
        if ((pos.castling & WHITE_OO) && !(occ & ((1ULL << 5) | (1ULL << 6)))
            && !pos.isAttacked(SQ_E1, BLACK) && !pos.isAttacked(5, BLACK) && !pos.isAttacked(6, BLACK))
            list.add(encodeMove(SQ_E1, 6, KING_CASTLE));
        if ((pos.castling & WHITE_OOO) && !(occ & ((1ULL << 1) | (1ULL << 2) | (1ULL << 3)))
            && !pos.isAttacked(SQ_E1, BLACK) && !pos.isAttacked(3, BLACK) && !pos.isAttacked(2, BLACK))
            list.add(encodeMove(SQ_E1, 2, QUEEN_CASTLE));
    } else {
        if ((pos.castling & BLACK_OO) && !(occ & ((1ULL << 61) | (1ULL << 62)))
            && !pos.isAttacked(SQ_E8, WHITE) && !pos.isAttacked(61, WHITE) && !pos.isAttacked(62, WHITE))
            list.add(encodeMove(SQ_E8, 62, KING_CASTLE));
        if ((pos.castling & BLACK_OOO) && !(occ & ((1ULL << 57) | (1ULL << 58) | (1ULL << 59)))
            && !pos.isAttacked(SQ_E8, WHITE) && !pos.isAttacked(59, WHITE) && !pos.isAttacked(58, WHITE))
            list.add(encodeMove(SQ_E8, 58, QUEEN_CASTLE));
    }
}

void generateMoves(const Position& pos, MoveList& list, bool capturesOnly) {
    const Color us = pos.side, them = ~us;
    const Bitboard occ = pos.occupied();
    const Bitboard enemy = pos.byColor[them];
    const Bitboard targets = capturesOnly ? enemy : ~pos.byColor[us];
    const Bitboard empty = ~occ;

    const int up = (us == WHITE) ? 8 : -8;
    const int startRank = (us == WHITE) ? 1 : 6;
    const int promoRank = (us == WHITE) ? 6 : 1;

    // Pawns
    Bitboard pawns = pos.pieces(us, PAWN);
    while (pawns) {
        const int from = lsb(pawns);
        popLsb(pawns);
        const int r = rankOf(from);

        if (!capturesOnly) {
            const int to = from + up;
            if (empty & (1ULL << to)) {
                if (r == promoRank) {
                    addPromotions(list, from, to, false);
                } else {
                    list.add(encodeMove(from, to, QUIET));
                    if (r == startRank && (empty & (1ULL << (to + up))))
                        list.add(encodeMove(from, to + up, DOUBLE_PUSH));
                }
            }
        }

        Bitboard att = BB::PawnAttacks[us][from] & enemy;
        while (att) {
            const int to = lsb(att);
            popLsb(att);
            if (r == promoRank) addPromotions(list, from, to, true);
            else list.add(encodeMove(from, to, CAPTURE));
        }

        if (pos.ep != -1 && (BB::PawnAttacks[us][from] & (1ULL << pos.ep)))
            list.add(encodeMove(from, pos.ep, EP_CAPTURE));
    }

    // Knights
    Bitboard b = pos.pieces(us, KNIGHT);
    while (b) {
        const int from = lsb(b);
        popLsb(b);
        Bitboard att = BB::KnightAttacks[from] & targets;
        while (att) {
            const int to = lsb(att);
            popLsb(att);
            list.add(encodeMove(from, to, (enemy & (1ULL << to)) ? CAPTURE : QUIET));
        }
    }

    // Sliders
    auto genSlider = [&](PieceType pt, Bitboard (*attackFn)(int, Bitboard)) {
        Bitboard s = pos.pieces(us, pt);
        while (s) {
            const int from = lsb(s);
            popLsb(s);
            Bitboard att = attackFn(from, occ) & targets;
            while (att) {
                const int to = lsb(att);
                popLsb(att);
                list.add(encodeMove(from, to, (enemy & (1ULL << to)) ? CAPTURE : QUIET));
            }
        }
    };
    genSlider(BISHOP, bishopAttacks);
    genSlider(ROOK, rookAttacks);
    genSlider(QUEEN, queenAttacks);

    // King
    const int ks = pos.kingSq(us);
    {
        Bitboard att = BB::KingAttacks[ks] & targets;
        while (att) {
            const int to = lsb(att);
            popLsb(att);
            list.add(encodeMove(ks, to, (enemy & (1ULL << to)) ? CAPTURE : QUIET));
        }
    }

    if (!capturesOnly) generateCastling(pos, list);
}

void generateLegal(const Position& pos, MoveList& list, bool capturesOnly) {
    MoveList pseudo;
    generateMoves(pos, pseudo, capturesOnly);

    Position& p = const_cast<Position&>(pos);
    for (int i = 0; i < pseudo.count; ++i) {
        const Move m = pseudo.moves[i];
        Undo u;
        p.makeMove(m, u);
        if (!p.inCheck(~p.side)) list.add(m);
        p.unmakeMove(m, u);
    }
}

Move parseUciMove(Position& pos, const std::string& str) {
    MoveList list;
    generateMoves(pos, list);
    for (int i = 0; i < list.count; ++i) {
        const Move m = list.moves[i];
        if (moveToStr(m) != str) continue;
        Undo u;
        pos.makeMove(m, u);
        const bool legal = !pos.inCheck(~pos.side);
        pos.unmakeMove(m, u);
        if (legal) return m;
    }
    return MOVE_NONE;
}
