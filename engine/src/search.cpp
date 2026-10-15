#include "search.h"

#include "eval.h"
#include "movegen.h"
#include "tt.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>

namespace {

constexpr int MAX_PLY    = 128;
constexpr int MATE       = 30000;
constexpr int INF        = 32000;
constexpr int MATE_SCORE = MATE - MAX_PLY;

TranspositionTable TT;

Move  killers[MAX_PLY][2];
int   history[2][64][64];
Move  pvTable[MAX_PLY][MAX_PLY];
int   pvLength[MAX_PLY];

std::atomic<bool> stopRequested{false};
uint64_t nodes = 0;
long long startTime = 0;
long long timeLimit = 0;
bool timeSet = false;

const int PieceValue[PIECE_TYPE_NB] = {100, 320, 330, 500, 900, 20000};

long long nowMs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now().time_since_epoch()).count();
}

void checkTime() {
    if (timeSet && nowMs() - startTime >= timeLimit) stopRequested = true;
}

int scoreMove(const Position& pos, Move m, Move ttMove, int ply) {
    if (m == ttMove) return 2'000'000;

    const int from = moveFrom(m), to = moveTo(m);
    if (isCapture(m)) {
        const PieceType victim = (moveFlag(m) == EP_CAPTURE) ? PAWN : typeOf(pos.board[to]);
        const PieceType attacker = typeOf(pos.board[from]);
        return 1'000'000 + PieceValue[victim] * 10 - PieceValue[attacker];
    }
    if (isPromotion(m)) return 900'000 + (moveFlag(m) & 3);

    if (m == killers[ply][0]) return 800'000;
    if (m == killers[ply][1]) return 799'000;

    return history[pos.side][from][to];
}

int qsearch(Position& pos, int alpha, int beta, int ply) {
    ++nodes;
    if ((nodes & 2047) == 0) checkTime();
    if (stopRequested) return 0;
    if (ply >= MAX_PLY) return evaluate(pos);

    const int standPat = evaluate(pos);
    if (standPat >= beta) return beta;
    if (standPat > alpha) alpha = standPat;

    MoveList list;
    generateLegal(pos, list, /*capturesOnly=*/true);

    int scores[256];
    for (int i = 0; i < list.count; ++i) scores[i] = scoreMove(pos, list.moves[i], MOVE_NONE, ply);

    for (int i = 0; i < list.count; ++i) {
        for (int j = i + 1; j < list.count; ++j)
            if (scores[j] > scores[i]) { std::swap(scores[j], scores[i]); std::swap(list.moves[j], list.moves[i]); }

        const Move m = list.moves[i];
        Undo u;
        pos.makeMove(m, u);
        const int score = -qsearch(pos, -beta, -alpha, ply + 1);
        pos.unmakeMove(m, u);

        if (score >= beta) return beta;
        if (score > alpha) alpha = score;
    }
    return alpha;
}

int search(Position& pos, int depth, int alpha, int beta, int ply, bool pvNode) {
    pvLength[ply] = ply;

    if (depth <= 0) return qsearch(pos, alpha, beta, ply);

    ++nodes;
    if ((nodes & 2047) == 0) checkTime();
    if (stopRequested) return 0;
    if (ply >= MAX_PLY - 1) return evaluate(pos);

    const bool inCheck = pos.inCheck(pos.side);

    // Draw by fifty-move rule.
    if (pos.halfmove >= 100 && (!inCheck || ply > 0)) return 0;

    // Mate-distance pruning.
    alpha = std::max(alpha, -MATE + ply);
    beta  = std::min(beta, MATE - ply - 1);
    if (alpha >= beta) return alpha;

    // Transposition table probe.
    Move ttMove = MOVE_NONE;
    if (TTEntry* e = TT.probe(pos.key)) {
        ttMove = static_cast<Move>(e->move);
        if (e->depth >= depth && !pvNode) {
            int s = e->score;
            if (s >= MATE_SCORE) s -= ply;
            else if (s <= -MATE_SCORE) s += ply;
            if (e->flag == BOUND_EXACT) return s;
            if (e->flag == BOUND_LOWER && s >= beta) return s;
            if (e->flag == BOUND_UPPER && s <= alpha) return s;
        }
    }

    // Null-move pruning.
    const Bitboard nonPawnMat = pos.pieces(pos.side, KNIGHT) | pos.pieces(pos.side, BISHOP)
                              | pos.pieces(pos.side, ROOK)   | pos.pieces(pos.side, QUEEN);
    if (!pvNode && !inCheck && depth >= 3 && nonPawnMat) {
        Undo u;
        pos.makeNull(u);
        const int R = 2 + depth / 4;
        const int score = -search(pos, depth - 1 - R, -beta, -beta + 1, ply + 1, false);
        pos.unmakeNull(u);
        if (stopRequested) return 0;
        if (score >= beta) return beta;
    }

    MoveList list;
    generateLegal(pos, list);
    if (list.count == 0)
        return inCheck ? -MATE + ply : 0;

    int scores[256];
    for (int i = 0; i < list.count; ++i) scores[i] = scoreMove(pos, list.moves[i], ttMove, ply);

    const int origAlpha = alpha;
    int bestScore = -INF;
    Move bestMove = MOVE_NONE;

    for (int i = 0; i < list.count; ++i) {
        for (int j = i + 1; j < list.count; ++j)
            if (scores[j] > scores[i]) { std::swap(scores[j], scores[i]); std::swap(list.moves[j], list.moves[i]); }

        const Move m = list.moves[i];
        int newDepth = depth - 1;
        if (inCheck) ++newDepth; // check extension

        Undo u;
        pos.makeMove(m, u);

        int score;
        if (i == 0) {
            score = -search(pos, newDepth, -beta, -alpha, ply + 1, pvNode);
        } else {
            int R = 0;
            if (depth >= 3 && i >= 4 && !isCapture(m) && !isPromotion(m)) {
                R = 1 + (i >= 8) + (depth >= 6);
                R = std::min(R, std::max(0, newDepth - 1));
            }
            score = -search(pos, newDepth - R, -alpha - 1, -alpha, ply + 1, false);
            if (score > alpha && R > 0)
                score = -search(pos, newDepth, -alpha - 1, -alpha, ply + 1, false);
            if (score > alpha && score < beta)
                score = -search(pos, newDepth, -beta, -alpha, ply + 1, pvNode);
        }

        pos.unmakeMove(m, u);
        if (stopRequested) return 0;

        if (score > bestScore) { bestScore = score; bestMove = m; }

        if (score > alpha) {
            alpha = score;
            if (pvNode) {
                pvTable[ply][ply] = m;
                for (int k = ply + 1; k < pvLength[ply + 1]; ++k)
                    pvTable[ply][k] = pvTable[ply + 1][k];
                pvLength[ply] = pvLength[ply + 1];
            }
        }

        if (alpha >= beta) {
            if (!isCapture(m)) {
                if (killers[ply][0] != m) {
                    killers[ply][1] = killers[ply][0];
                    killers[ply][0] = m;
                }
                const int from = moveFrom(m), to = moveTo(m);
                history[pos.side][from][to] += depth * depth;
                if (history[pos.side][from][to] > 500'000) history[pos.side][from][to] /= 2;
            }
            break;
        }
    }

    const int flag = (bestScore >= beta) ? BOUND_LOWER
                   : (bestScore > origAlpha) ? BOUND_EXACT : BOUND_UPPER;
    int storeScore = bestScore;
    if (storeScore >= MATE_SCORE) storeScore += ply;
    else if (storeScore <= -MATE_SCORE) storeScore -= ply;
    TT.store(pos.key, depth, storeScore, bestMove, flag);

    return bestScore;
}

void printInfo(int depth, int score) {
    auto elapsed = nowMs() - startTime;
    printf("info depth %d ", depth);
    if (score >= MATE_SCORE)        printf("score mate %d ", (MATE - score + 1) / 2);
    else if (score <= -MATE_SCORE)  printf("score mate %d ", -(MATE + score + 1) / 2);
    else                            printf("score cp %d ", score);
    printf("nodes %llu nps %llu time %lld pv",
           static_cast<unsigned long long>(nodes),
           static_cast<unsigned long long>(elapsed > 0 ? nodes * 1000 / elapsed : 0),
           static_cast<long long>(elapsed));
    for (int i = 0; i < pvLength[0]; ++i)
        printf(" %s", moveToStr(pvTable[0][i]).c_str());
    printf("\n");
    fflush(stdout);
}

} // namespace

void searchSetHash(int megabytes) {
    TT.resize(static_cast<size_t>(std::max(1, megabytes)));
}

void searchStop() {
    stopRequested = true;
}

void searchClear() {
    stopRequested = false;
}

Move searchPosition(Position& pos, const SearchLimits& limits) {
    nodes = 0;
    std::memset(killers, 0, sizeof(killers));
    std::memset(pvTable, 0, sizeof(pvTable));
    std::memset(pvLength, 0, sizeof(pvLength));
    for (auto& color : history)
        for (auto& from : color)
            for (int& v : from) v /= 4; // decay history between searches

    startTime = nowMs();
    timeSet = false;
    if (!limits.infinite) {
        if (limits.movetime > 0) {
            timeLimit = std::max<long long>(1, limits.movetime - 20);
            timeSet = true;
        } else if (limits.wtime || limits.btime) {
            const long long myTime = (pos.side == WHITE) ? limits.wtime : limits.btime;
            const long long inc    = (pos.side == WHITE) ? limits.winc : limits.binc;
            const long long mtg    = limits.movestogo > 0 ? limits.movestogo : 30;
            long long alloc = myTime / mtg + inc / 2;
            alloc = std::min(alloc, myTime / 2);
            timeLimit = std::max<long long>(1, alloc - 20);
            timeSet = true;
        }
    }

    Move best = MOVE_NONE;
    int lastScore = 0;

    for (int depth = 1; depth <= limits.depth; ++depth) {
        int alpha = -INF, beta = INF;
        if (depth >= 4) { alpha = lastScore - 25; beta = lastScore + 25; }

        int score;
        for (;;) {
            score = search(pos, depth, alpha, beta, 0, true);
            if (stopRequested) break;
            if (score <= alpha) { alpha = std::max(-INF, score - 60); continue; }
            if (score >= beta)  { beta  = std::min(INF, score + 60); continue; }
            break;
        }
        if (stopRequested) break;

        lastScore = score;
        if (pvLength[0] > 0) best = pvTable[0][0];
        printInfo(depth, score);

        if (timeSet && nowMs() - startTime > timeLimit * 3 / 5) break; // don't start a slow next iteration
    }

    if (best == MOVE_NONE) {
        MoveList list;
        generateLegal(pos, list);
        if (list.count > 0) best = list.moves[0];
    }
    return best;
}
