# Development Rules - Health Agentic Workflow MVP

## 🚨 CRITICAL: Hot Reload Blocking Rules

### Rule 1: Zero ESLint Errors/Warnings
**REQUIREMENT**: All ESLint errors and warnings MUST be resolved before committing code.

**RATIONALE**: ESLint warnings can break React's hot reload functionality, causing:
- Manual server restarts required
- Slow development iteration
- Frustrated developers
- Lost productivity

**ENFORCEMENT**:
```bash
# Pre-commit hook should run:
npm run lint
# Must return exit code 0 (no errors/warnings)
```

**EXCEPTIONS**: None. All warnings must be fixed or explicitly disabled with `// eslint-disable-next-line` comments.

### Rule 2: No Console Errors in Browser
**REQUIREMENT**: Browser console must be clean of JavaScript errors.

**RATIONALE**: Console errors can break hot reload and cause silent failures.

**ENFORCEMENT**: 
- Check browser console before committing
- Fix all red error messages
- Yellow warnings should be investigated

### Rule 3: Port Conflict Prevention
**REQUIREMENT**: Always check for existing processes before starting servers.

**ENFORCEMENT**:
```bash
# Before starting backend:
lsof -ti:3001 | xargs kill -9 2>/dev/null || true

# Before starting frontend:
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
```

### Rule 4: Database Connection Validation
**REQUIREMENT**: Backend must successfully connect to database before serving requests.

**ENFORCEMENT**:
```bash
# Backend startup should include:
- Database connection test
- Schema validation
- Graceful error handling
```

## 🔧 Development Workflow

### Starting Development Environment
```bash
# 1. Clean slate
./scripts/clean-ports.sh

# 2. Start backend (with DB validation)
cd backend && npm start

# 3. Start frontend (with lint check)
cd frontend && npm start

# 4. Verify both are running
curl http://localhost:3001/health
curl http://localhost:3000
```

### Pre-Commit Checklist
- [ ] ESLint passes with zero warnings
- [ ] Browser console is clean
- [ ] Hot reload works (make test change)
- [ ] All tests pass
- [ ] Database migrations applied

### Hot Reload Test
Before committing, make a small change to verify hot reload works:
```javascript
// Change this in App.js
<h1>Health Agentic Workflow MVP - TEST</h1>
// Should appear in browser without refresh
```

## 🚫 Anti-Patterns (Never Do These)

1. **Ignore ESLint warnings** - They break hot reload
2. **Start servers without cleaning ports** - Causes conflicts
3. **Commit code with console errors** - Breaks development flow
4. **Skip database connection validation** - Causes runtime failures
5. **Work around hot reload issues** - Fix the root cause instead

## 🎯 Success Metrics

- **Hot reload works 100% of the time**
- **Zero manual server restarts during development**
- **Clean browser console**
- **Fast development iteration**
- **Happy developers**

## 🔄 Continuous Improvement

If hot reload breaks:
1. **STOP** - Don't work around it
2. **IDENTIFY** - Check ESLint, console, ports
3. **FIX** - Resolve root cause
4. **VERIFY** - Test hot reload works
5. **COMMIT** - Only when everything works

---

**Remember**: The goal is smooth, fast development. Any friction in the development workflow should be eliminated, not worked around.
