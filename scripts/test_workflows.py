#!/usr/bin/env python3
"""
Automated workflow testing script for FuzzForge.

This script reads the test matrix configuration and executes workflows
to validate end-to-end functionality, SARIF export, and platform-specific
Dockerfile selection.

Usage:
    python scripts/test_workflows.py --suite fast
    python scripts/test_workflows.py --workflow python_sast
    python scripts/test_workflows.py --workflow android_static_analysis --platform linux/amd64
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


@dataclass
class WorkflowTestResult:
    """Result of a workflow test execution."""
    workflow_name: str
    success: bool
    duration: float
    status: Optional[str] = None
    run_id: Optional[str] = None
    error: Optional[str] = None
    findings_count: Optional[int] = None
    sarif_exported: bool = False


class WorkflowTester:
    """Executes and validates FuzzForge workflows."""

    def __init__(self, matrix_file: Path, root_dir: Path):
        self.matrix_file = matrix_file
        self.root_dir = root_dir
        self.matrix = self._load_matrix()
        self.results: List[WorkflowTestResult] = []

    def _load_matrix(self) -> Dict[str, Any]:
        """Load test matrix configuration."""
        with open(self.matrix_file, 'r') as f:
            return yaml.safe_load(f)

    def check_services(self) -> bool:
        """Check if FuzzForge services are running."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=fuzzforge-backend", "--format", "{{.Status}}"],
                capture_output=True,
                text=True,
                check=False
            )
            return "Up" in result.stdout
        except Exception as e:
            print(f"❌ Error checking services: {e}")
            return False

    def start_services(self) -> bool:
        """Start FuzzForge services if not running."""
        if self.check_services():
            print("✅ FuzzForge services already running")
            return True

        print("🚀 Starting FuzzForge services...")
        try:
            subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=self.root_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            # Wait for services to be ready
            print("⏳ Waiting for services to be ready...")
            max_wait = 60
            waited = 0
            while waited < max_wait:
                if self.check_services():
                    print("✅ Services ready")
                    time.sleep(5)  # Extra wait for full initialization
                    return True
                time.sleep(2)
                waited += 2
            print(f"⚠️  Services did not become ready within {max_wait}s")
            return False
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start services: {e}")
            return False

    def execute_workflow(
        self,
        workflow_name: str,
        config: Dict[str, Any],
        platform: Optional[str] = None
    ) -> WorkflowTestResult:
        """Execute a single workflow and validate results."""
        start_time = time.time()
        print(f"\n{'='*60}")
        print(f"Testing workflow: {workflow_name}")
        if platform:
            print(f"Platform: {platform}")
        print(f"{'='*60}")

        # Build command
        working_dir = self.root_dir / config['working_directory']
        cmd = [
            "ff", "workflow", "run",
            workflow_name,
            ".",
            "--wait",
            "--no-interactive"
        ]

        # Add parameters
        params = config.get('parameters', {})
        for key, value in params.items():
            if isinstance(value, (str, int, float)):
                cmd.append(f"{key}={value}")

        # Add SARIF export if expected
        sarif_file = None
        if config.get('expected', {}).get('sarif_export'):
            sarif_file = working_dir / f"test-{workflow_name}.sarif"
            cmd.extend(["--export-sarif", str(sarif_file)])

        # Execute workflow
        print(f"Command: {' '.join(cmd)}")
        print(f"Working directory: {working_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=config.get('timeout', 300)
            )

            duration = time.time() - start_time
            print(f"\n⏱️  Duration: {duration:.2f}s")

            # Parse output for run_id
            run_id = self._extract_run_id(result.stdout)

            # Check if workflow completed successfully
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                print(f"❌ Workflow failed with exit code {result.returncode}")
                print(f"Error: {error_msg[:500]}")
                return WorkflowTestResult(
                    workflow_name=workflow_name,
                    success=False,
                    duration=duration,
                    run_id=run_id,
                    error=error_msg[:500]
                )

            # Validate SARIF export
            sarif_exported = False
            if sarif_file and sarif_file.exists():
                sarif_exported = self._validate_sarif(sarif_file)
                print(f"✅ SARIF export validated" if sarif_exported else "⚠️  SARIF export invalid")

            # Get findings count
            findings_count = self._count_findings(run_id) if run_id else None

            print(f"✅ Workflow completed successfully")
            if findings_count is not None:
                print(f"   Findings: {findings_count}")

            return WorkflowTestResult(
                workflow_name=workflow_name,
                success=True,
                duration=duration,
                status="COMPLETED",
                run_id=run_id,
                findings_count=findings_count,
                sarif_exported=sarif_exported
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"❌ Workflow timed out after {duration:.2f}s")
            return WorkflowTestResult(
                workflow_name=workflow_name,
                success=False,
                duration=duration,
                error=f"Timeout after {config.get('timeout')}s"
            )
        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ Unexpected error: {e}")
            return WorkflowTestResult(
                workflow_name=workflow_name,
                success=False,
                duration=duration,
                error=str(e)
            )

    def _extract_run_id(self, output: str) -> Optional[str]:
        """Extract run_id from workflow output."""
        for line in output.split('\n'):
            if 'run_id' in line.lower() or 'execution id' in line.lower():
                # Try to extract the ID
                parts = line.split()
                for part in parts:
                    if '-' in part and len(part) > 10:
                        return part.strip(',:')
        return None

    def _validate_sarif(self, sarif_file: Path) -> bool:
        """Validate SARIF file structure."""
        try:
            with open(sarif_file, 'r') as f:
                sarif = json.load(f)
            # Basic SARIF validation
            return (
                'version' in sarif and
                'runs' in sarif and
                isinstance(sarif['runs'], list)
            )
        except Exception as e:
            print(f"⚠️  SARIF validation error: {e}")
            return False

    def _count_findings(self, run_id: str) -> Optional[int]:
        """Count findings for a run."""
        try:
            result = subprocess.run(
                ["ff", "findings", "list", run_id, "--format", "json"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                findings = json.loads(result.stdout)
                return len(findings) if isinstance(findings, list) else 0
        except Exception:
            pass
        return None

    def run_suite(self, suite_name: str) -> bool:
        """Run a predefined test suite."""
        suite = self.matrix.get('test_suites', {}).get(suite_name)
        if not suite:
            print(f"❌ Suite '{suite_name}' not found")
            return False

        workflows = suite.get('workflows', [])
        print(f"\n{'='*60}")
        print(f"Running test suite: {suite_name}")
        print(f"Workflows: {', '.join(workflows)}")
        print(f"{'='*60}\n")

        for workflow_name in workflows:
            config = self.matrix['workflows'].get(workflow_name)
            if not config:
                print(f"⚠️  Workflow '{workflow_name}' not found in matrix")
                continue

            result = self.execute_workflow(workflow_name, config)
            self.results.append(result)

        return self.print_summary()

    def run_workflow(self, workflow_name: str, platform: Optional[str] = None) -> bool:
        """Run a single workflow."""
        config = self.matrix['workflows'].get(workflow_name)
        if not config:
            print(f"❌ Workflow '{workflow_name}' not found")
            return False

        result = self.execute_workflow(workflow_name, config, platform)
        self.results.append(result)

        return result.success

    def print_summary(self) -> bool:
        """Print test summary."""
        print(f"\n\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}\n")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed

        print(f"Total tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print()

        if failed > 0:
            print("Failed tests:")
            for result in self.results:
                if not result.success:
                    print(f"  - {result.workflow_name}")
                    if result.error:
                        print(f"    Error: {result.error[:100]}")

        print(f"\n{'='*60}\n")
        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test FuzzForge workflows")
    parser.add_argument(
        "--suite",
        choices=["fast", "full", "platform"],
        help="Test suite to run"
    )
    parser.add_argument(
        "--workflow",
        help="Single workflow to test"
    )
    parser.add_argument(
        "--platform",
        help="Platform for platform-specific testing (e.g., linux/amd64)"
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path(".github/test-matrix.yaml"),
        help="Path to test matrix file"
    )
    parser.add_argument(
        "--skip-service-start",
        action="store_true",
        help="Skip starting services (assume already running)"
    )

    args = parser.parse_args()

    # Determine root directory
    root_dir = Path(__file__).parent.parent

    # Load tester
    matrix_file = root_dir / args.matrix
    if not matrix_file.exists():
        print(f"❌ Matrix file not found: {matrix_file}")
        sys.exit(1)

    tester = WorkflowTester(matrix_file, root_dir)

    # Start services if needed
    if not args.skip_service_start:
        if not tester.start_services():
            print("❌ Failed to start services")
            sys.exit(1)

    # Run tests
    success = False
    if args.suite:
        success = tester.run_suite(args.suite)
    elif args.workflow:
        success = tester.run_workflow(args.workflow, args.platform)
    else:
        print("❌ Must specify --suite or --workflow")
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
