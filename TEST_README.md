# Shared Meshtastic Connection Test Suite

This directory contains comprehensive tests for validating the shared Meshtastic connection between the offgrid bot and Telegram bot integration.

## Overview

The test suite validates that:
- Both bots use the same Meshtastic interface instance
- Configuration is properly shared from the main project's `[interface]` section
- No duplicate connections are created
- Message routing works between both bots
- Configuration changes propagate correctly
- Connection stability and error handling work properly

## Test Files

### 1. `test_shared_connection.py`
**Comprehensive test suite** for the shared Meshtastic connection.

**Features:**
- Validates shared interface instance usage
- Tests configuration integration
- Verifies no duplicate connections
- Tests message routing functionality
- Validates connection stability and error handling
- Tests simultaneous operation capability

**Usage:**
```bash
# Run all tests with mocked interfaces (no hardware required)
python test_shared_connection.py

# Run with verbose logging
python test_shared_connection.py --verbose

# Run only integration validation (no full test suite)
python test_shared_connection.py --integration-only
```

### 2. `validate_integration.py`
**Hardware-independent integration validation script** that can be run independently.

**Features:**
- Validates configuration loading and structure
- Tests component creation and instantiation
- Validates shared connection logic
- Tests message processing pipeline
- Validates error handling capabilities
- Tests Telegram integration setup

**Usage:**
```bash
# Run complete validation
python validate_integration.py

# Run with verbose logging
python validate_integration.py --verbose

# Only validate configuration
python validate_integration.py --config-only

# Only validate component creation
python validate_integration.py --components-only

# Output results in JSON format
python validate_integration.py --json
```

### 3. `test_config_integration.py`
**Focused test script** for configuration integration between bots.

**Features:**
- Tests that both bots share the same configuration object
- Validates Meshtastic configuration reading from main project
- Tests configuration change propagation
- Verifies shared interface configuration

**Usage:**
```bash
# Run configuration integration tests
python test_config_integration.py

# Run with verbose logging
python test_config_integration.py --verbose
```

## Running the Tests

### Prerequisites
- Python 3.7+
- Project dependencies installed (run `pip install -r requirements.txt`)
- Project configuration file (`config.ini`) present

### Quick Start
```bash
# 1. Run the integration validation (fastest, no hardware needed)
python validate_integration.py

# 2. Run configuration integration tests
python test_config_integration.py

# 3. Run full shared connection test suite
python test_shared_connection.py
```

### Test Results
All tests provide detailed output showing:
- ✅ Passed tests with timing information
- ❌ Failed tests with error messages
- 📊 Summary statistics
- 🔍 Detailed logging for debugging

## Test Coverage

### Shared Connection Tests (`test_shared_connection.py`)
1. **Shared Interface Instance** - Verifies both bots use the same Meshtastic interface
2. **Configuration Integration** - Tests config reading from main project
3. **No Duplicate Connections** - Ensures only one connection is created
4. **Message Routing** - Validates message flow between bots
5. **Configuration Changes Propagation** - Tests config changes affect both bots
6. **Connection Stability** - Tests error handling and recovery
7. **Simultaneous Operation** - Verifies both bots can operate without conflicts

### Integration Validation (`validate_integration.py`)
1. **Configuration Validation** - Tests config loading and structure
2. **Component Creation** - Validates all components can be instantiated
3. **Shared Connection Logic** - Tests shared connection implementation
4. **Message Processing** - Validates message processing pipeline
5. **Error Handling** - Tests error handling and recovery
6. **Telegram Integration** - Validates Telegram bot setup

### Configuration Integration (`test_config_integration.py`)
1. **Configuration Sharing** - Tests shared configuration object
2. **Meshtastic Config Reading** - Validates config reading from main project
3. **Configuration Change Propagation** - Tests config change propagation
4. **Shared Interface Configuration** - Verifies interface config sharing

## Hardware Requirements

### No Hardware Required
- `validate_integration.py` - Runs entirely with mocked interfaces
- `test_config_integration.py` - Tests configuration only
- `test_shared_connection.py --mock` - Uses mocked interfaces (default)

### Hardware Required
- `test_shared_connection.py` without `--mock` flag
- Requires actual Meshtastic device connected
- Tests real connection stability and message routing

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Make sure you're running from the project root directory
   cd /path/to/ff-bbs
   python validate_integration.py
   ```

2. **Configuration Errors**
   ```bash
   # Check that config.ini exists and has required sections
   ls -la config.ini
   # Validate configuration structure
   python validate_integration.py --config-only
   ```

3. **Permission Errors**
   ```bash
   # Ensure proper file permissions
   chmod +x test_shared_connection.py validate_integration.py
   ```

### Debug Mode
```bash
# Enable verbose logging for detailed output
python test_shared_connection.py --verbose
python validate_integration.py --verbose
python test_config_integration.py --verbose
```

## Integration with CI/CD

These tests can be integrated into your development workflow:

```bash
# Add to your CI/CD pipeline
# Run integration validation on every commit
python validate_integration.py --json > validation_results.json

# Run configuration tests on config changes
python test_config_integration.py

# Run full test suite before deployment
python test_shared_connection.py
```

## Expected Test Output

### Successful Run Example
```
$ python validate_integration.py
Starting Meshgram integration validation...
✅ Configuration Validation: Configuration validation successful (0.15s)
✅ Component Creation: All components created successfully (0.23s)
✅ Shared Connection Logic: Shared connection logic validated (0.12s)
✅ Message Processing: Message processing validated (0.08s)
✅ Error Handling: Error handling validated (0.18s)
✅ Telegram Integration: Telegram integration validated (0.05s)

======================================================================
INTEGRATION VALIDATION SUMMARY
======================================================================
Total duration: 0.81s
Steps validated: 6

✅ Configuration Validation     (0.15s)
✅ Component Creation           (0.23s)
✅ Shared Connection Logic      (0.12s)
✅ Message Processing           (0.08s)
✅ Error Handling               (0.18s)
✅ Telegram Integration         (0.05s)

Results: 6 passed, 0 failed
🎉 All validation steps completed successfully!
```

### Failed Test Example
```
$ python test_shared_connection.py
Starting comprehensive shared connection tests...
✗ Shared Interface Instance: Different interface instances: 140234567890 != 140234567891

======================================================================
TEST SUMMARY: 6/7 tests passed
======================================================================
PASS: Configuration Integration (0.12s)
FAIL: Shared Interface Instance (0.08s)
  └─ Different interface instances: 140234567890 != 140234567891
...
```

## Contributing

When adding new tests:
1. Follow the existing test structure and naming conventions
2. Include proper error handling and logging
3. Add tests for both mocked and real hardware scenarios
4. Update this README with new test descriptions
5. Ensure tests are hardware-independent where possible

## Support

For issues with the test suite:
1. Check the troubleshooting section above
2. Enable verbose logging for detailed output
3. Review the project configuration in `config.ini`
4. Ensure all dependencies are installed correctly