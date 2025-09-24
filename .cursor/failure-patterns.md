# AI Collaboration Failure Patterns

## Schema Evolution Disaster - 2025-09-18
**Time Lost:** 5 hours
**Root Cause:** Multiple AI failure modes in database operations
**Prevention:** Systematic rules for AI supervision

## Core AI Failure Modes Observed

### 1. State Blindness and Context Drift
**Symptom:** AI hallucinates table names, forgets object types (TABLE vs VIEW), references non-existent objects
**Root Cause:** AI has no persistent memory of executed code results
**Prevention Rule:** Force state check before every database operation
**Required Action:** Always start with: "List all public and temporary tables and views before writing any DDL/DML"

### 2. Probabilistic Code Generation  
**Symptom:** Syntax errors in complex SQL, incorrect function arguments, numerically unstable results
**Root Cause:** Pattern-based code generation without execution plan understanding
**Prevention Rule:** Demand small, testable code blocks
**Required Action:** "Give me a single CREATE/UPDATE statement only. Wait for my confirmation before proceeding."

### 3. Ignoring Process Directives
**Symptom:** AI provides large multi-step blocks despite explicit "wait for results" instructions
**Root Cause:** AI optimized for comprehensive answers over disciplined process
**Prevention Rule:** Enforce strict call-and-response cadence
**Required Action:** End prompts with: "**Do not proceed until I reply with the results of this query.**"

### 4. Semantic Regression
**Symptom:** AI forgets key architectural decisions (p0 table exclusions, imputation logic)
**Root Cause:** Older constraints lose prominence in growing context window
**Prevention Rule:** Pin working specifications in every major prompt
**Required Action:** Start tasks with: "**REMINDER:** [key architectural constraints]. Now proceed with..."

## Factory Rules for AI Database Operations

### Before Any Database Work
1. **State Check Required:** "List all tables and views in current schema"
2. **Single Statement Only:** Never accept multi-step SQL blocks
3. **Wait for Confirmation:** AI must pause after each statement
4. **Idempotent Code:** All operations must be safely re-runnable
5. **Pin Architecture:** Restate key constraints in each major prompt

### Mandatory AI Supervision Pattern

**Phase 1: State Discovery**
- AI lists current database state
- Human confirms state is accurate
- AI proceeds with single operation

**Phase 2: Single Operation**
- AI provides ONE statement only
- Human executes and reports results
- AI analyzes results before next step

**Phase 3: Validation**
- AI confirms operation succeeded
- Human validates against schema manifest
- AI documents any deviations

### Emergency Recovery Procedures
**When AI Goes Off-Rails:**
1. **STOP** - Do not execute any more AI-generated code
2. **STATE CHECK** - Manually verify current database state
3. **ROLLBACK** - Revert to last known good state if needed
4. **RESTART** - Begin with fresh AI context and pinned constraints
5. **DOCUMENT** - Record the failure pattern for future prevention

### Red Flag Phrases
**Never proceed when AI says:**
- "I'll create multiple tables..."
- "Here's a complete migration script..."
- "Let me handle the entire schema..."
- "I'll fix everything at once..."

**Always demand:**
- "Show me the current state first"
- "One statement at a time"
- "Wait for my confirmation"
- "What are the current constraints?"

## Prevention Checklist
- [ ] State check completed before any database work
- [ ] Single statement provided by AI
- [ ] Human confirmation received before proceeding
- [ ] Key architectural constraints restated
- [ ] Idempotent code generated
- [ ] Results validated against schema manifest
