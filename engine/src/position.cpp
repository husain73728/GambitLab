#include "position.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <sstream>

// ---------------------------------------------------------------------------
// Zobrist keys
// ---------------------------------------------------------------------------

namespace Zobrist {
Key psq[PIECE_NB][64];
Key castling[16];
Key epFile[8];
Key side;

static uint64_t s = 0x9E3779B97F4A7C15ULL;
static uint64_t rnd() {
    s ^= s >> 12;
    s ^= s << 25;
    s ^= s >> 27;
    return s * 2685821657736338717ULL;
}

void init() {
    for (int p = 0; p < PIECE_NB; ++p)
        for (int sq = 0; sq < 64; ++sq) psq[p][sq] = rnd();
    for (int i = 0; i < 16; ++i) castling[i] = rnd();
    for (int i = 0; i < 8; ++i) epFile[i] = rnd();
    side = rnd();
}
} // namespace Zobrist

// ---------------------------------------------------------------------------
// Piece / move string helpers
// ---------------------------------------------------------------------------

std::string moveToStr(Move m) {
    std::string s = squareStr(moveFrom(m)) + squareStr(moveTo(m));
    if (isPromotion(m)) {
        switch (moveFlag(m)) {
            case PROMO_N: case PROMO_CAP_N: s += 'n'; break;
            case PROMO_B: case PROMO_CAP_B: s += 'b'; break;
            case PROMO_R: case PROMO_CAP_R: s += 'r'; break;
            default:                        s += 'q'; break;
        }
    }
    return s;
}

static char pieceChar(Piece p) {
    static const char* w = "PNBRQK";
    static const char* b = "pnbrqk";
    return (colorOf(p) == WHITE ? w : b)[typeOf(p)];
}

static int castleMask(int sq) {
    switch (sq) {
        case SQ_E1: return ~(WHITE_OO | WHITE_OOO) & ANY_CASTLING;
        case SQ_A1: return ~WHITE_OOO & ANY_CASTLING;
        case SQ_H1: return ~WHITE_OO & ANY_CASTLING;
        case SQ_E8: return ~(BLACK_OO | BLACK_OOO) & ANY_CASTLING;
        case SQ_A8: return ~BLACK_OOO & ANY_CASTLING;
        case SQ_H8: return ~BLACK_OO & ANY_CASTLING;
        default:    return ANY_CASTLING;
    }
}

// ---------------------------------------------------------------------------
// Piece-set primitives
// ---------------------------------------------------------------------------

void Position::putPiece(Piece p, int sq) {
    Bitboard b = 1ULL << sq;
    byColor[colorOf(p)] |= b;
    byType[typeOf(p)] |= b;
    board[sq] = p;
    key ^= Zobrist::psq[p][sq];
}

void Position::removePiece(int sq) {
    Piece p = board[sq];
    Bitboard b = 1ULL << sq;
    byColor[colorOf(p)] ^= b;
    byType[typeOf(p)] ^= b;
    board[sq] = NO_PIECE;
    key ^= Zobrist::psq[p][sq];
}

void Position::movePiece(Piece p, int from, int to) {
    removePiece(from);
    putPiece(p, to);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

void Position::clear() {
    for (int c = 0; c < COLOR_NB; ++c) byColor[c] = 0;
    for (int t = 0; t < PIECE_TYPE_NB; ++t) byType[t] = 0;
    for (int s = 0; s < 64; ++s) board[s] = NO_PIECE;
    side = WHITE;
    castling = 0;
    ep = -1;
    halfmove = 0;
    fullmove = 1;
    key = 0;
}

void Position::computeKey() {
    key = 0;
    for (int s = 0; s < 64; ++s)
        if (board[s] != NO_PIECE) key ^= Zobrist::psq[board[s]][s];
    key ^= Zobrist::castling[castling];
    if (ep != -1) key ^= Zobrist::epFile[fileOf(ep)];
    if (side == BLACK) key ^= Zobrist::side;
}

bool Position::setFen(const std::string& fen) {
    clear();

    std::istringstream ss(fen);
    std::string placement, stm, castle, epStr, half, full;
    if (!(ss >> placement)) return false;
    ss >> stm >> castle >> epStr;
    ss >> half >> full;

    int r = 7, f = 0;
    for (char c : placement) {
        if (c == '/') { --r; f = 0; }
        else if (std::isdigit(static_cast<unsigned char>(c))) f += c - '0';
        else {
            Piece p = NO_PIECE;
            switch (c) {
                case 'P': p = W_PAWN;   break;
                case 'N': p = W_KNIGHT; break;
                case 'B': p = W_BISHOP; break;
                case 'R': p = W_ROOK;   break;
                case 'Q': p = W_QUEEN;  break;
                case 'K': p = W_KING;   break;
                case 'p': p = B_PAWN;   break;
                case 'n': p = B_KNIGHT; break;
                case 'b': p = B_BISHOP; break;
                case 'r': p = B_ROOK;   break;
                case 'q': p = B_QUEEN;  break;
                case 'k': p = B_KING;   break;
                default: break;
            }
            if (p != NO_PIECE && r >= 0 && r < 8 && f >= 0 && f < 8)
                putPiece(p, makeSquare(f, r));
            ++f;
        }
    }

    side = (stm == "b") ? BLACK : WHITE;

    if (castle.find('K') != std::string::npos) castling |= WHITE_OO;
    if (castle.find('Q') != std::string::npos) castling |= WHITE_OOO;
    if (castle.find('k') != std::string::npos) castling |= BLACK_OO;
    if (castle.find('q') != std::string::npos) castling |= BLACK_OOO;

    if (!epStr.empty() && epStr != "-" && epStr.size() >= 2)
        ep = makeSquare(epStr[0] - 'a', epStr[1] - '1');

    halfmove = half.empty() ? 0 : std::atoi(half.c_str());
    fullmove = full.empty() ? 1 : std::atoi(full.c_str());

    key ^= Zobrist::castling[castling];
    if (ep != -1) key ^= Zobrist::epFile[fileOf(ep)];
    if (side == BLACK) key ^= Zobrist::side;
    return true;
}

std::string Position::fen() const {
    std::ostringstream ss;
    for (int r = 7; r >= 0; --r) {
        int empty = 0;
        for (int f = 0; f < 8; ++f) {
            Piece p = board[makeSquare(f, r)];
            if (p == NO_PIECE) { ++empty; continue; }
            if (empty) { ss << empty; empty = 0; }
            ss << pieceChar(p);
        }
        if (empty) ss << empty;
        if (r) ss << '/';
    }

    ss << (side == WHITE ? " w " : " b ");

    std::string cr;
    if (castling & WHITE_OO)  cr += 'K';
    if (castling & WHITE_OOO) cr += 'Q';
    if (castling & BLACK_OO)  cr += 'k';
    if (castling & BLACK_OOO) cr += 'q';
    ss << (cr.empty() ? "-" : cr) << ' ';

    if (ep == -1) ss << "- ";
    else ss << squareStr(ep) << ' ';

    ss << halfmove << ' ' << fullmove;
    return ss.str();
}

void Position::print() const {
    static const char* files = "  a b c d e f g h";
    printf("%s\n", files);
    for (int r = 7; r >= 0; --r) {
        printf("%d ", r + 1);
        for (int f = 0; f < 8; ++f) {
            Piece p = board[makeSquare(f, r)];
            printf("%c ", p == NO_PIECE ? '.' : pieceChar(p));
        }
        printf("%d\n", r + 1);
    }
    printf("%s\n", files);
    printf("FEN: %s\n", fen().c_str());
    printf("Key: %016llx\n", static_cast<unsigned long long>(key));
}

// ---------------------------------------------------------------------------
// Attack detection
// ---------------------------------------------------------------------------

bool Position::isAttacked(int sq, Color by) const {
    Bitboard occ = occupied();
    if (BB::PawnAttacks[~by][sq] & pieces(by, PAWN)) return true;
    if (BB::KnightAttacks[sq] & pieces(by, KNIGHT)) return true;
    if (BB::KingAttacks[sq] & pieces(by, KING)) return true;
    if (bishopAttacks(sq, occ) & (pieces(by, BISHOP) | pieces(by, QUEEN))) return true;
    if (rookAttacks(sq, occ) & (pieces(by, ROOK) | pieces(by, QUEEN))) return true;
    return false;
}

// ---------------------------------------------------------------------------
// Make / unmake
// ---------------------------------------------------------------------------

void Position::makeMove(Move m, Undo& u) {
    const int from = moveFrom(m), to = moveTo(m), flag = moveFlag(m);

    u.castling = castling;
    u.ep = ep;
    u.halfmove = halfmove;
    u.key = key;

    Piece pc = board[from];
    Piece captured = (flag == EP_CAPTURE) ? makePiece(~side, PAWN) : board[to];
    u.captured = captured;

    if (ep != -1) key ^= Zobrist::epFile[fileOf(ep)];

    if (typeOf(pc) == PAWN || captured != NO_PIECE) halfmove = 0;
    else ++halfmove;

    if (flag == EP_CAPTURE) {
        removePiece(to + (side == WHITE ? -8 : 8));
    } else if (captured != NO_PIECE) {
        removePiece(to);
    }

    removePiece(from);

    if (isPromotion(m)) {
        PieceType promo;
        switch (flag) {
            case PROMO_N: case PROMO_CAP_N: promo = KNIGHT; break;
            case PROMO_B: case PROMO_CAP_B: promo = BISHOP; break;
            case PROMO_R: case PROMO_CAP_R: promo = ROOK;   break;
            default:                        promo = QUEEN;  break;
        }
        putPiece(makePiece(side, promo), to);
    } else {
        putPiece(pc, to);
        if (flag == KING_CASTLE) {
            int rf = (side == WHITE) ? 7 : 63;
            int rt = (side == WHITE) ? 5 : 61;
            movePiece(makePiece(side, ROOK), rf, rt);
        } else if (flag == QUEEN_CASTLE) {
            int rf = (side == WHITE) ? 0 : 56;
            int rt = (side == WHITE) ? 3 : 59;
            movePiece(makePiece(side, ROOK), rf, rt);
        }
    }

    key ^= Zobrist::castling[castling];
    castling &= castleMask(from) & castleMask(to);
    key ^= Zobrist::castling[castling];

    ep = -1;
    if (flag == DOUBLE_PUSH) {
        ep = to + (side == WHITE ? -8 : 8);
        key ^= Zobrist::epFile[fileOf(ep)];
    }

    if (side == BLACK) ++fullmove;
    side = ~side;
    key ^= Zobrist::side;
}

void Position::unmakeMove(Move m, const Undo& u) {
    const int from = moveFrom(m), to = moveTo(m), flag = moveFlag(m);

    side = ~side;
    if (side == BLACK) --fullmove;

    Piece moved = board[to];
    removePiece(to);

    if (isPromotion(m)) {
        putPiece(makePiece(side, PAWN), from);
    } else {
        putPiece(moved, from);
        if (flag == KING_CASTLE) {
            int rf = (side == WHITE) ? 7 : 63;
            int rt = (side == WHITE) ? 5 : 61;
            movePiece(makePiece(side, ROOK), rt, rf);
        } else if (flag == QUEEN_CASTLE) {
            int rf = (side == WHITE) ? 0 : 56;
            int rt = (side == WHITE) ? 3 : 59;
            movePiece(makePiece(side, ROOK), rt, rf);
        }
    }

    if (flag == EP_CAPTURE) {
        putPiece(makePiece(~side, PAWN), to + (side == WHITE ? -8 : 8));
    } else if (u.captured != NO_PIECE) {
        putPiece(u.captured, to);
    }

    castling = u.castling;
    ep = u.ep;
    halfmove = u.halfmove;
    key = u.key;
}

void Position::makeNull(Undo& u) {
    u.castling = castling;
    u.ep = ep;
    u.halfmove = halfmove;
    u.captured = NO_PIECE;
    u.key = key;

    if (ep != -1) key ^= Zobrist::epFile[fileOf(ep)];
    ep = -1;
    side = ~side;
    key ^= Zobrist::side;
    ++halfmove;
}

void Position::unmakeNull(const Undo& u) {
    side = ~side;
    castling = u.castling;
    ep = u.ep;
    halfmove = u.halfmove;
    key = u.key;
}
