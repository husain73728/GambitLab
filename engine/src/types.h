#pragma once

#include <cstdint>
#include <string>

// ---------------------------------------------------------------------------
// Basic chess types
// ---------------------------------------------------------------------------

using Bitboard = uint64_t;
using Key = uint64_t;

enum Color { WHITE, BLACK, COLOR_NB };

enum PieceType { PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, PIECE_TYPE_NB };

enum Piece {
    W_PAWN, W_KNIGHT, W_BISHOP, W_ROOK, W_QUEEN, W_KING,
    B_PAWN = 6, B_KNIGHT, B_BISHOP, B_ROOK, B_QUEEN, B_KING,
    NO_PIECE = 12, PIECE_NB
};

constexpr Color operator~(Color c) { return Color(c ^ 1); }

constexpr Piece makePiece(Color c, PieceType pt) { return Piece(c * 6 + pt); }
constexpr PieceType typeOf(Piece p) { return p == NO_PIECE ? PIECE_TYPE_NB : PieceType(p % 6); }
constexpr Color colorOf(Piece p) { return Color(p / 6); }

// Square / file / rank (A1 = 0, H8 = 63)
constexpr int fileOf(int s) { return s & 7; }
constexpr int rankOf(int s) { return s >> 3; }
constexpr int makeSquare(int f, int r) { return r * 8 + f; }

constexpr int SQ_A1 = 0, SQ_E1 = 4, SQ_H1 = 7, SQ_A8 = 56, SQ_E8 = 60, SQ_H8 = 63;

// Castling rights bitmask
enum { WHITE_OO = 1, WHITE_OOO = 2, BLACK_OO = 4, BLACK_OOO = 8, ANY_CASTLING = 15 };

// ---------------------------------------------------------------------------
// Move encoding: 16 bits [flag:4][from:6][to:6]
// ---------------------------------------------------------------------------

enum MoveFlag : int {
    QUIET = 0, DOUBLE_PUSH = 1, KING_CASTLE = 2, QUEEN_CASTLE = 3,
    CAPTURE = 4, EP_CAPTURE = 5,
    PROMO_N = 8, PROMO_B = 9, PROMO_R = 10, PROMO_Q = 11,
    PROMO_CAP_N = 12, PROMO_CAP_B = 13, PROMO_CAP_R = 14, PROMO_CAP_Q = 15
};

using Move = uint16_t;
constexpr Move MOVE_NONE = 0;

constexpr Move encodeMove(int from, int to, int flag) {
    return Move((flag << 12) | (from << 6) | to);
}
constexpr int moveFrom(Move m) { return (m >> 6) & 0x3F; }
constexpr int moveTo(Move m) { return m & 0x3F; }
constexpr int moveFlag(Move m) { return (m >> 12) & 0xF; }
constexpr bool isPromotion(Move m) { return (moveFlag(m) & 8) != 0; }
constexpr bool isCapture(Move m) { return (moveFlag(m) & 4) != 0; }

// Human-readable square, e.g. 0 -> "a1"
inline std::string squareStr(int s) {
    return std::string{char('a' + fileOf(s)), char('1' + rankOf(s))};
}

// UCI move string, e.g. e2e4 or e7e8q
std::string moveToStr(Move m);
