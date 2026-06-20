# Glossary

## Core Terms

### Document

A private file uploaded by an authenticated user to build their personal knowledge base.
Allowed types are PDF, TXT, and Markdown, up to 10 MB. Every document is owned by exactly one user.

### Chunk

A contextual slice of a document's extracted text produced by the chunking step. The system
uses LangChain's `RecursiveCharacterTextSplitter` with `chunk_size = 1000` and
`chunk_overlap = 150`. Chunks are the unit that gets embedded and retrieved.

### Embedding

A fixed-length numeric vector representing the meaning of a chunk, computed by an embedding
model. This project uses the local HuggingFace `all-MiniLM-L6-v2` model, producing 384-dimensional
vectors. Embeddings enable semantic similarity search.

### Vector Store

The database that stores embeddings and supports similarity search. This project uses Chroma.

### Collection

A named partition inside the vector store. This project maintains one collection per user,
named `user_{user_id}`, which is how per-user vector isolation is enforced.

### Namespace

The logical boundary that keeps one user's vectors separate from another's. In this project the
namespace is realized as the per-user Chroma collection `user_{user_id}`. The brief refers to
storing chunks "inside an isolated namespace linked to the uploading user's user_id."

### Retrieval

The step that searches a user's collection for the chunks most semantically similar to a query.
Retrieval is always scoped to the authenticated user's collection.

### Top-K

The number of most-similar chunks retrieval returns for a query. This project uses `top_k = 4`.

### Similarity (Cosine)

The metric used to rank chunk relevance to a query. This project uses cosine similarity.

### Context Window

The bounded set of retrieved chunks (at most Top-K) that is injected into the LLM prompt as
grounding context. Context is capped so the prompt sent to the LLM stays bounded.

### RAG Chain

The Retrieval-Augmented Generation flow that takes a user query, retrieves owner-scoped context,
assembles a context-grounded prompt, calls the LLM via OpenRouter, and returns an answer.

### Ingestion Pipeline

The asynchronous background flow, executed by a Celery worker, that turns an uploaded document
into searchable vectors: text extraction, chunking, embedding, and per-user vector indexing.

### Tokens Consumed

The number of tokens the LLM reported using to produce an answer. It is read from the LLM
response `usage` field and returned to the client as `tokens_consumed`. It is never estimated.

### Credit

A simple per-user balance that is decremented by `tokens_consumed` after each successful chat
answer. It models the assessment's "Credit Consumption" requirement.

### Conversation

A sequence of related chat turns belonging to one user. The bonus chat continuation feature lets
a user extend a prior conversation by supplying a `chat_id`. Conversations are owner-scoped.

### chat_id

The identifier of a Conversation. Supplied (optionally) on `POST /api/chat/query/` and
`POST /api/chat/stream/` to continue an existing owner-scoped conversation; returned in the
response. A `chat_id` not owned by the requester returns `404`.

### Server-Sent Events (SSE)

A one-way streaming protocol over HTTP used by `POST /api/chat/stream/` to push the answer to
the client incrementally, ending with a done event carrying `chat_id` and `tokens_consumed`.

### Citation

A reference back to the source chunk(s) or document(s) a chat answer was grounded in, used to
make answers traceable to the user's own documents. Note: explicit citation is not a delivered
feature of the 12 live endpoints; it is documented here for conceptual reference only.

### Task ID

The identifier returned when an ingestion job is enqueued. It is used to poll ingestion status.

### Document ID

A backend-generated identifier for an uploaded document record, returned on upload and used to
reference the document internally.

### Ingestion Status

The public lifecycle state of an ingestion task, exposed as `PROCESSING`, `SUCCESS`, or `FAILURE`.
Internal Celery states are mapped onto these three public values.

### Protected Route

An API endpoint that requires a valid JWT token in the `Authorization: Bearer <token>` header.

### JWT

JSON Web Token used for authenticating requests to protected routes.

### OpenRouter

The unified LLM gateway used as the project's LLM provider. It is OpenAI-compatible (base URL
`https://openrouter.ai/api/v1`, chat/completions shape) and offers free-tier models, removing the
need for a paid LLM key.

### LangChain

The orchestration framework used for document loaders, the `RecursiveCharacterTextSplitter`,
vector store abstractions, and the retriever that drives the RAG chain.

### Celery Worker

The background process that executes the asynchronous ingestion pipeline outside the
request-response cycle.

### Redis

The message broker and result backend used for background task communication.

### Chroma

The vector store used to index and search chunk embeddings, with one collection per user.

### Structured Logging

Logging in machine-readable JSON format with stable fields such as service name, task metadata,
and status. Secrets and raw document text are never logged.

### Grafana Alloy

The log collection and forwarding component used to ship container logs to Loki.

### Loki

The log storage and query backend used for centralized log aggregation.

### Grafana

The UI used to visualize logs and dashboards.

### Docker Compose

The local orchestration mechanism used to run the web app, database, Redis, Celery, vector
store, and observability services together.

## Actors

### User

The authenticated API consumer who registers, uploads private documents, polls ingestion status,
and asks questions answered only from their own documents.

### Candidate

The person implementing the assessment solution.

### Reviewer

The person assessing the implementation quality, completeness, and clarity.
