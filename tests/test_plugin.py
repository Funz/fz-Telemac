#!/usr/bin/env python3
"""
Basic test suite for fz-Telemac plugin.

These tests verify the plugin structure.
They test:
- Model file validity
- Variable parsing
- Input file compilation
- Calculator configuration
"""

import os
import json
import tempfile
import sys


def test_model_files():
    """Test that all model JSON files are valid and have required fields."""
    print("Testing model files...")
    
    models = [
        ".fz/models/Telemac.json"
    ]
    
    required_fields = ["id", "varprefix", "var_delim", "formulaprefix", "formula_delim", "commentline", "output"]
    
    for model_file in models:
        print(f"  Checking {model_file}...", end=" ")
        
        # Check file exists
        assert os.path.exists(model_file), f"File not found: {model_file}"
        
        # Load and validate JSON
        with open(model_file, 'r') as f:
            model = json.load(f)
        
        # Check required fields
        for field in required_fields:
            assert field in model, f"Missing field '{field}' in {model_file}"
        
        # Check output section has at least one variable
        assert len(model["output"]) > 0, f"No output variables in {model_file}"
        
        print("✓")
    
    print("  All model files valid!\n")


def test_calculator_files():
    """Test that calculator JSON files are valid."""
    print("Testing calculator configuration files...")

    calculators = [
        ".fz/calculators/localhost_Telemac.json"
    ]
    
    for calc_file in calculators:
        print(f"  Checking {calc_file}...", end=" ")
        
        # Check file exists
        assert os.path.exists(calc_file), f"File not found: {calc_file}"
        
        # Load and validate JSON
        with open(calc_file, 'r') as f:
            calc = json.load(f)
        
        # Check required fields
        assert "uri" in calc, f"Missing 'uri' field in {calc_file}"
        assert "models" in calc, f"Missing 'models' field in {calc_file}"
        
        print("✓")
    
    print("  All calculator files valid!\n")


def test_calculator_scripts():
    """Test that calculator shell scripts exist and are executable."""
    print("Testing calculator shell scripts...")
    
    scripts = [
        ".fz/calculators/Telemac.sh",
        ".fz/calculators/telemac_poi.py"
    ]
    
    for script_file in scripts:
        print(f"  Checking {script_file}...", end=" ")
        
        # Check file exists
        assert os.path.exists(script_file), f"File not found: {script_file}"
        
        # Check if executable
        assert os.access(script_file, os.X_OK), f"Script not executable: {script_file}"
        
        print("✓")
    
    print("  All calculator scripts valid!\n")


def test_example_files():
    """Test that example files exist."""
    print("Testing example files...")
    
    examples = [
        "examples/Telemac/t2d_breach.cas/t2d_breach.cas",
        "examples/Telemac/t2d_breach.cas/t2d_breach.poi",
        # files referenced by t2d_breach.cas
        "examples/Telemac/t2d_breach.cas/geo_breach.slf",
        "examples/Telemac/t2d_breach.cas/ini_breach.slf",
        "examples/Telemac/t2d_breach.cas/geo_breach.cli",
        "examples/Telemac/t2d_breach.cas/t2d_breach.liq",
        "examples/Telemac/t2d_breach.cas/breach.txt"
    ]
    
    for example_path in examples:
        print(f"  Checking {example_path}...", end=" ")
        assert os.path.exists(example_path), f"Path not found: {example_path}"
        print("✓")
    
    print("  All example files present!\n")


def test_with_fz():
    """Test integration with fz framework (if available)."""
    print("Testing fz framework integration...")
    
    try:
        import fz
        print("  fz module found ✓")
        
        # Test parsing input file
        print("  Testing fz.fzi() on t2d_breach.cas...", end=" ")
        cas_dir = "examples/Telemac/t2d_breach.cas"
        if os.path.exists(cas_dir):
            variables = fz.fzi(cas_dir, "Telemac")
            print("✓")
            print(f"    Variables found: {list(variables.keys())}")
        else:
            print("⚠ (example not found)")
        
        # Test compiling input file
        print("  Testing fz.fzc() compilation...", end=" ")
        if os.path.exists(cas_dir):
            with tempfile.TemporaryDirectory() as tmpdir:
                fz.fzc(
                    cas_dir,
                    {},  # No variables to substitute in the base case
                    "Telemac",
                    output_dir=tmpdir
                )
                
                # Check that some output was created
                output_exists = any(os.listdir(tmpdir))
                assert output_exists, "No output created by fzc"
                
            print("✓")
        else:
            print("⚠ (example not found)")
        
        print("  fz integration tests passed!\n")
        
    except ImportError:
        print("  fz module not installed - skipping integration tests")
        print("  (Install with: pip install git+https://github.com/Funz/fz.git)\n")


def main():
    """Run all tests."""
    print("=" * 70)
    print("fz-Telemac Plugin Test Suite")
    print("=" * 70)
    print()
    
    # Change to repository root if needed
    if not os.path.exists(".fz"):
        if os.path.exists("../fz-telemac/.fz"):
            os.chdir("../fz-telemac")
        else:
            print("Error: Could not find .fz directory")
            print("Please run this script from the fz-telemac repository root")
            return 1
    
    try:
        test_model_files()
        test_calculator_files()
        test_calculator_scripts()
        test_example_files()
        test_with_fz()
        
        print("=" * 70)
        print("All tests passed! ✓")
        print("=" * 70)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
