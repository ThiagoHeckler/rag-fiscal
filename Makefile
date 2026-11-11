.PHONY: help db baixar ingerir api test avaliar lint

help: ## Lista os comandos
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

db: ## Sobe o PostgreSQL com pgvector (porta 5436)
	docker compose up -d db

baixar: ## Baixa RICMS-SC, NCM e CFOP das fontes oficiais
	python -m rag_fiscal baixar

ingerir: ## Indexa tudo (gera embeddings; demora na 1ª vez)
	python -m rag_fiscal ingerir

api: ## Sobe a API em http://localhost:8000/docs
	uvicorn rag_fiscal.api:app --reload

test: ## Testes (os de banco usam DATABASE_URL_TESTE)
	DATABASE_URL_TESTE=$${DATABASE_URL_TESTE:-postgresql://rag:rag@localhost:5436/rag_fiscal} python -m pytest -q

avaliar: ## Mede a qualidade da busca com as 40 perguntas
	python avaliacao/avaliar.py

lint:
	ruff check .
