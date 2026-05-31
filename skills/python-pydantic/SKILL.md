---
name: python-pydantic
description: Python coding standards with Pydantic data models, type hints, and pylint compliance
orchestrator:
  parallel: false
  type: kb
---

# Python Coding Skills

To ensure high-quality, pythonic, and robust code, follow these guidelines when writing Python.

## Core Principles

- **Pythonic Code**: Follow PEP 8 guidelines. Use idiomatic Python (e.g., list comprehensions, context managers, decorators).
- **Pydantic for Data Validation**: Use Pydantic models for all data structures, API requests, and configuration management to ensure type safety and validation.
- **Type Hinting**: Use extensive type hinting throughout the codebase to improve maintainity and catch errors early.

## Implementation Standards

### 1. Data Modeling with Pydantic
Always prefer Pydantic models over standard classes or dictionaries for structured data.
```python
from pydantic import BaseModel, Field, EmailStr

class User(BaseModel):
    id: int
    username: str = Field(..., min_length=3)
    email: EmailStr
    is_active: bool = True
```

### 2. Linting and Quality
All code must be linting-free. Before proposing any code, you MUST:
- Run `pylint` to ensure compliance with linting rules.
- Ensure no `pylint` errors or warnings are present.

### 3. Compilation and Verification
- Ensure code is syntactically correct and "compilable" (valid Python).
- Verify logic through unit tests where applicable.

## Workflow Requirement
Before presenting any Python solution:
1. Write the code using Pydantic and type hints.
2. Run `pylint` on the proposed code.
3. Only present the code if it passes all linting checks.
