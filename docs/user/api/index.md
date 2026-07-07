# API Reference

This section documents the public API of Unladen Velocity for programmatic use.

## Modules

- [Model](model.md) - Core data structures (`Dataset`, `Revision`, `Environment`, `Benchmark`, `ResultSeries`, `ResultPoint`)
- [Config](config.md) - Configuration loading (`Settings`, `load_settings`)
- [Errors](errors.md) - Error handling (`UlvError`)
- [Testbeds](testbeds.md) - Testbed decomposition (`TestbedConfig`, `parse_testbeds`, `load_testbeds_file`)
- [Plugins](plugins.md) - Plugin system (`InputFormat`, `OutputGenerator`, `Registry`)

## Usage

The API is designed for advanced use cases such as:

- Building custom input formats or output generators
- Programmatically constructing datasets
- Integrating ulv into larger pipelines

For typical usage, the CLI is recommended. See the [CLI Reference](../cli-reference.md).
