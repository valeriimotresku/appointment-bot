import asyncio


_pending_codes: dict[
    str,
    tuple[asyncio.Future[str], asyncio.AbstractEventLoop]
] = {}


def register_code_waiter(email: str) -> asyncio.Future[str]:
    email = email.lower()

    loop = asyncio.get_running_loop()
    future = loop.create_future()

    _pending_codes[email] = (future, loop)

    print(f"[WAITER] registered: {email}, future={future}")

    return future


def deliver_code(email: str, code: str) -> bool:
    email = email.lower()

    print(f"[WAITER] delivering: {email}, code={code}")
    print(f"[WAITER] available: {list(_pending_codes.keys())}")

    pending = _pending_codes.get(email)

    if pending is None:
        print("[WAITER] no waiter found")
        return False

    future, loop = pending

    if future.done():
        print("[WAITER] future already done")
        return False

    # Safe even if a future deployment calls this from another thread.
    # Re-check done() inside the owner loop to avoid a timeout/set_result race.
    def set_result_if_pending() -> None:
        if not future.done():
            future.set_result(code)

    loop.call_soon_threadsafe(set_result_if_pending)

    print("[WAITER] code scheduled for delivery")

    return True


async def wait_for_code(
    email: str,
    future: asyncio.Future[str],
    timeout: int = 120,
) -> str | None:
    try:
        print(f"[WAITER] waiting for code: {email}")

        code = await asyncio.wait_for(
            future,
            timeout=timeout,
        )

        print(f"[WAITER] received: {email}, code={code}")

        return code

    except asyncio.TimeoutError:
        print(f"[WAITER] timeout: {email}")
        return None

    finally:
        _pending_codes.pop(email.lower(), None)
        print(f"[WAITER] removed: {email}")