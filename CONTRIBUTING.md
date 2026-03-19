# Contributing to SentinelAI

Thank you for your interest in contributing to SentinelAI! This guide will help you get started.

---

## 🎯 Development Workflow

### 1. Fork & Clone
```bash
git clone https://github.com/yourusername/SentinelAI.git
cd SentinelAI
git checkout -b feature/your-feature
```

### 2. Set Up Local Environment
```bash
docker compose up --build
# OR for manual setup:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Make Changes

**Backend:**
- Code in `app/` following existing patterns
- Add tests in `tests/`
- Run: `pytest -v`

**Frontend:**
- Code in `sentinel-frontend/src/`
- Run `npm run dev` to test
- Ensure TypeScript types are correct

### 4. Commit & Push
```bash
git add .
git commit -m "feat: add new feature" -m "Description of changes"
git push origin feature/your-feature
```

### 5. Create Pull Request
- Link any related issues
- Describe changes clearly
- Request review from maintainers

---

## 📋 Code Standards

### Python
- Follow PEP 8
- Use type hints
- Write docstrings for functions/classes
- Add tests for new functionality

### TypeScript/React
- Use strict TypeScript
- Follow functional component patterns
- Use React hooks
- Add prop types/interfaces

### Git Commits
- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Be descriptive but concise
- Reference issues when applicable

---

## 🧪 Testing

### Run Backend Tests
```bash
pytest -v                    # All tests
pytest tests/test_alerts.py  # Specific file
pytest -k "test_name"        # Specific test
```

### Run Frontend Build
```bash
cd sentinel-frontend
npm run build
npm run lint
```

---

## 🚀 Deployment Testing

Before submitting a PR, verify Docker build works:

```bash
docker compose up --build
curl http://localhost:8000/health  # Should return ok
```

---

## 📝 Documentation

- Update README.md if user-facing changes
- Add comments to complex algorithms
- Update Architecture.md for structural changes
- Document breaking changes clearly

---

## 🐛 Reporting Issues

Include:
- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Python version, etc.)
- Relevant logs/screenshots

---

## 📄 License

By contributing, you agree your changes are licensed under the same license as this project.

---

**Questions?** Open an issue or reach out to maintainers.
