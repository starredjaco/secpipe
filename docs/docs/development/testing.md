# Testing Guide

This guide explains FuzzForge's testing infrastructure, including unit tests, workflow integration tests, and platform-specific testing for multi-architecture support.

---

## Overview

FuzzForge has multiple layers of testing:

1. **Unit Tests** - Backend and CLI unit tests
2. **Worker Validation** - Docker image and metadata validation
3. **Platform Detection Tests** - Verify correct Dockerfile selection across platforms
4. **Workflow Integration Tests** - End-to-end workflow execution validation
5. **Multi-Platform Tests** - Verify platform-specific Docker images (AMD64 vs ARM64)

---

## Test Organization

```
.github/
├── workflows/
│   ├── test.yml             # Unit tests, linting, worker builds
│   └── test-workflows.yml   # Workflow integration tests
├── test-matrix.yaml         # Workflow test configuration
└── scripts/
    └── validate-workers.sh  # Worker validation script

cli/
└── tests/
    └── test_platform_detection.py  # Platform detection unit tests

backend/
└── tests/
    ├── unit/          # Backend unit tests
    └── integration/   # Backend integration tests (commented out)

scripts/
└── test_workflows.py  # Workflow execution test script
```

---

## Running Tests Locally

### Prerequisites

```bash
# Start FuzzForge services
docker compose up -d

# Install CLI in development mode
cd cli
pip install -e ".[dev]"
pip install pytest pytest-cov pyyaml
```

### Unit Tests

#### Backend Unit Tests

```bash
cd backend
pytest tests/unit/ -v \
  --cov=toolbox/modules \
  --cov=src \
  --cov-report=html
```

#### CLI Platform Detection Tests

```bash
cd cli
pytest tests/test_platform_detection.py -v
```

### Workflow Integration Tests

#### Run Fast Test Suite

Tests a subset of fast-running workflows:

```bash
python scripts/test_workflows.py --suite fast
```

Workflows in fast suite:
- `android_static_analysis`
- `python_sast`
- `secret_detection`
- `gitleaks_detection`
- `trufflehog_detection`

#### Run Full Test Suite

Tests all workflows (excludes LLM and OSS-Fuzz workflows):

```bash
python scripts/test_workflows.py --suite full
```

Additional workflows in full suite:
- `atheris_fuzzing`
- `cargo_fuzzing`
- `security_assessment`

#### Run Single Workflow Test

```bash
python scripts/test_workflows.py --workflow python_sast
```

#### Test Platform-Specific Dockerfile

```bash
python scripts/test_workflows.py \
  --workflow android_static_analysis \
  --platform linux/amd64
```

---

## Test Matrix Configuration

The test matrix (`.github/test-matrix.yaml`) defines:

- Workflow-to-worker mappings
- Test projects for each workflow
- Required parameters
- Expected outcomes
- Timeout values
- Test suite groupings

### Example Configuration

```yaml
workflows:
  python_sast:
    worker: python
    test_project: test_projects/vulnerable_app
    working_directory: test_projects/vulnerable_app
    parameters: {}
    timeout: 180
    expected:
      status: "COMPLETED"
      has_findings: true
      sarif_export: true
    tags: [python, sast, fast]
```

### Adding a New Workflow Test

1. Add workflow configuration to `.github/test-matrix.yaml`:

```yaml
workflows:
  my_new_workflow:
    worker: python  # Which worker runs this workflow
    test_project: test_projects/my_test
    working_directory: test_projects/my_test
    parameters:
      # Any required parameters
      severity: "high"
    timeout: 300
    expected:
      status: "COMPLETED"
      has_findings: true
      sarif_export: true
    tags: [python, custom, fast]
```

2. Add to appropriate test suite:

```yaml
test_suites:
  fast:
    workflows:
      - python_sast
      - my_new_workflow  # Add here
```

3. Ensure test project exists with appropriate test cases

---

## Platform-Specific Testing

### Why Platform-Specific Tests?

Some workers (like Android) have different capabilities on different platforms:

- **AMD64 (x86_64)**: Full toolchain including MobSF
- **ARM64 (Apple Silicon)**: Limited toolchain (MobSF incompatible with Rosetta 2)

### Platform Detection

Platform detection happens in `cli/src/fuzzforge_cli/worker_manager.py`:

```python
def _detect_platform(self) -> str:
    """Detect current platform for Docker image selection."""
    machine = platform.machine()
    system = platform.system()

    # Map to Docker platform identifiers
    if machine in ['x86_64', 'AMD64']:
        return 'linux/amd64'
    elif machine in ['aarch64', 'arm64']:
        return 'linux/arm64'
    else:
        return 'linux/amd64'  # Default fallback
```

### Dockerfile Selection

Workers with `metadata.yaml` can define platform-specific Dockerfiles:

```yaml
# workers/android/metadata.yaml
platforms:
  linux/amd64:
    dockerfile: Dockerfile.amd64
    description: "Full Android toolchain with MobSF support"

  linux/arm64:
    dockerfile: Dockerfile.arm64
    description: "Android toolchain without MobSF"
```

### Testing Platform Detection

```bash
# Run platform detection unit tests
cd cli
pytest tests/test_platform_detection.py -v

# Test with mocked platforms
pytest tests/test_platform_detection.py::TestPlatformDetection::test_detect_platform_linux_x86_64 -v
```

---

## CI/CD Testing

### GitHub Actions Workflows

#### 1. Main Test Workflow (`.github/workflows/test.yml`)

Runs on every push and PR:

- **Worker Validation**: Validates Dockerfiles and metadata
- **Docker Image Builds**: Builds only modified workers
- **Linting**: Ruff and mypy checks
- **Backend Unit Tests**: pytest on Python 3.11 and 3.12

#### 2. Workflow Integration Tests (`.github/workflows/test-workflows.yml`)

Runs end-to-end workflow tests:

- **Platform Detection Tests**: Unit tests for platform detection logic
- **Fast Workflow Tests**: Quick smoke tests (runs on every PR)
- **Android Platform Tests**: Verifies AMD64 and ARM64 Dockerfile selection
- **Full Workflow Tests**: Comprehensive tests (runs on main/master or schedule)

### Test Triggers

```yaml
# Runs on every push/PR
on:
  push:
    branches: [ main, master, dev, develop, test/** ]
  pull_request:
    branches: [ main, master, dev, develop ]

# Manual trigger with test suite selection
workflow_dispatch:
  inputs:
    test_suite:
      type: choice
      options:
        - fast
        - full
        - platform
```

---

## Debugging Test Failures

### Local Debugging

#### 1. Check Service Status

```bash
docker ps
docker logs fuzzforge-backend
docker logs fuzzforge-worker-python
```

#### 2. Run Workflow Manually

```bash
cd test_projects/vulnerable_app
ff workflow run python_sast . --wait --no-interactive
```

#### 3. Check Findings

```bash
ff findings list
ff findings list python_sast-xxxxx --format json
```

### CI Debugging

Test workflows automatically collect logs on failure:

```yaml
- name: Collect logs on failure
  if: failure()
  run: |
    docker ps -a
    docker logs fuzzforge-backend --tail 100
    docker logs fuzzforge-worker-python --tail 50
```

View logs in GitHub Actions:
1. Go to failed workflow run
2. Click on failed job
3. Scroll to "Collect logs on failure" step

---

## Writing New Tests

### Adding a Backend Unit Test

```python
# backend/tests/unit/test_my_feature.py
import pytest
from toolbox.modules.my_module import my_function

def test_my_function():
    result = my_function("input")
    assert result == "expected_output"

@pytest.mark.asyncio
async def test_async_function():
    result = await my_async_function()
    assert result is not None
```

### Adding a CLI Unit Test

```python
# cli/tests/test_my_feature.py
import pytest
from fuzzforge_cli.my_module import MyClass

@pytest.fixture
def my_instance():
    return MyClass()

def test_my_method(my_instance):
    result = my_instance.my_method()
    assert result == expected_value
```

### Adding a Platform Detection Test

```python
# cli/tests/test_platform_detection.py
from unittest.mock import patch

def test_detect_platform_linux_x86_64(worker_manager):
    with patch('platform.machine', return_value='x86_64'), \
         patch('platform.system', return_value='Linux'):
        platform = worker_manager._detect_platform()
        assert platform == 'linux/amd64'
```

---

## Test Coverage

### Viewing Coverage Reports

#### Backend Coverage

```bash
cd backend
pytest tests/unit/ --cov=toolbox/modules --cov=src --cov-report=html
open htmlcov/index.html
```

#### CLI Coverage

```bash
cd cli
pytest tests/ --cov=src/fuzzforge_cli --cov-report=html
open htmlcov/index.html
```

### Coverage in CI

Coverage reports are automatically uploaded to Codecov:

- Backend: `codecov-backend`
- CLI Platform Detection: `cli-platform-detection`

View at: https://codecov.io/gh/FuzzingLabs/fuzzforge_ai

---

## Test Best Practices

### 1. Fast Tests First

Order tests by execution time:
- Unit tests (< 1s each)
- Integration tests (< 10s each)
- Workflow tests (< 5min each)

### 2. Use Test Fixtures

```python
@pytest.fixture
def temp_project(tmp_path):
    """Create temporary test project."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    # Setup project files
    return project_dir
```

### 3. Mock External Dependencies

```python
@patch('subprocess.run')
def test_docker_command(mock_run):
    mock_run.return_value = Mock(returncode=0, stdout="success")
    result = run_docker_command()
    assert result == "success"
```

### 4. Parametrize Similar Tests

```python
@pytest.mark.parametrize("platform,expected", [
    ("linux/amd64", "Dockerfile.amd64"),
    ("linux/arm64", "Dockerfile.arm64"),
])
def test_dockerfile_selection(platform, expected):
    dockerfile = select_dockerfile(platform)
    assert expected in str(dockerfile)
```

### 5. Tag Tests Appropriately

```python
@pytest.mark.integration
def test_full_workflow():
    # Integration test that requires services
    pass

@pytest.mark.slow
def test_long_running_operation():
    # Test that takes > 10 seconds
    pass
```

Run specific tags:
```bash
pytest -m "not slow"  # Skip slow tests
pytest -m integration  # Only integration tests
```

---

## Continuous Improvement

### Adding Test Coverage

1. Identify untested code paths
2. Write unit tests for core logic
3. Add integration tests for end-to-end flows
4. Update test matrix for new workflows

### Performance Optimization

1. Use test suites to group tests
2. Run fast tests on every commit
3. Run slow tests nightly or on main branch
4. Parallelize independent tests

### Monitoring Test Health

1. Track test execution time trends
2. Monitor flaky tests
3. Keep coverage above 80%
4. Review and update stale tests

---

## Related Documentation

- [Docker Setup](../how-to/docker-setup.md) - Worker management
- [CLI Reference](../reference/cli-reference.md) - CLI commands
- [Workflow Guide](../how-to/create-workflow.md) - Creating workflows

---

## Troubleshooting

### Tests Timeout

**Symptom**: Workflow tests hang and timeout

**Solutions**:
1. Check if services are running: `docker ps`
2. Verify backend is healthy: `docker logs fuzzforge-backend`
3. Increase timeout in test matrix
4. Check for deadlocks in workflow code

### Worker Build Failures

**Symptom**: Docker image build fails in CI

**Solutions**:
1. Test build locally: `docker compose build worker-python`
2. Check Dockerfile syntax
3. Verify base image is accessible
4. Review build logs for specific errors

### Platform Detection Failures

**Symptom**: Wrong Dockerfile selected on ARM64

**Solutions**:
1. Verify metadata.yaml syntax
2. Check platform detection logic
3. Test locally with: `python -c "import platform; print(platform.machine())"`
4. Review WorkerManager._detect_platform() logic

### SARIF Export Validation Fails

**Symptom**: Workflow completes but SARIF validation fails

**Solutions**:
1. Check SARIF file exists: `ls -la test-*.sarif`
2. Validate JSON syntax: `jq . test-*.sarif`
3. Verify SARIF schema: Must have `version` and `runs` fields
4. Check workflow SARIF export logic

---

**Questions?** Open an issue or consult the [development discussions](https://github.com/FuzzingLabs/fuzzforge_ai/discussions).
