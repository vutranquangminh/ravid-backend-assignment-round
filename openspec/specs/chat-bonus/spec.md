# chat-bonus Specification

## Purpose
TBD - created by archiving change s08-bonus-chat-continuation-sse. Update Purpose after archive.
## Requirements
### Requirement: Chat continuation by chat_id
The system SHALL let a user continue an existing conversation by supplying a `chat_id`, with prior turns informing the answer, scoped to that user.

#### Scenario: New conversation
- **WHEN** an authenticated user sends `POST /api/chat/query/` with no `chat_id`
- **THEN** a new conversation is created and the response includes its `chat_id` alongside `answer` and `tokens_consumed`
- **AND** the user's query and the assistant's answer are persisted to that conversation

#### Scenario: Continue an existing conversation
- **WHEN** the user sends a query WITH a `chat_id` they own
- **THEN** the conversation's recent history is included in the prompt and the new turn is appended to the same conversation

#### Scenario: Another user's chat_id
- **WHEN** a user supplies a `chat_id` that belongs to a different user (or does not exist)
- **THEN** the response is `404` (no existence leak)

### Requirement: SSE streaming of answers
The system SHALL stream chat answers in real time over Server-Sent Events.

#### Scenario: Streamed answer
- **WHEN** an authenticated user sends `POST /api/chat/stream/` with `{query}` (and optional `chat_id`)
- **THEN** the response has content type `text/event-stream` and emits incremental `data:` token events followed by a final event containing the `chat_id` and `tokens_consumed`, then a `[DONE]` marker
- **AND** after streaming completes, the turn is persisted and credits are decremented by the tokens consumed

#### Scenario: Streaming requires auth and a query
- **WHEN** `/api/chat/stream/` is called without a valid JWT
- **THEN** the response is `401`
- **WHEN** it is called with an empty query
- **THEN** the response is `400`

#### Scenario: Insufficient credits before streaming
- **WHEN** a user with a zero balance requests a stream
- **THEN** the response is `402` and no stream is started
