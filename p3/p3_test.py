"""
End-to-end tests for the P3
Designed and created by JAMI
EPS-UAM 2026
"""

import pytest
import httpx
import asyncio

BASE_URL = "http://localhost:8080"

# ── Test data ─────────────────────────────────────────────────────────────────
TEST_USER = {
    "username": "testuser",
    "password": "testpassword123",
    "email":    "testuser@example.com",
}

TEST_USER_2 = {
    "username": "testuser2",
    "password": "testpassword456",
    "email":    "testuser2@example.com",
}

TEST_BOOK = {
    "isbn":            "978-9-99-999999-9",
    "title":           "Test Book",
    "author":          "Test Author",
    "year":            2024,
    "publisher":       "Test Editorial",
    "available_stock": 5,
}


# ── Shared state across tests ─────────────────────────────────────────────────
state = {}


# ── Fixtures ──────────────────────────────────────────────────────────────────

#@pytest.fixture(scope="session")
#def event_loop():
#    """Single event loop shared across all session-scoped async tests."""
#    loop = asyncio.new_event_loop()
#    yield loop
#    loop.close()

#@pytest.fixture(scope="session")
#async def client():
#    """Async HTTP client for the full test session."""
#    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as c:
#        yield c


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def anyio_backend():
    """Define el backend asíncrono que usará AnyIO."""
    return "asyncio"


@pytest.fixture(scope="session")
async def client():
    """Async HTTP client for the full test session using AnyIO."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_1_register_user(client):
    """Step 1: Register a new user."""
    resp = await client.post("/auth/register", json=TEST_USER)
    # 201 Created, or 409 if re-running tests against a live stack
    assert resp.status_code in (201, 409), (
        f"Expected 201 or 409, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.anyio
async def test_2_login_user(client):
    """Step 2: Log in and obtain a session token."""
    resp = await client.post(
        "/auth/login",
        json={"username": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    body = resp.json()
    assert "token" in body, "Response does not contain a token"
    state["token"]   = body["token"]
    state["user_id"] = TEST_USER["username"]


@pytest.mark.anyio
async def test_3_create_book(client):
    """Step 3: Create a new book (requires valid token)."""
    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.post("/library/books", json=TEST_BOOK, headers=headers)
    # 201 Created, or 409 if re-running tests
    assert resp.status_code in (201, 409), (
        f"Expected 201 or 409, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.anyio
async def test_4_borrow_book(client):
    """Step 4: Borrow the newly created book."""
    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/borrow",
        headers=headers,
    )
    assert resp.status_code == 200, f"Borrow failed: {resp.text}"


@pytest.mark.anyio
async def test_5_list_active_loans(client):
    """Step 5: Verify the book appears in the user's active loans."""
    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.get(
        "/library/loans/active",
        headers=headers,
    )
    assert resp.status_code == 200, f"Active loans request failed: {resp.text}"
    books = resp.json()
    assert isinstance(books, list), "Expected a list of books"
    isbns = [b["isbn"] for b in books]
    assert TEST_BOOK["isbn"] in isbns, (
        f"Borrowed book {TEST_BOOK['isbn']} not found in active loans: {isbns}"
    )


@pytest.mark.anyio
async def test_6_return_book(client):
    """Step 6: Return the borrowed book."""
    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/return",
        headers=headers,
    )
    assert resp.status_code == 200, f"Return failed: {resp.text}"


@pytest.mark.anyio
async def test_7_active_loans_empty_after_return(client):
    """Step 7: Confirm the user has no active loans after returning the book."""
    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.get(
        "/library/loans/active",
        headers=headers,
    )
    assert resp.status_code == 200, f"Active loans request failed: {resp.text}"
    books = resp.json()
    assert isinstance(books, list), "Expected a list"
    isbns = [b["isbn"] for b in books]
    assert TEST_BOOK["isbn"] not in isbns, (
        f"Book {TEST_BOOK['isbn']} still appears in active loans after return: {isbns}"
    )


# ── Additional Security & Edge Case Tests ────────────────────────────────────

@pytest.mark.anyio
async def test_8_user_data_isolation(client):
    """Test that users can only see their own loan data, not other users' data."""
    # User 1 borrows a book
    headers_user1 = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/borrow",
        headers=headers_user1,
    )
    assert resp.status_code == 200, f"User 1 borrow failed: {resp.text}"

    # Register and login user 2
    resp = await client.post("/auth/register", json=TEST_USER_2)
    assert resp.status_code in (201, 409), f"User 2 registration failed: {resp.text}"

    resp = await client.post(
        "/auth/login",
        json={"username": TEST_USER_2["username"], "password": TEST_USER_2["password"]},
    )
    assert resp.status_code == 200, f"User 2 login failed: {resp.text}"
    user2_token = resp.json()["token"]
    headers_user2 = {"Authorization": f"Bearer {user2_token}"}

    # User 2 checks active loans - should NOT see user 1's loan
    resp = await client.get("/library/loans/active", headers=headers_user2)
    assert resp.status_code == 200, f"User 2 active loans request failed: {resp.text}"
    books = resp.json()
    assert isinstance(books, list), "Expected a list"
    # User 2 should have no active loans
    assert len(books) == 0, (
        f"User 2 should have no active loans, but got: {books}"
    )

    # User 2 checks loan history - should NOT see user 1's history
    resp = await client.get("/library/loans/history", headers=headers_user2)
    assert resp.status_code == 200, f"User 2 loan history request failed: {resp.text}"
    history = resp.json()
    assert isinstance(history, list), "Expected a list"
    # User 2 should have no loan history
    assert len(history) == 0, (
        f"User 2 should have no loan history, but got: {history}"
    )

    # User 1 returns the book to clean up
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/return",
        headers=headers_user1,
    )
    assert resp.status_code == 200, f"User 1 return failed: {resp.text}"


@pytest.mark.anyio
async def test_9_unauthorized_access_no_token(client):
    """Test that accessing protected endpoints without a token returns 401."""
    # Try to access library endpoint without Authorization header
    resp = await client.get("/library/books/out-of-stock")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.anyio
async def test_10_unauthorized_access_invalid_token(client):
    """Test that accessing protected endpoints with an invalid token returns 401."""
    headers = {"Authorization": "Bearer invalid-token-12345"}
    resp = await client.get("/library/books/out-of-stock", headers=headers)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.anyio
async def test_11_cannot_delete_book_with_active_loan(client):
    """Test that a book with an active loan cannot be deleted."""
    headers = {"Authorization": f"Bearer {state['token']}"}

    # Borrow the test book
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/borrow",
        headers=headers,
    )
    assert resp.status_code == 200, f"Borrow failed: {resp.text}"

    # Try to delete it while it's on loan
    resp = await client.delete(
        f"/library/books/{TEST_BOOK['isbn']}",
        headers=headers,
    )
    assert resp.status_code == 409, (
        f"Expected 409 when deleting book with active loan, got {resp.status_code}: {resp.text}"
    )

    # Return the book to clean up
    resp = await client.post(
        f"/library/books/{TEST_BOOK['isbn']}/return",
        headers=headers,
    )
    assert resp.status_code == 200, f"Return failed: {resp.text}"


@pytest.mark.anyio
async def test_12_stock_never_negative_concurrent_borrows(client):
    """Test that concurrent borrow requests never make stock negative."""
    # Create a new book with stock=1 for this test
    test_book_limited = {
        "isbn":            "978-1-11-111111-1",
        "title":           "Limited Stock Book",
        "author":          "Test Author",
        "year":            2024,
        "publisher":       "Test Editorial",
        "available_stock": 1,
    }

    headers = {"Authorization": f"Bearer {state['token']}"}
    resp = await client.post("/library/books", json=test_book_limited, headers=headers)
    # Accept 201 or 409 if book already exists from previous runs
    assert resp.status_code in (201, 409), f"Book creation failed: {resp.text}"

    # If book already exists, ensure it has stock=1 by returning any active loans
    if resp.status_code == 409:
        # Try to return it (might not have active loan, that's OK)
        await client.post(
            f"/library/books/{test_book_limited['isbn']}/return",
            headers=headers,
        )

    # Launch 5 concurrent borrow requests for a book with stock=1
    import asyncio
    borrow_tasks = [
        client.post(
            f"/library/books/{test_book_limited['isbn']}/borrow",
            headers=headers,
        )
        for _ in range(5)
    ]
    responses = await asyncio.gather(*borrow_tasks, return_exceptions=True)

    # Count successful borrows (status 200)
    success_count = sum(
        1 for r in responses
        if not isinstance(r, Exception) and r.status_code == 200
    )

    # Only 1 borrow should succeed
    assert success_count == 1, (
        f"Expected exactly 1 successful borrow, got {success_count}"
    )

    # Verify stock is now 0 (not negative)
    resp = await client.get(
        f"/library/books/{test_book_limited['isbn']}",
        headers=headers,
    )
    assert resp.status_code == 200, f"Failed to fetch book: {resp.text}"
    book_data = resp.json()
    assert book_data["available_stock"] == 0, (
        f"Expected stock=0, got {book_data['available_stock']}"
    )

    # Clean up: return the book
    await client.post(
        f"/library/books/{test_book_limited['isbn']}/return",
        headers=headers,
    )



# ── Logout tests ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_13_login_logout_invalidates_token(client):
    """Login, use the token, logout, and verify the token is no longer valid."""
    resp = await client.post(
        "/auth/login",
        json={"username": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    resp = await client.get("/library/books/out-of-stock", headers=headers)
    assert resp.status_code == 200, f"Token should be valid before logout: {resp.text}"

    resp = await client.post("/auth/logout", headers=headers)
    assert resp.status_code == 200, f"Logout failed: {resp.text}"

    resp = await client.get("/library/books/out-of-stock", headers=headers)
    assert resp.status_code == 401, (
        f"Token should be invalid after logout, got {resp.status_code}"
    )


@pytest.mark.anyio
async def test_14_logout_twice_fails(client):
    """A second logout with the same token must be rejected."""
    resp = await client.post(
        "/auth/login",
        json={"username": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert (await client.post("/auth/logout", headers=headers)).status_code == 200
    resp = await client.post("/auth/logout", headers=headers)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.anyio
async def test_15_logout_without_login_fails(client):
    """Logout without a token or with a never-issued token returns 401."""
    resp = await client.post("/auth/logout")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    headers = {"Authorization": "Bearer never-issued-token"}
    resp = await client.post("/auth/logout", headers=headers)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.anyio
async def test_16_logout_only_affects_own_session(client):
    """Logging out one session must not invalidate another session of the same user."""
    creds = {"username": TEST_USER["username"], "password": TEST_USER["password"]}
    h1 = {"Authorization": f"Bearer {(await client.post('/auth/login', json=creds)).json()['token']}"}
    h2 = {"Authorization": f"Bearer {(await client.post('/auth/login', json=creds)).json()['token']}"}
    assert (await client.post("/auth/logout", headers=h1)).status_code == 200
    resp = await client.get("/library/books/out-of-stock", headers=h2)
    assert resp.status_code == 200, f"Second session should remain valid: {resp.text}"
    await client.post("/auth/logout", headers=h2)
