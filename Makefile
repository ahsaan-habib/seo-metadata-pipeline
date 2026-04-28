.PHONY: install migrate worker web
install:
	python -m venv .venv && .venv/bin/pip install -e .
migrate:
	python manage.py makemigrations metadata && python manage.py migrate
# 4, not 12: well under what the model server can take. Ollama answers 503 when
# its queue is full (OLLAMA_MAX_QUEUE); concurrency is the first line of defence.
worker:
	celery -A seopipe worker --concurrency 4 -l info
web:
	python manage.py runserver 8060
