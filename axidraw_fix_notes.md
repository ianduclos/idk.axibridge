# AxiDraw Connection Drop Fix Notes

## The Problem
The user was experiencing consistent USB connection drops with their AxiDraw plotter immediately after starting a plot. The terminal logs indicated that PyAxidraw (`plotink.ebb_serial`) was receiving an unexpected response (`!7 Err: Extra parmater`) when querying the firmware version (`V`), followed by receiving the firmware version string when it was actually expecting an `OK` response to a motor enable command (`EM,1,1`).

This offset cascading failure caused PyAxidraw's interactive `draw_path()` command to execute stepper motor (`SM`) commands continuously without waiting for the physical plotter to finish moving, overflowing the hardware buffer on the AxiDraw and causing it to fatally drop the connection.

## Root Cause
The root cause was traced to a subtle interaction between the `axibridge` backend wrapper and the `pyaxidraw` connection lifecycle:
1. `axibridge`'s `axidraw_native.py` tries to cache the firmware version upon connection: `self._firmware = getattr(ad.plot_status, "fw_version_string", "") or self._query_fw()`.
2. PyAxidraw's `serial_utils.py` actually stores the parsed version number in `plot_status.fw_version`, not `fw_version_string`.
3. Because the lookup always evaluated to `""`, `axibridge` fell back to `self._query_fw()`, which explicitly sends a `V\r` command to the EBB over USB immediately after the connection was initialized.
4. For reasons specific to macOS PySerial's `flushInput()` implementation and EBB's response handling, sending this trailing `V\r` command directly after the motor initialization phase was leaving the AxiDraw's response buffer misaligned by exactly one command (shifted by 1). 
5. When the user subsequently triggered a plot, the software sent an `EM,1,1` (Enable Motors) command, but read the leftover `EBBv...` string from the previous `V\r` query. Every subsequent `SM` command read the leftover `OK` from the command preceding it, flooding the board.

## The Fix
1. Updated `axibridge/backends/axidraw_native.py` to correctly query `getattr(ad.plot_status, "fw_version", "")`. This successfully intercepts the cached version and entirely prevents `axibridge` from sending the redundant `V\r` query.
2. Added an explicit read loop (`while port_obj.read(1024): pass`) directly after `ad.connect()` to purge any lingering bytes in the macOS PySerial receive buffer before `axibridge` hands the port off for plotting. This ensures clean synchronization.

Both fixes have been applied and saved directly to the user's `axibridge/backends/axidraw_native.py` file. The server will need to be restarted to load the new backend changes.
