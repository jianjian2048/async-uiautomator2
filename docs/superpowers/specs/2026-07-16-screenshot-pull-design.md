# Screenshot and pull design

## Scope

Add asynchronous screenshot and device-to-host file transfer support to the
public `AsyncDevice` API.  The new calls use the existing `AsyncAdbDevice`
abstraction, so callers remain independent from `adbutils`.

## Public API

```python
image = await device.screenshot()
await device.screenshot("artifacts/home.png")
size = await device.pull("/sdcard/report.txt", "artifacts/report.txt")
```

`AsyncDevice.screenshot(filename=None, format="pillow", display_id=None)`
matches the established `uiautomator2.Device.screenshot` call shape:

- Without `filename`, return a Pillow image for `format="pillow"`.
- With `filename`, save the image at that local path and return `None`.
- Pass `display_id` through for multi-display devices.

`AsyncDevice.pull(src, dst, exist_ok=False)` returns the integer byte count
reported by the ADB sync transfer.  `exist_ok` applies when pulling a remote
directory, matching `adbutils.sync.pull`.

## Architecture and error handling

Add corresponding methods to `AsyncAdbDevice` and implement them in
`ThreadedAdbDevice`.  The implementation calls `adbutils` through
`asyncio.to_thread`, consistent with existing `shell` and `push` methods and
therefore keeping blocking ADB and filesystem operations off the event loop.

The adapter delegates transfer and screenshot errors unchanged.  It does not
silently create directories, retry transfers, or translate third-party
exceptions; those policies are outside the existing backend contract.

## Testing

Use fake ADB backends to verify `AsyncDevice` forwards every argument and
returns the backend result.  Use fake synchronous `adbutils` devices to prove
the threaded backend invokes `sync.pull` and `screenshot` with the correct
arguments without requiring an attached Android device.

The README API examples will document both additions.
