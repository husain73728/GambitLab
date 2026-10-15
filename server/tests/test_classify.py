"""Classification, perspective and mate handling."""
from app.analysis.classify import (
    accuracy_from_winpct,
    classify,
    effective_cp,
    pv_to_san,
    win_percent,
)


def test_effective_cp_perspective():
    # +100 for white to move is +100 for the mover; from black's view it is -100.
    assert effective_cp(100, None, True) == 100
    assert effective_cp(100, None, False) == -100


def test_mate_dominates_and_perspective():
    assert effective_cp(None, 3, True) == 1000      # white mates -> +win for white mover
    assert effective_cp(None, 3, False) == -1000    # white mates -> bad for black mover
    assert effective_cp(None, -2, False) == 1000    # black mates -> good for black mover


def test_best_move_is_best():
    a = classify(before_cp=20, before_mate=None, after_cp=15, after_mate=None,
                 mover_is_white=True, played_uci="e2e4", best_uci="e2e4")
    assert a.classification == "best"
    assert a.cp_loss <= 10


def test_blunder_threshold_and_loss():
    a = classify(before_cp=30, before_mate=None, after_cp=-300, after_mate=None,
                 mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert a.classification == "blunder"
    assert a.cp_loss == 330


def test_inaccuracy_and_mistake_boundaries():
    inc = classify(before_cp=0, before_mate=None, after_cp=-80, after_mate=None,
                   mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert inc.classification == "inaccuracy"
    mis = classify(before_cp=0, before_mate=None, after_cp=-150, after_mate=None,
                   mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert mis.classification == "mistake"


def test_missed_mate_detected_only_when_mate_lost():
    missed = classify(before_cp=None, before_mate=2, after_cp=200, after_mate=None,
                      mover_is_white=True, played_uci="a2a3", best_uci="d1h5",
                      depth=20)
    assert missed.classification == "missed_mate"
    assert missed.missed_mate

    kept = classify(before_cp=None, before_mate=2, after_cp=None, after_mate=1,
                    mover_is_white=True, played_uci="d1h5", best_uci="d1h5")
    assert not kept.missed_mate


def test_missed_win_requires_losing_a_won_game():
    a = classify(before_cp=600, before_mate=None, after_cp=20, after_mate=None,
                 mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert a.missed_win
    assert a.classification == "missed_win"


def test_no_false_missed_win_when_still_winning():
    a = classify(before_cp=600, before_mate=None, after_cp=350, after_mate=None,
                 mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert not a.missed_win


def test_forced_move():
    a = classify(before_cp=0, before_mate=None, after_cp=0, after_mate=None,
                 mover_is_white=True, played_uci="a1a2", best_uci="a1a2", only_move=True)
    assert a.classification == "forced"


def test_book_only_swallows_small_losses():
    small = classify(before_cp=10, before_mate=None, after_cp=-20, after_mate=None,
                     mover_is_white=True, played_uci="e2e4", best_uci="d2d4",
                     book=True, depth=20)
    assert small.classification == "book"
    big = classify(before_cp=10, before_mate=None, after_cp=-400, after_mate=None,
                   mover_is_white=True, played_uci="e2e4", best_uci="d2d4",
                   book=True, depth=20)
    assert big.classification == "blunder"  # a blunder in the opening is not "book"


def test_provisional_when_shallow():
    a = classify(before_cp=0, before_mate=None, after_cp=-300, after_mate=None,
                 mover_is_white=True, played_uci="a2a3", best_uci="e2e4", depth=8)
    assert a.provisional


def test_no_blunder_when_already_lost():
    # already lost, still lost: severity is downgraded
    a = classify(before_cp=-900, before_mate=None, after_cp=-950, after_mate=None,
                 mover_is_white=True, played_uci="a2a3", best_uci="e2e4")
    assert a.classification in ("good", "excellent", "inaccuracy", "best")


def test_win_percent_and_accuracy_monotonic():
    assert win_percent(0) == 50
    assert win_percent(1000) > win_percent(100) > 50
    assert 0 <= accuracy_from_winpct(50, 10) <= 100


def test_pv_to_san_handles_illegal_and_empty():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert "e4" in pv_to_san(fen, ["e2e4", "e7e5"])
    assert pv_to_san(fen, ["zzzz"]) == ""
    assert pv_to_san(fen, []) == ""
