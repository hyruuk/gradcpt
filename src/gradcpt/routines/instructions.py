"""Welcome / instructions / debrief screens (PsychoPy)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from psychopy import visual
    from psychopy.hardware import keyboard


def show_text_then_wait(
    win: "visual.Window",
    kb: "keyboard.Keyboard",
    text: str,
    *,
    advance_keys: tuple[str, ...] = ("space", "return"),
) -> float:
    """Display ``text`` and block until any of ``advance_keys`` is pressed.

    Returns the global flip time at which the screen first appeared.
    """
    from psychopy import visual

    stim = visual.TextStim(win, text=text, color=(1, 1, 1), wrapWidth=1.5)
    stim.draw()
    onset = win.flip()
    kb.clearEvents()
    while True:
        keys = kb.getKeys(keyList=list(advance_keys), waitRelease=False, clear=True)
        if keys:
            return onset
        stim.draw()
        win.flip()


def welcome_screen(win, kb, dom_key: str, nondom_role: str = "no-go") -> float:
    msg = (
        "Welcome to GradCPT.\n\n"
        f"Press '{dom_key}' for CITY scenes (go).\n"
        f"Withhold your response for MOUNTAIN scenes ({nondom_role}).\n\n"
        "Press SPACE to continue."
    )
    return show_text_then_wait(win, kb, msg)


def block_start_screen(win, kb, dom_key: str, block_idx: int) -> float:
    msg = (
        f"Block {block_idx + 1}\n\n"
        f"Press '{dom_key}' for CITY scenes; withhold for MOUNTAIN.\n\n"
        "Press SPACE when ready."
    )
    return show_text_then_wait(win, kb, msg)


def block_rest_screen(win, kb, block_idx: int) -> float:
    msg = (
        f"End of block {block_idx + 1}.\n\n"
        "Take a short break.\n\n"
        "Press SPACE to continue."
    )
    return show_text_then_wait(win, kb, msg)


def debrief_screen(win, kb) -> float:
    msg = (
        "Thank you!\n\n"
        "The task is complete.\n\n"
        "Press SPACE to exit."
    )
    return show_text_then_wait(win, kb, msg)


def countdown_screen(
    win, seconds: int = 5, message_template: str = "The next images will appear in {n} seconds."
) -> None:
    """Block for ``seconds`` while displaying a countdown."""
    from psychopy import core, visual

    stim = visual.TextStim(win, text="", color=(1, 1, 1), wrapWidth=1.5)
    clock = core.Clock()
    clock.reset()
    while True:
        elapsed = clock.getTime()
        remaining = max(0, seconds - int(elapsed))
        if remaining <= 0:
            break
        stim.text = message_template.format(n=remaining)
        stim.draw()
        win.flip()
