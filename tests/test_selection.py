from service_validation.selection import MAX_BATCH_SIZE, BatchSelection


def test_page_selection_selects_up_to_500_without_ctrl_clicks() -> None:
    state = BatchSelection(total=1_237)

    state.select_page()

    assert len(state.selected) == MAX_BATCH_SIZE
    assert min(state.selected) == 0
    assert max(state.selected) == 499
    assert state.page_count == 3


def test_moving_to_next_page_exposes_next_500_and_clears_selection() -> None:
    state = BatchSelection(total=1_237)
    state.select_page()

    state.move(1)
    state.select_page()

    assert len(state.selected) == MAX_BATCH_SIZE
    assert min(state.selected) == 500
    assert max(state.selected) == 999


def test_last_page_selects_all_remaining_records() -> None:
    state = BatchSelection(total=1_237)

    state.move(2)
    state.select_page()

    assert len(state.selected) == 237
    assert min(state.selected) == 1_000
    assert max(state.selected) == 1_236


def test_toggle_never_allows_more_than_500_records() -> None:
    state = BatchSelection(total=501)
    state.select_page()

    assert not state.toggle(500)
    assert len(state.selected) == MAX_BATCH_SIZE
