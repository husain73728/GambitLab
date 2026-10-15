#include "bitboard.h"
#include "movegen.h"
#include "perft.h"
#include "position.h"
#include "search.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

static const char* START_FEN =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// Search runs on a worker thread so `stop` (and `quit`) can interrupt it.
std::thread searchThread;

static void waitSearch() {
    if (searchThread.joinable()) searchThread.join();
}

static void startSearch(Position pos, const SearchLimits& lim) {
    waitSearch();
    searchClear();
    searchThread = std::thread([pos, lim]() mutable {
        const Move best = searchPosition(pos, lim);
        printf("bestmove %s\n", best == MOVE_NONE ? "0000" : moveToStr(best).c_str());
        fflush(stdout);
    });
}

static void cmdPosition(Position& pos, std::istringstream& is) {
    std::string token;
    is >> token;

    std::string fen;
    if (token == "startpos") {
        fen = START_FEN;
        is >> token;
    } else if (token == "fen") {
        std::string part;
        for (int i = 0; i < 6 && (is >> part); ++i)
            fen += (i ? " " : "") + part;
        is >> token;
    } else {
        return;
    }

    pos.setFen(fen);

    if (token == "moves") {
        std::string mv;
        while (is >> mv) {
            const Move m = parseUciMove(pos, mv);
            if (m == MOVE_NONE) break;
            Undo u;
            pos.makeMove(m, u);
        }
    }
}

static void cmdGo(Position& pos, std::istringstream& is) {
    std::vector<std::string> tokens;
    std::string t;
    while (is >> t) tokens.push_back(t);

    if (!tokens.empty() && tokens[0] == "perft") {
        const int d = tokens.size() > 1 ? std::atoi(tokens[1].c_str()) : 1;
        auto start = std::chrono::steady_clock::now();
        const uint64_t n = perft(pos, d);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                      std::chrono::steady_clock::now() - start).count();
        printf("Nodes: %llu\n", static_cast<unsigned long long>(n));
        if (ms > 0)
            printf("Time: %lld ms (%.1f Mnps)\n", static_cast<long long>(ms),
                   static_cast<double>(n) / (static_cast<double>(ms) * 1000.0));
        return;
    }

    SearchLimits lim;
    for (size_t i = 0; i < tokens.size(); ++i) {
        const std::string& k = tokens[i];
        auto val = [&](long long def) -> long long {
            return (i + 1 < tokens.size()) ? std::stoll(tokens[++i]) : def;
        };
        if (k == "depth")           lim.depth = static_cast<int>(val(lim.depth));
        else if (k == "movetime")   lim.movetime = val(0);
        else if (k == "wtime")      lim.wtime = val(0);
        else if (k == "btime")      lim.btime = val(0);
        else if (k == "winc")       lim.winc = val(0);
        else if (k == "binc")       lim.binc = val(0);
        else if (k == "movestogo")  lim.movestogo = static_cast<int>(val(0));
        else if (k == "infinite")   lim.infinite = true;
    }

    startSearch(pos, lim);
}

static void cmdSetOption(std::istringstream& is) {
    std::string token, name, value;
    while (is >> token) {
        if (token == "name")       is >> name;
        else if (token == "value") is >> value;
    }
    if (name == "Hash" && !value.empty())
        searchSetHash(std::atoi(value.c_str()));
}

// Test utility: play a fixed number of plies against itself from the current
// position, verifying every move is legal.
static void cmdSelfPlay(Position& pos, std::istringstream& is) {
    int plies = 10;
    is >> plies;
    searchClear();
    for (int i = 0; i < plies; ++i) {
        MoveList list;
        generateLegal(pos, list);
        if (list.count == 0) {
            printf("gameover ply %d %s\n", i, pos.inCheck(pos.side) ? "checkmate" : "stalemate");
            break;
        }
        SearchLimits lim;
        lim.depth = 5;
        const Move m = searchPosition(pos, lim);
        if (m == MOVE_NONE) { printf("no move at ply %d\n", i); break; }
        printf("ply %d: %s\n", i + 1, moveToStr(m).c_str());
        Undo u;
        pos.makeMove(m, u);
    }
    printf("fen %s\n", pos.fen().c_str());
}

int main(int argc, char** argv) {
    BB::init();
    Zobrist::init();
    searchSetHash(16);

    if (argc > 1) {
        std::string a = argv[1];
        if (a == "perftsuite") return runPerftSuite() ? 0 : 1;
    }

    Position pos;
    pos.setFen(START_FEN);

    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream is(line);
        std::string cmd;
        is >> cmd;
        if (cmd.empty()) continue;

        if (cmd == "uci") {
            waitSearch();
            printf("id name xdsa 0.1\n");
            printf("id author xdsa\n");
            printf("option name Hash type spin default 16 min 1 max 4096\n");
            printf("uciok\n");
        } else if (cmd == "isready") {
            printf("readyok\n");
        } else if (cmd == "ucinewgame") {
            waitSearch();
            pos.setFen(START_FEN);
        } else if (cmd == "position") {
            waitSearch();
            cmdPosition(pos, is);
        } else if (cmd == "setoption") {
            waitSearch();
            cmdSetOption(is);
        } else if (cmd == "stop") {
            searchStop();
        } else if (cmd == "selfplay") {
            cmdSelfPlay(pos, is);
        } else if (cmd == "go") {
            cmdGo(pos, is);
        } else if (cmd == "d") {
            pos.print();
        } else if (cmd == "perftsuite") {
            runPerftSuite();
        } else if (cmd == "perft") {
            int d = 1;
            is >> d;
            printf("Nodes: %llu\n", static_cast<unsigned long long>(perft(pos, d)));
        } else if (cmd == "quit") {
            searchStop();
            waitSearch();
            break;
        }
        fflush(stdout);
    }
    waitSearch();
    return 0;
}
