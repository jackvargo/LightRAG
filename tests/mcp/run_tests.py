#!/usr/bin/env python3
"""
Test runner for MCP Protocol Tests

This script provides a convenient way to run MCP protocol tests with various options.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, cwd=None):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode == 0


def install_test_dependencies():
    """Install test dependencies."""
    test_dir = Path(__file__).parent
    requirements_file = test_dir / "requirements-test.txt"

    if requirements_file.exists():
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
        return run_command(cmd)
    else:
        print(f"Requirements file not found: {requirements_file}")
        return False


def run_tests(
    test_type="all", coverage=True, parallel=True, verbose=True, markers=None
):
    """Run the tests with specified options."""
    test_dir = Path(__file__).parent

    # Base pytest command
    cmd = [sys.executable, "-m", "pytest"]

    # Add test directory
    if test_type == "unit":
        cmd.append(str(test_dir / "unit"))
    elif test_type == "integration":
        cmd.append(str(test_dir / "integration"))
    elif test_type == "performance":
        cmd.append(str(test_dir / "performance"))
    else:
        cmd.append(str(test_dir))

    # Add options
    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(
            [
                "--cov=lightrag_mcp",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov",
                "--cov-report=xml:coverage.xml",
            ]
        )

    if parallel:
        cmd.extend(["-n", "auto"])

    if markers:
        for marker in markers:
            cmd.extend(["-m", marker])

    # Run the tests
    return run_command(cmd, cwd=test_dir)


def run_linting():
    """Run code linting."""
    test_dir = Path(__file__).parent

    # Run flake8
    print("Running flake8...")
    flake8_cmd = [sys.executable, "-m", "flake8", str(test_dir)]
    flake8_success = run_command(flake8_cmd)

    # Run black check
    print("Running black check...")
    black_cmd = [sys.executable, "-m", "black", "--check", str(test_dir)]
    black_success = run_command(black_cmd)

    # Run isort check
    print("Running isort check...")
    isort_cmd = [sys.executable, "-m", "isort", "--check-only", str(test_dir)]
    isort_success = run_command(isort_cmd)

    return flake8_success and black_success and isort_success


def run_type_checking():
    """Run type checking with mypy."""
    test_dir = Path(__file__).parent

    print("Running mypy type checking...")
    mypy_cmd = [sys.executable, "-m", "mypy", str(test_dir)]
    return run_command(mypy_cmd)


def generate_test_report():
    """Generate a comprehensive test report."""
    test_dir = Path(__file__).parent

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_dir),
        "--html=test_report.html",
        "--self-contained-html",
        "--cov=lightrag_mcp",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--junit-xml=test_results.xml",
        "-v",
    ]

    return run_command(cmd, cwd=test_dir)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run MCP Protocol Tests")

    parser.add_argument(
        "--type",
        choices=["all", "unit", "integration", "performance"],
        default="all",
        help="Type of tests to run",
    )

    parser.add_argument(
        "--no-coverage", action="store_true", help="Disable coverage reporting"
    )

    parser.add_argument(
        "--no-parallel", action="store_true", help="Disable parallel test execution"
    )

    parser.add_argument("--quiet", action="store_true", help="Run tests in quiet mode")

    parser.add_argument(
        "--markers", nargs="*", help="Run only tests with specified markers"
    )

    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install test dependencies before running tests",
    )

    parser.add_argument("--lint", action="store_true", help="Run code linting")

    parser.add_argument("--type-check", action="store_true", help="Run type checking")

    parser.add_argument(
        "--report", action="store_true", help="Generate comprehensive test report"
    )

    parser.add_argument(
        "--all-checks",
        action="store_true",
        help="Run all checks (tests, linting, type checking)",
    )

    args = parser.parse_args()

    success = True

    # Install dependencies if requested
    if args.install_deps:
        print("Installing test dependencies...")
        if not install_test_dependencies():
            print("Failed to install test dependencies")
            return 1

    # Run linting if requested
    if args.lint or args.all_checks:
        print("Running code linting...")
        if not run_linting():
            print("Linting failed")
            success = False

    # Run type checking if requested
    if args.type_check or args.all_checks:
        print("Running type checking...")
        if not run_type_checking():
            print("Type checking failed")
            success = False

    # Generate report if requested
    if args.report:
        print("Generating test report...")
        if not generate_test_report():
            print("Test report generation failed")
            success = False
    else:
        # Run regular tests
        print(f"Running {args.type} tests...")
        if not run_tests(
            test_type=args.type,
            coverage=not args.no_coverage,
            parallel=not args.no_parallel,
            verbose=not args.quiet,
            markers=args.markers,
        ):
            print("Tests failed")
            success = False

    if success:
        print("All checks passed!")
        return 0
    else:
        print("Some checks failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
