# Source Links

These official references justify the locked stack, LLM/embedding choices, and delivery defaults in
`.agents/references/assessment-decisions.md`. **Provider and model facts (slugs, request shapes,
limits) must be verified against these at implementation time — never answered from memory**
(decision D-009, mistakes M-008/M-009).

## Django / DRF / JWT

- Django 5.x release notes index: https://docs.djangoproject.com/en/5.2/releases/
- Django logging (structured/JSON config) guide: https://docs.djangoproject.com/en/5.2/howto/logging/
- DRF authentication guide (JWT package note): https://www.django-rest-framework.org/api-guide/authentication/
- DRF release notes: https://www.django-rest-framework.org/community/release-notes/
- djangorestframework-simplejwt docs: https://django-rest-framework-simplejwt.readthedocs.io/en/latest/

## Celery / Redis

- Celery 5.x getting started: https://docs.celeryq.dev/en/stable/getting-started/index.html
- Celery + Django integration: https://docs.celeryq.dev/en/latest/django/first-steps-with-django.html
- Celery task states (for internal→public status mapping, D-019): https://docs.celeryq.dev/en/stable/userguide/tasks.html#states

## LangChain (loaders / splitter / retriever)

- RecursiveCharacterTextSplitter (chunk_size/overlap, D-011): https://python.langchain.com/docs/how_to/recursive_text_splitter/
- Document loaders (PDF/TXT/Markdown): https://python.langchain.com/docs/integrations/document_loaders/
- Chroma vector store integration: https://python.langchain.com/docs/integrations/vectorstores/chroma/
- HuggingFace embeddings (`langchain-huggingface`, D-010): https://python.langchain.com/docs/integrations/text_embedding/huggingfacehub/
- Retrievers (top_k / similarity, D-012): https://python.langchain.com/docs/how_to/vectorstore_retriever/

## Chroma (vector store)

- Chroma docs home: https://docs.trychroma.com/
- Collections & client/server usage (per-user collections, D-013): https://docs.trychroma.com/docs/collections/manage-collections
- Distance / similarity (cosine, D-012): https://docs.trychroma.com/docs/collections/configure

## Embedding model

- sentence-transformers `all-MiniLM-L6-v2` model card (384 dims, D-010):
  https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- sentence-transformers docs: https://www.sbert.net/

## OpenRouter (LLM gateway)

- Quickstart / base URL `https://openrouter.ai/api/v1` (OpenAI-compatible, D-007):
  https://openrouter.ai/docs/quickstart
- API reference — chat completions request/response shape: https://openrouter.ai/docs/api-reference/chat-completion
- Models catalogue — **verify the free slug `google/gemma-4-31b-it:free` is still live**
  (D-008): https://openrouter.ai/models
- Usage accounting (`usage` field for `tokens_consumed`, D-009): https://openrouter.ai/docs/use-cases/usage-accounting

## Observability: Grafana / Loki / Alloy

- Promtail deprecation/EOL (why Alloy, D-029): https://grafana.com/docs/loki/latest/send-data/promtail/
- Grafana Alloy `loki.write`: https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/
- Grafana provisioning (datasources + dashboards from files): https://grafana.com/docs/grafana/latest/administration/provisioning/
- Loki configuration examples (single-node filesystem): https://grafana.com/docs/loki/latest/configure/examples/configuration-examples/

## Docker Compose

- Startup order / `service_healthy` (V-10): https://docs.docker.com/compose/how-tos/startup-order/
- Compose services reference: https://docs.docker.com/reference/compose-file/services/

## OpenSpec (hybrid workflow, D-024)

- OpenSpec project: https://github.com/Fission-AI/OpenSpec
- Repo-local commands/skills: `.claude/commands/opsx/*`, `.claude/skills/openspec-*/SKILL.md`

## Claude / Anthropic model facts

- For any Claude/Anthropic model facts (ids, pricing, params, streaming, tool use, token counting),
  use the **bundled `claude-api` skill** (invoke via the Skill tool) — it is the authoritative,
  in-environment reference. **Do not answer Claude model questions from memory** (M-009).
- Note: RAVID's runtime LLM is **OpenRouter + Mistral**, *not* Claude (D-007/D-008). The claude-api
  reference is for accuracy when Claude/Anthropic is named in a task, not for the product runtime.
