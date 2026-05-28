# Contributing to PhotoTagger

Thank you for your interest in contributing to PhotoTagger! This document provides guidelines for contributing.

## Code of Conduct

- Be respectful and inclusive
- Focus on the code, not the person
- Help others learn and grow
- Report issues privately if they involve security

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a feature branch** from `main`
4. **Make your changes** with tests
5. **Submit a pull request**

## Development Setup

```bash
# Clone and setup
git clone https://github.com/YOUR_USERNAME/PhotoTagger.git
cd PhotoTagger
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Verify setup
pytest tests/ -v
```

## Making Changes

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings for all functions
- Keep functions focused and small
- Max line length: 100 characters

### Before You Start
1. Check existing [issues](https://github.com/BrettSEvans/PhotoTagger/issues)
2. Read the implementation plan if available
3. Discuss major changes in an issue first

### Test-Driven Development
1. Write test first (TDD approach)
2. Run `pytest tests/` to see it fail
3. Implement minimal code to pass
4. Run tests again to verify
5. Refactor if needed
6. Commit with clear message

### Example Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and add tests
# tests/test_my_feature.py - write test
# src/my_feature.py - implement feature

# Run tests
pytest tests/test_my_feature.py -v

# Commit
git add tests/test_my_feature.py src/my_feature.py
git commit -m "feat: add my new feature"

# Push to your fork
git push origin feature/my-feature
```

## Commit Messages

Follow conventional commits format:

```
feat: add new feature
fix: fix a bug
docs: update documentation
test: add or update tests
refactor: refactor code
chore: update dependencies
```

Examples:
- `feat: add face clustering support`
- `fix: handle uppercase image extensions`
- `docs: add roster format documentation`

## Pull Request Process

1. **Update tests** - All new features must have tests
2. **Run full test suite** - `pytest tests/ -v`
3. **Update documentation** - README, docstrings, etc.
4. **Keep commits clean** - One feature per PR if possible
5. **Write clear PR description** - What, why, and testing

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Documentation update
- [ ] Performance improvement

## Testing
How to test these changes:
```bash
# Your testing steps here
```

## Related Issues
Closes #123

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Commits are clean and well-described
- [ ] No breaking changes
```

## Phase 2A Development

To contribute to Phase 2A (Backend Enhancement):

1. Review the plan: `docs/superpowers/plans/2026-05-28-phototagger-phase2a-backend.md`
2. Pick a task to work on
3. Follow TDD approach with provided test code
4. Submit PR with task-specific tests passing

**Phase 2A Features:**
- Face detection (InsightFace)
- Roster management
- Parallel OCR processing
- Confidence filtering
- Enhanced API

## Reporting Issues

**Bug Reports:**
1. Clear description of the problem
2. Steps to reproduce
3. Expected vs actual behavior
4. Python version, OS, and environment
5. Relevant error messages/logs

**Feature Requests:**
1. Clear description of desired feature
2. Motivation and use case
3. Suggested implementation (optional)
4. Any related issues/PRs

## Performance Considerations

When making changes:
- Benchmark critical paths
- Don't optimize prematurely
- Consider CPU and memory impact
- Test on real data if possible
- Document performance characteristics

## Documentation

Update docs when:
- Adding new features
- Changing behavior
- Adding CLI commands
- Modifying API endpoints

Key docs:
- `README.md` - Overview and quick start
- `CLAUDE.md` - Project context
- Docstrings - In all functions
- `docs/` - Architecture and detailed guides

## Questions?

- Check existing [issues](https://github.com/BrettSEvans/PhotoTagger/issues)
- Review implementation plans in `docs/superpowers/plans/`
- Ask in a new GitHub issue
- Review `CLAUDE.md` for project context

## Recognition

Contributors are recognized in the README and commit history. Major contributions will be featured in release notes.

---

Thank you for helping make PhotoTagger better! 🎉
