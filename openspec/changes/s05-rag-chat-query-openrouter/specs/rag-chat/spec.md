# Spec delta — rag-chat

## ADDED Requirements

### Requirement: Grounded chat answer
The system SHALL answer a user's question using only that user's own indexed documents and return the answer with the tokens consumed.

#### Scenario: Successful grounded answer
- **WHEN** an authenticated user with indexed documents sends `POST /api/chat/query/` with `{ "query": "..." }`
- **THEN** the system retrieves the top-k chunks from the caller's collection, generates an answer via the LLM, and responds `200` with `{ "answer": "<text>", "tokens_consumed": <int> }`
- **AND** `tokens_consumed` is taken from the LLM `usage`, not estimated

#### Scenario: Answers are isolated per user
- **WHEN** user A asks a question
- **THEN** only user A's document chunks are used as context — user B's documents are never retrieved or referenced

### Requirement: No-context guard
When no relevant context exists, the system SHALL NOT fabricate an answer or charge the user.

#### Scenario: Empty knowledge base
- **WHEN** a user with no indexed documents (or no relevant chunks) sends a query
- **THEN** the response is `200` with a message indicating there isn't enough information in their documents and `tokens_consumed` is `0`
- **AND** no LLM call is made and no credits are charged

### Requirement: Credit consumption
The system SHALL maintain a per-user credit balance and decrement it by the tokens consumed per chat.

#### Scenario: Credits decremented
- **WHEN** a chat successfully consumes N tokens
- **THEN** the user's credit balance decreases by N (floored at zero)

#### Scenario: Insufficient credits
- **WHEN** a user with a zero balance sends a chat query
- **THEN** the response is `402` with body `{ "error": "<message>" }` and no LLM call is made

### Requirement: Input validation and auth
The chat endpoint SHALL require authentication and a non-empty query.

#### Scenario: Missing or empty query
- **WHEN** the body has no `query` or an empty/whitespace query
- **THEN** the response is `400` with body `{ "error": "<message>" }`

#### Scenario: Unauthenticated request
- **WHEN** `POST /api/chat/query/` is called without a valid JWT
- **THEN** the response is `401` with body `{ "error": "<message>" }`
