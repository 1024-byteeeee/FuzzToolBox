# Project workflow

After modifying project source code, tests, packaging, or UI assets:

1. Run the automated test suite.
2. Rebuild the macOS application with `sh scripts/build_macos.sh`.
3. Verify that `build/FuzzToolBox.app` launches successfully before completing the task.
