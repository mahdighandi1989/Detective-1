"""Test package for Detective-1 backend.

This package contains the test suite for the Detective-1 OSINT platform
backend, including unit tests, integration tests, and fixtures.

Test modules:
    - test_auth: Authentication and RBAC tests
    - test_persons: Person profile module tests
    - test_encyclopedia: Encyclopedia and semantic search tests
    - test_graph: Relationship graph tests
    - test_risk_engine: Risk assessment engine tests
    - test_osint_agent: OSINT search agent tests
    - test_llm_adapter: LLM adapter tests

Run the full suite with:
    pytest

Run with coverage:
    pytest --cov=app --cov-report=term-missing
"""